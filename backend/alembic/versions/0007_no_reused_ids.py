"""Ids are never given out twice

SQLite hands the id of the newest deleted row to the next one. Photos are served at
/api/media/<id> and kept by the browser for a week, so a new photo could show the cached
picture of a deleted one; old bot buttons name meals and pending actions by id too.
AUTOINCREMENT keeps every new id above all ids ever used.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Batch mode recreates each table; unnamed CHECK constraints are not carried over by
# reflection, so they are restated here.
TABLES = {
    "media": (),
    "meals": (
        sa.CheckConstraint("status IN ('draft', 'confirmed')"),
        sa.CheckConstraint("meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')"),
        sa.CheckConstraint("source IN ('photo', 'text', 'manual')"),
        sa.CheckConstraint("confidence IN ('low', 'medium', 'high')"),
    ),
    "pending_actions": (sa.CheckConstraint("status IN ('pending', 'done', 'cancelled')"),),
}


def _recreate(autoincrement: bool) -> None:
    for name, checks in TABLES.items():
        with op.batch_alter_table(
            name,
            recreate="always",
            table_args=checks,
            table_kwargs={"sqlite_autoincrement": autoincrement},
        ):
            pass


def upgrade() -> None:
    _recreate(True)


def downgrade() -> None:
    _recreate(False)
