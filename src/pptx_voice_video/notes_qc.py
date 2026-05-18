from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from .models import SlideRecord
from .text_normalizer import chunk_text

Severity = Literal["info", "warning", "error"]


@dataclass
class QCConfig:
    max_raw_chars: int = 1200
    max_normalized_chars: int = 900
    max_chunk_chars: int = 90
    max_chunks: int = 12
    max_line_chars: int = 180
    max_symbol_ratio: float = 0.12
    max_digit_ratio: float = 0.18
    warn_empty_notes: bool = True
    estimated_chars_per_second: float = 6.2
    slide_padding_seconds: float = 0.35


@dataclass
class QCIssue:
    code: str
    severity: Severity
    message: str
    detail: str = ""


@dataclass
class SlideQCResult:
    index: int
    title: str = ""
    raw_chars: int = 0
    normalized_chars: int = 0
    line_count: int = 0
    chunk_count: int = 0
    max_chunk_chars: int = 0
    symbol_ratio: float = 0.0
    digit_ratio: float = 0.0
    estimated_speech_seconds: float = 0.0
    estimated_slide_seconds: float = 0.0
    issues: list[QCIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
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
class NotesQCReport:
    slides: list[SlideQCResult]

    @property
    def status(self) -> str:
        if any(s.status == "error" for s in self.slides):
            return "error"
        if any(s.status == "warning" for s in self.slides):
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        counts = {"ok": 0, "warning": 0, "error": 0}
        for slide in self.slides:
            counts[slide.status] += 1
        estimated_total_seconds = round(sum(s.estimated_slide_seconds for s in self.slides), 2)
        return {
            "status": self.status,
            "counts": counts,
            "estimated_total_seconds": estimated_total_seconds,
            "estimated_total_minutes": round(estimated_total_seconds / 60.0, 2),
            "slides": [s.to_dict() for s in self.slides],
        }

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


_SYMBOL_RE = re.compile(r"[※●■◆◇▶▷→←↑↓⇢⇒✓✔✗✘★☆]{1}|[=+*/\\|<>_~^]{2,}")
_BRACKET_RE = re.compile(r"\[[^\]]+\]|\([^)]{8,}\)")
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_FILE_EXT_RE = re.compile(r"\.(pptx|pdf|docx|xlsx|png|jpg|mp4|wav|m4a)\b", re.IGNORECASE)


def _ratio(count: int, total: int) -> float:
    return 0.0 if total <= 0 else round(count / total, 4)


def _add(issues: list[QCIssue], code: str, severity: Severity, message: str, detail: str = "") -> None:
    issues.append(QCIssue(code=code, severity=severity, message=message, detail=detail))


def analyze_slide_notes(slide: SlideRecord, normalized_text: str, qc: QCConfig) -> SlideQCResult:
    raw = slide.raw_notes or ""
    normalized = normalized_text or ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    chunks = chunk_text(normalized, qc.max_chunk_chars)
    symbol_count = len(_SYMBOL_RE.findall(raw))
    digit_count = sum(1 for ch in raw if ch.isdigit())

    result = SlideQCResult(
        index=slide.index,
        title=slide.title,
        raw_chars=len(raw),
        normalized_chars=len(normalized),
        line_count=len(lines),
        chunk_count=len(chunks),
        max_chunk_chars=max((len(c) for c in chunks), default=0),
        symbol_ratio=_ratio(symbol_count, max(len(raw), 1)),
        digit_ratio=_ratio(digit_count, max(len(raw), 1)),
        estimated_speech_seconds=round(len(normalized) / max(qc.estimated_chars_per_second, 0.1), 2) if normalized else 0.0,
        estimated_slide_seconds=round((len(normalized) / max(qc.estimated_chars_per_second, 0.1)) + qc.slide_padding_seconds, 2) if normalized else qc.slide_padding_seconds,
    )
    issues = result.issues

    if not normalized.strip():
        severity: Severity = "warning" if qc.warn_empty_notes else "info"
        _add(issues, "empty_notes", severity, "발표자 노트가 비어 있습니다.")
    if len(raw) > qc.max_raw_chars:
        _add(issues, "raw_too_long", "warning", "원본 노트가 깁니다.", f"{len(raw)} > {qc.max_raw_chars}")
    if len(normalized) > qc.max_normalized_chars:
        _add(issues, "normalized_too_long", "warning", "정규화 후 TTS 입력이 깁니다.", f"{len(normalized)} > {qc.max_normalized_chars}")
    if len(chunks) > qc.max_chunks:
        _add(issues, "too_many_chunks", "warning", "TTS chunk 수가 많아 합성 실패 가능성이 있습니다.", f"{len(chunks)} > {qc.max_chunks}")
    long_lines = [(i + 1, len(line)) for i, line in enumerate(lines) if len(line) > qc.max_line_chars]
    if long_lines:
        _add(issues, "long_lines", "warning", "너무 긴 줄이 있습니다. 문장 단위로 나누는 편이 안전합니다.", str(long_lines[:5]))
    if result.symbol_ratio > qc.max_symbol_ratio:
        _add(issues, "symbol_heavy", "warning", "기호가 많아 TTS 발음이 불안정할 수 있습니다.", f"ratio={result.symbol_ratio}")
    if result.digit_ratio > qc.max_digit_ratio:
        _add(issues, "digit_heavy", "warning", "숫자가 많아 읽기 품질이 떨어질 수 있습니다.", f"ratio={result.digit_ratio}")
    if _URL_RE.search(raw):
        _add(issues, "url_present", "warning", "URL은 TTS가 그대로 읽기 어렵습니다. 설명 문장으로 바꾸는 것이 좋습니다.")
    if _FILE_EXT_RE.search(raw):
        _add(issues, "filename_or_extension", "info", "파일명/확장자처럼 보이는 텍스트가 있습니다.")
    bracketed = _BRACKET_RE.findall(raw)
    if bracketed:
        _add(issues, "stage_directions", "info", "괄호 안 지시문이 있습니다. 설정에 따라 TTS 전 제거됩니다.", str(bracketed[:3]))
    if re.search(r"[A-Za-z]{2,}.*[가-힣]|[가-힣].*[A-Za-z]{2,}", normalized):
        _add(issues, "mixed_language", "info", "한국어/영어 혼합 문장입니다. 고유명사는 발음 사전에 넣으면 안정적입니다.")
    if re.search(r"(.)\1{5,}", raw):
        _add(issues, "repeated_chars", "warning", "반복 문자가 많습니다. TTS가 늘어질 수 있습니다.")

    return result


def run_notes_qc(slides: list[SlideRecord], normalized_by_index: dict[int, str], qc: QCConfig | None = None) -> NotesQCReport:
    qc = qc or QCConfig()
    return NotesQCReport([
        analyze_slide_notes(slide, normalized_by_index.get(slide.index, slide.normalized_notes), qc)
        for slide in slides
    ])
