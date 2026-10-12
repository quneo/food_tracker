"""Progress photos grouped into one entry per day, a code that unblurs them, reminders
for measurements every 1-4 weeks

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSE = "pose IN ('front', 'side', 'back', 'other')"
PROFILE_CHECKS = (
    sa.CheckConstraint("activity IN ('sedentary', 'light', 'moderate', 'high', 'very_high')"),
    sa.CheckConstraint("goal IN ('lose', 'maintain', 'gain')"),
    sa.CheckConstraint("sex IN ('male', 'female')"),
)


def upgrade() -> None:
    op.create_table(
        "progress_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("taken_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "taken_on", name="uq_progress_entries_day"),
    )
    # Photos of the same day become one entry; its note is the first photo note.
    op.execute(
        "INSERT INTO progress_entries (user_id, taken_on, note, created_at) "
        "SELECT p.user_id, p.taken_on, "
        "(SELECT q.note FROM progress_photos q WHERE q.user_id = p.user_id "
        "AND q.taken_on = p.taken_on AND q.note IS NOT NULL ORDER BY q.id LIMIT 1), "
        "MIN(p.created_at) FROM progress_photos p GROUP BY p.user_id, p.taken_on"
    )
    op.add_column("progress_photos", sa.Column("entry_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE progress_photos SET entry_id = (SELECT e.id FROM progress_entries e "
        "WHERE e.user_id = progress_photos.user_id AND e.taken_on = progress_photos.taken_on)"
    )
    with op.batch_alter_table(
        "progress_photos", table_args=(sa.CheckConstraint(POSE, name="ck_progress_pose"),)
    ) as batch:
        batch.alter_column("entry_id", existing_type=sa.Integer(), nullable=False)
        batch.create_index("ix_progress_photos_entry_id", ["entry_id"])
        batch.create_foreign_key(
            "fk_progress_photos_entry_id",
            "progress_entries",
            ["entry_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.add_column("profiles", sa.Column("photo_pin_hash", sa.String(length=200), nullable=True))
    op.add_column(
        "profiles",
        sa.Column("photo_pin_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("profiles", sa.Column("photo_pin_blocked_until", sa.DateTime(), nullable=True))
    op.add_column("profiles", sa.Column("photo_pin_reset_at", sa.DateTime(), nullable=True))
    op.add_column("web_sessions", sa.Column("photos_unlocked_until", sa.DateTime(), nullable=True))

    with op.batch_alter_table("reminders") as batch:
        batch.drop_constraint("ck_reminders_kind", type_="check")
        batch.create_check_constraint(
            "ck_reminders_kind",
            "kind IN ('meal', 'weight', 'photo', 'measure', 'review', 'custom')",
        )
        batch.add_column(sa.Column("every_weeks", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("anchor_on", sa.Date(), nullable=True))
    # Everyone gets the measurements reminder, switched off like the other presets.
    op.execute(
        "INSERT INTO reminders "
        "(user_id, kind, time, days, enabled, smart_skip, every_weeks, created_at) "
        "SELECT id, 'measure', '09:00', '[1]', 0, 1, 1, CURRENT_TIMESTAMP FROM users "
        "WHERE id NOT IN (SELECT user_id FROM reminders WHERE kind = 'measure')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM reminders WHERE kind = 'measure'")
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("anchor_on")
        batch.drop_column("every_weeks")
        batch.drop_constraint("ck_reminders_kind", type_="check")
        batch.create_check_constraint(
            "ck_reminders_kind", "kind IN ('meal', 'weight', 'photo', 'review', 'custom')"
        )

    with op.batch_alter_table("web_sessions") as batch:
        batch.drop_column("photos_unlocked_until")
    with op.batch_alter_table("profiles", table_args=PROFILE_CHECKS) as batch:
        batch.drop_column("photo_pin_reset_at")
        batch.drop_column("photo_pin_blocked_until")
        batch.drop_column("photo_pin_failures")
        batch.drop_column("photo_pin_hash")

    # Entry notes go back to the first photo of the day that has none.
    op.execute(
        "UPDATE progress_photos SET note = (SELECT e.note FROM progress_entries e "
        "WHERE e.id = progress_photos.entry_id) WHERE note IS NULL AND id IN "
        "(SELECT MIN(id) FROM progress_photos GROUP BY entry_id)"
    )
    with op.batch_alter_table("progress_photos", table_args=(sa.CheckConstraint(POSE),)) as batch:
        batch.drop_constraint("ck_progress_pose", type_="check")
        batch.drop_constraint("fk_progress_photos_entry_id", type_="foreignkey")
        batch.drop_index("ix_progress_photos_entry_id")
        batch.drop_column("entry_id")
    op.drop_table("progress_entries")
