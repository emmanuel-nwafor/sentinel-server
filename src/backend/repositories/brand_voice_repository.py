from abc import abstractmethod
from typing import List, Optional
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.brand_voice import BrandVoiceModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IBrandVoiceRepository(IBaseRepository[BrandVoiceModel]):
    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> List[BrandVoiceModel]:
        pass

    @abstractmethod
    async def get_default_by_user(self, user_id: uuid.UUID) -> Optional[BrandVoiceModel]:
        pass

    @abstractmethod
    async def set_default(self, user_id: uuid.UUID, voice_id: uuid.UUID) -> Optional[BrandVoiceModel]:
        pass


class BrandVoiceRepository(BaseRepository[BrandVoiceModel], IBrandVoiceRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(BrandVoiceModel, session)

    async def list_by_user(self, user_id: uuid.UUID) -> List[BrandVoiceModel]:
        result = await self.session.execute(
            select(BrandVoiceModel)
            .where(BrandVoiceModel.user_id == user_id)
            .order_by(BrandVoiceModel.is_default.desc(), BrandVoiceModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_default_by_user(self, user_id: uuid.UUID) -> Optional[BrandVoiceModel]:
        result = await self.session.execute(
            select(BrandVoiceModel)
            .where(BrandVoiceModel.user_id == user_id, BrandVoiceModel.is_default.is_(True))
        )
        return result.scalars().first()

    async def set_default(self, user_id: uuid.UUID, voice_id: uuid.UUID) -> Optional[BrandVoiceModel]:
        # Unset all current defaults for user
        await self.session.execute(
            update(BrandVoiceModel)
            .where(BrandVoiceModel.user_id == user_id)
            .values(is_default=False)
        )
        # Set specified voice as default
        await self.session.execute(
            update(BrandVoiceModel)
            .where(BrandVoiceModel.user_id == user_id, BrandVoiceModel.id == voice_id)
            .values(is_default=True)
        )
        await self.session.flush()
        return await self.get_by_id(voice_id)
