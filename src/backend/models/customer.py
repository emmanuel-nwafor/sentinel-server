from typing import Optional, Dict, Any, List, TYPE_CHECKING
import uuid
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.user import UserModel
    from backend.models.conversation import ConversationModel


class CustomerModel(Base):
    """
    Stores an external customer profile (e.g. buyer or follower) across Instagram, X, or LinkedIn.
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "platform", "platform_customer_id", name="uq_customers_user_platform_id"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    platform_customer_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_handle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    metadata_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="customers")
    conversations: Mapped[List["ConversationModel"]] = relationship(
        "ConversationModel",
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
