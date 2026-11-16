"""Day 06 pipeline: ingest -> chunk (A, B) -> embed -> Chroma -> retrieve A/B/C -> evaluate.

Run from starter/:
    python -m src.run                 # dev questions only (default; use for choosing a strategy)
    python -m src.run --split test    # run once AFTER the strategy choice is fixed
    python -m src.run --split all

Outputs go to starter/results/. Audit CSVs for manual labels are created only if they
do not exist yet (existing labels are never overwritten).
"""
import argparse
import csv
import hashlib
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_article, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import MIN_CONTENT_CHARS, build_stream, load_pdf
from .models import Chunk
from .store import ChromaStore

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
MANIFEST = ROOT / "data" / "manifest.csv"
QUESTIONS = ROOT / "benchmark" / "questions.jsonl"
RESULTS = STARTER / "results"
CHROMA_DIR = STARTER / "chroma_db"
MIN_CONTENT_PAGES = 30
TOP_K = 3

# Exactly one factor changes per comparison: A->B chunking, B->C metadata filter.
STRATEGIES = {
    "A": {"chunking": "fixed_size", "size": 500, "overlap": 50, "collection": "A", "use_filter": False},
    "B": {"chunking": "by_article", "max_size": 1200, "collection": "B", "use_filter": False},
    "C": {"chunking": "by_article (index B)", "max_size": 1200, "collection": "B", "use_filter": True},
}
# Coherence sample, fixed before looking at any score: midpoint of every 9th content page.
COHERENCE_PAGES = [1, 10, 19, 28, 37, 46, 55, 64, 73, 82]


def pkg_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_corpus():
    with MANIFEST.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    docs, log = [], []
    for row in rows:
        path = ROOT / row["source_path"]
        digest = sha256(path)
        pages = load_pdf(path, row["source_id"], row["source_path"])
        empty = [p.page for p in pages if p.metadata["empty"]]
        log.append({
            "source_id": row["source_id"], "path": row["source_path"], "sha256": digest,
            "sha256_matches_manifest": digest == row.get("sha256"),
            "physical_pages": len(pages), "content_pages": len(pages) - len(empty),
            "empty_or_short_pages": empty, "min_content_chars": MIN_CONTENT_CHARS,
            "content_chars": sum(p.metadata["char_count"] for p in pages if not p.metadata["empty"]),
            "header_lines_removed": sum(len(p.metadata["header_removed"]) for p in pages),
        })
        if digest != row.get("sha256"):
            print(f"WARNING: {path.name} differs from manifest sha256 (source changed?)")
        docs.append(pages)
    total = sum(e["content_pages"] for e in log)
    if total < MIN_CONTENT_PAGES:
        raise SystemExit(f"Only {total} content pages (< {MIN_CONTENT_PAGES})")
    return docs, log


def chunk_stats(chunks: list[Chunk], embedder: MyEmbedder) -> dict:
    lens = [len(c.text) for c in chunks]
    toks = embedder.count_tokens([c.text for c in chunks])
    return {
        "chunks": len(chunks), "total_chars": sum(lens),
        "chars": {"min": min(lens), "median": statistics.median(lens), "mean": round(statistics.mean(lens), 1),
                  "max": max(lens)},
        "tokens": {"total": sum(toks), "median": statistics.median(toks), "max": max(toks)},
        "truncated_over_max_seq_length": sum(t > embedder.max_seq_length for t in toks),
        "crosses_page": sum(bool(c.metadata.get("crosses_page")) for c in chunks),
        "crosses_chapter": sum(bool(c.metadata.get("crosses_chapter")) for c in chunks),
        "with_context_prefix": sum(bool(c.metadata.get("has_context_prefix")) for c in chunks),
    }


