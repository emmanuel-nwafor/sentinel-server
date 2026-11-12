from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
import uuid
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.user import UserModel


class SocialPlatform(str, Enum):
    LINKEDIN = "linkedin"
    X = "x"
    INSTAGRAM = "instagram"


class SocialAccountModel(Base):
    """
    Stores a user's connected social media OAuth credentials and identity metadata.
    Access and refresh tokens are encrypted at rest via TokenCipher before persistence.
    """

    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_social_accounts_user_platform"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    platform: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    platform_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_handle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    scopes: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="social_accounts")
