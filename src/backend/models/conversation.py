from datetime import datetime
from typing import List, TYPE_CHECKING
import uuid
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.user import UserModel
    from backend.models.customer import CustomerModel
    from backend.models.message import MessageModel


class ConversationModel(Base):
    """
    Represents an ongoing interaction thread (DM or comment) between a business owner and a customer.
    """

    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), default="dm", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True, nullable=False)
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    last_message_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="conversations")
    customer: Mapped["CustomerModel"] = relationship("CustomerModel", back_populates="conversations", lazy="joined")
    messages: Mapped[List["MessageModel"]] = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MessageModel.sent_at.asc()",
    )
