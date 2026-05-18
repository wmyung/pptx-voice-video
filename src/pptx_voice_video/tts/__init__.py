from .base import TTSBackend, SynthesisOptions
from .voxcpm import VoxCPMBackend

def create_backend(name: str, config):
    name = name.lower()
    if name in {"voxcpm", "voxcpm2", "vox-cpm"}:
        return VoxCPMBackend(config.voxcpm)
    raise ValueError(f"Unsupported TTS engine: {name}. This public build includes VoxCPM2 only.")