def ingest(store: ChromaStore, embedder: MyEmbedder, collection: str, chunks: list[Chunk]) -> dict:
    """Incremental, idempotent ingest: embed only new/changed chunks, delete obsolete ones."""
    t0 = time.perf_counter()
    doc_ids = {c.document_id for c in chunks}
    existing = {}
    for d in doc_ids:
        existing.update(store.existing_hashes(collection, d))
    changed = [c for c in chunks if existing.get(c.chunk_id) != c.metadata["content_hash"]]
    vectors = embedder.embed_documents([c.text for c in changed])
    store.upsert(collection, changed, vectors)
    removed = []
    for d in doc_ids:
        removed += store.delete_obsolete(collection, d, {c.chunk_id for c in chunks if c.document_id == d})
    return {"embedded": len(changed), "deleted_obsolete": len(removed),
            "count_after": store.count(collection), "seconds": round(time.perf_counter() - t0, 2)}


def write_audit_templates(traces: list[dict], streams, chunk_sets: dict[str, list[Chunk]]) -> list[str]:
    created = []

    def create(path: Path, header: list[str], rows: list[list]):
        if path.exists():
            print(f"keep existing {path.name} (labels are never overwritten)")
            return
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        created.append(path.name)

    test = [t for t in traces if t["split"] == "test"]
    if test:
        create(RESULTS / "audit_grounding_test.csv",
               ["strategy", "id", "question", "expected_answer", "top3_chunk_ids", "top3_text",
                "label_0_1_2", "reason"],
               [[t["strategy"], t["id"], t["question"], t["expected_answer"],
                 " | ".join(h["chunk_id"] for h in t["hits"]),
                 "\n---\n".join(f"#{h['rank']} p{h['page']}-{h['page_end']} {h['text']}" for h in t["hits"]),
                 "", ""] for t in test])
        create(RESULTS / "audit_metadata_test.csv",
               ["strategy", "id", "rank", "chunk_id", "source", "page", "page_end", "chuong", "dieu",
                "question_filter", "text_excerpt", "source_ok", "page_ok", "chuong_ok", "notes"],
               [[t["strategy"], t["id"], h["rank"], h["chunk_id"], h["source"], h["page"], h["page_end"],
                 h["chuong"], h["dieu"], json.dumps(t["question_filter"], ensure_ascii=False),
                 h["text"][:300], "", "", "", ""] for t in test for h in t["hits"]])

    rows = []
    stream = streams[0]
    for n, page in enumerate(COHERENCE_PAGES, 1):
        idx = stream.page_numbers.index(page)
        start = stream.page_starts[idx]
        end = stream.page_starts[idx + 1] if idx + 1 < len(stream.page_starts) else len(stream.text)
        offset = (start + end) // 2
        for strategy, chunks in chunk_sets.items():
            c = next(c for c in chunks if c.metadata["char_start"] <= offset < c.metadata["char_end"])
            rows.append([f"pos{n:02d}", page, offset, strategy, c.chunk_id, c.text, "", ""])
    create(RESULTS / "audit_coherence.csv",
           ["position", "page", "char_offset", "strategy", "chunk_id", "chunk_text", "label_0_1_2", "reason"],
           rows)
    return created


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    args = ap.parse_args()
    load_dotenv(STARTER / ".env")                 # optional EMBEDDING_MODEL override
    RESULTS.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 1. corpus
    docs, ingest_log = load_corpus()
    streams = [build_stream(pages) for pages in docs]
    print(f"Corpus: {sum(e['content_pages'] for e in ingest_log)} content pages, "
          f"empty/short pages: {[e['empty_or_short_pages'] for e in ingest_log]}")

    # 2. chunking
    chunks_a = [c for s in streams for c in fixed_size(s, STRATEGIES["A"]["size"], STRATEGIES["A"]["overlap"])]
    chunks_b = [c for s in streams for c in by_article(s, STRATEGIES["B"]["max_size"])]
    chunk_sets = {"A": chunks_a, "B": chunks_b}

    # 3. embed + store (twice: second pass must embed 0 and keep the same count)
    embedder = MyEmbedder()
    store = ChromaStore(CHROMA_DIR, embedder.model_name, embedder.dimensions)
    stats = {}
    old_stats = json.loads((RESULTS / "chunk_stats.json").read_text(encoding="utf-8")) \
        if (RESULTS / "chunk_stats.json").exists() else {}
    for coll, chunks in chunk_sets.items():
        first = ingest(store, embedder, coll, chunks)
        second = ingest(store, embedder, coll, chunks)
        ok = second["embedded"] == 0 and second["count_after"] == first["count_after"] == len(chunks)
        # keep the timing of the last run that embedded every chunk (cold ingest) for the report
        full = {**first, "at": started} if first["embedded"] == len(chunks) \
            else old_stats.get(coll, {}).get("full_ingest")
        stats[coll] = {**chunk_stats(chunks, embedder), "full_ingest": full, "this_run_ingest": first,
                       "reingest_check": second, "no_duplicates": ok}
        print(f"Index {coll}: {len(chunks)} chunks, embedded {first['embedded']} in {first['seconds']}s, "
              f"re-ingest embedded {second['embedded']}, count {second['count_after']} -> no duplicates: {ok}")
        if not ok:
            raise SystemExit(f"Re-ingest check failed for {coll}: {first} / {second}")

    # 4. retrieval
    questions = [json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.split != "all":
        questions = [q for q in questions if q["split"] == args.split]
    qvecs, traces, timing = {}, [], {}
    for strategy, cfg in STRATEGIES.items():
        t0 = time.perf_counter()
        for q in questions:
            if q["id"] not in qvecs:
                qvecs[q["id"]] = embedder.embed_query(q["question"])
            flt = q.get("filter") if cfg["use_filter"] else None
            hits = store.search(cfg["collection"], qvecs[q["id"]], TOP_K, flt)
            traces.append(evaluate_query(q, hits, strategy, flt))
        timing[strategy] = round(time.perf_counter() - t0, 3)

    # 5. outputs
    tag = args.split
    for strategy in STRATEGIES:
        with (RESULTS / f"traces_{strategy}_{tag}.jsonl").open("w", encoding="utf-8") as f:
            for t in traces:
                if t["strategy"] == strategy:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
    summary = summarize(traces)
    write_json(RESULTS / f"summary_{tag}.json", {"started_at": started, "split": tag, "metrics": summary,
                                                 "retrieval_seconds": timing})
    write_json(RESULTS / "chunk_stats.json", stats)
    write_json(RESULTS / "ingest_log.json", ingest_log)
    write_json(RESULTS / "run_config.json", {
        "started_at": started, "split": tag, "strategies": STRATEGIES, "top_k": TOP_K,
        "embedding": embedder.describe(),
        "vector_store": {"name": "chroma", "version": pkg_version("chromadb"), "path": str(CHROMA_DIR.relative_to(ROOT)),
                         "collections": {k: ChromaStore.collection_name(k) for k in chunk_sets},
                         "metric": "cosine", "search": "approximate (HNSW)"},
        "versions": {p: pkg_version(p) for p in ["pymupdf", "chromadb", "sentence-transformers", "torch", "transformers"]},
        "python": platform.python_version(), "platform": platform.platform(),
        "coherence_pages": COHERENCE_PAGES, "cost_usd": 0,
    })
    created = write_audit_templates(traces, streams, chunk_sets)

    print(f"\nRetrieval ({tag}):")
    print(f"{'key':<10}{'Hit@1':>8}{'Hit@3':>8}  filter-compliance  misses")
    for key, m in summary.items():
        fc = m["filter_compliance"] if m["filter_compliance"] == "N/A" else m["filter_compliance"]["text"]
        print(f"{key:<10}{m['hit1']['text']:>8}{m['hit3']['text']:>8}  {fc:<17}  {', '.join(m['misses'])}")
    print(f"\nResults in {RESULTS}" + (f"; new audit templates: {created}" if created else ""))


if __name__ == "__main__":
    main()
