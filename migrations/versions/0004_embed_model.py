"""Record which embedding model produced each law vector (switch from local e5 to the Gemini API).

Existing rows get NULL: retrieval ignores them until scripts/ingest_law.py (or AUTO_INGEST_LAW) re-embeds.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("law_articles", sa.Column("embed_model", sa.String(80)))


def downgrade() -> None:
    op.drop_column("law_articles", "embed_model")
