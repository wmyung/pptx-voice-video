from pptx_voice_video.models import SlideRecord
from pptx_voice_video.notes_qc import QCConfig, run_notes_qc
from pptx_voice_video.text_normalizer import normalize_text


def test_notes_qc_flags_long_notes_and_many_chunks():
    slide = SlideRecord(index=1, title="긴 노트", raw_notes="문장입니다. " * 80)
    normalized = normalize_text(slide.raw_notes)
    report = run_notes_qc([slide], {1: normalized}, QCConfig(max_normalized_chars=100, max_chunks=2, max_chunk_chars=40))

    assert report.status == "warning"
    codes = {issue.code for issue in report.slides[0].issues}
    assert "normalized_too_long" in codes
    assert "too_many_chunks" in codes


def test_notes_qc_empty_notes_warning():
    slide = SlideRecord(index=2, title="빈 노트", raw_notes="")
    report = run_notes_qc([slide], {2: ""}, QCConfig())

    assert report.status == "warning"
    assert report.slides[0].issues[0].code == "empty_notes"


def test_notes_qc_symbol_and_url_detection():
    raw = "참고: https://example.com → → → → → → → → → →"
    slide = SlideRecord(index=3, title="기호", raw_notes=raw)
    report = run_notes_qc([slide], {3: normalize_text(raw)}, QCConfig(max_symbol_ratio=0.01))

    codes = {issue.code for issue in report.slides[0].issues}
    assert "symbol_heavy" in codes
    assert "url_present" in codes
