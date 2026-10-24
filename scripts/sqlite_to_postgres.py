"""One-off: copy analyses from the old SQLite file into the database in DATABASE_URL (PostgreSQL).

Usage:  python scripts/sqlite_to_postgres.py [path/to/kiraye.db]
The SQLite file is left untouched as a backup.
"""
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import Analysis, ClauseRow, SessionLocal, init_db  # noqa: E402

src_path = Path(sys.argv[1] if len(sys.argv) > 1 else "kiraye.db")
if not src_path.exists():
    sys.exit(f"{src_path} tapılmadı.")

init_db()
src = create_engine(f"sqlite:///{src_path}")
copied = 0
with Session(src) as s, SessionLocal() as dst:
    for a in s.scalars(select(Analysis).options(selectinload(Analysis.clauses)).order_by(Analysis.id)):
        # New ids are assigned by Postgres; copy every column except the primary/foreign keys.
        new = Analysis(**{c.name: getattr(a, c.name) for c in Analysis.__table__.columns if c.name != "id"})
        new.clauses = [
            ClauseRow(**{c.name: getattr(r, c.name) for c in ClauseRow.__table__.columns if c.name not in ("id", "analysis_id")})
            for r in a.clauses
        ]
        dst.add(new)
        copied += 1
    dst.commit()
print(f"{copied} analiz köçürüldü. {src_path} ehtiyat nüsxə kimi saxlanıldı.")
