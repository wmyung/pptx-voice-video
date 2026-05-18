from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Literal

SlideStatus = Literal["pending", "notes_extracted", "rendered", "synthesized", "composed", "skipped", "failed"]

@dataclass
class SlideRecord:
    index: int
    title: str = ""
    raw_notes: str = ""
    normalized_notes: str = ""
    image_path: str = ""
    audio_path: str = ""
    subtitle_segments: list[dict[str, Any]] | None = None
    duration: float = 0.0
    engine_name: str = ""
    status: SlideStatus = "pending"
    error: str = ""
    pointer_plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["subtitle_segments"] = self.subtitle_segments or []
        return d

@dataclass
class PipelineInputs:
    pptx: Path
    voices: list[Path]
    output_dir: Path
    background_music: Path | None = None
    config_path: Path | None = None
    engine: str | None = None
    language: str | None = None
    subtitles: bool | None = None
    transitions: bool | None = None
    pointer: bool | None = None
    slide_audio_overrides: dict[int, Path] | None = None
    slide_visual_source: Path | None = None
    start_slide: int | None = None
    end_slide: int | None = None
