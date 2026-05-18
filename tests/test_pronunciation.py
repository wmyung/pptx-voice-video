from pptx_voice_video.pronunciation import apply_pronunciation

def test_apply_pronunciation_word_boundary():
    assert apply_pronunciation('AI and AIX', {'AI':'에이아이'}) == '에이아이 and AIX'


def test_apply_pronunciation_ascii_term_with_korean_josa():
    assert apply_pronunciation('GWAS에서 SNP가', {'GWAS': '지워스', 'SNP': '스닙'}) == '지워스에서 스닙이'
