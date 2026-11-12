from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Type, Optional, List, Any
import uuid
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.base import Base

T = TypeVar("T", bound=Base)


class IBaseRepository(ABC, Generic[T]):
    """Abstract Repository Interface defining standard contract."""

    @abstractmethod
    async def get_by_id(self, entity_id: uuid.UUID) -> Optional[T]:
        pass

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        pass

    @abstractmethod
    async def create(self, entity: T) -> T:
        pass

    @abstractmethod
    async def delete(self, entity_id: uuid.UUID) -> bool:
        pass


class BaseRepository(IBaseRepository[T], Generic[T]):
    """
    Concrete Generic Repository implementing standard async SQLAlchemy queries.
    Encapsulates all database operations, insulating domain logic from ORM mechanics.
    """

    def __init__(self, model_class: Type[T], session: AsyncSession):
        self.model_class = model_class
        self.session = session

    async def get_by_id(self, entity_id: uuid.UUID) -> Optional[T]:
        result = await self.session.execute(
            select(self.model_class).where(self.model_class.id == entity_id)
        )
        return result.scalars().first()

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        result = await self.session.execute(
            select(self.model_class).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(self.model_class).where(self.model_class.id == entity_id)
        )
        return (result.rowcount or 0) > 0
