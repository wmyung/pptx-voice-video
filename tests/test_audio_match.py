from pathlib import Path

from pptx_voice_video.audio_match import AudioMatchConfig, match_recordings_to_slides
from pptx_voice_video.models import SlideRecord


def test_numbered_recording_is_accepted_for_declared_slide_when_confident(tmp_path: Path):
    audio = tmp_path / "01.mp3"
    audio.write_bytes(b"fake")
    slides = [SlideRecord(index=1, raw_notes="외상 후 스트레스 장애의 진단 기준과 회피 증상을 설명합니다.")]

    report = match_recordings_to_slides(
        slides,
        tmp_path,
        config=AudioMatchConfig(min_similarity=0.2, min_keyword_recall=0.2),
        transcripts_by_path={audio.resolve(): "외상 후 스트레스 장애 진단 기준과 회피 증상을 설명합니다."},
    )

    assert report.overrides == {1: audio.resolve()}
    assert report.matches[0].status == "accepted"
    assert report.matches[0].source == "filename"


def test_numbered_recording_is_rejected_for_declared_slide_when_confidence_is_low(tmp_path: Path):
    audio = tmp_path / "01.mp3"
    audio.write_bytes(b"fake")
    slides = [
        SlideRecord(index=1, raw_notes="외상 후 스트레스 장애의 진단 기준과 회피 증상을 설명합니다."),
        SlideRecord(index=2, raw_notes="심부전 치료와 이뇨제 용량 조절을 설명합니다."),
    ]

    report = match_recordings_to_slides(
        slides,
        tmp_path,
        config=AudioMatchConfig(min_similarity=0.5, min_keyword_recall=0.5),
        transcripts_by_path={audio.resolve(): "심부전 치료와 이뇨제 용량 조절을 설명합니다."},
    )

    assert report.overrides == {}
    assert report.matches[0].slide_index == 1
    assert report.matches[0].status == "rejected"
    assert report.matches[0].reason == "low_confidence_for_numbered_slide"


def test_unnumbered_recording_is_auto_matched_to_best_confident_slide(tmp_path: Path):
    audio = tmp_path / "kakao_recording.mp3"
    audio.write_bytes(b"fake")
    slides = [
        SlideRecord(index=1, raw_notes="외상 후 스트레스 장애의 진단 기준과 회피 증상을 설명합니다."),
        SlideRecord(index=2, raw_notes="급성 스트레스 장애와 적응장애의 차이를 설명합니다."),
    ]

    report = match_recordings_to_slides(
        slides,
        tmp_path,
        config=AudioMatchConfig(min_similarity=0.2, min_keyword_recall=0.2, min_margin=0.05),
        transcripts_by_path={audio.resolve(): "급성 스트레스 장애와 적응장애의 차이를 설명합니다."},
    )

    assert report.overrides == {2: audio.resolve()}
    assert report.matches[0].slide_index == 2
    assert report.matches[0].status == "accepted"
    assert report.matches[0].source == "semantic"
