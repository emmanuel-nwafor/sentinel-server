from datetime import datetime
from typing import Optional, TYPE_CHECKING
import uuid
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.conversation import ConversationModel


class MessageModel(Base):
    """
    Individual message or comment in an inbox conversation thread.
    """

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'customer' | 'user' | 'ai_agent'
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    media_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    platform_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_suggested_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

    conversation: Mapped["ConversationModel"] = relationship("ConversationModel", back_populates="messages")
