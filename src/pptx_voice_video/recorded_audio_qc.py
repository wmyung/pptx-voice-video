from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from .models import SlideRecord
from .notes_qc import QCIssue, Severity
from .overrides import scan_slide_audio_directory
from .text_normalizer import normalize_text


@dataclass
class RecordedAudioQCConfig:
    min_similarity: float = 0.42
    min_keyword_recall: float = 0.35
    asr_model: str = "small"
    language: str = "ko"


@dataclass
class RecordedSlideQCResult:
    index: int
    audio_path: str = ""
    title: str = ""
    normalized_notes: str = ""
    transcript: str = ""
    similarity: float = 0.0
    keyword_recall: float = 0.0
    issues: list[QCIssue] = field(default_factory=list)

    @property
    def status(self) -> Literal["ok", "warning", "error"]:
        if any(i.severity == "error" for i in self.issues):
            return "error"
        if any(i.severity == "warning" for i in self.issues):
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status
        return data


@dataclass
class RecordedAudioQCReport:
    slides: list[RecordedSlideQCResult]

    @property
    def status(self) -> Literal["ok", "warning", "error"]:
        if any(s.status == "error" for s in self.slides):
            return "error"
        if any(s.status == "warning" for s in self.slides):
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        counts = {"ok": 0, "warning": 0, "error": 0}
        for slide in self.slides:
            counts[slide.status] += 1
        return {"status": self.status, "counts": counts, "slides": [s.to_dict() for s in self.slides]}

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _add(issues: list[QCIssue], code: str, severity: Severity, message: str, detail: str = "") -> None:
    issues.append(QCIssue(code=code, severity=severity, message=message, detail=detail))


def _clean_for_compare(text: str) -> str:
    text = normalize_text(text, language="ko", strip_stage_directions=True)
    text = text.lower()
    text = re.sub(r"[^0-9a-z가-힣\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _keywords(text: str) -> set[str]:
    words = set(re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}|\d+", text.lower()))
    stop = {"그리고", "그러나", "이것", "저것", "합니다", "있습니다", "대한", "위한", "통해", "먼저", "다음", "이번", "슬라이드"}
    return {w for w in words if w not in stop and len(w) >= 2}


def compare_transcript_to_notes(transcript: str, notes: str) -> tuple[float, float]:
    clean_t = _clean_for_compare(transcript)
    clean_n = _clean_for_compare(notes)
    similarity = SequenceMatcher(None, clean_t, clean_n).ratio() if clean_t and clean_n else 0.0
    note_kw = _keywords(clean_n)
    trans_kw = _keywords(clean_t)
    recall = len(note_kw & trans_kw) / len(note_kw) if note_kw else 1.0
    return round(similarity, 4), round(recall, 4)


def transcribe_audio(path: Path, *, model: str = "small", language: str = "ko") -> str:
    """Transcribe audio with local ASR if available.

    Preferred: faster-whisper Python package. Fallback: whisper CLI.
    Raises RuntimeError when no supported local ASR is installed.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore

        whisper = WhisperModel(model, device="cuda", compute_type="float16")
        segments, _info = whisper.transcribe(str(path), language=language, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()
    except ImportError:
        pass

    whisper_cli = shutil.which("whisper")
    if whisper_cli:
        with tempfile.TemporaryDirectory(prefix="recorded_asr_") as td:
            outdir = Path(td)
            cmd = [
                whisper_cli,
                str(path),
                "--model",
                model,
                "--language",
                language,
                "--output_format",
                "txt",
                "--output_dir",
                str(outdir),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            txts = list(outdir.glob("*.txt"))
            if txts:
                return txts[0].read_text(encoding="utf-8").strip()

    raise RuntimeError("local ASR is not available: install faster-whisper or openai-whisper CLI")


def run_recorded_audio_qc(
    slides: list[SlideRecord],
    recordings_dir: Path,
    *,
    config: RecordedAudioQCConfig | None = None,
    transcripts_by_index: dict[int, str] | None = None,
) -> RecordedAudioQCReport:
    config = config or RecordedAudioQCConfig()
    transcripts_by_index = transcripts_by_index or {}
    slide_by_index = {s.index: s for s in slides}
    audio_by_index = scan_slide_audio_directory(recordings_dir)
    results: list[RecordedSlideQCResult] = []

    for idx, audio in sorted(audio_by_index.items()):
        slide = slide_by_index.get(idx)
        result = RecordedSlideQCResult(index=idx, audio_path=str(audio), title=slide.title if slide else "")
        if slide is None:
            _add(result.issues, "slide_not_found", "error", "파일명에 해당하는 슬라이드가 PPTX에 없습니다.")
            results.append(result)
            continue
        result.normalized_notes = normalize_text(slide.raw_notes, language=config.language, strip_stage_directions=True)
        try:
            result.transcript = transcripts_by_index.get(idx) or transcribe_audio(audio, model=config.asr_model, language=config.language)
        except Exception as exc:
            _add(result.issues, "transcription_failed", "error", "녹음 파일을 로컬 ASR로 전사하지 못했습니다.", str(exc))
            results.append(result)
            continue
        result.similarity, result.keyword_recall = compare_transcript_to_notes(result.transcript, result.normalized_notes)
        if result.similarity < config.min_similarity and result.keyword_recall < config.min_keyword_recall:
            _add(
                result.issues,
                "content_mismatch",
                "error",
                "녹음 내용이 해당 슬라이드 발표자 노트와 충분히 일치하지 않습니다.",
                f"similarity={result.similarity}, keyword_recall={result.keyword_recall}",
            )
        elif result.keyword_recall < config.min_keyword_recall:
            _add(
                result.issues,
                "low_keyword_recall",
                "warning",
                "핵심 키워드 일치율이 낮습니다. 다른 슬라이드 녹음일 수 있습니다.",
                f"keyword_recall={result.keyword_recall}",
            )
        results.append(result)

    return RecordedAudioQCReport(results)
