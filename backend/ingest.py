"""Load the Civil Code articles (data/law/*.json) into the database with their embeddings."""
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import law
from .db import LawArticle


def ingest_law(db: Session) -> int:
    """Idempotent: existing articles are updated in place. Returns the number of articles in the table."""
    articles = law.load_articles()
    started = time.perf_counter()
    vecs = law.embed_passages([law.passage(a["article"], a["title"], a["text"]) for a in articles])
    print(f"[law] {len(articles)} articles embedded ({law.EMBED_MODEL}, {time.perf_counter() - started:.1f}s)")
    for a, vec in zip(articles, vecs):
        db.merge(LawArticle(
            id=a["article"], title=a["title"], text=a["text"],
            chapter=a["chapter"], source_url=a["source_url"], embedding=vec,
        ))
    db.commit()
    return db.query(LawArticle).count()


def has_law(db: Session) -> bool:
    return db.scalar(select(LawArticle.id).limit(1)) is not None
