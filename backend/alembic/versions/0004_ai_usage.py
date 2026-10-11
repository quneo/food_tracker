"""Token usage details of assistant requests: cached input and reasoning output.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_CHECKS = (sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')"),)


def upgrade() -> None:
    with op.batch_alter_table("ai_jobs") as batch:
        batch.add_column(sa.Column("cached_input_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("reasoning_output_tokens", sa.Integer(), nullable=True))
    # Usage per person over time.
    op.create_index("ix_ai_jobs_user_finished", "ai_jobs", ["user_id", "finished_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_user_finished", table_name="ai_jobs")
    with op.batch_alter_table("ai_jobs", table_args=JOB_CHECKS) as batch:
        batch.drop_column("reasoning_output_tokens")
        batch.drop_column("cached_input_tokens")
