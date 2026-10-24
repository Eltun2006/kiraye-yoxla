"""Law RAG: pgvector extension, law_articles table, clause citations, invalid-citation counter.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "law_articles",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("chapter", sa.String(120), nullable=False),
        sa.Column("source_url", sa.String(255), nullable=False),
        sa.Column("embedding", Vector(768)),
    )
    # No ANN index (HNSW/IVFFlat): with 25 rows an exact scan is faster and exact.
    op.add_column("clauses", sa.Column("law_refs", sa.JSON, server_default=sa.text("'[]'")))
    op.add_column("analyses", sa.Column("invalid_refs", sa.Integer))


def downgrade() -> None:
    op.drop_column("analyses", "invalid_refs")
    op.drop_column("clauses", "law_refs")
    op.drop_table("law_articles")
