from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

APP_ROOT = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(os.environ.get("WORMHOLE_WEB_DOWNLOAD_DIR", APP_ROOT / "downloads")).resolve()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_SECONDS = int(os.environ.get("WORMHOLE_WEB_TIMEOUT_SECONDS", "7200"))
TOKEN_TTL_SECONDS = int(os.environ.get("WORMHOLE_WEB_TOKEN_TTL_SECONDS", "86400"))

# By default, local-file sharing is intentionally limited to DOWNLOAD_DIR.
# To share generated videos directly, set for example:
# WORMHOLE_WEB_ALLOWED_ROOTS=/path/to/pptx-voice-video/local_outputs:/path/to/pptx-voice-video/tools/wormhole_web_recv/downloads
_ALLOWED_ROOTS_RAW = os.environ.get("WORMHOLE_WEB_ALLOWED_ROOTS", str(DOWNLOAD_DIR))
ALLOWED_ROOTS = tuple(Path(p).expanduser().resolve() for p in _ALLOWED_ROOTS_RAW.split(":") if p)

_CODE_RE = re.compile(r"^[0-9]+-[A-Za-z0-9_-]+-[A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)*$")
_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(name: str, default: str = "wormhole-download") -> str:
    """Return a conservative filename without path components."""
    base = Path(name or default).name.strip().replace("\x00", "")
    base = _SAFE_CHARS_RE.sub("_", base).strip(" .")
    if not base:
        base = default
    return base[:180]


def validate_wormhole_code(code: str) -> str:
    code = code.strip()
    if not _CODE_RE.fullmatch(code):
        raise ValueError("invalid magic-wormhole code format")
    return code


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_allowed_file(path_text: str, allowed_roots: tuple[Path, ...] = ALLOWED_ROOTS) -> Path:
    p = Path(path_text).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    if not any(is_under(p, root) for root in allowed_roots):
        roots = ", ".join(str(r) for r in allowed_roots)
        raise PermissionError(f"path is outside allowed roots: {roots}")
    return p


def make_token() -> str:
    return secrets.token_urlsafe(24)


JobStatus = Literal["queued", "running", "done", "failed", "expired"]


@dataclass
class Job:
    id: str
    code: str
    output_hint: str | None
    status: JobStatus = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    return_code: int | None = None
    log: list[str] = field(default_factory=list)
    file_path: Path | None = None
    token: str | None = None
    error: str | None = None


@dataclass
class TokenEntry:
    path: Path
    created_at: float = field(default_factory=time.time)


JOBS: dict[str, Job] = {}
TOKENS: dict[str, TokenEntry] = {}
LOCK = threading.Lock()

app = FastAPI(title="Wormhole Web Receiver", version="0.1.0")


class ReceiveRequest(BaseModel):
    code: str = Field(..., examples=["7-example-code"])
    output_filename: str | None = Field(default=None, description="Optional local saved filename")


class ShareLocalRequest(BaseModel):
    path: str


def prune_tokens() -> None:
    now = time.time()
    with LOCK:
        for token, entry in list(TOKENS.items()):
            if now - entry.created_at > TOKEN_TTL_SECONDS:
                TOKENS.pop(token, None)


def register_download(path: Path) -> str:
    token = make_token()
    with LOCK:
        TOKENS[token] = TokenEntry(path=path.resolve())
    return token


