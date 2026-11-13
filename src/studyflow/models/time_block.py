from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from studyflow.models.base import Base


class TimeBlock(Base):
    """A planned period of time: working on a task, a lecture, a workout."""

    __tablename__ = "time_blocks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'completed', 'skipped')",
            name="ck_time_block_status",
        ),
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_time_block_ends_after_start",
        ),
        CheckConstraint(
            "task_id IS NULL OR subject_id IS NULL",
            name="ck_time_block_task_or_subject",
        ),
        ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            ondelete="CASCADE",
            name="fk_time_block_task_owner",
        ),
        ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subjects.id", "subjects.user_id"],
            ondelete="RESTRICT",
            name="fk_time_block_subject_owner",
        ),
        Index("ix_time_blocks_user_id_starts_at", "user_id", "starts_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    subject_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    series_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="planned",
        server_default="planned",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
