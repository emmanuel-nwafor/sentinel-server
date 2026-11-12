from abc import abstractmethod
from datetime import datetime
from typing import Optional, List
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.social_account import SocialAccountModel
from backend.repositories.base import IBaseRepository, BaseRepository


class ISocialAccountRepository(IBaseRepository[SocialAccountModel]):
    """Abstract repository contract for user social account OAuth records."""

    @abstractmethod
    async def get_by_user_and_platform(
        self, user_id: uuid.UUID, platform: str
    ) -> Optional[SocialAccountModel]:
        pass

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> List[SocialAccountModel]:
        pass

    @abstractmethod
    async def upsert_account(
        self,
        *,
        user_id: uuid.UUID,
        platform: str,
        platform_account_id: str,
        account_name: str,
        account_handle: Optional[str],
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str],
        token_expires_at: Optional[datetime],
        scopes: List[str],
        is_sandbox: bool = False,
    ) -> SocialAccountModel:
        pass

    @abstractmethod
    async def delete_by_user_and_platform(self, user_id: uuid.UUID, platform: str) -> bool:
        pass


class SocialAccountRepository(BaseRepository[SocialAccountModel], ISocialAccountRepository):
    """Concrete SQLAlchemy repository for connected social media accounts."""

    def __init__(self, session: AsyncSession):
        super().__init__(SocialAccountModel, session)

    async def get_by_user_and_platform(
        self, user_id: uuid.UUID, platform: str
    ) -> Optional[SocialAccountModel]:
        result = await self.session.execute(
            select(SocialAccountModel).where(
                SocialAccountModel.user_id == user_id,
                SocialAccountModel.platform == platform,
            )
        )
        return result.scalars().first()

    async def list_by_user(self, user_id: uuid.UUID) -> List[SocialAccountModel]:
        result = await self.session.execute(
            select(SocialAccountModel)
            .where(SocialAccountModel.user_id == user_id)
            .order_by(SocialAccountModel.platform.asc())
        )
        return list(result.scalars().all())

    async def upsert_account(
        self,
        *,
        user_id: uuid.UUID,
        platform: str,
        platform_account_id: str,
        account_name: str,
        account_handle: Optional[str],
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str],
        token_expires_at: Optional[datetime],
        scopes: List[str],
        is_sandbox: bool = False,
    ) -> SocialAccountModel:
        existing = await self.get_by_user_and_platform(user_id, platform)
        if existing:
            existing.platform_account_id = platform_account_id
            existing.account_name = account_name
            existing.account_handle = account_handle
            existing.encrypted_access_token = encrypted_access_token
            existing.encrypted_refresh_token = encrypted_refresh_token
            existing.token_expires_at = token_expires_at
            existing.scopes = scopes
            existing.is_active = True
            existing.is_sandbox = is_sandbox
            await self.session.flush()
            return existing

        account = SocialAccountModel(
            user_id=user_id,
            platform=platform,
            platform_account_id=platform_account_id,
            account_name=account_name,
            account_handle=account_handle,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            token_expires_at=token_expires_at,
            scopes=scopes,
            is_active=True,
            is_sandbox=is_sandbox,
        )
        return await self.create(account)

    async def delete_by_user_and_platform(self, user_id: uuid.UUID, platform: str) -> bool:
        result = await self.session.execute(
            delete(SocialAccountModel).where(
                SocialAccountModel.user_id == user_id,
                SocialAccountModel.platform == platform,
            )
        )
        return (result.rowcount or 0) > 0
