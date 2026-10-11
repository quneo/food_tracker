"""Bastion accounts: users may exist before their Telegram is linked

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_CHECK = sa.CheckConstraint("status IN ('pending', 'confirmed', 'rejected', 'used')")


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("telegram_id", existing_type=sa.BigInteger(), nullable=True)
        batch.add_column(sa.Column("bastion_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("username", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("bastion_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.create_unique_constraint("uq_users_bastion_id", ["bastion_id"])
    # SQLite batch mode drops unnamed CHECK constraints when it recreates the table:
    # restate the status check from 0001.
    with op.batch_alter_table("login_requests", table_args=(STATUS_CHECK,)) as batch:
        batch.add_column(
            sa.Column("purpose", sa.String(length=8), nullable=False, server_default="login")
        )
        batch.create_check_constraint("ck_login_requests_purpose", "purpose IN ('login', 'link')")


def downgrade() -> None:
    with op.batch_alter_table("login_requests", table_args=(STATUS_CHECK,)) as batch:
        batch.drop_constraint("ck_login_requests_purpose", type_="check")
        batch.drop_column("purpose")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_bastion_id", type_="unique")
        batch.drop_column("bastion_active")
        batch.drop_column("username")
        batch.drop_column("bastion_id")
        batch.alter_column("telegram_id", existing_type=sa.BigInteger(), nullable=False)
