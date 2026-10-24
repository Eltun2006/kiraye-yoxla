"""Per-clause law retrieval: hybrid dense (pgvector) + lexical (BM25) ranking, fused with RRF.

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


@dataclass
class LawContext:
    articles: dict[str, LawArticle]                                # id -> article, all candidates
    candidates: dict[int, list[str]] = field(default_factory=dict)  # clause idx -> article ids


def _dense_ranking(db: Session, vec: list[float], arts: list[LawArticle]) -> list[str]:
    if db.bind.dialect.name == "postgresql":
        # `<=>` is pgvector's cosine distance; the database does the nearest-neighbour search.
        rows = db.execute(
            text("SELECT id FROM law_articles ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"),
            {"q": str(vec), "n": DENSE_N},
        )
        return [r[0] for r in rows]
    # SQLite fallback: same ranking in numpy (vectors are normalized, so dot product = cosine).
    sims = np.array([a.embedding for a in arts]) @ np.array(vec)
    return [arts[i].id for i in np.argsort(-sims)[:DENSE_N]]


def build_context(db: Session, clauses: list[Clause]) -> LawContext | None:
    """None when the law table is empty (ingest not run) — the analysis then runs without citations."""
    arts = db.scalars(select(LawArticle).where(LawArticle.embedding.is_not(None))).all()
    if not arts:
        return None
    bm25 = law.BM25([law.passage(a.id, a.title, a.text) for a in arts], stem=law.STEM)
    ids = [a.id for a in arts]
    q_vecs = law.embed_queries([c.text for c in clauses])

    candidates = {}
    for clause, vec in zip(clauses, q_vecs):
        scores = np.array(bm25.scores(clause.text))
        # Articles sharing no word with the clause get no vote (a zero-score "ranking" is just noise).
        lexical = [ids[i] for i in np.argsort(-scores)[:DENSE_N] if scores[i] > 0]
        candidates[clause.idx] = law.rrf(_dense_ranking(db, vec, arts), lexical)[:TOP_K]

    by_id = {a.id: a for a in arts}
    used = {i for ids_ in candidates.values() for i in ids_}
    return LawContext(articles={i: by_id[i] for i in sorted(used, key=int)}, candidates=candidates)
