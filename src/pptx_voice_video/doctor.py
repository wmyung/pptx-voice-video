from __future__ import annotations
import shutil, subprocess
from .config import AppConfig
from .tts import create_backend
from .renderer import create_renderer

def run_doctor(config: AppConfig) -> dict:
    report={}
    report['ffmpeg']={"available": bool(shutil.which('ffmpeg')), "path": shutil.which('ffmpeg')}
    report['ffprobe']={"available": bool(shutil.which('ffprobe')), "path": shutil.which('ffprobe')}
    report['nvidia_smi']={"available": bool(shutil.which('nvidia-smi'))}
    if shutil.which('nvidia-smi'):
        cp=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        report['nvidia_smi']['output']=cp.stdout.strip()
    try:
        import torch
        report['torch']={"version": torch.__version__, "cuda_available": torch.cuda.is_available(), "cuda_version": torch.version.cuda}
        if torch.cuda.is_available(): report['torch']['gpu']=torch.cuda.get_device_name(0)
    except Exception as e: report['torch']={"error": str(e)}
    report['renderer']=create_renderer(config.render.backend, config.render).health_check()
    report['tts']=create_backend(config.tts.engine, config.tts).health_check()
    return report
