from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from .audio_utils import audio_duration
from .models import SlideRecord
from .notes_qc import QCIssue, Severity


@dataclass
class AudioQCConfig:
    min_duration_seconds: float = 1.0
    max_duration_seconds: float = 180.0
    max_expected_duration_ratio: float = 2.3
    min_expected_duration_ratio: float = 0.25
    min_rms_db: float = -45.0
    max_peak_db: float = -0.1
    max_clipping_ratio: float = 0.003
    max_silence_ratio: float = 0.55


@dataclass
class SlideAudioQCResult:
    index: int
    audio_path: str
    expected_seconds: float = 0.0
    duration_seconds: float = 0.0
    duration_ratio: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    rms_db: float = -120.0
    peak_db: float = -120.0
    clipping_ratio: float = 0.0
    silence_ratio: float = 0.0
    issues: list[QCIssue] = field(default_factory=list)

    @property
    def status(self) -> Literal["ok", "warning", "error"]:
        if any(i.severity == "error" for i in self.issues):
            return "error"
        if any(i.severity == "warning" for i in self.issues):
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status
        return data


@dataclass
class AudioQCReport:
    slides: list[SlideAudioQCResult]

    @property
    def status(self) -> Literal["ok", "warning", "error"]:
        if any(s.status == "error" for s in self.slides):
            return "error"
        if any(s.status == "warning" for s in self.slides):
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        counts = {"ok": 0, "warning": 0, "error": 0}
        for slide in self.slides:
            counts[slide.status] += 1
        total_duration = round(sum(s.duration_seconds for s in self.slides), 2)
        return {
            "status": self.status,
            "counts": counts,
            "actual_total_seconds": total_duration,
            "actual_total_minutes": round(total_duration / 60.0, 2),
            "slides": [s.to_dict() for s in self.slides],
        }

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _add(issues: list[QCIssue], code: str, severity: Severity, message: str, detail: str = "") -> None:
    issues.append(QCIssue(code=code, severity=severity, message=message, detail=detail))


def _db(value: float) -> float:
    return round(20.0 * float(np.log10(max(value, 1e-8))), 2)


def analyze_audio(path: Path, *, index: int, expected_seconds: float = 0.0, cfg: AudioQCConfig | None = None) -> SlideAudioQCResult:
    cfg = cfg or AudioQCConfig()
    result = SlideAudioQCResult(index=index, audio_path=str(path), expected_seconds=round(expected_seconds, 2))
    issues = result.issues

    if not path.exists():
        _add(issues, "missing_audio", "error", "오디오 파일이 없습니다.")
        return result
    if path.stat().st_size < 1024:
        _add(issues, "tiny_audio_file", "error", "오디오 파일 크기가 너무 작습니다.", f"{path.stat().st_size} bytes")

    try:
        result.duration_seconds = round(audio_duration(path), 3)
        data, sr = sf.read(str(path), always_2d=True, dtype="float32")
        result.sample_rate = int(sr)
        result.channels = int(data.shape[1])
        mono = np.mean(data, axis=1) if data.size else np.array([], dtype=np.float32)
    except Exception as exc:
        _add(issues, "audio_decode_failed", "error", "오디오 파일을 디코딩할 수 없습니다.", str(exc))
        return result

    if mono.size == 0:
        _add(issues, "empty_audio", "error", "오디오 샘플이 비어 있습니다.")
        return result

    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(np.square(mono))))
    result.peak_db = _db(peak)
    result.rms_db = _db(rms)
    result.clipping_ratio = round(float(np.mean(np.abs(mono) >= 0.999)), 5)

    frame = max(int(sr * 0.05), 1)
    usable = (mono.size // frame) * frame
    if usable > 0:
        frames = mono[:usable].reshape(-1, frame)
        frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
        result.silence_ratio = round(float(np.mean(frame_rms < 0.003)), 4)

    if expected_seconds > 0:
        result.duration_ratio = round(result.duration_seconds / max(expected_seconds, 0.1), 3)

    if result.duration_seconds < cfg.min_duration_seconds:
        _add(issues, "too_short", "error", "오디오 길이가 너무 짧습니다.", f"{result.duration_seconds}s")
    if result.duration_seconds > cfg.max_duration_seconds:
        _add(issues, "too_long", "error", "오디오 길이가 비정상적으로 깁니다. TTS runaway 가능성이 큽니다.", f"{result.duration_seconds}s > {cfg.max_duration_seconds}s")
    if expected_seconds > 0 and result.duration_ratio > cfg.max_expected_duration_ratio:
        _add(issues, "longer_than_expected", "error", "예상 발화 시간보다 지나치게 깁니다.", f"ratio={result.duration_ratio}")
    if expected_seconds > 0 and result.duration_ratio < cfg.min_expected_duration_ratio:
        _add(issues, "shorter_than_expected", "warning", "예상 발화 시간보다 지나치게 짧습니다. 누락 가능성이 있습니다.", f"ratio={result.duration_ratio}")
    if result.rms_db < cfg.min_rms_db:
        _add(issues, "low_volume", "warning", "평균 볼륨이 낮습니다.", f"rms_db={result.rms_db}")
    if result.peak_db > cfg.max_peak_db:
        _add(issues, "peak_too_high", "warning", "피크가 너무 높아 왜곡 가능성이 있습니다.", f"peak_db={result.peak_db}")
    if result.clipping_ratio > cfg.max_clipping_ratio:
        _add(issues, "clipping", "warning", "클리핑 비율이 높습니다.", f"ratio={result.clipping_ratio}")
    if result.silence_ratio > cfg.max_silence_ratio:
        _add(issues, "too_much_silence", "warning", "무음 구간 비율이 높습니다.", f"ratio={result.silence_ratio}")

    return result


def run_audio_qc(slides: list[SlideRecord], expected_seconds_by_index: dict[int, float] | None = None, cfg: AudioQCConfig | None = None) -> AudioQCReport:
    expected_seconds_by_index = expected_seconds_by_index or {}
    return AudioQCReport([
        analyze_audio(
            Path(slide.audio_path),
            index=slide.index,
            expected_seconds=expected_seconds_by_index.get(slide.index, 0.0),
            cfg=cfg,
        )
        for slide in slides
        if slide.audio_path
    ])
