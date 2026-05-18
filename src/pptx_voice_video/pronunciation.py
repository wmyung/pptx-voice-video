from __future__ import annotations
import re

_JOSA_PAIRS = {
    "은": ("은", "는"), "는": ("은", "는"),
    "이": ("이", "가"), "가": ("이", "가"),
    "을": ("을", "를"), "를": ("을", "를"),
    "과": ("과", "와"), "와": ("과", "와"),
}


def _has_jongseong(ch: str) -> bool:
    code = ord(ch) - 0xAC00
    return 0 <= code <= 11171 and code % 28 != 0


def _adjust_josa(dst: str, josa: str | None) -> str:
    if not josa:
        return dst
    hangul = [ch for ch in dst if "가" <= ch <= "힣"]
    if not hangul or josa not in _JOSA_PAIRS:
        return dst + josa
    with_batchim, without_batchim = _JOSA_PAIRS[josa]
    return dst + (with_batchim if _has_jongseong(hangul[-1]) else without_batchim)


def apply_pronunciation(text: str, dictionary: dict[str, str]) -> str:
    for src, dst in sorted(dictionary.items(), key=lambda kv: len(kv[0]), reverse=True):
        if not src:
            continue
        if src.isascii():
            pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(src)}(?![A-Za-z0-9_])([은는이가을를과와])?", re.IGNORECASE)
            text = pattern.sub(lambda m: _adjust_josa(dst, m.group(1)), text)
        else:
            pattern = re.compile(rf"(?<!\w){re.escape(src)}(?!\w)")
            text = pattern.sub(dst, text)
    return text
