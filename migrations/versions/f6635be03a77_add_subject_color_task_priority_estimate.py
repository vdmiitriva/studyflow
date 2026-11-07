"""add subject color, task priority and estimate

Revision ID: f6635be03a77
Revises: eb55d90ccac5
Create Date: 2026-11-06 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6635be03a77"
down_revision: Union[str, Sequence[str], None] = "eb55d90ccac5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "subjects",
        sa.Column(
            "color",
            sa.String(length=7),
            server_default="#4F46E5",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_subject_color",
        "subjects",
        "color ~ '^#[0-9A-Fa-f]{6}$'",
    )
    op.add_column(
        "tasks",
        sa.Column(
            "priority",
            sa.String(length=10),
            server_default="medium",
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column("estimate_minutes", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_task_priority",
        "tasks",
        "priority IN ('low', 'medium', 'high')",
    )
    op.create_check_constraint(
        "ck_task_estimate_minutes",
        "tasks",
        "estimate_minutes BETWEEN 1 AND 1440",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_task_estimate_minutes", "tasks", type_="check")
    op.drop_constraint("ck_task_priority", "tasks", type_="check")
    op.drop_column("tasks", "estimate_minutes")
    op.drop_column("tasks", "priority")
    op.drop_constraint("ck_subject_color", "subjects", type_="check")
    op.drop_column("subjects", "color")
