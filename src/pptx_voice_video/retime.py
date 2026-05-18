from __future__ import annotations

import concurrent.futures as cf
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

STRONG_NEXT = (
    "however", "therefore", "so", "next", "first", "second", "third", "finally",
    "but", "in contrast", "for example", "in summary", "in conclusion",
    "하지만", "그래서", "따라서", "반면", "반면에", "이제", "다음", "먼저", "두 번째", "세 번째",
    "네 번째", "다섯 번째", "마지막", "결국", "즉", "예를 들어", "이번", "오늘", "여기서",
)
WEAK_COMMA_AFTER = (
    "first", "second", "third", "finally", "for example", "therefore", "however",
    "먼저", "두 번째로", "세 번째로", "네 번째로", "다섯 번째로", "마지막으로", "즉", "예를 들어", "반면에", "따라서",
)
LISTY_PREV = (
    "gene", "genes", "diagnosis", "treatment", "population", "조현병", "우울증", "양극성장애", "자폐", "유전자", "기능", "진단", "치료", "인구집단",
)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    return float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        ).strip()
    )


def semantic_pause_events(text: str) -> list[dict[str, Any]]:
    """Choose natural pause candidates from text meaning, not raw whitespace.

    This intentionally ignores spaces and line breaks. Sentence endings and discourse
    transitions get higher weights; ordinary list commas get little or no pause.
    """
    events: list[dict[str, Any]] = []
    chars = [ch for ch in text if not ch.isspace()]
    total = max(len(chars), 1)
    nonspace = 0
    lowered = text.lower()
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        nonspace += 1
        if ch not in ".!?。！？,，;；:：":
            continue
        ratio = nonspace / total
        if not (0.025 < ratio < 0.985):
            continue
        prev = text[max(0, i - 40):i].strip()
        nxt = text[i + 1:i + 70].strip()
        prev_l = lowered[max(0, i - 40):i].strip()
        nxt_l = lowered[i + 1:i + 70].strip()
        weight = 0.0
        reason = ""
        if ch in ".!?。！？":
            weight = 1.15
            reason = "sentence_end"
            if any(nxt_l.startswith(s.lower()) for s in STRONG_NEXT):
                weight = 1.75
                reason = "sentence_end_discourse_shift"
            if ch in "!?！？":
                weight = max(weight, 1.55)
                reason = "question_emphasis"
            if len(prev) < 12 and not any(nxt_l.startswith(s.lower()) for s in STRONG_NEXT):
                weight *= 0.65
                reason += "_short"
        elif ch in ";；:：":
            weight = 0.9
            reason = "colon_semicolon"
        elif ch in ",，":
            if any(prev_l.endswith(s.lower()) or s.lower() in prev_l[-18:] for s in WEAK_COMMA_AFTER):
                weight = 0.75
                reason = "signpost_comma"
            elif any(w in prev_l[-18:] for w in ("however", "therefore", "but", "하지만", "그래서", "따라서", "반면")):
                weight = 0.8
                reason = "contrast_causal_comma"
            elif len(prev) >= 18 and len(nxt) >= 18 and not any(w.lower() in prev_l[-18:] for w in LISTY_PREV):
                weight = 0.35
                reason = "long_clause_comma"
        if weight > 0:
            events.append({"ratio": ratio, "punct": ch, "weight": weight, "reason": reason, "prev": prev[-30:], "next": nxt[:30]})
    return events


def _silence_centers(data: np.ndarray, sr: int, *, frame_sec: float, threshold_db: float) -> list[int]:
    if data.ndim > 1:
        data = data.mean(axis=1)
    n = max(1, int(frame_sec * sr))
    dbs = []
    for i in range(0, len(data), n):
        chunk = data[i:i + n]
        rms = float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0
        dbs.append(20 * math.log10(max(rms, 1e-8)))
    silent = np.asarray(dbs) < threshold_db
    centers: list[int] = []
    i = 0
    min_frames = max(1, math.ceil(0.10 / frame_sec))
    edge = int(0.20 * sr)
    while i < len(silent):
        if not silent[i]:
            i += 1
            continue
        j = i
        while j < len(silent) and silent[j]:
            j += 1
        if j - i >= min_frames:
            c = int(((i + j) / 2) * n)
            if edge < c < len(data) - edge:
                centers.append(c)
        i = j
    return centers


def _choose_insertions(data: np.ndarray, sr: int, events: list[dict[str, Any]], scale: float, *, search_sec: float, frame_sec: float, threshold_db: float) -> list[tuple[int, float, str]]:
    centers = _silence_centers(data, sr, frame_sec=frame_sec, threshold_db=threshold_db)
    used: set[int] = set()
    insertions: list[tuple[int, float, str]] = []
    search = int(search_sec * sr)
    last_sample = -10**9
    for ev in events:
        target = int(ev["ratio"] * len(data))
        candidates = [(abs(c - target), idx, c) for idx, c in enumerate(centers) if idx not in used and abs(c - target) <= search]
        if candidates:
            _, idx, sample = min(candidates)
            used.add(idx)
            factor = 1.0
        else:
            sample = target
            factor = 0.45
        if sample - last_sample < int(1.2 * sr):
            factor *= 0.45
        pause = float(ev["weight"]) * scale * factor
        if pause >= 0.18:
            insertions.append((sample, pause, str(ev["reason"])))
            last_sample = sample
    insertions.sort(key=lambda x: x[0])
    return insertions


