from __future__ import annotations
from pathlib import Path
from typing import Protocol
class SlideRenderer(Protocol):
    name: str
    def render(self, pptx: Path, output_dir: Path) -> list[Path]: ...
    def health_check(self) -> dict: ...
