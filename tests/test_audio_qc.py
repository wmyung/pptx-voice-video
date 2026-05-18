from pathlib import Path

import numpy as np
import soundfile as sf

from pptx_voice_video.audio_qc import AudioQCConfig, analyze_audio, run_audio_qc
from pptx_voice_video.models import SlideRecord


def test_audio_qc_flags_too_long_audio(tmp_path: Path):
    path = tmp_path / "long.wav"
    sr = 24000
    sf.write(path, np.zeros(sr * 2, dtype=np.float32), sr)

    result = analyze_audio(path, index=1, expected_seconds=0.5, cfg=AudioQCConfig(max_duration_seconds=1.0, max_expected_duration_ratio=2.0))

    assert result.status == "error"
    codes = {issue.code for issue in result.issues}
    assert "too_long" in codes
    assert "longer_than_expected" in codes


def test_audio_qc_ok_short_tone(tmp_path: Path):
    path = tmp_path / "tone.wav"
    sr = 24000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    audio = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, audio, sr)

    result = analyze_audio(path, index=1, expected_seconds=1.0, cfg=AudioQCConfig(max_duration_seconds=10.0))

    assert result.status == "ok"
    assert result.duration_seconds > 0.9


def test_run_audio_qc_uses_slide_audio_paths(tmp_path: Path):
    path = tmp_path / "tone.wav"
    sr = 24000
    sf.write(path, np.ones(sr, dtype=np.float32) * 0.05, sr)
    slide = SlideRecord(index=3, audio_path=str(path), normalized_notes="테스트 문장")

    report = run_audio_qc([slide], {3: 1.0}, AudioQCConfig(max_duration_seconds=10.0))

    assert len(report.slides) == 1
    assert report.to_dict()["actual_total_seconds"] > 0
