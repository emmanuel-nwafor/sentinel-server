from typing import Optional, List, TYPE_CHECKING
import uuid
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.user import UserModel


class UserBrandProfileModel(Base):
    """
    User Brand & Profile Memory Layer.
    Persists deep professional context (niche, headline, about, skills, positioning,
    target audience, core topics) extracted from LinkedIn, CVs, or user notes.
    """
    __tablename__ = "user_brand_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_brand_profiles_user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(255), default="Emmanuel Chinecherem", nullable=False)
    headline: Mapped[str] = mapped_column(String(255), default="Software Engineer at Foremade", nullable=False)
    about: Mapped[str] = mapped_column(Text, nullable=False)
    niche: Mapped[str] = mapped_column(String(255), default="Fullstack & Mobile Engineering, Scalable Architectures", nullable=False)
    target_audience: Mapped[str] = mapped_column(String(255), default="Engineering leaders, tech founders, software engineers", nullable=False)
    tone: Mapped[str] = mapped_column(String(255), default="Opinionated, high-conviction, technical, charismatic", nullable=False)
    
    core_topics: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    skills: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    current_company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    education: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="linkedin_enrichment", nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="brand_profile")
