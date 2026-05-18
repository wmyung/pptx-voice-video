from __future__ import annotations
import json
from pathlib import Path
import click
from .audio_match import AudioMatchConfig, match_recordings_to_slides
from .audio_qc import AudioQCConfig, run_audio_qc
from .config import load_config
from .doctor import run_doctor
from .models import PipelineInputs
from .notes_extractor import extract_notes
from .notes_qc import QCConfig, run_notes_qc
from .overrides import load_slide_audio_overrides
from .pipeline import run_pipeline
from .recorded_audio_qc import RecordedAudioQCConfig, run_recorded_audio_qc
from .retime import retime_manifest
from .text_normalizer import normalize_text

@click.group()
def main(): pass

@main.command()
@click.option('--config','config_path', type=click.Path(exists=True), default=None)
def doctor(config_path):
    cfg=load_config(config_path)
    click.echo(json.dumps(run_doctor(cfg), ensure_ascii=False, indent=2))

@main.command('notes-qc')
@click.option('--pptx', required=True, type=click.Path(exists=True))
@click.option('--config','config_path', type=click.Path(exists=True), default=None)
@click.option('--out', 'output_path', type=click.Path(), default=None)
@click.option('--language', default=None)
def notes_qc(pptx, config_path, output_path, language):
    """Inspect presenter notes before expensive TTS synthesis."""
    cfg=load_config(config_path)
    slides=extract_notes(Path(pptx))
    normalized={
        s.index: normalize_text(
            s.raw_notes,
            language=language or cfg.text.language,
            pronunciation=cfg.text.pronunciation,
            strip_stage_directions=cfg.text.strip_stage_directions,
        )
        for s in slides
    }
    report=run_notes_qc(
        slides,
        normalized,
        QCConfig(**cfg.notes_qc.model_dump(exclude={"enabled", "fail_on_error"})),
    )
    payload=report.to_dict()
    text=json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding='utf-8')
    click.echo(text)

@main.command('audio-qc')
@click.option('--manifest', 'manifest_path', required=True, type=click.Path(exists=True))
@click.option('--config','config_path', type=click.Path(exists=True), default=None)
@click.option('--out', 'output_path', type=click.Path(), default=None)
def audio_qc(manifest_path, config_path, output_path):
    """Inspect synthesized audio before final video composition."""
    cfg=load_config(config_path)
    data=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    from .models import SlideRecord
    slides=[SlideRecord(**{k:v for k,v in s.items() if k in SlideRecord.__dataclass_fields__}) for s in data.get('slides', [])]
    expected={s.index: round(len(s.normalized_notes)/max(cfg.notes_qc.estimated_chars_per_second, 0.1), 2) if s.normalized_notes else 0.0 for s in slides}
    report=run_audio_qc(
        slides,
        expected,
        AudioQCConfig(**cfg.audio_qc.model_dump(exclude={"enabled", "fail_on_error"})),
    )
    text=json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding='utf-8')
    click.echo(text)

@main.command('recorded-audio-qc')
@click.option('--pptx', required=True, type=click.Path(exists=True))
@click.option('--recordings', required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True), help='Directory containing numbered files like 24.m4a or slide_024.wav')
@click.option('--config','config_path', type=click.Path(exists=True), default=None)
@click.option('--out', 'output_path', type=click.Path(), default=None)
@click.option('--language', default=None)
@click.option('--asr-model', default='small')
@click.option('--min-similarity', default=0.42, type=float)
@click.option('--min-keyword-recall', default=0.35, type=float)
def recorded_audio_qc(pptx, recordings, config_path, output_path, language, asr_model, min_similarity, min_keyword_recall):
    """Match numbered recorded audio files to slide notes and verify content with local ASR."""
    cfg=load_config(config_path)
    slides=extract_notes(Path(pptx))
    report=run_recorded_audio_qc(
        slides,
        Path(recordings),
        config=RecordedAudioQCConfig(
            min_similarity=min_similarity,
            min_keyword_recall=min_keyword_recall,
            asr_model=asr_model,
            language=language or cfg.text.language,
        ),
    )
    text=json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding='utf-8')
    click.echo(text)

