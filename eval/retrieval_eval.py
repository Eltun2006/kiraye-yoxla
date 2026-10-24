"""Retrieval evaluation: does the right Civil Code article come back for a contract clause?

Compares a lexical baseline (BM25, with and without prefix stemming), dense retrieval (multilingual-e5)
and hybrids (RRF of both), over two chunking strategies (whole articles vs. articles split into points).
Metrics are article-level: hit@k = an expected article is in the top-k; MRR = mean of 1/rank of the first hit.
The production setting (backend/retrieval.py) uses the same BM25/rrf code from backend/law.py.

Usage:  python eval/retrieval_eval.py [-v]     (-v prints the misses)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.law import BM25, STEM, chunk_articles, embed_passages, embed_queries, load_articles, rrf  # noqa: E402

QUERIES = [json.loads(l) for l in (ROOT / "eval" / "retrieval_queries.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
KS = (1, 3, 5)
MODELS = ["intfloat/multilingual-e5-small", "intfloat/multilingual-e5-base"]  # BAAI/bge-m3 (2.2 GB) did not fit on disk


def ranked_articles(scores, chunk_arts: list[str], positive_only: bool = False) -> list[str]:
    """Chunk scores -> unique article ids, best first (optionally only chunks with a non-zero score)."""
    scores = np.asarray(scores)
    return list(dict.fromkeys(chunk_arts[i] for i in np.argsort(-scores) if not positive_only or scores[i] > 0))


def evaluate(name: str, rank_fn) -> dict:
    hits = {k: 0 for k in KS}
    rr, misses = 0.0, []
    for q in QUERIES:
        ranking = rank_fn(q["query"])
        rank = next((i + 1 for i, a in enumerate(ranking) if a in q["expected"]), None)
        for k in KS:
            hits[k] += bool(rank and rank <= k)
        rr += 1 / rank if rank else 0
        if not rank or rank > 3:
            misses.append(f"    rank {rank}: {q['query'][:70]}  (gözlənilən {q['expected']}, top-3 {ranking[:3]})")
    n = len(QUERIES)
    row = {"method": name, **{f"hit@{k}": hits[k] / n for k in KS}, "MRR": round(rr / n, 3)}
    print(f"{name:<44} " + "  ".join(f"hit@{k} {row[f'hit@{k}']:.0%}" for k in KS) + f"  MRR {row['MRR']:.2f}")
    for m in misses if "-v" in sys.argv else []:
        print(m)
    return row


def main() -> None:
    articles = load_articles()
    queries = [q["query"] for q in QUERIES]
    results = []
    for strategy, max_chars in (("bütöv maddə", None), ("bəndlər", 1200)):
        chunks = chunk_articles(articles, max_chars=max_chars)
        arts = [c["article"] for c in chunks]
        passages = [c["passage"] for c in chunks]
        print(f"\n== Chunking: {strategy} ({len(chunks)} chunk) ==")
        bm25, bm25s = BM25(passages), BM25(passages, stem=STEM)
        lex = lambda q: ranked_articles(bm25s.scores(q), arts)  # noqa: E731
        results.append(evaluate(f"BM25 / {strategy}", lambda q: ranked_articles(bm25.scores(q), arts)))
        results.append(evaluate(f"BM25+stem{STEM} / {strategy}", lex))
        for model in MODELS:
            short = model.split("/")[1].replace("multilingual-", "")
            p_vecs = np.array(embed_passages(passages, model))
            q_vecs = dict(zip(queries, np.array(embed_queries(queries, model))))
            dense = lambda q, p=p_vecs, v=q_vecs: ranked_articles(p @ v[q], arts)  # noqa: E731
            results.append(evaluate(f"{short} / {strategy}", dense))
            # as in production (backend/retrieval.py): zero-score BM25 results do not vote
            lex_pos = lambda q: ranked_articles(bm25s.scores(q), arts, positive_only=True)  # noqa: E731
            results.append(evaluate(f"hybrid {short}+BM25s / {strategy}", lambda q, d=dense: rrf(d(q), lex_pos(q))))

    out = ROOT / "eval" / "retrieval_results.json"
    out.write_text(json.dumps({"n_queries": len(QUERIES), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nNəticələr → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
