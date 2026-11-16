"""Fixed-size (strategy A) and structure-aware by-article (strategy B) chunking.

Both work on a DocStream so every chunk keeps: document_id, source, page/page_end,
chuong, dieu and character offsets back into the source.
"""
import hashlib
import re

from .ingestion import DocStream
from .models import Chunk

_CLAUSE_RE = re.compile(r"^\d+\. ", re.M)          # "1. ", "2. " ... = khoản
_SECTION_HEAD_RE = re.compile(r"^(Chương [IVXLC]+|Mục \d+)$", re.M)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _make_chunk(stream: DocStream, chunk_id: str, start: int, end: int, strategy: str,
                prefix: str = "", **overrides) -> Chunk:
    body = stream.text[start:end].strip()
    text = f"{prefix}{body}" if prefix else body
    meta = stream.span_metadata(start, end)
    meta.update(overrides)
    meta.update(strategy=strategy, content_hash=_hash(text), has_context_prefix=bool(prefix))
    return Chunk(chunk_id=chunk_id, document_id=stream.document_id, source=stream.source,
                 page=meta["page"], text=text, metadata=meta)


def fixed_size(stream: DocStream, size: int, overlap: int) -> list[Chunk]:
    """Strategy A: overlapping character windows inside each page.

    Windows never cross a page boundary, so `page` is exact. The window end is moved back
    to the last whitespace (if one exists in the last 20% of the window) so words are not
    cut in half; this is the only deviation from a pure character split.
    """
    if not 0 <= overlap < size:
        raise ValueError("Require 0 <= overlap < size")
    chunks: list[Chunk] = []
    bounds = stream.page_starts + [len(stream.text) + 1]
    for p_idx, page_no in enumerate(stream.page_numbers):
        p_start, p_end = bounds[p_idx], bounds[p_idx + 1] - 1
        start, k = p_start, 0
        while start < p_end:
            end = min(start + size, p_end)
            if end < p_end:
                cut = stream.text.rfind(" ", start + int(size * 0.8), end)
                cut = max(cut, stream.text.rfind("\n", start + int(size * 0.8), end))
                if cut > start:
                    end = cut
            if stream.text[start:end].strip():
                cid = f"{stream.document_id}:A:p{page_no:03d}:c{k:02d}"
                chunks.append(_make_chunk(stream, cid, start, end, "A"))
                k += 1
            if end >= p_end:
                break
            start = max(end - overlap, start + 1)
    return chunks


def _split_long(text_start: int, text_end: int, stream: DocStream, max_size: int) -> list[tuple[int, int]]:
    """Split [text_start, text_end) into pieces <= max_size, preferring clause (khoản)
    boundaries, then line breaks, then spaces."""
    pieces, start = [], text_start
    while text_end - start > max_size:
        window = stream.text[start:start + max_size]
        cut = -1
        clause_starts = [m.start() for m in _CLAUSE_RE.finditer(window) if m.start() > max_size * 0.3]
        if clause_starts:
            cut = clause_starts[-1]
        if cut <= 0:
            cut = window.rfind("\n", int(max_size * 0.5))
        if cut <= 0:
            cut = window.rfind(" ", int(max_size * 0.5))
        if cut <= 0:
            cut = max_size
        pieces.append((start, start + cut))
        start += cut
    pieces.append((start, text_end))
    return pieces


def by_article(stream: DocStream, max_size: int) -> list[Chunk]:
    """Strategy B: one chunk per article (Điều), split by clause when > max_size.

    - Text before an article heading (chapter/section titles, preamble) is attached to
      the following article, so a chunk starting a chapter carries the chapter title.
    - Continuation pieces of a long article get a short context prefix
      "[Chương X – Điều N. <title>] " so they remain understandable on their own.
      The prefix is metadata-derived text, flagged in metadata['has_context_prefix'].
    - Chunks may span two pages; metadata keeps page (start) and page_end.
    """
    heads = stream.article_pos
    if not heads:
        raise ValueError("No 'Điều' headings found; cannot chunk by article")
    # Region of article i = [region_start[i], region_start[i+1]). region_start[i] moves back
    # to the first Chương/Mục heading line between article i-1 and article i, if any.
    region_start = [0]                                    # preamble joins Điều 1
    for i in range(1, len(heads)):
        seg = stream.text[heads[i - 1]:heads[i]]
        m = _SECTION_HEAD_RE.search(seg)
        region_start.append(heads[i - 1] + m.start() if m else heads[i])
    region_end = region_start[1:] + [len(stream.text)]

    chunks: list[Chunk] = []
    for a_idx, (a_start, a_end) in enumerate(zip(region_start, region_end)):
        dieu = stream.article_ids[a_idx]
        head_pos = heads[a_idx]
        title_line = stream.text[head_pos:stream.text.find("\n", head_pos)].strip()
        pieces = _split_long(a_start, a_end, stream, max_size)
        for k, (s, e) in enumerate(pieces):
            prefix = "" if k == 0 else f"[Chương {stream.chapter_at(head_pos)} – {title_line}] "
            cid = f"{stream.document_id}:B:d{dieu:03d}:s{k:02d}"
            chunks.append(_make_chunk(stream, cid, s, e, "B", prefix=prefix,
                                      dieu=dieu, chuong=stream.chapter_at(head_pos)))
    return chunks
