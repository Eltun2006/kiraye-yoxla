"""Pipeline trace for the "Necə işləyir" panel: per-stage timings/tokens and the retrieval candidates per clause.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("trace", sa.JSON()))
    op.add_column("clauses", sa.Column("law_candidates", sa.JSON()))


def downgrade() -> None:
    op.drop_column("clauses", "law_candidates")
    op.drop_column("analyses", "trace")
