from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from studyflow.models.base import Base

DEFAULT_SUBJECT_COLOR = "#4F46E5"


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_subject_status",
        ),
        CheckConstraint(
            "color ~ '^#[0-9A-Fa-f]{6}$'",
            name="ck_subject_color",
        ),
        UniqueConstraint(
            "id",
            "user_id",
            name="uq_subject_id_user_id",
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
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default="active",
        nullable=False,
    )
    color: Mapped[str] = mapped_column(
        String(7),
        default=DEFAULT_SUBJECT_COLOR,
        server_default=DEFAULT_SUBJECT_COLOR,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="subjects")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="subject",
        passive_deletes=True,
        foreign_keys="Task.subject_id",
    )
