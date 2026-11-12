from abc import abstractmethod
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.user import UserModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IUserRepository(IBaseRepository[UserModel]):
    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[UserModel]:
        pass


class UserRepository(BaseRepository[UserModel], IUserRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(UserModel, session)

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email.lower().strip())
        )
        return result.scalars().first()
