from pathlib import Path
import sys
import types

import numpy as np
import soundfile as sf

from pptx_voice_video.config import load_config
from pptx_voice_video.tts import create_backend
from pptx_voice_video.tts.base import SynthesisOptions


class FakeVoxCPM:
    calls = []

    @classmethod
    def from_pretrained(cls, model_id, **kwargs):
        inst = cls()
        inst.model_id = model_id
        inst.kwargs = kwargs
        inst.tts_model = types.SimpleNamespace(sample_rate=48000)
        return inst

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return np.zeros(480, dtype=np.float32)


def test_voxcpm_config_loads_and_backend_factory_creates_backend(tmp_path: Path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
tts:
  engine: voxcpm
  voxcpm:
    model_id: openbmb/VoxCPM2
    cfg_value: 2.5
    inference_timesteps: 12
    voice_control: calm Korean lecturer voice
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(cfg_path)
    backend = create_backend(cfg.tts.engine, cfg.tts)

    assert backend.name == "voxcpm"
    assert cfg.tts.voxcpm.model_id == "openbmb/VoxCPM2"
    assert cfg.tts.active_engine_config().model_id == "openbmb/VoxCPM2"


def test_active_engine_config_honors_cli_engine_override():
    cfg = load_config(None)
    cfg.tts.engine = "voxcpm"

    assert cfg.tts.active_engine_config("voxcpm").model_id == "openbmb/VoxCPM2"


def test_voxcpm_backend_synthesizes_with_reference_audio_without_spoken_style_control(tmp_path: Path, monkeypatch):
    fake_module = types.SimpleNamespace(VoxCPM=FakeVoxCPM)
    monkeypatch.setitem(sys.modules, "voxcpm", fake_module)
    FakeVoxCPM.calls = []

    cfg = load_config(None)
    cfg.tts.engine = "voxcpm"
    cfg.tts.voxcpm.voice_control = "calm Korean psychiatry lecture voice"
    backend = create_backend("voxcpm", cfg.tts)
    ref = tmp_path / "voice.wav"
    sf.write(ref, np.zeros(160, dtype=np.float32), 16000)
    out = tmp_path / "out.wav"

    result = backend.synthesize(
        "스트레스 관련 장애를 설명합니다.",
        [ref],
        out,
        SynthesisOptions(language="ko", sample_rate=48000, generation={"cfg_value": 2.1}),
    )

    assert result == out
    assert out.exists()
    assert sf.info(out).samplerate == 48000
    assert FakeVoxCPM.calls[0]["reference_wav_path"] == str(ref)
    assert FakeVoxCPM.calls[0]["cfg_value"] == 2.1
    assert FakeVoxCPM.calls[0]["text"] == "스트레스 관련 장애를 설명합니다."


def test_voxcpm_backend_uses_prompt_text_for_ultimate_cloning(tmp_path: Path, monkeypatch):
    fake_module = types.SimpleNamespace(VoxCPM=FakeVoxCPM)
    monkeypatch.setitem(sys.modules, "voxcpm", fake_module)
    FakeVoxCPM.calls = []

    cfg = load_config(None)
    cfg.tts.engine = "voxcpm"
    cfg.tts.voxcpm.prompt_text = "이것은 참조 음성의 정확한 전사입니다."
    backend = create_backend("voxcpm", cfg.tts)
    ref = tmp_path / "voice.wav"
    sf.write(ref, np.zeros(160, dtype=np.float32), 16000)

    backend.synthesize(
        "새로운 발표자 노트입니다.",
        [ref],
        tmp_path / "out.wav",
        SynthesisOptions(language="ko", sample_rate=48000),
    )

    assert FakeVoxCPM.calls[0]["prompt_wav_path"] == str(ref)
    assert FakeVoxCPM.calls[0]["prompt_text"] == "이것은 참조 음성의 정확한 전사입니다."
    assert FakeVoxCPM.calls[0]["reference_wav_path"] == str(ref)