def newest_download_since(since: float) -> Path | None:
    candidates = [p for p in DOWNLOAD_DIR.iterdir() if p.is_file() and p.stat().st_mtime >= since - 1]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_receive(job_id: str) -> None:
    with LOCK:
        job = JOBS[job_id]
        job.status = "running"
        job.started_at = time.time()
        job.log.append(f"Starting wormhole receive for code {job.code}")

    wormhole = shutil.which("wormhole")
    if not wormhole:
        with LOCK:
            job.status = "failed"
            job.error = "wormhole command not found"
            job.finished_at = time.time()
        return

    started = time.time()
    if job.output_hint:
        output_target = DOWNLOAD_DIR / safe_filename(job.output_hint)
    else:
        output_target = DOWNLOAD_DIR

    cmd = [wormhole, "receive", job.code, "--accept-file", "--output-file", str(output_target), "--hide-progress"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        deadline = time.time() + MAX_SECONDS
        for line in proc.stdout:
            with LOCK:
                JOBS[job_id].log.append(line.rstrip()[:1000])
                JOBS[job_id].log = JOBS[job_id].log[-200:]
            if time.time() > deadline:
                proc.kill()
                raise TimeoutError(f"wormhole receive exceeded {MAX_SECONDS}s")
        rc = proc.wait(timeout=5)
        received_path = output_target if output_target.is_file() else newest_download_since(started)
        with LOCK:
            job = JOBS[job_id]
            job.return_code = rc
            job.finished_at = time.time()
            if rc == 0 and received_path and received_path.exists():
                job.file_path = received_path.resolve()
                job.token = register_download(received_path)
                job.status = "done"
                job.log.append(f"Received: {received_path}")
            elif rc == 0:
                job.status = "failed"
                job.error = "wormhole finished but no downloaded file was found"
            else:
                job.status = "failed"
                job.error = f"wormhole exited with code {rc}"
    except Exception as exc:  # subprocess failures should become visible in UI
        with LOCK:
            job = JOBS[job_id]
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = time.time()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML


@app.post("/api/receive")
def receive(req: ReceiveRequest) -> dict[str, str]:
    try:
        code = validate_wormhole_code(req.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = uuid.uuid4().hex
    job = Job(id=job_id, code=code, output_hint=req.output_filename)
    with LOCK:
        JOBS[job_id] = job
    thread = threading.Thread(target=run_receive, args=(job_id,), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    prune_tokens()
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="unknown job")
        return {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "return_code": job.return_code,
            "log": job.log[-100:],
            "error": job.error,
            "filename": job.file_path.name if job.file_path else None,
            "download_url": f"/download/{job.token}" if job.token else None,
        }


@app.post("/api/share-local")
def share_local(req: ShareLocalRequest) -> dict[str, str]:
    try:
        path = resolve_allowed_file(req.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    token = register_download(path)
    return {"download_url": f"/download/{token}", "filename": path.name}


@app.get("/download/{token}")
def download(token: str) -> FileResponse:
    prune_tokens()
    with LOCK:
        entry = TOKENS.get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="download token not found or expired")
    if not entry.path.exists() or not entry.path.is_file():
        raise HTTPException(status_code=404, detail="file no longer exists")
    return FileResponse(entry.path, filename=entry.path.name, media_type="application/octet-stream")


HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Wormhole Web Receiver</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; max-width: 780px; }
    input, button { font-size: 1rem; padding: .7rem; margin: .25rem 0; width: 100%; box-sizing: border-box; }
    button { cursor: pointer; font-weight: 700; }
    pre { background: #111; color: #eee; padding: 1rem; overflow-x: auto; border-radius: 8px; min-height: 8rem; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 1rem; margin: 1rem 0; }
    a.download { display: inline-block; background: #0a7cff; color: white; padding: .8rem 1rem; border-radius: 8px; text-decoration: none; font-weight: 700; }
  </style>
</head>
<body>
  <h1>Wormhole Web Receiver</h1>
  <p>아이폰 Safari에서 이 페이지를 열고 wormhole 코드를 입력하면, 서버가 대신 받고 브라우저 다운로드 링크를 만듭니다.</p>

  <div class="card">
    <h2>Wormhole 코드로 받기</h2>
    <input id="code" placeholder="예: 7-example-code" />
    <input id="filename" placeholder="저장 파일명 선택사항: lecture.mp4" />
    <button onclick="startReceive()">받기 시작</button>
  </div>

  <div class="card">
    <h2>서버에 이미 있는 파일 링크 만들기</h2>
    <input id="localPath" placeholder="서버 파일 경로" />
    <button onclick="shareLocal()">다운로드 링크 만들기</button>
  </div>

  <div id="result"></div>
  <pre id="log">대기 중...</pre>

<script>
let timer = null;
function log(msg) { document.getElementById('log').textContent = msg; }
async function startReceive() {
  const code = document.getElementById('code').value;
  const output_filename = document.getElementById('filename').value || null;
  const res = await fetch('/api/receive', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({code, output_filename})});
  const data = await res.json();
  if (!res.ok) { log(JSON.stringify(data, null, 2)); return; }
  poll(data.job_id);
}
async function poll(jobId) {
  if (timer) clearInterval(timer);
  timer = setInterval(async () => {
    const res = await fetch('/api/jobs/' + jobId);
    const data = await res.json();
    log('상태: ' + data.status + '\n' + (data.log || []).join('\n') + (data.error ? '\nERROR: ' + data.error : ''));
    if (data.download_url) {
      document.getElementById('result').innerHTML = `<p>완료: ${data.filename}</p><a class="download" href="${data.download_url}">아이폰으로 다운로드</a>`;
    }
    if (data.status === 'done' || data.status === 'failed') clearInterval(timer);
  }, 1000);
}
async function shareLocal() {
  const path = document.getElementById('localPath').value;
  const res = await fetch('/api/share-local', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({path})});
  const data = await res.json();
  if (!res.ok) { log(JSON.stringify(data, null, 2)); return; }
  document.getElementById('result').innerHTML = `<p>링크 생성: ${data.filename}</p><a class="download" href="${data.download_url}">아이폰으로 다운로드</a>`;
  log('다운로드 링크가 생성되었습니다.');
}
</script>
</body>
</html>
"""
