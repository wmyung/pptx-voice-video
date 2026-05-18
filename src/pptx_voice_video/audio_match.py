from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from .models import SlideRecord
from .overrides import AUDIO_EXTENSIONS, _slide_index_from_stem
from .recorded_audio_qc import compare_transcript_to_notes, transcribe_audio
from .text_normalizer import normalize_text

MatchStatus = Literal["accepted", "rejected", "needs_review"]
MatchSource = Literal["filename", "semantic"]


@dataclass
class AudioMatchConfig:
    min_similarity: float = 0.42
    min_keyword_recall: float = 0.35
    min_margin: float = 0.08
    asr_model: str = "small"
    language: str = "ko"


@dataclass
class AudioSlideCandidate:
    slide_index: int
    similarity: float
    keyword_recall: float
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AudioMatchResult:
    audio_path: str
    transcript: str = ""
    slide_index: int | None = None
    source: MatchSource = "semantic"
    status: MatchStatus = "rejected"
    reason: str = ""
    similarity: float = 0.0
    keyword_recall: float = 0.0
    score: float = 0.0
    second_best_score: float = 0.0
    candidates: list[AudioSlideCandidate] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["candidates"] = [c.to_dict() for c in self.candidates]
        return data


@dataclass
class AudioMatchReport:
    matches: list[AudioMatchResult]
    overrides: dict[int, Path]
    unmatched_slides: list[int]
    unmatched_audio: list[str]

    def to_dict(self) -> dict:
        return {
            "matches": [m.to_dict() for m in self.matches],
            "overrides": {str(k): str(v) for k, v in sorted(self.overrides.items())},
            "unmatched_slides": self.unmatched_slides,
            "unmatched_audio": self.unmatched_audio,
        }

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_overrides_yaml(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"slides": {int(k): str(v) for k, v in sorted(self.overrides.items())}}
        path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=True), encoding="utf-8")
        return path


def _audio_files(recordings_dir: Path) -> list[Path]:
    root = recordings_dir.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    return sorted(
        f.resolve()
        for f in root.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )


def _score(similarity: float, keyword_recall: float) -> float:
    return round((similarity + keyword_recall) / 2, 4)


def _confident(candidate: AudioSlideCandidate, config: AudioMatchConfig) -> bool:
    # Match existing recorded-audio QC semantics: only reject when both text-level
    # similarity and keyword recall are below thresholds.
    return not (
        candidate.similarity < config.min_similarity
        and candidate.keyword_recall < config.min_keyword_recall
    )


def _candidate_for(transcript: str, slide: SlideRecord, config: AudioMatchConfig) -> AudioSlideCandidate:
    notes = normalize_text(slide.raw_notes, language=config.language, strip_stage_directions=True)
    similarity, keyword_recall = compare_transcript_to_notes(transcript, notes)
    return AudioSlideCandidate(
        slide_index=slide.index,
        similarity=similarity,
        keyword_recall=keyword_recall,
        score=_score(similarity, keyword_recall),
    )


def _transcript_for(
    audio: Path,
    *,
    config: AudioMatchConfig,
    transcripts_by_path: dict[Path, str] | None,
) -> str:
    transcripts_by_path = transcripts_by_path or {}
    resolved = audio.resolve()
    if resolved in transcripts_by_path:
        return transcripts_by_path[resolved]
    if audio in transcripts_by_path:
        return transcripts_by_path[audio]
    return transcribe_audio(resolved, model=config.asr_model, language=config.language)


def match_recordings_to_slides(
    slides: list[SlideRecord],
    recordings_dir: Path,
    *,
    config: AudioMatchConfig | None = None,
    transcripts_by_path: dict[Path, str] | None = None,
) -> AudioMatchReport:
    """Match recorded narration files to slides by filename first, then semantics.

    Numbered files (for example ``01.mp3`` or ``slide_024.wav``) are only eligible
    for their declared slide. If ASR/text comparison confidence is too low, the
    file is rejected so that the pipeline can synthesize that slide instead.
    Unnumbered files are assigned to the best unmatched slide when the best score
    is confident and separated from the second-best score by ``min_margin``.
    """
    config = config or AudioMatchConfig()
    slide_by_index = {s.index: s for s in slides}
    normalized_slides = sorted(slides, key=lambda s: s.index)
    overrides: dict[int, Path] = {}
    results: list[AudioMatchResult] = []
    unnumbered: list[tuple[Path, str, list[AudioSlideCandidate]]] = []

    for audio in _audio_files(recordings_dir):
        transcript = _transcript_for(audio, config=config, transcripts_by_path=transcripts_by_path)
        declared_index = _slide_index_from_stem(audio.stem)
        if declared_index is not None:
            result = AudioMatchResult(
                audio_path=str(audio),
                transcript=transcript,
                slide_index=declared_index,
                source="filename",
            )
            slide = slide_by_index.get(declared_index)
            if slide is None:
                result.status = "rejected"
                result.reason = "declared_slide_not_found"
                results.append(result)
                continue
            candidate = _candidate_for(transcript, slide, config)
            result.similarity = candidate.similarity
            result.keyword_recall = candidate.keyword_recall
            result.score = candidate.score
            result.candidates = [candidate]
            if _confident(candidate, config):
                result.status = "accepted"
                result.reason = "filename_match_confident"
                overrides[declared_index] = audio
            else:
                result.status = "rejected"
                result.reason = "low_confidence_for_numbered_slide"
            results.append(result)
            continue

        candidates = [_candidate_for(transcript, slide, config) for slide in normalized_slides]
        candidates.sort(key=lambda c: c.score, reverse=True)
        unnumbered.append((audio, transcript, candidates))

    accepted_slides = set(overrides)
    semantic_attempts: list[AudioMatchResult] = []
    for audio, transcript, candidates in unnumbered:
        available = [c for c in candidates if c.slide_index not in accepted_slides]
        best = available[0] if available else None
        second = available[1] if len(available) > 1 else None
        result = AudioMatchResult(
            audio_path=str(audio),
            transcript=transcript,
            slide_index=best.slide_index if best else None,
            source="semantic",
            candidates=candidates[:5],
        )
        if best is None:
            result.status = "rejected"
            result.reason = "no_unmatched_slide_available"
        else:
            result.similarity = best.similarity
            result.keyword_recall = best.keyword_recall
            result.score = best.score
            result.second_best_score = second.score if second else 0.0
            if not _confident(best, config):
                result.status = "rejected"
                result.reason = "low_confidence"
            elif second and best.score - second.score < config.min_margin:
                result.status = "needs_review"
                result.reason = "second_best_too_close"
            else:
                result.status = "accepted"
                result.reason = "semantic_match_confident"
                overrides[best.slide_index] = audio
                accepted_slides.add(best.slide_index)
        semantic_attempts.append(result)

    results.extend(semantic_attempts)
    unmatched_slides = [s.index for s in normalized_slides if s.index not in overrides]
    unmatched_audio = [m.audio_path for m in results if m.status != "accepted"]
    return AudioMatchReport(
        matches=results,
        overrides=overrides,
        unmatched_slides=unmatched_slides,
        unmatched_audio=unmatched_audio,
    )
