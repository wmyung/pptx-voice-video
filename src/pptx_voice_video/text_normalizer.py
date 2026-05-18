from __future__ import annotations
import re
from .pronunciation import apply_pronunciation

_ABBR = {
    "e.g.": "for example", "i.e.": "that is", "vs.": "versus",
    "Dr.": "Doctor", "Mr.": "Mister", "Ms.": "Miss",
}
_KO_SPACING = [(r"\s+([,.!?])", r"\1"), (r"([가-힣])\s+([,.!?])", r"\1\2")]


def _has_jongseong(ch: str) -> bool:
    code = ord(ch) - 0xAC00
    return 0 <= code <= 11171 and code % 28 != 0


def _fix_korean_josa(text: str) -> str:
    pairs = {
        "은": ("은", "는"), "는": ("은", "는"),
        "이": ("이", "가"), "가": ("이", "가"),
        "을": ("을", "를"), "를": ("을", "를"),
        "과": ("과", "와"), "와": ("과", "와"),
    }

    def repl(match: re.Match[str]) -> str:
        ch, josa = match.group(1), match.group(2)
        with_batchim, without_batchim = pairs[josa]
        return ch + (with_batchim if _has_jongseong(ch) else without_batchim)

    return re.sub(r"([가-힣])([은는이가을를과와])(?=\s|[,.!?;:]|$)", repl, text)

def normalize_text(text: str, *, language: str="ko", pronunciation: dict[str,str] | None=None, strip_stage_directions: bool=True) -> str:
    text = text or ""
    text = text.replace("\u00a0", " ").replace("\r", "\n")
    text = text.replace("“", "").replace("”", "").replace("‘", "").replace("’", "")
    if strip_stage_directions:
        text = re.sub(r"\[[^\]]{1,120}\]|\([^)]{1,120}\)", " ", text)
    lines=[]
    for line in text.splitlines():
        line = re.sub(r"^\s*[-*•·]+\s*", "", line)
        line = re.sub(r"^\s*\d+[.)]\s*", "", line)
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if re.fullmatch(r"[.。·,;:!?\-–—\s]+", line):
            continue
        lines.append(line)
    text = " ".join(lines)
    for k,v in _ABBR.items():
        text = text.replace(k,v)
    text = apply_pronunciation(text, pronunciation or {})
    text = re.sub(r"\s+", " ", text).strip()
    if language.lower().startswith("ko"):
        for a,b in _KO_SPACING:
            text = re.sub(a,b,text)
    text = re.sub(r"\s*([,.;:!?])\s*", r"\1 ", text)
    text = re.sub(r"(?:\.\s*){2,}", ". ", text)
    text = re.sub(r"\s+\.\s*", ". ", text)
    return re.sub(r"\s+", " ", text).strip()

def chunk_text(text: str, max_chars: int=260) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？다요죠니다까])\s+", text)
    chunks=[]
    cur=""
    for part in parts:
        part=part.strip()
        if not part or re.fullmatch(r"[.。·,;:!?\-–—\s]+", part):
            continue
        if len(part) > max_chars:
            if cur:
                chunks.append(cur)
                cur=""
            for i in range(0, len(part), max_chars):
                chunks.append(part[i:i+max_chars].strip())
        elif len(cur)+len(part)+1 <= max_chars:
            cur = (cur+" "+part).strip()
        else:
            if cur:
                chunks.append(cur)
            cur=part
    if cur:
        chunks.append(cur)
    return chunks
