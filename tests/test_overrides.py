from pathlib import Path

from pptx_voice_video.models import SlideRecord
from pptx_voice_video.overrides import load_slide_audio_overrides, scan_slide_audio_directory
from pptx_voice_video.recorded_audio_qc import compare_transcript_to_notes, run_recorded_audio_qc, RecordedAudioQCConfig


def test_load_slide_audio_overrides_relative_paths(tmp_path: Path):
    cfg = tmp_path / "overrides.yaml"
    cfg.write_text("slides:\n  24: recordings/slide_024.m4a\n", encoding="utf-8")

    overrides = load_slide_audio_overrides(cfg)

    assert 24 in overrides
    assert overrides[24] == (tmp_path / "recordings" / "slide_024.m4a").resolve()


def test_load_slide_audio_overrides_plain_mapping(tmp_path: Path):
    cfg = tmp_path / "overrides.yaml"
    cfg.write_text("9: /tmp/slide_009.wav\n", encoding="utf-8")

    overrides = load_slide_audio_overrides(cfg)

    assert overrides[9] == Path("/tmp/slide_009.wav")


def test_scan_slide_audio_directory_numbered_files(tmp_path: Path):
    (tmp_path / "24.m4a").write_bytes(b"audio")
    (tmp_path / "slide_025.mp3").write_bytes(b"audio")
    (tmp_path / "not_a_slide.txt").write_text("x", encoding="utf-8")

    overrides = scan_slide_audio_directory(tmp_path)

    assert sorted(overrides) == [24, 25]


def test_compare_transcript_to_notes_detects_match():
    notes = "이 슬라이드는 핵심 기능과 구성 요소의 역할을 설명합니다. 처리량이 증가합니다."
    transcript = "이번 슬라이드는 핵심 기능 그리고 구성 요소 역할을 설명합니다. 처리량이 증가합니다."

    similarity, recall = compare_transcript_to_notes(transcript, notes)

    assert similarity > 0.5
    assert recall > 0.5


def test_run_recorded_audio_qc_with_supplied_transcript(tmp_path: Path):
    audio = tmp_path / "24.m4a"
    audio.write_bytes(b"fake audio but transcript supplied")
    slide = SlideRecord(index=24, title="주제", raw_notes="핵심 기능과 구성 요소의 역할을 설명합니다.")

    report = run_recorded_audio_qc(
        [slide],
        tmp_path,
        config=RecordedAudioQCConfig(min_similarity=0.2, min_keyword_recall=0.2),
        transcripts_by_index={24: "핵심 기능과 구성 요소 역할을 설명합니다."},
    )

    assert report.status == "ok"
    assert report.slides[0].index == 24