@main.command('auto-match-audio')
@click.option('--pptx', required=True, type=click.Path(exists=True))
@click.option('--recordings', required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True), help='Directory containing recorded narration audio files. Numbered files are validated against that slide; unnumbered files are semantically matched.')
@click.option('--config','config_path', type=click.Path(exists=True), default=None)
@click.option('--out', 'output_path', type=click.Path(), default=None, help='Write full JSON match report.')
@click.option('--mapping-out', type=click.Path(), default=None, help='Write accepted slide audio overrides YAML for render --slide-audio-overrides.')
@click.option('--language', default=None)
@click.option('--asr-model', default='small')
@click.option('--min-similarity', default=0.42, type=float)
@click.option('--min-keyword-recall', default=0.35, type=float)
@click.option('--min-margin', default=0.08, type=float)
def auto_match_audio(pptx, recordings, config_path, output_path, mapping_out, language, asr_model, min_similarity, min_keyword_recall, min_margin):
    """Transcribe recordings and match them to slide notes without relying on filenames."""
    cfg=load_config(config_path)
    slides=extract_notes(Path(pptx))
    report=match_recordings_to_slides(
        slides,
        Path(recordings),
        config=AudioMatchConfig(
            min_similarity=min_similarity,
            min_keyword_recall=min_keyword_recall,
            min_margin=min_margin,
            asr_model=asr_model,
            language=language or cfg.text.language,
        ),
    )
    if mapping_out:
        report.write_overrides_yaml(Path(mapping_out))
    text=json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding='utf-8')
    click.echo(text)

@main.command()
@click.option('--pptx', required=True, type=click.Path(exists=True))
@click.option('--voice', 'voices', multiple=True, required=True, type=click.Path(exists=True))
@click.option('--config','config_path', type=click.Path(exists=True), default=None)
@click.option('--background-music', type=click.Path(exists=True), default=None)
@click.option('--out', 'output_dir', required=True, type=click.Path())
@click.option('--engine', default=None)
@click.option('--language', default=None)
@click.option('--subtitles/--no-subtitles', default=None)
@click.option('--transitions/--no-transitions', default=None)
@click.option('--pointer/--no-pointer', default=None, help='Enable automatic mouse pointer overlay. Ambiguous slides hide the cursor.')
@click.option('--slide-audio-overrides', type=click.Path(exists=True), default=None, help='YAML mapping slide index to recorded narration audio file, or a directory of recorded files. Directories are ASR-validated before use.')
@click.option('--slide-visual-source', type=click.Path(exists=True), default=None, help='Optional PDF exported from PowerPoint to use for slide visuals while reading presenter notes from --pptx.')
@click.option('--auto-match-recordings', type=click.Path(exists=True, file_okay=False, dir_okay=True), default=None, help='Directory of arbitrary-named recorded narration files to ASR-match against slide notes before synthesizing missing slides.')
@click.option('--match-asr-model', default='small')
@click.option('--match-min-similarity', default=0.42, type=float)
@click.option('--match-min-keyword-recall', default=0.35, type=float)
@click.option('--match-min-margin', default=0.08, type=float)
@click.option('--start-slide', type=int, default=None, help='First slide number to render, 1-based.')
@click.option('--end-slide', type=int, default=None, help='Last slide number to render, inclusive.')
@click.option('--target-minutes', type=float, default=None, help='After rendering, create a retimed copy with semantic pauses matching this target duration.')
@click.option('--retime-tempo', type=float, default=0.85, show_default=True, help='Tempo factor for --target-minutes retiming. Lower is slower.')
@click.option('--retime-slide-pause', type=float, default=3.0, show_default=True, help='Slide-end pause in seconds for --target-minutes retiming.')
def render(pptx, voices, config_path, background_music, output_dir, engine, language, subtitles, transitions, pointer, slide_audio_overrides, slide_visual_source, auto_match_recordings, match_asr_model, match_min_similarity, match_min_keyword_recall, match_min_margin, start_slide, end_slide, target_minutes, retime_tempo, retime_slide_pause):
    cfg=load_config(config_path)
    overrides={}
    match_config=AudioMatchConfig(
        min_similarity=match_min_similarity,
        min_keyword_recall=match_min_keyword_recall,
        min_margin=match_min_margin,
        asr_model=match_asr_model,
        language=language or cfg.text.language,
    )
    if slide_audio_overrides:
        override_path=Path(slide_audio_overrides)
        if override_path.is_dir():
            slides=extract_notes(Path(pptx))
            report=match_recordings_to_slides(slides, override_path, config=match_config)
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            report.write_json(Path(output_dir)/'slide_audio_overrides_match_report.json')
            overrides.update(report.overrides)
        else:
            overrides.update(load_slide_audio_overrides(slide_audio_overrides))
    if auto_match_recordings:
        slides=extract_notes(Path(pptx))
        report=match_recordings_to_slides(slides, Path(auto_match_recordings), config=match_config)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        report.write_json(Path(output_dir)/'auto_match_audio_report.json')
        # Explicit mapping from --slide-audio-overrides wins on conflicts.
        for idx, audio_path in report.overrides.items():
            overrides.setdefault(idx, audio_path)
    inputs=PipelineInputs(pptx=Path(pptx), voices=[Path(v) for v in voices], output_dir=Path(output_dir), background_music=Path(background_music) if background_music else None, config_path=Path(config_path) if config_path else None, engine=engine, language=language, subtitles=subtitles, transitions=transitions, pointer=pointer, slide_audio_overrides=overrides, slide_visual_source=Path(slide_visual_source) if slide_visual_source else None, start_slide=start_slide, end_slide=end_slide)
    report = run_pipeline(inputs, cfg)
    if target_minutes:
        retimed_dir = Path(output_dir) / f"retimed_{int(round(target_minutes))}min"
        report["retime"] = retime_manifest(
            Path(report["manifest"]),
            retimed_dir,
            target_seconds=target_minutes * 60.0,
            tempo=retime_tempo,
            slide_end_pause=retime_slide_pause,
            width=report.get("video_width", cfg.video.width),
            height=report.get("video_height", cfg.video.height),
        )
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))

