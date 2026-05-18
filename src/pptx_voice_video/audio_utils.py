from __future__ import annotations
import subprocess, wave
from pathlib import Path

def ffprobe_duration(path: Path) -> float:
    cmd=['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)]
    cp=subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return float(cp.stdout.strip())

def wav_duration(path: Path) -> float:
    with wave.open(str(path), 'rb') as w: return w.getnframes()/float(w.getframerate())

def audio_duration(path: Path) -> float:
    try: return ffprobe_duration(path)
    except Exception: return wav_duration(path)

def concat_audio(inputs: list[Path], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    listfile=output.with_suffix('.concat.txt')
    listfile.write_text(''.join(f"file {p.resolve()}\n" for p in inputs), encoding='utf-8')
    subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(listfile),'-c','copy',str(output)], check=True)
    return output
