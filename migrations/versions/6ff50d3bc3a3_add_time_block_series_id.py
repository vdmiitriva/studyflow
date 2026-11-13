"""add time block series id

Revision ID: 6ff50d3bc3a3
Revises: 396e75c7d56a
Create Date: 2026-11-10 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ff50d3bc3a3"
down_revision: Union[str, Sequence[str], None] = "396e75c7d56a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Blocks of one repeating series share a series_id. There is no table of
    # series: a series is simply the set of blocks that have the same id.
    op.add_column("time_blocks", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_time_blocks_series_id"), "time_blocks", ["series_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_time_blocks_series_id"), table_name="time_blocks")
    op.drop_column("time_blocks", "series_id")
