"""Store and search vectors with Chroma (persistent on disk, cosine, metadata filter).

One collection per chunking strategy (A, B). Strategy C reuses collection B and only adds
a metadata filter, so B and C differ in exactly one factor.
Chroma uses an HNSW index: search is approximate (ANN), not exact.
"""
from pathlib import Path
from typing import Any

import chromadb

from .models import Chunk

ALLOWED_FILTERS = {"chuong", "document_id", "dieu"}   # whitelist of filterable metadata


class ChromaStore:
    def __init__(self, persist_dir: Path, model_name: str, dimensions: int) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.model_name = model_name
        self.dimensions = dimensions

    @staticmethod
    def collection_name(strategy: str) -> str:
        return f"day06_blld_{strategy}"

    def collection(self, strategy: str):
        """Open/create the collection; refuse to mix vectors from another model/dimension."""
        col = self.client.get_or_create_collection(
            name=self.collection_name(strategy),
            metadata={"hnsw:space": "cosine", "embedding_model": self.model_name,
                      "dimensions": self.dimensions},
        )
        meta = col.metadata or {}
        if meta.get("embedding_model") != self.model_name or int(meta.get("dimensions", -1)) != self.dimensions:
            raise RuntimeError(
                f"Collection {col.name} was built with {meta.get('embedding_model')} "
                f"({meta.get('dimensions')} dims), current model is {self.model_name} "
                f"({self.dimensions} dims). Delete {self.persist_dir} or use the same model.")
        if meta.get("hnsw:space") != "cosine":
            raise RuntimeError(f"Collection {col.name} does not use cosine distance")
        return col

    def existing_hashes(self, strategy: str, document_id: str) -> dict[str, str]:
        """chunk_id -> content_hash currently stored for a document (for incremental re-ingest)."""
        got = self.collection(strategy).get(where={"document_id": document_id}, include=["metadatas"])
        return {i: (m or {}).get("content_hash", "") for i, m in zip(got["ids"], got["metadatas"])}

    def count(self, strategy: str) -> int:
        return self.collection(strategy).count()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Write chunks with stable IDs (upsert = no duplicates on re-ingest)."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if not chunks:
            return
        bad = [c.chunk_id for c, v in zip(chunks, vectors) if len(v) != self.dimensions]
        if bad:
            raise ValueError(f"Vector dimension != {self.dimensions} for {bad[:3]}")
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate chunk IDs in one upsert")
        metas = []
        for c in chunks:
            m = {"document_id": c.document_id, "source": c.source, "page": c.page}
            m.update(c.metadata)
            metas.append({k: v for k, v in m.items() if isinstance(v, (str, int, float, bool))})
        col = self.collection(strategy)
        for i in range(0, len(ids), 500):                    # keep batches small
            col.upsert(ids=ids[i:i + 500], embeddings=vectors[i:i + 500],
                       documents=[c.text for c in chunks[i:i + 500]], metadatas=metas[i:i + 500])

    def delete_obsolete(self, strategy: str, document_id: str, keep_ids: set[str]) -> list[str]:
        """Remove chunks of a document that no longer exist after re-chunking a changed source."""
        stale = [i for i in self.existing_hashes(strategy, document_id) if i not in keep_ids]
        if stale:
            self.collection(strategy).delete(ids=stale)
        return stale

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Rank by cosine distance; optional metadata filter (whitelisted keys only).

        Returns rank, chunk ID, text, score (= 1 - cosine distance) and metadata.
        """
        if len(query_vector) != self.dimensions:
            raise ValueError("Query vector dimension mismatch")
        where = None
        if filters:
            unknown = set(filters) - ALLOWED_FILTERS
            if unknown:
                raise ValueError(f"Filter keys not allowed: {unknown}")
            clauses = [{k: {"$eq": v}} for k, v in filters.items()]
            where = clauses[0] if len(clauses) == 1 else {"$and": clauses}
        res = self.collection(strategy).query(
            query_embeddings=[query_vector], n_results=top_k, where=where,
            include=["documents", "metadatas", "distances"])
        hits = []
        for rank, (cid, doc, meta, dist) in enumerate(zip(res["ids"][0], res["documents"][0],
                                                          res["metadatas"][0], res["distances"][0]), 1):
            hits.append({"rank": rank, "chunk_id": cid, "score": round(1 - float(dist), 6),
                         "distance": round(float(dist), 6), "text": doc, "metadata": meta})
        return hits
