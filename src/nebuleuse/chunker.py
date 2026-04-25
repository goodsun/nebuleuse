"""見出し境界を尊重した素朴なチャンク分割。"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 512
OVERLAP = 50
HEADING_RE = re.compile(r"^(#{1,6})\s+.+$", re.MULTILINE)


@dataclass
class Chunk:
    content: str
    char_start: int
    char_end: int


def chunk_text(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[Chunk]:
    """まず見出しでセクション分割し、長いセクションはオーバーラップ付きで再分割する。"""
    if not text.strip():
        return []

    cuts = [m.start() for m in HEADING_RE.finditer(text)]
    if not cuts or cuts[0] != 0:
        cuts = [0] + cuts
    cuts.append(len(text))

    chunks: list[Chunk] = []
    for i in range(len(cuts) - 1):
        start, end = cuts[i], cuts[i + 1]
        section = text[start:end]
        if not section.strip():
            continue
        if len(section) <= max_chars:
            chunks.append(Chunk(section.strip(), start, end))
            continue
        # 長いセクションは max_chars 単位 + overlap で分割
        cursor = start
        while cursor < end:
            piece_end = min(cursor + max_chars, end)
            piece = text[cursor:piece_end]
            if piece.strip():
                chunks.append(Chunk(piece.strip(), cursor, piece_end))
            if piece_end >= end:
                break
            cursor = piece_end - overlap
    return chunks
