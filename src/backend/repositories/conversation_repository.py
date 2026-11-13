from abc import abstractmethod
from datetime import datetime, timezone
from typing import List, Optional
import uuid
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.conversation import ConversationModel
from backend.models.customer import CustomerModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IConversationRepository(IBaseRepository[ConversationModel]):
    """Abstract repository contract for inbox conversation threads."""

    @abstractmethod
    async def get_by_id_and_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[ConversationModel]:
        pass

    @abstractmethod
    async def list_by_user(
        self,
        user_id: uuid.UUID,
        platform: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConversationModel]:
        pass

    @abstractmethod
    async def get_or_create_thread(
        self,
        *,
        user_id: uuid.UUID,
        customer_id: uuid.UUID,
        platform: str,
        channel_type: str = "dm",
    ) -> ConversationModel:
        pass

    @abstractmethod
    async def update_status(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, status: str
    ) -> Optional[ConversationModel]:
        pass

    @abstractmethod
    async def mark_as_read(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[ConversationModel]:
        pass


class ConversationRepository(BaseRepository[ConversationModel], IConversationRepository):
    """Concrete SQLAlchemy repository for ConversationModel."""

    def __init__(self, session: AsyncSession):
        super().__init__(ConversationModel, session)

    async def get_by_id_and_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[ConversationModel]:
        result = await self.session.execute(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                ConversationModel.user_id == user_id,
            )
            .options(
                selectinload(ConversationModel.customer),
                selectinload(ConversationModel.messages),
            )
        )
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        platform: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConversationModel]:
        stmt = (
            select(ConversationModel)
            .join(CustomerModel, ConversationModel.customer_id == CustomerModel.id)
            .where(ConversationModel.user_id == user_id)
            .options(selectinload(ConversationModel.customer))
        )

        if platform:
            stmt = stmt.where(ConversationModel.platform == platform)
        if status:
            stmt = stmt.where(ConversationModel.status == status)
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    CustomerModel.customer_name.ilike(term),
                    CustomerModel.customer_handle.ilike(term),
                    ConversationModel.last_message_preview.ilike(term),
                )
            )

        stmt = stmt.order_by(ConversationModel.last_message_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create_thread(
        self,
        *,
        user_id: uuid.UUID,
        customer_id: uuid.UUID,
        platform: str,
        channel_type: str = "dm",
    ) -> ConversationModel:
        stmt = select(ConversationModel).where(
            ConversationModel.user_id == user_id,
            ConversationModel.customer_id == customer_id,
            ConversationModel.platform == platform,
            ConversationModel.channel_type == channel_type,
        )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        if existing:
            return existing

        now = datetime.now(timezone.utc)
        thread = ConversationModel(
            user_id=user_id,
            customer_id=customer_id,
            platform=platform,
            channel_type=channel_type,
            status="open",
            unread_count=0,
            last_message_at=now,
            last_message_preview="",
        )
        return await self.create(thread)

    async def update_status(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, status: str
    ) -> Optional[ConversationModel]:
        thread = await self.get_by_id_and_user(conversation_id, user_id)
        if not thread:
            return None
        thread.status = status
        await self.session.flush()
        return thread

    async def mark_as_read(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[ConversationModel]:
        thread = await self.get_by_id_and_user(conversation_id, user_id)
        if not thread:
            return None
        thread.unread_count = 0
        for msg in thread.messages:
            msg.is_read = True
        await self.session.flush()
        return thread
