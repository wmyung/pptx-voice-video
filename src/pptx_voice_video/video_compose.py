from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from .models import SlideRecord
from .pointer import PointerPlan


def _ffmpeg_run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _concat_file_line(path: Path) -> str:
    # ffmpeg concat demuxer accepts single-quoted paths; escape embedded quotes.
    return "file " + shlex.quote(str(path.resolve())) + "\n"


def _segment_meta(
    slide: SlideRecord,
    *,
    fps: int,
    width: int,
    height: int,
    pointer_plan: PointerPlan | None = None,
) -> dict:
    image = Path(slide.image_path).resolve()
    audio = Path(slide.audio_path).resolve()
    image_stat = image.stat()
    audio_stat = audio.stat()
    meta = {
        "slide_index": slide.index,
        "image_path": str(image),
        "image_size": image_stat.st_size,
        "image_mtime_ns": image_stat.st_mtime_ns,
        "audio_path": str(audio),
        "audio_size": audio_stat.st_size,
        "audio_mtime_ns": audio_stat.st_mtime_ns,
        "duration": round(float(slide.duration), 3),
        "fps": fps,
        "width": width,
        "height": height,
    }
    if pointer_plan and pointer_plan.visible:
        meta["pointer_plan"] = pointer_plan.to_dict()
    return meta


def _segment_is_current(segment: Path, meta_path: Path, expected_meta: dict) -> bool:
    if not segment.exists() or segment.stat().st_size <= 0 or not meta_path.exists():
        return False
    try:
        current = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return current == expected_meta


def _ensure_cursor_asset(path: Path, *, size: int = 48) -> Path:
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Classic pointer arrow: tip is at (0, 0), so overlay x/y are the pointed location.
    fill = (255, 255, 255, 255)
    outline = (20, 20, 20, 255)
    points = [(0, 0), (0, size - 6), (size // 3, size - 18), (size // 2, size - 2), (size // 2 + 8, size - 7), (size // 3 + 3, size - 23), (size - 5, size - 23)]
    draw.polygon(points, fill=fill, outline=outline)
    image.save(path)
    return path


def _pointer_overlay_filter(plan: PointerPlan, *, cursor_width: int, cursor_height: int) -> str:
    start_x = plan.start_x if plan.start_x is not None else plan.target_x
    start_y = plan.start_y if plan.start_y is not None else plan.target_y
    move = max(float(plan.move_seconds), 0.001)
    target_x = max(0, plan.target_x)
    target_y = max(0, plan.target_y)
    start_x = max(0, start_x)
    start_y = max(0, start_y)
    # Smoothstep easing: slow at start/end, closer to a human pointer adjustment.
    ratio = f"min(t/{move:.3f},1)"
    ease = f"({ratio})*({ratio})*(3-2*({ratio}))"
    x = f"if(lt(t,{move:.3f}),{start_x}+({target_x}-{start_x})*{ease},{target_x})"
    y = f"if(lt(t,{move:.3f}),{start_y}+({target_y}-{start_y})*{ease},{target_y})"
    enable = ""
    if plan.hide_after_seconds is not None:
        enable = f":enable='lt(t,{max(float(plan.hide_after_seconds), 0.001):.3f})'"
    return f"overlay=x='{x}':y='{y}':format=auto{enable}"


def render_slide_segment(
    slide: SlideRecord,
    segment: Path,
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    force: bool = False,
    pointer_plan: PointerPlan | None = None,
) -> Path:
    """Render one slide+audio pair to a reusable MP4 segment."""
    segment.parent.mkdir(parents=True, exist_ok=True)
    meta_path = segment.with_suffix(".json")
    expected_meta = _segment_meta(slide, fps=fps, width=width, height=height, pointer_plan=pointer_plan)
    if not force and _segment_is_current(segment, meta_path, expected_meta):
        return segment

    base_vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    if pointer_plan and pointer_plan.visible:
        cursor = _ensure_cursor_asset(segment.parent / "cursor_pointer.png")
        overlay = _pointer_overlay_filter(pointer_plan, cursor_width=48, cursor_height=48)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-t",
            f"{slide.duration:.3f}",
            "-i",
            str(slide.image_path),
            "-i",
            str(slide.audio_path),
            "-loop",
            "1",
            "-i",
            str(cursor),
            "-filter_complex",
            f"[0:v]{base_vf}[base];[base][2:v]{overlay}[v]",
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(segment),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-t",
            f"{slide.duration:.3f}",
            "-i",
            str(slide.image_path),
            "-i",
            str(slide.audio_path),
            "-vf",
            base_vf,
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(segment),
        ]
    _ffmpeg_run(cmd)
    meta_path.write_text(json.dumps(expected_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return segment


def concat_segments(segments: list[Path], output: Path, *, work_dir: Path | None = None) -> Path:
    if not segments:
        raise ValueError("No video segments to concatenate")
    output.parent.mkdir(parents=True, exist_ok=True)
    work_dir = work_dir or output.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    listfile = work_dir / f"{output.stem}.concat.txt"
    listfile.write_text("".join(_concat_file_line(p) for p in segments), encoding="utf-8")
    _ffmpeg_run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listfile),
            "-c",
            "copy",
            str(output),
        ]
    )
    return output


def compose_video(
    slides: list[SlideRecord],
    output: Path,
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    subtitles: Path | None = None,
    background_music: Path | None = None,
    bgm_volume: float = 0.12,
    segment_dir: Path | None = None,
    force_segments: bool = False,
    pointer_plans: dict[int, PointerPlan] | None = None,
) -> Path:
    """Create an MP4 from slide images and narration.

    The expensive per-slide encodes are written to a persistent segment directory.
    Re-running after a timeout reuses unchanged segments and only rebuilds missing
    or stale slides before doing a final concat.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    segment_dir = segment_dir or output.parent / f"{output.stem}_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)

    segments: list[Path] = []
    for slide in slides:
        segment = segment_dir / f"seg_{slide.index:03}.mp4"
        segments.append(
            render_slide_segment(
                slide,
                segment,
                fps=fps,
                width=width,
                height=height,
                force=force_segments,
                pointer_plan=(pointer_plans or {}).get(slide.index),
            )
        )

    concat = output.parent / f"{output.stem}.concat.mp4"
    concat_segments(segments, concat, work_dir=segment_dir)

    vf: list[str] = []
    if subtitles:
        vf.append(f"subtitles={subtitles}")
    if background_music:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(concat),
            "-stream_loop",
            "-1",
            "-i",
            str(background_music),
            "-filter_complex",
            f"[1:a]volume={bgm_volume}[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    elif vf:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(concat),
            "-vf",
            ",".join(vf),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(output),
        ]
    else:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(concat), "-c", "copy", str(output)]
    _ffmpeg_run(cmd)
    return output
