from pathlib import Path

import pytest

import app


def test_safe_filename_strips_path_and_bad_chars():
    assert app.safe_filename("../../lecture?.mp4") == "lecture_.mp4"
    assert app.safe_filename("   ...   ") == "wormhole-download"
    assert app.safe_filename("강의.mp4") == "_.mp4"


def test_validate_wormhole_code():
    assert app.validate_wormhole_code("7-example-code") == "7-example-code"
    with pytest.raises(ValueError):
        app.validate_wormhole_code("; rm -rf /")
    with pytest.raises(ValueError):
        app.validate_wormhole_code("abc")


def test_resolve_allowed_file_allows_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    f = root / "video.mp4"
    f.write_bytes(b"x")
    assert app.resolve_allowed_file(str(f), (root,)) == f.resolve()


def test_resolve_allowed_file_blocks_outside_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")
    with pytest.raises(PermissionError):
        app.resolve_allowed_file(str(outside), (root,))


def test_register_download_returns_token(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("ok")
    token = app.register_download(f)
    assert token in app.TOKENS
    assert app.TOKENS[token].path == f.resolve()
