from __future__ import annotations
import json, logging
from pathlib import Path
from .audio_utils import audio_duration
from .aspect import dimensions_for_slide_aspect
from .audio_qc import AudioQCConfig, run_audio_qc
from .cache import FileCache, cache_key
from .config import AppConfig
from .models import PipelineInputs, SlideRecord
from .notes_extractor import extract_notes
from .notes_qc import QCConfig, run_notes_qc
from .pointer import plan_slide_pointers
from .renderer import create_renderer
from .subtitles import make_segments, write_srt
from .text_normalizer import normalize_text
from .tts import create_backend
from .tts.base import SynthesisOptions
from .video_compose import compose_video

log=logging.getLogger(__name__)

def _load_manifest(path: Path) -> dict[int, SlideRecord]:
    if not path.exists(): return {}
    data=json.loads(path.read_text(encoding='utf-8'))
    return {int(x['index']): SlideRecord(**{k:v for k,v in x.items() if k in SlideRecord.__dataclass_fields__}) for x in data.get('slides', data if isinstance(data,list) else [])}

def _save_manifest(path: Path, slides: list[SlideRecord]) -> None:
    path.write_text(json.dumps({"slides":[s.to_dict() for s in slides]}, ensure_ascii=False, indent=2), encoding='utf-8')

