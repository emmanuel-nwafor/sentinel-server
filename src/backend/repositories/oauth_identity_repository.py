from abc import abstractmethod
from typing import List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.oauth_identity import OAuthIdentityModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IOAuthIdentityRepository(IBaseRepository[OAuthIdentityModel]):
    """Abstract repository contract for external OAuth login identities."""

    @abstractmethod
    async def get_by_provider_identity(
        self, provider: str, provider_user_id: str
    ) -> Optional[OAuthIdentityModel]:
        pass

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> List[OAuthIdentityModel]:
        pass


class OAuthIdentityRepository(BaseRepository[OAuthIdentityModel], IOAuthIdentityRepository):
    """Concrete SQLAlchemy repository for OAuthIdentityModel."""

    def __init__(self, session: AsyncSession):
        super().__init__(OAuthIdentityModel, session)

    async def get_by_provider_identity(
        self, provider: str, provider_user_id: str
    ) -> Optional[OAuthIdentityModel]:
        result = await self.session.execute(
            select(OAuthIdentityModel).where(
                OAuthIdentityModel.provider == provider,
                OAuthIdentityModel.provider_user_id == provider_user_id,
            )
        )
        return result.scalars().first()

    async def list_by_user(self, user_id: uuid.UUID) -> List[OAuthIdentityModel]:
        result = await self.session.execute(
            select(OAuthIdentityModel).where(OAuthIdentityModel.user_id == user_id)
        )
        return list(result.scalars().all())
