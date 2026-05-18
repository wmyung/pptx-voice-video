from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def cache_key(*, engine: str, text: str, voice_paths: list[Path], options: dict[str, Any]) -> str:
    h=hashlib.sha256()
    h.update(engine.encode()); h.update(text.encode())
    for p in voice_paths:
        h.update(str(p.resolve()).encode())
        if p.exists(): h.update(sha256_file(p).encode())
    h.update(json.dumps(options, sort_keys=True, default=str).encode())
    return h.hexdigest()[:32]

class FileCache:
    def __init__(self, root: Path, enabled: bool=True):
        self.root=root; self.enabled=enabled; self.root.mkdir(parents=True, exist_ok=True)
    def audio_path(self, key: str) -> Path: return self.root / f"{key}.wav"
    def hit(self, key: str) -> Path | None:
        p=self.audio_path(key)
        return p if self.enabled and p.exists() and p.stat().st_size>0 else None
