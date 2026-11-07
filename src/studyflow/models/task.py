from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from studyflow.models.base import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('todo', 'in_progress', 'completed')",
            name="ck_task_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="ck_task_priority",
        ),
        CheckConstraint(
            "estimate_minutes BETWEEN 1 AND 1440",
            name="ck_task_estimate_minutes",
        ),
        UniqueConstraint(
            "id",
            "user_id",
            name="uq_task_id_user_id",
        ),
        ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subjects.id", "subjects.user_id"],
            ondelete="RESTRICT",
            name="fk_task_subject_owner",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="todo",
        server_default="todo",
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(10),
        default="medium",
        server_default="medium",
        nullable=False,
    )
    estimate_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="tasks")
    subject: Mapped["Subject"] = relationship(
        back_populates="tasks",
        foreign_keys=[subject_id],
    )
