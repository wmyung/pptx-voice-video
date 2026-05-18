from __future__ import annotations
from pathlib import Path
import tempfile
from .models import PipelineInputs
from .pipeline import run_pipeline

def launch_ui(config, host: str='127.0.0.1', port: int=7860):
    import gradio as gr
    def run(pptx, voice, engine, language, subtitles, pointer, bgm):
        out=Path(tempfile.mkdtemp(prefix='pptx_voice_video_'))
        report=run_pipeline(PipelineInputs(pptx=Path(pptx), voices=[Path(voice)], output_dir=out, background_music=Path(bgm) if bgm else None, engine=engine, language=language, subtitles=subtitles, pointer=pointer), config)
        return report.get('final'), report
    with gr.Blocks(title='PPTX Voice Video') as demo:
        gr.Markdown('# PPTX 발표자 노트 → 보이스 클론 강의 영상')
        pptx=gr.File(label='PPTX', file_types=['.pptx'], type='filepath')
        voice=gr.File(label='목소리 레퍼런스 오디오', file_types=['.wav','.mp3','.m4a','.flac'], type='filepath')
        bgm=gr.File(label='배경음악(선택)', type='filepath')
        engine=gr.Dropdown(['voxcpm'], value=config.tts.engine, label='TTS Engine')
        language=gr.Dropdown(['ko','en'], value=config.text.language, label='Language')
        subtitles=gr.Checkbox(value=config.video.subtitles, label='자막 생성')
        pointer=gr.Checkbox(value=config.pointer.enabled, label='자동 마우스 포인터')
        btn=gr.Button('영상 생성')
        video=gr.Video(label='final.mp4'); report=gr.JSON(label='report')
        btn.click(run, [pptx, voice, engine, language, subtitles, pointer, bgm], [video, report])
    demo.launch(server_name=host, server_port=port)
