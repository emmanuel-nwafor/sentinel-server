from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
import uuid
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.user import UserModel


class PostModel(Base):
    __tablename__ = "posts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    workspace: Mapped[str] = mapped_column(String(50), default="content", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True, nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # PostgreSQL JSONB columns: Semi-structured AI variants & media
    linkedin_variant: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    x_variant: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    instagram_variant: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    media: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    metadata_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    publish_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship to Author
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="posts")