def run_pipeline(inputs: PipelineInputs, config: AppConfig) -> dict:
    out=inputs.output_dir; out.mkdir(parents=True, exist_ok=True)
    (out/'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=out/'logs'/'pipeline.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    notes_json=out/'notes.json'; manifest_path=out/'manifest.json'
    slides=extract_notes(inputs.pptx, notes_json)
    if inputs.start_slide is not None or inputs.end_slide is not None:
        start = inputs.start_slide or 1
        end = inputs.end_slide or len(slides)
        if start < 1 or end < start:
            raise ValueError(f"invalid slide range: start={start}, end={end}")
        slides=[s for s in slides if start <= s.index <= end]
        if not slides:
            raise ValueError(f"slide range {start}-{end} did not match any slides")
    normalized_for_qc={
        s.index: normalize_text(
            s.raw_notes,
            language=inputs.language or config.text.language,
            pronunciation=config.text.pronunciation,
            strip_stage_directions=config.text.strip_stage_directions,
        )
        for s in slides
    }
    if config.notes_qc.enabled:
        qc_report=run_notes_qc(
            slides,
            normalized_for_qc,
            QCConfig(**config.notes_qc.model_dump(exclude={"enabled", "fail_on_error"})),
        )
        qc_report.write_json(out/'notes_qc.json')
        if qc_report.status != 'ok':
            log.warning('Presenter notes QC status=%s; see %s', qc_report.status, out/'notes_qc.json')
        if config.notes_qc.fail_on_error and qc_report.status == 'error':
            raise RuntimeError(f'Presenter notes QC failed; see {out/"notes_qc.json"}')
    prev=_load_manifest(manifest_path)
    renderer=create_renderer(config.render.backend, config.render)
    visual_source = inputs.slide_visual_source or inputs.pptx
    images_dir=out/'slides'; images=renderer.render(visual_source, images_dir)
    video_width = config.video.width
    video_height = config.video.height
    if config.video.preserve_slide_aspect_ratio:
        video_width, video_height = dimensions_for_slide_aspect(
            inputs.pptx,
            width=config.video.width,
            height=config.video.height,
        )
    pointer_enabled = inputs.pointer if inputs.pointer is not None else config.pointer.enabled
    pointer_plans = {}
    if pointer_enabled:
        pointer_plans = plan_slide_pointers(
            inputs.pptx,
            {s.index: s.raw_notes for s in slides},
            video_width=video_width,
            video_height=video_height,
            move_seconds=config.pointer.move_seconds,
        )
    selected_engine = inputs.engine or config.tts.engine
    backend=create_backend(selected_engine, config.tts)
    engine_config = config.tts.active_engine_config(selected_engine)
    cache=FileCache(out/'cache'/'audio', config.cache.enabled)
    all_segments=[]; cursor=0.0
    expected_seconds_by_index={}
    for s in slides:
        old=prev.get(s.index)
        s.image_path=str(images[s.index-1]) if s.index-1 < len(images) else ''
        s.normalized_notes=normalized_for_qc.get(s.index) or normalize_text(s.raw_notes, language=inputs.language or config.text.language, pronunciation=config.text.pronunciation, strip_stage_directions=config.text.strip_stage_directions)
        if not s.normalized_notes:
            s.normalized_notes=s.title or f"Slide {s.index}"
        expected_seconds_by_index[s.index]=round(len(s.normalized_notes)/max(config.notes_qc.estimated_chars_per_second, 0.1), 2) if s.normalized_notes else 0.0
        key=cache_key(engine=backend.name, text=s.normalized_notes, voice_paths=inputs.voices, options=engine_config.model_dump())
        cached=cache.hit(key)
        target=out/'audio'/f"slide_{s.index:03}.wav"
        try:
            override=(inputs.slide_audio_overrides or {}).get(s.index)
            if override:
                if not override.exists():
                    raise FileNotFoundError(f'slide {s.index} audio override not found: {override}')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(override.read_bytes())
                s.audio_path=str(target); s.status='synthesized'; s.engine_name='recorded'
            elif old and old.audio_path and Path(old.audio_path).exists() and old.normalized_notes == s.normalized_notes:
                s.audio_path=old.audio_path; s.status='skipped'
            elif cached:
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(cached.read_bytes()); s.audio_path=str(target); s.status='synthesized'
            else:
                backend.synthesize(s.normalized_notes, inputs.voices, target, SynthesisOptions(language=inputs.language or config.text.language, sample_rate=engine_config.sample_rate, generation=engine_config.generation))
                cache.audio_path(key).write_bytes(target.read_bytes())
                s.audio_path=str(target); s.status='synthesized'
            s.duration=audio_duration(Path(s.audio_path)) + config.video.slide_padding_seconds
            if not s.engine_name:
                s.engine_name=backend.name
            plan = pointer_plans.get(s.index)
            if plan:
                s.pointer_plan = plan.to_dict()
            segs=make_segments(s.normalized_notes, cursor, s.duration); s.subtitle_segments=segs; all_segments.extend(segs); cursor += s.duration
        except Exception as e:
            s.status='failed'; s.error=str(e); _save_manifest(manifest_path, slides); raise
        _save_manifest(manifest_path, slides)
    if config.audio_qc.enabled:
        audio_report=run_audio_qc(
            slides,
            expected_seconds_by_index,
            AudioQCConfig(**config.audio_qc.model_dump(exclude={"enabled", "fail_on_error"})),
        )
        audio_report.write_json(out/'audio_qc.json')
        if audio_report.status != 'ok':
            log.warning('Audio QC status=%s; see %s', audio_report.status, out/'audio_qc.json')
        if config.audio_qc.fail_on_error and audio_report.status == 'error':
            raise RuntimeError(f'Audio QC failed; see {out/"audio_qc.json"}')
    srt=None
    if inputs.subtitles if inputs.subtitles is not None else config.video.subtitles:
        srt=write_srt(all_segments, out/'subtitles.srt')
    final=compose_video(slides, out/'final.mp4', fps=config.video.fps, width=video_width, height=video_height, subtitles=srt, background_music=inputs.background_music, bgm_volume=config.video.background_music_volume, pointer_plans=pointer_plans)
    report={"final": str(final), "slides": len(slides), "duration": cursor, "manifest": str(manifest_path), "subtitles": str(srt) if srt else None, "pointer_enabled": bool(pointer_enabled), "start_slide": inputs.start_slide, "end_slide": inputs.end_slide, "video_width": video_width, "video_height": video_height, "preserve_slide_aspect_ratio": config.video.preserve_slide_aspect_ratio}
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
