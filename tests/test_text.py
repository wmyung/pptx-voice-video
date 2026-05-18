from pptx_voice_video.text_normalizer import normalize_text, chunk_text

def test_normalize_bullets_and_pronunciation():
    out=normalize_text('- AI 소개\n- GPU 사용', pronunciation={'AI':'에이아이','GPU':'지피유'})
    assert '에이아이' in out and '지피유' in out and '-' not in out

def test_chunk_text_max():
    chunks=chunk_text('가'*25, max_chars=10)
    assert chunks == ['가'*10, '가'*10, '가'*5]


def test_normalize_removes_slide_number_and_empty_punctuation_lines():
    out = normalize_text('첫 문장입니다.\n.\n24\n')
    assert out == '첫 문장입니다.'
    assert '24' not in out


def test_normalize_joins_manual_linebreaks_without_inserting_pauses():
    out = normalize_text('안녕하세요\n발표자\n입니다')
    assert out == '안녕하세요 발표자 입니다'


def test_normalize_preserves_explicit_sentence_punctuation_across_lines():
    out = normalize_text('첫 문장입니다.\n두 번째 문장입니다.')
    assert out == '첫 문장입니다. 두 번째 문장입니다.'


def test_normalize_fixes_korean_josa_after_pronunciation_replacement():
    out = normalize_text(
        '새로운 discovery와 fine-mapping을 봅니다.',
        pronunciation={'discovery': '발견', 'fine-mapping': '파인 매핑'},
    )
    assert out == '새로운 발견과 파인 매핑을 봅니다.'


def test_chunk_text_skips_punctuation_only_chunks():
    chunks = chunk_text('첫 문장입니다. . 두 번째 문장입니다.', max_chars=40)
    assert chunks == ['첫 문장입니다. 두 번째 문장입니다.']
    assert all(chunk.strip() != '.' for chunk in chunks)
