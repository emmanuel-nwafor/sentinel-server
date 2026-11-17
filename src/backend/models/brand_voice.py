from typing import Optional, List, TYPE_CHECKING
import uuid
from sqlalchemy import String, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.user import UserModel


class BrandVoiceModel(Base):
    """
    Brand Voice Persona (Premium Feature).
    Allows creators and businesses to define custom AI writing styles,
    brand tones, target audiences, and forbidden/taboo words.
    """
    __tablename__ = "brand_voices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "Founder Storyteller"
    tone: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "authoritative, humble, analytical"
    target_audience: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "Seed-to-Series A founders"
    key_pillars: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    taboo_words: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)  # Words to never use
    signature_cta: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sample_post: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="brand_voices")
