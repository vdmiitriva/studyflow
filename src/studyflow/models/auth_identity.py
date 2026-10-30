from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from studyflow.models.base import Base


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_auth_identity_provider_user",
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
    provider: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    provider_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="auth_identities",
    )
