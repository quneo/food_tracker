"""Weigh notes: grams written down now for a meal eaten later

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weigh_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=True),
        sa.Column("due_from", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("meal_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')", name="ck_weigh_notes_meal"
        ),
        sa.CheckConstraint("status IN ('active', 'used', 'deleted')", name="ck_weigh_notes_status"),
        sa.CheckConstraint("source IN ('web', 'bot', 'ai')", name="ck_weigh_notes_source"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meal_id"], ["meals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_weigh_notes_user_open", "weigh_notes", ["user_id", "status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_weigh_notes_user_open", table_name="weigh_notes")
    op.drop_table("weigh_notes")
