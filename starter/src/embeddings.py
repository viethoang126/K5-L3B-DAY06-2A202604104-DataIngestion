"""Real embedding provider: a local Sentence Transformers model (no API key, no cost).

Default: intfloat/multilingual-e5-small (384 dims, max 512 tokens, multilingual incl.
Vietnamese). E5 models expect the prefixes "query: " and "passage: "; they are applied
automatically when the model name contains "e5". There is no fallback to mock vectors:
if the model cannot be loaded, an exception is raised.
"""
import os
from typing import Protocol

DEFAULT_MODEL = "intfloat/multilingual-e5-small"


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Sentence Transformers adapter. Vectors are L2-normalized (cosine-ready)."""

    def __init__(self, model_name: str | None = None, batch_size: int = 32, device: str = "cpu") -> None:
        from sentence_transformers import SentenceTransformer  # import here: heavy dependency

        self.model_name = model_name or os.getenv("EMBEDDING_MODEL") or DEFAULT_MODEL
        self.batch_size = batch_size
        self.model = SentenceTransformer(self.model_name, device=device)
        get_dim = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        self.dimensions = int(get_dim())
        self.max_seq_length = int(self.model.max_seq_length)
        use_e5 = "e5" in self.model_name.lower()
        self.query_prefix = "query: " if use_e5 else ""
        self.doc_prefix = "passage: " if use_e5 else ""

    def count_tokens(self, texts: list[str]) -> list[int]:
        """Token length incl. prefix and special tokens; used to report truncation."""
        tok = self.model.tokenizer
        return [len(tok(self.doc_prefix + t, add_special_tokens=True)["input_ids"]) for t in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self.model.encode([self.doc_prefix + t for t in texts], batch_size=self.batch_size,
                                 normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()

    def embed_query(self, question: str) -> list[float]:
        vec = self.model.encode(self.query_prefix + question, normalize_embeddings=True,
                                show_progress_bar=False)
        return vec.tolist()

    def describe(self) -> dict:
        return {"provider": "local sentence-transformers", "model": self.model_name,
                "dimensions": self.dimensions, "max_seq_length": self.max_seq_length,
                "query_prefix": self.query_prefix, "document_prefix": self.doc_prefix,
                "normalized": True, "cost_usd": 0}
