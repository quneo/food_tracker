"""Saved products with label photos, the assistant's meal comments, diet reviews

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite batch mode drops unnamed CHECK constraints when it recreates a table: restate them.
ITEM_CHECKS = (
    sa.CheckConstraint("grams_source IN ('estimated', 'stated', 'label')"),
    sa.CheckConstraint("kcal >= 0 AND protein >= 0 AND fat >= 0 AND carbs >= 0"),
)
MEAL_CHECKS = (
    sa.CheckConstraint("status IN ('draft', 'confirmed')"),
    sa.CheckConstraint("meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')"),
    sa.CheckConstraint("source IN ('photo', 'text', 'manual')"),
    sa.CheckConstraint("confidence IN ('low', 'medium', 'high')"),
)
JOB_CHECKS = (sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')"),)


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("kcal", sa.Double(), nullable=False),
        sa.Column("protein", sa.Double(), nullable=False),
        sa.Column("fat", sa.Double(), nullable=False),
        sa.Column("carbs", sa.Double(), nullable=False),
        sa.Column("portion_name", sa.String(length=60), nullable=True),
        sa.Column("portion_grams", sa.Double(), nullable=True),
        sa.Column("package_grams", sa.Double(), nullable=True),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kcal >= 0 AND protein >= 0 AND fat >= 0 AND carbs >= 0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_user_name", "products", ["user_id", "name"], unique=False)

    with op.batch_alter_table("meals") as batch:
        batch.add_column(sa.Column("ai_comment", sa.String(length=1500), nullable=True))

    with op.batch_alter_table("meal_items", table_args=ITEM_CHECKS) as batch:
        batch.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch.create_index("ix_meal_items_product_id", ["product_id"], unique=False)
        batch.create_foreign_key(
            "fk_meal_items_product_id", "products", ["product_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("media") as batch:
        batch.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch.create_index("ix_media_product_id", ["product_id"], unique=False)
        batch.create_foreign_key(
            "fk_media_product_id", "products", ["product_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_check_constraint(
            "ck_media_kind", "kind IN ('chat', 'meal', 'body', 'product')"
        )

    with op.batch_alter_table("reminders") as batch:
        batch.create_check_constraint(
            "ck_reminders_kind", "kind IN ('meal', 'weight', 'photo', 'review', 'custom')"
        )
    # People who signed up earlier get the weekly review too, switched off like the rest.
    op.execute(
        "INSERT INTO reminders (user_id, kind, time, days, enabled, smart_skip, created_at) "
        "SELECT id, 'review', '20:00', '[7]', 0, 1, CURRENT_TIMESTAMP FROM users "
        "WHERE id NOT IN (SELECT user_id FROM reminders WHERE kind = 'review')"
    )

    with op.batch_alter_table("ai_jobs") as batch:
        batch.add_column(
            sa.Column("kind", sa.String(length=8), nullable=False, server_default="turn")
        )
        batch.add_column(sa.Column("days", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_jobs", table_args=JOB_CHECKS) as batch:
        batch.drop_column("days")
        batch.drop_column("kind")
    # Back to the original unnamed checks, exactly as 0001 made them.
    op.execute("DELETE FROM reminders WHERE kind = 'review'")
    old_reminder_kind = sa.CheckConstraint("kind IN ('meal', 'weight', 'photo', 'custom')")
    with op.batch_alter_table("reminders", table_args=(old_reminder_kind,)) as batch:
        batch.drop_constraint("ck_reminders_kind", type_="check")
    old_media_kind = sa.CheckConstraint("kind IN ('chat', 'meal', 'body')")
    with op.batch_alter_table("media", table_args=(old_media_kind,)) as batch:
        batch.drop_constraint("ck_media_kind", type_="check")
        batch.drop_constraint("fk_media_product_id", type_="foreignkey")
        batch.drop_index("ix_media_product_id")
        batch.drop_column("product_id")
    with op.batch_alter_table("meal_items", table_args=ITEM_CHECKS) as batch:
        batch.drop_constraint("fk_meal_items_product_id", type_="foreignkey")
        batch.drop_index("ix_meal_items_product_id")
        batch.drop_column("product_id")
    with op.batch_alter_table("meals", table_args=MEAL_CHECKS) as batch:
        batch.drop_column("ai_comment")
    op.drop_index("ix_products_user_name", table_name="products")
    op.drop_table("products")
