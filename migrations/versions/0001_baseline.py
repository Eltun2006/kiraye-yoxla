"""Baseline: analyses + clauses (the schema from week 2, created before migrations existed).

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("preamble", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("model", sa.String(64)),
        sa.Column("cost_usd", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "clauses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer, sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("risk", sa.String(10)),
        sa.Column("category", sa.String(30)),
        sa.Column("explanation", sa.Text),
        sa.Column("suggestion", sa.Text),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("user_text", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("clauses")
    op.drop_table("analyses")
