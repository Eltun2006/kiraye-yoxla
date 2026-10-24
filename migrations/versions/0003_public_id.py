"""Unguessable public ids for analyses (replaces sequential ids in URLs and the API).

Revision ID: 0003
Revises: 0002
"""
import secrets

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("public_id", sa.String(32)))
    conn = op.get_bind()
    for (row_id,) in conn.execute(sa.text("SELECT id FROM analyses")):
        conn.execute(sa.text("UPDATE analyses SET public_id = :p WHERE id = :i"),
                     {"p": secrets.token_urlsafe(16), "i": row_id})
    op.alter_column("analyses", "public_id", nullable=False)
    op.create_index("ix_analyses_public_id", "analyses", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_analyses_public_id", "analyses")
    op.drop_column("analyses", "public_id")
