from enum import Enum
from typing import Optional, TYPE_CHECKING
import uuid
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.user import UserModel


class OAuthLoginProvider(str, Enum):
    GOOGLE = "google"
    LINKEDIN = "linkedin"
    X = "x"


class OAuthIdentityModel(Base):
    """
    Maps an external OAuth login identity (Google, LinkedIn, X) to a Sentinel UserModel.
    Allows one user to sign in with multiple providers seamlessly.
    """

    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="oauth_identities")
