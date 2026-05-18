from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, Field

class VoxCPMConfig(BaseModel):
    model_id: str = "openbmb/VoxCPM2"
    model_path: str | None = None
    sample_rate: int = 48000
    max_chunk_chars: int = 260
    load_denoiser: bool = False
    cfg_value: float = 2.0
    inference_timesteps: int = 10
    # Optional natural-language style control. Keep null when the reference audio already carries the target speaking style.
    voice_control: str | None = None
    # Optional transcript of the reference audio for stronger cloning and cadence matching.
    prompt_text: str | None = None
    generation: dict[str, Any] = Field(default_factory=dict)

class TTSConfig(BaseModel):
    engine: str = "voxcpm"
    voxcpm: VoxCPMConfig = Field(default_factory=VoxCPMConfig)

    def active_engine_config(self, engine: str | None = None):
        name = (engine or self.engine).lower()
        if name in {"voxcpm", "voxcpm2", "vox-cpm"}:
            return self.voxcpm
        raise ValueError(f"Unsupported TTS engine: {engine or self.engine}")

class RenderConfig(BaseModel):
    backend: str = "libreoffice"
    width: int = 1920
    height: int = 1080

class VideoConfig(BaseModel):
    fps: int = 30
    width: int = 1920
    height: int = 1080
    preserve_slide_aspect_ratio: bool = True
    slide_padding_seconds: float = 0.35
    fade_seconds: float = 0.25
    subtitles: bool = False
    background_music_volume: float = 0.12

class PointerConfig(BaseModel):
    enabled: bool = False
    mode: str = "auto"
    move_seconds: float = 0.8

class TextConfig(BaseModel):
    language: str = "ko"
    strip_stage_directions: bool = True
    pronunciation: dict[str, str] = Field(default_factory=dict)

class NotesQCConfig(BaseModel):
    enabled: bool = True
    fail_on_error: bool = False
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

class AudioQCConfig(BaseModel):
    enabled: bool = True
    fail_on_error: bool = False
    min_duration_seconds: float = 1.0
    max_duration_seconds: float = 180.0
    max_expected_duration_ratio: float = 2.3
    min_expected_duration_ratio: float = 0.25
    min_rms_db: float = -45.0
    max_peak_db: float = -0.1
    max_clipping_ratio: float = 0.003
    max_silence_ratio: float = 0.55

class CacheConfig(BaseModel):
    enabled: bool = True

class AppConfig(BaseModel):
    tts: TTSConfig = Field(default_factory=TTSConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    pointer: PointerConfig = Field(default_factory=PointerConfig)
    text: TextConfig = Field(default_factory=TextConfig)
    notes_qc: NotesQCConfig = Field(default_factory=NotesQCConfig)
    audio_qc: AudioQCConfig = Field(default_factory=AudioQCConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)

def load_config(path: str | Path | None = None) -> AppConfig:
    if path is None:
        return AppConfig()
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)
