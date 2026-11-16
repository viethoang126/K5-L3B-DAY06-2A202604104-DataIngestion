"""Shared data contracts; keep traceability from chunk back to source."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentPage:
    document_id: str
    source: str
    page: int                      # physical PDF page, 1-based
    text: str                      # normalized text of the page
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    chunk_id: str                  # stable: same input -> same ID (no duplicates on re-ingest)
    document_id: str
    source: str
    page: int                      # first physical page covered by the chunk
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # metadata keys used in this lab:
    #   page_end (int), chuong (str), dieu (int, -1 if none), char_start/char_end (int,
    #   offsets in the document stream), crosses_chapter (bool), crosses_page (bool),
    #   strategy (str), content_hash (str)
