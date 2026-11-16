"""Read and normalize source data (PDF -> pages) and build a document stream with structure."""
import bisect
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .models import DocumentPage

MIN_CONTENT_CHARS = 200            # same rule as data/MANIFEST.md
_HEADER_RE = re.compile(r"^CÔNG BÁO/Số [^\n]*$")
_PAGE_NO_RE = re.compile(r"^\d{1,3}$")
CHAPTER_RE = re.compile(r"^Chương ([IVXLC]+)$", re.M)
ARTICLE_RE = re.compile(r"^Điều (\d+)\.", re.M)


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace without discarding useful structure.

    - Unicode NFC (Vietnamese diacritics as precomposed characters)
    - remove soft hyphens / zero-width chars, unify non-breaking spaces
    - collapse runs of spaces inside a line, strip line ends
    - keep line breaks (needed to detect "Chương"/"Điều" headings), max one blank line
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("­", "").replace("​", "").replace("﻿", "")
    text = text.replace(" ", " ").replace("\t", " ")
    lines = [re.sub(r" {2,}", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_page_header(text: str) -> tuple[str, list[str]]:
    """Remove the Công báo running header and printed page number at the top of a page.

    Only the first 3 non-empty lines are inspected, so content is never removed.
    Returns (text, removed_lines) so the removal is logged, not silent.
    """
    lines = text.split("\n")
    removed, kept, inspected = [], [], 0
    for line in lines:
        if inspected < 3 and line.strip():
            inspected += 1
            if _HEADER_RE.match(line) or _PAGE_NO_RE.match(line):
                removed.append(line)
                continue
        kept.append(line)
    return "\n".join(kept).strip(), removed


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page; keep its page number and source.

    Pages with < MIN_CONTENT_CHARS characters are kept but flagged (metadata['empty']=True)
    so they can be reported; they produce no chunks. OCR is not needed for this corpus.
    """
    if not path.exists():
        raise FileNotFoundError(f"Corpus file not found: {path}")
    pages: list[DocumentPage] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = normalize_text(page.get_text())
            text, removed = strip_page_header(text)
            pages.append(DocumentPage(
                document_id=document_id, source=source, page=i, text=text,
                metadata={"char_count": len(text), "empty": len(text) < MIN_CONTENT_CHARS,
                          "header_removed": removed},
            ))
    return pages


@dataclass
class DocStream:
    """All content pages of one document joined into one string, with structure indexes.

    Lets chunkers work on character offsets while still mapping every chunk back to
    physical pages, chapter (Chương) and article (Điều).
    """
    document_id: str
    source: str
    text: str
    page_starts: list[int]          # offset where each page starts in `text`
    page_numbers: list[int]         # physical page number for each entry of page_starts
    chapter_pos: list[int]          # offsets of "Chương X" headings
    chapter_ids: list[str]
    article_pos: list[int]          # offsets of "Điều N." headings
    article_ids: list[int]

    def page_at(self, offset: int) -> int:
        return self.page_numbers[max(0, bisect.bisect_right(self.page_starts, offset) - 1)]

    def chapter_at(self, offset: int) -> str:
        i = bisect.bisect_right(self.chapter_pos, offset) - 1
        return self.chapter_ids[i] if i >= 0 else self.chapter_ids[0]

    def article_at(self, offset: int) -> int:
        i = bisect.bisect_right(self.article_pos, offset) - 1
        return self.article_ids[i] if i >= 0 else -1

    def span_metadata(self, start: int, end: int) -> dict:
        """Metadata for text[start:end]. Chapter = nearest heading at or before `start`."""
        last = max(start, end - 1)
        return {
            "page": self.page_at(start), "page_end": self.page_at(last),
            "chuong": self.chapter_at(start), "dieu": self.article_at(start),
            "char_start": start, "char_end": end,
            "crosses_page": self.page_at(start) != self.page_at(last),
            "crosses_chapter": self.chapter_at(start) != self.chapter_at(last),
        }


def build_stream(pages: list[DocumentPage]) -> DocStream:
    content = [p for p in pages if not p.metadata.get("empty")]
    if not content:
        raise ValueError("No content pages")
    parts, starts, numbers, pos = [], [], [], 0
    for p in content:
        starts.append(pos)
        numbers.append(p.page)
        parts.append(p.text)
        pos += len(p.text) + 1                      # +1 for the "\n" separator
    text = "\n".join(parts)
    chapters = [(m.start(), m.group(1)) for m in CHAPTER_RE.finditer(text)]
    articles = [(m.start(), int(m.group(1))) for m in ARTICLE_RE.finditer(text)]
    if not chapters:
        raise ValueError("No 'Chương' headings found; chapter metadata cannot be built")
    return DocStream(
        document_id=content[0].document_id, source=content[0].source, text=text,
        page_starts=starts, page_numbers=numbers,
        chapter_pos=[c[0] for c in chapters], chapter_ids=[c[1] for c in chapters],
        article_pos=[a[0] for a in articles], article_ids=[a[1] for a in articles],
    )
