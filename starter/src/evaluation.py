"""Evaluate retrieved evidence automatically and keep full per-query traces.

Automatic metric only: a hit = chunk covers a gold page AND contains the whole
evidence_quote (after NFC + whitespace normalization; same rule as
scripts/validate_benchmark.py). Alternatives in question['alternatives'] are accepted.
Chunk coherence and grounding are NOT inferred here; they are labelled manually
from the audit CSVs.
"""
import unicodedata
from collections import defaultdict
from typing import Any


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def _gold_list(question: dict[str, Any]) -> list[tuple[set[int], str]]:
    golds = [(question["gold_page"], question["evidence_quote"])]
    golds += [(a["gold_page"], a["evidence_quote"]) for a in question.get("alternatives", [])]
    out = []
    for pages, quote in golds:
        pages = pages if isinstance(pages, list) else [pages]
        out.append((set(int(p) for p in pages), norm(quote)))
    return out


def _covers(meta: dict[str, Any], pages: set[int]) -> bool:
    start, end = int(meta["page"]), int(meta.get("page_end", meta["page"]))
    return any(start <= p <= end for p in pages)


def is_hit(question: dict[str, Any], hit: dict[str, Any]) -> bool:
    if hit["metadata"].get("document_id") != question["gold_source_id"]:
        return False
    text = norm(hit["text"])
    return any(_covers(hit["metadata"], pages) and quote in text
               for pages, quote in _gold_list(question))


def _partial_evidence(question: dict[str, Any], hits: list[dict[str, Any]]) -> bool:
    """Heuristic flag: first or last 40 chars of the evidence appear in some top-k chunk,
    but no chunk contains the full evidence -> evidence probably split across chunks."""
    quote = norm(question["evidence_quote"])
    head, tail = quote[:40], quote[-40:]
    return any(head in norm(h["text"]) or tail in norm(h["text"]) for h in hits)


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]], strategy: str,
                   filter_applied: dict[str, Any] | None) -> dict[str, Any]:
    flags = [is_hit(question, h) for h in hits[:3]]
    hit3 = any(flags)
    flt = question.get("filter")
    compliant = None
    if flt:                                   # measured for every strategy, applied only in C
        compliant = all(all(h["metadata"].get(k) == v for k, v in flt.items()) for h in hits[:3])
    return {
        "strategy": strategy, "id": question["id"], "split": question["split"],
        "type": question.get("type"), "question": question["question"],
        "expected_answer": question["expected_answer"], "gold_page": question["gold_page"],
        "dieu": question.get("dieu"), "evidence_quote": question["evidence_quote"],
        "question_filter": flt, "filter_applied": filter_applied,
        "hit_flags": flags, "hit1": bool(flags and flags[0]), "hit3": hit3,
        "first_hit_rank": flags.index(True) + 1 if hit3 else None,
        "evidence_split_suspected": (not hit3) and _partial_evidence(question, hits[:3]),
        "top3_filter_compliant": compliant,
        "hits": [{"rank": h["rank"], "chunk_id": h["chunk_id"], "score": h["score"],
                  "page": h["metadata"].get("page"), "page_end": h["metadata"].get("page_end"),
                  "chuong": h["metadata"].get("chuong"), "dieu": h["metadata"].get("dieu"),
                  "source": h["metadata"].get("source"), "text": h["text"]} for h in hits[:3]],
    }


def _frac(n: int, d: int) -> dict[str, Any]:
    return {"n": n, "N": d, "text": f"{n}/{d}", "pct": round(100 * n / d, 1) if d else None}


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 / Evidence Hit@3 (n/N) and filter compliance by strategy and split."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"])].append(t)
    out: dict[str, Any] = {}
    for (strategy, split), ts in sorted(groups.items()):
        with_filter = [t for t in ts if t["question_filter"]]
        out[f"{strategy}/{split}"] = {
            "hit1": _frac(sum(t["hit1"] for t in ts), len(ts)),
            "hit3": _frac(sum(t["hit3"] for t in ts), len(ts)),
            "filter_compliance": (_frac(sum(bool(t["top3_filter_compliant"]) for t in with_filter),
                                        len(with_filter)) if with_filter else "N/A"),
            "evidence_split_suspected": [t["id"] for t in ts if t["evidence_split_suspected"]],
            "misses": [t["id"] for t in ts if not t["hit3"]],
        }
    return out
