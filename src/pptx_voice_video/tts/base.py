from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

@dataclass
class SynthesisOptions:
    language: str = "ko"
    sample_rate: int = 24000
    generation: dict[str, Any] = field(default_factory=dict)

class TTSBackend(Protocol):
    name: str
    def clone_or_prepare_voice(self, reference_audio: list[Path], cache_dir: Path) -> Any: ...
    def synthesize(self, text: str, reference_audio: list[Path], output_path: Path, options: SynthesisOptions) -> Path: ...
    def supports_streaming(self) -> bool: ...
    def supports_voice_cloning(self) -> bool: ...
    def health_check(self) -> dict[str, Any]: ...
