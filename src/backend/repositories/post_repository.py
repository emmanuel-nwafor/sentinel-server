from abc import abstractmethod
from typing import Optional, List
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.post import PostModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IPostRepository(IBaseRepository[PostModel]):
    @abstractmethod
    async def get_user_posts(
        self,
        user_id: uuid.UUID,
        workspace: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[PostModel]:
        pass

    @abstractmethod
    async def get_by_user_and_id(self, post_id: uuid.UUID, user_id: uuid.UUID) -> Optional[PostModel]:
        pass


class PostRepository(BaseRepository[PostModel], IPostRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(PostModel, session)

    async def get_user_posts(
        self,
        user_id: uuid.UUID,
        workspace: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[PostModel]:
        query = select(PostModel).where(PostModel.user_id == user_id)

        if workspace:
            query = query.where(PostModel.workspace == workspace)
        if status:
            query = query.where(PostModel.status == status)

        query = query.order_by(PostModel.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_user_and_id(self, post_id: uuid.UUID, user_id: uuid.UUID) -> Optional[PostModel]:
        result = await self.session.execute(
            select(PostModel).where(PostModel.id == post_id, PostModel.user_id == user_id)
        )
        return result.scalars().first()
