from __future__ import annotations
from pathlib import Path

def fmt_ts(sec: float) -> str:
    ms=int(round(sec*1000))
    h=ms//3600000
    ms%=3600000
    m=ms//60000
    ms%=60000
    s=ms//1000
    ms%=1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def make_segments(text: str, start: float, duration: float) -> list[dict]:
    return [{"start": start, "end": start+max(duration,0.1), "text": text}] if text else []

def write_srt(segments: list[dict], path: Path) -> Path:
    lines=[]
    for i,seg in enumerate(segments,1):
        lines += [str(i), f"{fmt_ts(seg['start'])} --> {fmt_ts(seg['end'])}", seg.get('text',''), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding='utf-8')
    return path
