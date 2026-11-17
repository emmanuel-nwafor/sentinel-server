from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.post import PostModel
    from backend.models.social_account import SocialAccountModel
    from backend.models.oauth_identity import OAuthIdentityModel
    from backend.models.customer import CustomerModel
    from backend.models.conversation import ConversationModel
    from backend.models.brand_voice import BrandVoiceModel


class UserModel(Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Monetization, Tiers & Quota (Enforcement can be toggled via ENABLE_PREMIUM_ENFORCEMENT)
    tier: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_status: Mapped[Optional[str]] = mapped_column(String(50), default="active", nullable=True)
    premium_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    monthly_ai_quota_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_ai_quota_limit: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    # Relationship to user's posts
    posts: Mapped[List["PostModel"]] = relationship(
        "PostModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Relationship to user's connected social accounts
    social_accounts: Mapped[List["SocialAccountModel"]] = relationship(
        "SocialAccountModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Relationship to external OAuth login identities
    oauth_identities: Mapped[List["OAuthIdentityModel"]] = relationship(
        "OAuthIdentityModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Relationship to customers across platforms
    customers: Mapped[List["CustomerModel"]] = relationship(
        "CustomerModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Relationship to inbox conversations
    conversations: Mapped[List["ConversationModel"]] = relationship(
        "ConversationModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Relationship to custom brand voices (Premium Feature)
    brand_voices: Mapped[List["BrandVoiceModel"]] = relationship(
        "BrandVoiceModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
