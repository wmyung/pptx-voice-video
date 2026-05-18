from pptx_voice_video.subtitles import fmt_ts

def test_fmt_ts():
    assert fmt_ts(61.234) == '00:01:01,234'
