import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings
from .law import EMBED_DIM

ROOT = Path(__file__).resolve().parents[1]

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Embedding(TypeDecorator):
    """pgvector `vector(768)` on PostgreSQL; a JSON list on SQLite (tests / no-Docker fallback)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(EMBED_DIM))
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # What URLs and the API use. Unguessable (128 random bits): knowing the link is what grants access,
    # so one user cannot enumerate another's contracts by trying /analyses/1, /analyses/2, ...
    public_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, default=lambda: secrets.token_urlsafe(16)
    )
    filename: Mapped[str] = mapped_column(String(255))
    # queued -> parsing -> analyzing -> done | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    preamble: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(64))
    cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # citations the LLM made outside the retrieved candidates (dropped / flagged) — should stay 0
    invalid_refs: Mapped[int | None] = mapped_column(Integer)
    trace: Mapped[dict | None] = mapped_column(JSON)  # per-stage timings, tokens, retrieval mode (UI: "Necə işləyir")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    clauses: Mapped[list["ClauseRow"]] = relationship(
        back_populates="analysis", order_by="ClauseRow.idx", cascade="all, delete-orphan"
    )


class ClauseRow(Base):
    __tablename__ = "clauses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    risk: Mapped[str | None] = mapped_column(String(10))
    category: Mapped[str | None] = mapped_column(String(30))
    explanation: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(10), default="pending")
    user_text: Mapped[str | None] = mapped_column(Text)
    law_refs: Mapped[list[str] | None] = mapped_column(JSON, default=list)  # validated article ids, e.g. ["688"]
    law_candidates: Mapped[list[str] | None] = mapped_column(JSON)  # what retrieval offered the LLM for this clause

    analysis: Mapped[Analysis] = relationship(back_populates="clauses")


class LawArticle(Base):
    """One article of the Civil Code rent chapter, with its embedding (filled by scripts/ingest_law.py)."""

    __tablename__ = "law_articles"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # article number: "688"
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    chapter: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(255))
    embedding = mapped_column(Embedding)
    embed_model: Mapped[str | None] = mapped_column(String(80))  # vectors of different models don't compare


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def init_db() -> None:
    """SQLite (tests, quick local run): create tables directly. PostgreSQL: apply Alembic migrations."""
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
        return
    from alembic import command

    cfg = _alembic_config()
    tables = inspect(engine).get_table_names()
    if "analyses" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "0001")  # database created by create_all before migrations existed
    command.upgrade(cfg, "head")
