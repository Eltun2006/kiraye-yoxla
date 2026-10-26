"""Clause number as printed in the contract ("2.1" in multi-level contracts; idx stays the position).

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clauses", sa.Column("label", sa.String(16)))


def downgrade() -> None:
    op.drop_column("clauses", "label")
