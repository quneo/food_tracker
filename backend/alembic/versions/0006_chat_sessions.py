"""Sessions in the bot: only messages inside one reach the assistant

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = (sa.CheckConstraint("role IN ('user', 'assistant')"),)


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.Column("answered_through_id", sa.Integer(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("end_reason", sa.String(length=8), nullable=True),
        sa.CheckConstraint("end_reason IN ('user', 'idle', 'new')", name="ck_chat_sessions_end"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_user_open", "chat_sessions", ["user_id", "ended_at"])
    with op.batch_alter_table("chat_messages", table_args=ROLE) as batch:
        batch.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
        batch.create_index("ix_chat_messages_session_id", ["session_id"])
        batch.create_foreign_key(
            "fk_chat_messages_session_id",
            "chat_sessions",
            ["session_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column("chat_states", sa.Column("awaiting", sa.String(length=16), nullable=True))
    op.add_column("chat_states", sa.Column("awaiting_until", sa.DateTime(), nullable=True))
    op.add_column(
        "chat_states",
        sa.Column("keyboard_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("ai_jobs", sa.Column("not_before", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table(
        "ai_jobs",
        table_args=(sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')"),),
    ) as batch:
        batch.drop_column("not_before")
    with op.batch_alter_table("chat_states") as batch:
        batch.drop_column("keyboard_version")
        batch.drop_column("awaiting_until")
        batch.drop_column("awaiting")
    with op.batch_alter_table("chat_messages", table_args=ROLE) as batch:
        batch.drop_constraint("fk_chat_messages_session_id", type_="foreignkey")
        batch.drop_index("ix_chat_messages_session_id")
        batch.drop_column("session_id")
    op.drop_index("ix_chat_sessions_user_open", table_name="chat_sessions")
    op.drop_table("chat_sessions")
