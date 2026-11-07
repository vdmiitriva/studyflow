"""add time blocks

Revision ID: cd67ec3cfa32
Revises: 74259d83c04e
Create Date: 2026-11-08 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cd67ec3cfa32"
down_revision: Union[str, Sequence[str], None] = "74259d83c04e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A block may only point to a task of the same user, so tasks need a
    # unique (id, user_id) pair that the composite foreign key can reference.
    op.create_unique_constraint("uq_task_id_user_id", "tasks", ["id", "user_id"])

    op.create_table(
        "time_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="planned", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'completed', 'skipped')",
            name="ck_time_block_status",
        ),
        sa.CheckConstraint(
            "ends_at > starts_at", name="ck_time_block_ends_after_start"
        ),
        sa.CheckConstraint(
            "task_id IS NULL OR subject_id IS NULL",
            name="ck_time_block_task_or_subject",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_time_block_task_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subjects.id", "subjects.user_id"],
            name="fk_time_block_subject_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_time_blocks_user_id_starts_at",
        "time_blocks",
        ["user_id", "starts_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_time_blocks_task_id"), "time_blocks", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_time_blocks_subject_id"), "time_blocks", ["subject_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_time_blocks_subject_id"), table_name="time_blocks")
    op.drop_index(op.f("ix_time_blocks_task_id"), table_name="time_blocks")
    op.drop_index("ix_time_blocks_user_id_starts_at", table_name="time_blocks")
    op.drop_table("time_blocks")
    op.drop_constraint("uq_task_id_user_id", "tasks", type_="unique")
