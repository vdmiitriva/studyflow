"""add user day hours

Revision ID: 396e75c7d56a
Revises: cd67ec3cfa32
Create Date: 2026-11-10 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "396e75c7d56a"
down_revision: Union[str, Sequence[str], None] = "cd67ec3cfa32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The server defaults fill the new columns for users that already exist,
    # so every current user gets the 08:00-22:00 day.
    op.add_column(
        "users",
        sa.Column("day_start", sa.Time(), server_default="08:00", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("day_end", sa.Time(), server_default="22:00", nullable=False),
    )
    op.create_check_constraint(
        "ck_user_day_start_before_end",
        "users",
        "day_start < day_end",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_user_day_start_before_end", "users", type_="check")
    op.drop_column("users", "day_end")
    op.drop_column("users", "day_start")