@main.command('retime')
@click.option('--manifest', 'manifest_path', required=True, type=click.Path(exists=True), help='manifest.json from a completed render job.')
@click.option('--out', 'output_dir', required=True, type=click.Path(), help='Directory for retimed audio, segments, report, and final_retimed.mp4.')
@click.option('--target-minutes', required=True, type=float, help='Target final video length in minutes.')
@click.option('--tempo', default=0.85, type=float, show_default=True, help='Speech tempo factor. Lower is slower; 0.85 is mildly slower than original.')
@click.option('--slide-pause', default=3.0, type=float, show_default=True, help='Silence added after each slide, in seconds.')
@click.option('--width', default=1920, type=int, show_default=True)
@click.option('--height', default=1080, type=int, show_default=True)
@click.option('--max-workers', default=4, type=int, show_default=True)
def retime(manifest_path, output_dir, target_minutes, tempo, slide_pause, width, height, max_workers):
    """Retiming pass with semantic pauses at natural discourse boundaries.

    This is for cases where raw TTS is too fast or too short. It avoids adding
    pauses at arbitrary whitespace; instead it weights sentence endings,
    contrast/causal transitions, signposts, and long clause boundaries.
    """
    report = retime_manifest(
        Path(manifest_path),
        Path(output_dir),
        target_seconds=target_minutes * 60.0,
        tempo=tempo,
        slide_end_pause=slide_pause,
        width=width,
        height=height,
        max_workers=max_workers,
    )
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))

@main.command()
@click.option('--config','config_path', type=click.Path(exists=True), default=None)
@click.option('--host', default='127.0.0.1')
@click.option('--port', default=7860, type=int)
def ui(config_path, host, port):
    from .ui import launch_ui
    launch_ui(load_config(config_path), host, port)

if __name__ == '__main__': main()