def _atempo_audio(src: Path, dst: Path, tempo: float, sr: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 1000:
        return
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-filter:a", f"atempo={tempo}", "-ac", "1", "-ar", str(sr), str(dst)])


def _extend_audio(data: np.ndarray, sr: int, insertions: list[tuple[int, float, str]], slide_end_pause: float) -> np.ndarray:
    if data.ndim > 1:
        data = data.mean(axis=1)
    parts: list[np.ndarray] = []
    pos = 0
    for sample, pause, _reason in insertions:
        sample = max(pos, min(int(sample), len(data)))
        parts.append(data[pos:sample])
        parts.append(np.zeros(int(round(pause * sr)), dtype=np.float32))
        pos = sample
    parts.append(data[pos:])
    if slide_end_pause > 0:
        parts.append(np.zeros(int(round(slide_end_pause * sr)), dtype=np.float32))
    return np.concatenate(parts).astype(np.float32)


def _render_segment(slide: dict[str, Any], root: Path, audio: Path, seg: Path, width: int, height: int) -> None:
    seg.parent.mkdir(parents=True, exist_ok=True)
    dur = ffprobe_duration(audio)
    image_path = Path(str(slide["image_path"]))
    if not image_path.is_absolute():
        image_path = root / image_path
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-t", f"{dur:.3f}",
        "-i", str(image_path), "-i", str(audio), "-vf", f"scale={width}:{height},setsar=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(seg),
    ])


def retime_manifest(
    manifest_path: Path,
    output_dir: Path,
    *,
    target_seconds: float,
    tempo: float = 0.85,
    slide_end_pause: float = 3.0,
    sample_rate: int = 48000,
    width: int = 1920,
    height: int = 1080,
    frame_sec: float = 0.02,
    threshold_db: float = -38.0,
    search_sec: float = 1.6,
    max_workers: int = 4,
) -> dict[str, Any]:
    root = Path.cwd().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    slides = manifest.get("slides", manifest if isinstance(manifest, list) else [])
    slowed = output_dir / "audio_tempo"
    processed = output_dir / "audio_semantic_pauses"
    segdir = output_dir / "segments"

    rows = []
    audio_sum = 0.0
    total_weight = 0.0
    total_events = 0
    for slide in slides:
        audio_path = Path(str(slide["audio_path"]))
        if not audio_path.is_absolute():
            audio_path = root / audio_path
        slowed_audio = slowed / f"slide_{int(slide['index']):03d}_tempo.wav"
        _atempo_audio(audio_path, slowed_audio, tempo, sample_rate)
        data, sr = sf.read(slowed_audio, dtype="float32")
        events = semantic_pause_events(slide.get("normalized_notes") or slide.get("raw_notes") or "")
        audio_sum += len(data) / sr
        total_weight += sum(float(e["weight"]) for e in events)
        total_events += len(events)
        rows.append((slide, data, sr, events))

    remaining = target_seconds - audio_sum - slide_end_pause * len(rows)
    scale = max(0.0, remaining / total_weight) if total_weight else 0.0

    jobs = []
    per_slide = []
    for slide, data, sr, events in rows:
        insertions = _choose_insertions(data, sr, events, scale, search_sec=search_sec, frame_sec=frame_sec, threshold_db=threshold_db)
        arr = _extend_audio(data, sr, insertions, slide_end_pause)
        out_audio = processed / f"slide_{int(slide['index']):03d}.wav"
        out_audio.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out_audio, arr, sr, subtype="PCM_16")
        seg = segdir / f"seg_{int(slide['index']):03d}.mp4"
        jobs.append((slide, out_audio, seg))
        per_slide.append({
            "slide": int(slide["index"]),
            "semantic_events": len(events),
            "inserted_pauses": len(insertions),
            "duration": len(arr) / sr,
            "pause_reasons": [x[2] for x in insertions[:20]],
        })

    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_render_segment, slide, root, audio, seg, width, height) for slide, audio, seg in jobs]
        for fut in cf.as_completed(futures):
            fut.result()

    listfile = output_dir / "concat.txt"
    listfile.write_text("".join(f"file '{seg.resolve()}'\n" for _slide, _audio, seg in jobs), encoding="utf-8")
    final = output_dir / "final_retimed.mp4"
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", "-movflags", "+faststart", str(final)])
    actual = ffprobe_duration(final)
    report = {
        "final": str(final),
        "actual_duration": actual,
        "target_seconds": target_seconds,
        "tempo": tempo,
        "slide_end_pause": slide_end_pause,
        "semantic_events": total_events,
        "semantic_weight": total_weight,
        "pause_scale": scale,
        "per_slide": per_slide,
    }
    (output_dir / "retime_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
