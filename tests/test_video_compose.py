from pathlib import Path

from pptx_voice_video.models import SlideRecord
from pptx_voice_video.pointer import PointerPlan
from pptx_voice_video.video_compose import (
    _concat_file_line,
    _pointer_overlay_filter,
    _segment_is_current,
    _segment_meta,
    render_slide_segment,
)


def test_concat_file_line_quotes_paths(tmp_path: Path):
    path = tmp_path / "a file's name.mp4"
    line = _concat_file_line(path)
    assert line.startswith("file ")
    assert str(path.resolve()).split("'")[0] in line


def test_segment_meta_current_detection(tmp_path: Path):
    image = tmp_path / "slide.png"
    audio = tmp_path / "slide.wav"
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    slide = SlideRecord(index=1, title="", raw_notes="", normalized_notes="", image_path=str(image), audio_path=str(audio), duration=1.2)
    meta = _segment_meta(slide, fps=30, width=1920, height=1080)
    seg = tmp_path / "seg_001.mp4"
    seg.write_bytes(b"video")
    meta_path = tmp_path / "seg_001.json"
    meta_path.write_text(__import__("json").dumps(meta), encoding="utf-8")
    assert _segment_is_current(seg, meta_path, meta)
    audio.write_bytes(b"changed")
    changed = _segment_meta(slide, fps=30, width=1920, height=1080)
    assert not _segment_is_current(seg, meta_path, changed)


def test_pointer_plan_is_part_of_segment_cache_key(tmp_path: Path):
    image = tmp_path / "slide.png"
    audio = tmp_path / "slide.wav"
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    slide = SlideRecord(index=1, image_path=str(image), audio_path=str(audio), duration=1.2)
    plan = PointerPlan(slide_index=1, visible=True, target_x=100, target_y=200, reason="matching_text")

    meta = _segment_meta(slide, fps=30, width=1920, height=1080, pointer_plan=plan)

    assert meta["pointer_plan"]["visible"] is True
    assert meta["pointer_plan"]["target_x"] == 100


def test_pointer_overlay_filter_moves_then_stays():
    plan = PointerPlan(
        slide_index=1,
        visible=True,
        target_x=500,
        target_y=300,
        start_x=100,
        start_y=900,
        move_seconds=0.8,
        reason="matching_text",
    )

    overlay = _pointer_overlay_filter(plan, cursor_width=48, cursor_height=48)

    assert "overlay=" in overlay
    assert "min(t/0.800,1)" in overlay
    assert "3-2*" in overlay
    assert "500" in overlay
    assert "300" in overlay


def test_pointer_overlay_filter_can_hide_after_hold():
    plan = PointerPlan(
        slide_index=4,
        visible=True,
        target_x=500,
        target_y=300,
        start_x=500,
        start_y=300,
        move_seconds=0.001,
        hide_after_seconds=1.2,
        reason="ambiguous_hold_then_hide",
    )

    overlay = _pointer_overlay_filter(plan, cursor_width=48, cursor_height=48)

    assert "enable='lt(t,1.200)'" in overlay


def test_render_slide_segment_creates_nested_segment_directory(tmp_path: Path, monkeypatch):
    image = tmp_path / "slide.png"
    audio = tmp_path / "slide.wav"
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    slide = SlideRecord(index=1, image_path=str(image), audio_path=str(audio), duration=1.2)
    segment = tmp_path / "missing" / "nested" / "seg_001.mp4"

    def fake_ffmpeg_run(cmd: list[str]) -> None:
        segment.write_bytes(b"video")

    monkeypatch.setattr("pptx_voice_video.video_compose._ffmpeg_run", fake_ffmpeg_run)

    result = render_slide_segment(slide, segment)

    assert result == segment
    assert segment.exists()
    assert segment.with_suffix(".json").exists()
