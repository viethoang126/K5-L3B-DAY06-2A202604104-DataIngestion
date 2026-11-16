"""Validate benchmark/questions.jsonl against the corpus PDF.

Hai chế độ (chạy từ thư mục starter/):

  python scripts/validate_benchmark.py
      Kiểm tra cấu trúc, split, filter và việc evidence_quote có thật trên gold_page.

  python scripts/validate_benchmark.py --find "cụm từ cần tìm"
      Tìm cụm từ trong PDF, in trang và chương để điền gold_page/filter.

Script chỉ đọc và kiểm tra, không sửa file và không chạy retrieval.
Exit code 1 nếu còn lỗi hoặc TODO.
"""
import argparse
import csv
import json
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "starter/data/bo-luat-lao-dong-2019_45-2019-QH14_congbao.pdf"
QUESTIONS = ROOT / "benchmark/questions.jsonl"
PAGES_CSV = ROOT / "data/manifest_pages.csv"
CHAPTERS_CSV = ROOT / "data/manifest_chapters.csv"

SOURCE_ID = "blld-2019"
SPLITS = {"dev", "test"}
TYPES = {"truc_tiep", "dien_dat_lai", "dieu_kien_ngoai_le", "metadata_filter"}
FILTER_KEYS = {"chuong"}
REQUIRED = ["id", "split", "question", "expected_answer", "gold_source_id",
            "gold_page", "evidence_quote", "filter"]


def norm(text: str) -> str:
    """Matching normalization: NFC + collapse whitespace. Keep it identical to evaluation."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def load_pages() -> dict[int, str]:
    return {i: norm(p.get_text()) for i, p in enumerate(pymupdf.open(PDF), start=1)}


def load_page_chapters() -> dict[int, set[str]]:
    with PAGES_CSV.open(encoding="utf-8") as f:
        return {int(r["page"]): set(filter(None, r["chuong"].split(";"))) for r in csv.DictReader(f)}


def find(phrase: str, pages: dict[int, str], page_ch: dict[int, set[str]]) -> None:
    target = norm(phrase)
    hits = [p for p, t in pages.items() if target in t]
    if not hits:
        print("Không tìm thấy trên một trang đơn lẻ (có thể cụm từ vắt qua 2 trang hoặc khác chính tả).")
        return
    for p in hits:
        t = pages[p]
        i = t.index(target)
        ctx = t[max(0, i - 80): i + len(target) + 80]
        print(f"trang {p} | chương {';'.join(sorted(page_ch.get(p, [])))}\n  …{ctx}…\n")


def validate(pages: dict[int, str], page_ch: dict[int, set[str]], questions: Path) -> int:
    with CHAPTERS_CSV.open(encoding="utf-8") as f:
        chapters = {r["chuong"] for r in csv.DictReader(f)}
    errors, todos, warns = [], [], []
    rows = []
    for n, line in enumerate(questions.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            errors.append(f"dòng {n}: JSON lỗi: {e}")

    ids = [q.get("id") for q in rows]
    if len(ids) != len(set(ids)):
        errors.append("id bị trùng")

    for q in rows:
        qid = q.get("id", "?")
        for k in REQUIRED:
            if k not in q:
                errors.append(f"{qid}: thiếu trường {k}")
        if "TODO" in json.dumps(q, ensure_ascii=False):
            todos.append(qid)
            continue
        if q.get("split") not in SPLITS:
            errors.append(f"{qid}: split phải là dev/test")
        if q.get("type") and q["type"] not in TYPES:
            warns.append(f"{qid}: type lạ '{q['type']}'")
        if q.get("gold_source_id") != SOURCE_ID:
            errors.append(f"{qid}: gold_source_id phải là {SOURCE_ID}")

        golds = [(q.get("gold_page"), q.get("evidence_quote"))]
        golds += [(a.get("gold_page"), a.get("evidence_quote")) for a in q.get("alternatives", [])]
        gold_pages_all = set()
        for gp, ev in golds:
            gp = gp if isinstance(gp, list) else [gp]
            if not gp or not all(isinstance(p, int) and p in pages for p in gp):
                errors.append(f"{qid}: gold_page {gp} không hợp lệ (số trang PDF 1–{len(pages)})")
                continue
            gold_pages_all.update(gp)
            ev_n = norm(ev or "")
            if len(ev_n) < 20:
                warns.append(f"{qid}: evidence_quote ngắn (<20 ký tự), dễ khớp nhầm")
            if not any(ev_n in pages[p] for p in gp):
                elsewhere = [p for p, t in pages.items() if ev_n in t]
                hint = f"; thấy ở trang {elsewhere}" if elsewhere else "; không thấy trên trang đơn lẻ nào"
                errors.append(f"{qid}: evidence không nằm trên gold_page {gp}{hint}")
            else:
                others = [p for p, t in pages.items() if ev_n in t and p not in gp]
                if others:
                    warns.append(f"{qid}: evidence cũng xuất hiện ở trang {others}; cân nhắc thêm vào alternatives")
            if ev_n and norm(q.get("expected_answer", "")) == ev_n:
                warns.append(f"{qid}: expected_answer trùng nguyên văn evidence")

        flt = q.get("filter")
        if flt is not None:
            if not isinstance(flt, dict) or not flt:
                errors.append(f"{qid}: filter phải là object hoặc null")
            else:
                for k, v in flt.items():
                    if k not in FILTER_KEYS:
                        errors.append(f"{qid}: filter key '{k}' không được phép ({FILTER_KEYS})")
                    elif v not in chapters:
                        errors.append(f"{qid}: chuong '{v}' không tồn tại")
                    elif not any(v in page_ch.get(p, set()) for p in gold_pages_all):
                        errors.append(f"{qid}: gold_page không thuộc chương {v}; filter sẽ loại mất đáp án")
        if q.get("type") == "metadata_filter" and flt is None:
            errors.append(f"{qid}: type metadata_filter nhưng filter = null")

    done = [q for q in rows if q.get("id") not in todos]
    n_dev = sum(q.get("split") == "dev" for q in rows)
    n_test = sum(q.get("split") == "test" for q in rows)
    n_flt = sum(q.get("filter") is not None for q in rows)
    n_flt_test = sum(q.get("filter") is not None and q.get("split") == "test" for q in rows)
    if len(rows) < 20: errors.append(f"cần ≥20 câu, có {len(rows)}")
    if n_dev < 15: errors.append(f"cần ≥15 dev, có {n_dev}")
    if n_test < 5: errors.append(f"cần ≥5 test, có {n_test}")
    if n_flt < 3: errors.append(f"cần ≥3 câu có filter, có {n_flt}")
    if n_flt_test < 1: errors.append("cần ≥1 câu test có filter")

    print(f"Tổng {len(rows)} câu | dev {n_dev} | test {n_test} | có filter {n_flt} (test {n_flt_test}) | "
          f"đã điền {len(done)} | còn TODO {len(todos)}")
    for w in warns: print("CẢNH BÁO", w)
    for e in errors: print("LỖI", e)
    if todos: print("TODO:", ", ".join(todos))
    ok = not errors and not todos
    print("OK: benchmark hợp lệ." if ok else "Chưa đạt.")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--find", help="tìm cụm từ trong PDF")
    ap.add_argument("--questions", type=Path, default=QUESTIONS, help="đường dẫn file JSONL")
    args = ap.parse_args()
    pages, page_ch = load_pages(), load_page_chapters()
    if args.find:
        find(args.find, pages, page_ch)
        return
    sys.exit(validate(pages, page_ch, args.questions))


if __name__ == "__main__":
    main()
