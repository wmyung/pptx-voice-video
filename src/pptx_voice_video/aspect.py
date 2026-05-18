from __future__ import annotations

from pathlib import Path

from pptx import Presentation


def even(value: int) -> int:
    """Return a positive even integer suitable for H.264 dimensions."""
    value = max(2, int(round(value)))
    return value if value % 2 == 0 else value + 1


def pptx_aspect_ratio(pptx: Path) -> float:
    """Return slide width / height for a PPTX file."""
    prs = Presentation(str(pptx))
    height = int(prs.slide_height)
    if height <= 0:
        raise ValueError(f"invalid PPTX slide height: {height}")
    return int(prs.slide_width) / height


def dimensions_for_slide_aspect(pptx: Path, *, width: int, height: int) -> tuple[int, int]:
    """Keep the requested width and derive an even height from the PPTX aspect ratio.

    Width is kept stable because downstream video quality/file-size expectations are
    usually keyed to horizontal resolution. Height is rounded to an even integer for
    encoder compatibility.
    """
    ratio = pptx_aspect_ratio(pptx)
    if ratio <= 0:
        raise ValueError(f"invalid PPTX aspect ratio: {ratio}")
    return even(width), even(width / ratio)
