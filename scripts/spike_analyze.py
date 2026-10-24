"""Day-1 spike: does Claude analyse an Azerbaijani rental contract well?

Usage:  python scripts/spike_analyze.py data/samples/kiraye_synthetic_01.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analyzer import AnalysisError, analyze_clauses  # noqa: E402
from backend.db import SessionLocal  # noqa: E402
from backend.parsing import extract_text, split_clauses  # noqa: E402
from backend.retrieval import build_context  # noqa: E402

ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def main(path: str) -> None:
    p = Path(path)
    text = extract_text(p.name, p.read_bytes())
    _, clauses = split_clauses(text)
    print(f"{len(clauses)} bənd tapıldı. Analiz edilir...\n")

    with SessionLocal() as db:
        ctx = build_context(db, clauses)  # None if the law table is empty (run scripts/ingest_law.py)
    print("Qanun maddələri: " + (f"{len(ctx.articles)} namizəd" if ctx else "yoxdur") + "\n")

    try:
        analysis, metrics = analyze_clauses(clauses, ctx)
    except AnalysisError as e:
        sys.exit(f"XƏTA: {e}")

    by_idx = {c.idx: c for c in clauses}
    for a in sorted(analysis.assessments, key=lambda a: a.clause_index):
        print(f"{ICON[a.risk]} [{a.clause_index}] ({a.category}) {by_idx[a.clause_index].text[:90]}")
        print(f"    → {a.explanation}")
        if a.law_refs:
            print(f"    § Maddə {', '.join(a.law_refs)}   (namizədlər: {', '.join(ctx.candidates[a.clause_index])})")
        if a.suggestion:
            print(f"    ✎ {a.suggestion}")
    print(f"\nXülasə: {analysis.summary}")
    print(f"Metrikalar: {metrics}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/samples/kiraye_synthetic_01.txt")
