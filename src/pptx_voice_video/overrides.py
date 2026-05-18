from __future__ import annotations

import re
from pathlib import Path

import yaml

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".wma"}


def _slide_index_from_stem(stem: str) -> int | None:
    """Return slide index from simple numeric filenames like 24.m4a or slide_024.wav."""
    text = stem.strip()
    if text.isdigit():
        return int(text)
    m = re.fullmatch(r"(?:slide|슬라이드|s)[-_ ]?0*(\d+)", text, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def scan_slide_audio_directory(path: str | Path) -> dict[int, Path]:
    """Scan a directory for audio files whose basename identifies the slide number."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    result: dict[int, Path] = {}
    for file in sorted(root.iterdir()):
        if not file.is_file() or file.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        idx = _slide_index_from_stem(file.stem)
        if idx is None:
            continue
        if idx in result:
            raise ValueError(f"duplicate audio override for slide {idx}: {result[idx]} and {file}")
        result[idx] = file.resolve()
    return result


def load_slide_audio_overrides(path: str | Path | None) -> dict[int, Path]:
    """Load slide audio overrides from a YAML/JSON mapping or a numbered-audio directory."""
    if not path:
        return {}
    p = Path(path).expanduser()
    if p.is_dir():
        return scan_slide_audio_directory(p)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if "slides" in data and isinstance(data["slides"], dict):
        data = data["slides"]
    result: dict[int, Path] = {}
    for key, value in data.items():
        idx = int(key)
        audio = Path(str(value)).expanduser()
        if not audio.is_absolute():
            audio = (p.parent / audio).resolve()
        result[idx] = audio
    return result
