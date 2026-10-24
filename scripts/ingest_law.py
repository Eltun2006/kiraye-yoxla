"""Load the scraped Civil Code articles into the database with their embeddings.

Run after scripts/scrape_law.py (and whenever the law JSON or the embedding model changes):
  python scripts/ingest_law.py
Idempotent: existing articles are updated in place. (In Docker, AUTO_INGEST_LAW=true does this on first start.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import SessionLocal, engine, init_db  # noqa: E402
from backend.ingest import ingest_law  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as db:
        total = ingest_law(db)
    print(f"law_articles: {total} sətir ({engine.dialect.name})")


if __name__ == "__main__":
    main()
