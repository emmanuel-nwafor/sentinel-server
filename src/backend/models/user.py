from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.post import PostModel
    from backend.models.social_account import SocialAccountModel
    from backend.models.oauth_identity import OAuthIdentityModel


class UserModel(Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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
