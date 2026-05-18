from pathlib import Path
from pptx_voice_video.cache import cache_key

def test_cache_key_changes_with_text(tmp_path: Path):
    v=tmp_path/'v.wav'; v.write_bytes(b'abc')
    a=cache_key(engine='voxcpm', text='hello', voice_paths=[v], options={})
    b=cache_key(engine='voxcpm', text='bye', voice_paths=[v], options={})
    assert a != b
