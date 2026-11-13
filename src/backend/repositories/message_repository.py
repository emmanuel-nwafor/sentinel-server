from abc import abstractmethod
from datetime import datetime, timezone
from typing import List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.conversation import ConversationModel
from backend.models.message import MessageModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IMessageRepository(IBaseRepository[MessageModel]):
    """Abstract repository contract for inbox messages."""

    @abstractmethod
    async def list_by_conversation(
        self, conversation_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[MessageModel]:
        pass

    @abstractmethod
    async def add_message(
        self,
        *,
        conversation: ConversationModel,
        sender_type: str,
        sender_name: str,
        text: str,
        media_url: Optional[str] = None,
        platform_message_id: Optional[str] = None,
        is_read: bool = False,
        ai_suggested_reply: Optional[str] = None,
        sent_at: Optional[datetime] = None,
    ) -> MessageModel:
        pass


class MessageRepository(BaseRepository[MessageModel], IMessageRepository):
    """Concrete SQLAlchemy repository for MessageModel."""

    def __init__(self, session: AsyncSession):
        super().__init__(MessageModel, session)

    async def list_by_conversation(
        self, conversation_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[MessageModel]:
        result = await self.session.execute(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.sent_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def add_message(
        self,
        *,
        conversation: ConversationModel,
        sender_type: str,
        sender_name: str,
        text: str,
        media_url: Optional[str] = None,
        platform_message_id: Optional[str] = None,
        is_read: bool = False,
        ai_suggested_reply: Optional[str] = None,
        sent_at: Optional[datetime] = None,
    ) -> MessageModel:
        now = sent_at or datetime.now(timezone.utc)
        message = MessageModel(
            conversation_id=conversation.id,
            sender_type=sender_type,
            sender_name=sender_name,
            text=text.strip(),
            media_url=media_url,
            platform_message_id=platform_message_id,
            is_read=is_read,
            ai_suggested_reply=ai_suggested_reply,
            sent_at=now,
        )
        self.session.add(message)

        # Update parent conversation state
        conversation.last_message_at = now
        clean_preview = text.strip().replace("\n", " ")
        conversation.last_message_preview = clean_preview[:140]

        if sender_type == "customer" and not is_read:
            conversation.unread_count += 1
            if conversation.status == "resolved":
                conversation.status = "open"
        elif sender_type in ("user", "ai_agent"):
            conversation.unread_count = 0
            if conversation.status == "open":
                conversation.status = "pending"

        await self.session.flush()
        return message
