"""Per-clause law retrieval: dense (pgvector) ranking, fused with lexical (BM25) via RRF for weaker models.

The result is a LawContext: the candidate article ids for every clause, plus the texts of all
candidates. The LLM may only cite from a clause's own candidates — analyzer.py enforces this.
"""
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import law
from .db import LawArticle
from .parsing import Clause

TOP_K = 5      # candidates per clause shown to the LLM (hit@5 = 90% in eval/retrieval_results.json)
DENSE_N = 10   # how many nearest neighbours each retriever contributes to the fusion
# Models strong enough alone: in eval/retrieval_results.json gemini-embedding-001 reaches hit@5 100% / MRR 0.90,
# and fusing BM25 in makes it worse (95% / 0.82). The weaker local e5 needs the hybrid (70% alone → 90% fused).
DENSE_ONLY = {"gemini-embedding-001"}


@dataclass
class LawContext:
    articles: dict[str, LawArticle]                                # id -> article, all candidates
    candidates: dict[int, list[str]] = field(default_factory=dict)  # clause idx -> article ids
    mode: str = ""      # "dense" | "hybrid" | "bm25" (embedding failed)
    corpus: int = 0     # articles searched


def _dense_ranking(db: Session, vec: list[float], arts: list[LawArticle]) -> list[str]:
    if db.bind.dialect.name == "postgresql":
        # `<=>` is pgvector's cosine distance; the database does the nearest-neighbour search.
        rows = db.execute(
            text("SELECT id FROM law_articles WHERE embed_model = :m "
                 "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"),
            {"q": str(vec), "n": DENSE_N, "m": law.current_model()},
        )
        return [r[0] for r in rows]
    # SQLite fallback: same ranking in numpy (vectors are normalized, so dot product = cosine).
    sims = np.array([a.embedding for a in arts]) @ np.array(vec)
    return [arts[i].id for i in np.argsort(-sims)[:DENSE_N]]


def build_context(db: Session, clauses: list[Clause]) -> LawContext | None:
    """None when the law table is empty (ingest not run) — the analysis then runs without citations."""
    arts = db.scalars(select(LawArticle).where(LawArticle.embed_model == law.current_model())).all()
    if not arts:
        return None  # empty, or embedded with another model: re-run scripts/ingest_law.py
    bm25 = law.BM25([law.passage(a.id, a.title, a.text) for a in arts], stem=law.STEM)
    ids = [a.id for a in arts]
    model = law.current_model()
    try:
        q_vecs = law.embed_queries([c.text for c in clauses])
    except Exception as e:  # API down / quota: lexical search alone still finds the right article 85% of the time
        print(f"[retrieval] query embedding failed, BM25 only: {e!r}")
        q_vecs = [None] * len(clauses)

    candidates = {}
    for clause, vec in zip(clauses, q_vecs):
        scores = np.array(bm25.scores(clause.text))
        # Articles sharing no word with the clause get no vote (a zero-score "ranking" is just noise).
        lexical = [ids[i] for i in np.argsort(-scores)[:DENSE_N] if scores[i] > 0]
        if vec is None:
            mode, ranking = "bm25", lexical
        elif model in DENSE_ONLY:
            mode, ranking = "dense", _dense_ranking(db, vec, arts)
        else:
            mode, ranking = "hybrid", law.rrf(_dense_ranking(db, vec, arts), lexical)
        candidates[clause.idx] = ranking[:TOP_K]

    by_id = {a.id: a for a in arts}
    used = {i for ids_ in candidates.values() for i in ids_}
    return LawContext(articles={i: by_id[i] for i in sorted(used, key=int)}, candidates=candidates,
                      mode=mode if clauses else "", corpus=len(arts))
