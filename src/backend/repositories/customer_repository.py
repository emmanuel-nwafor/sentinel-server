from abc import abstractmethod
from typing import Optional, Dict, Any
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.customer import CustomerModel
from backend.repositories.base import IBaseRepository, BaseRepository


class ICustomerRepository(IBaseRepository[CustomerModel]):
    """Abstract repository contract for customer identity records across platforms."""

    @abstractmethod
    async def get_by_platform_customer_id(
        self, user_id: uuid.UUID, platform: str, platform_customer_id: str
    ) -> Optional[CustomerModel]:
        pass

    @abstractmethod
    async def upsert_customer(
        self,
        *,
        user_id: uuid.UUID,
        platform: str,
        platform_customer_id: str,
        customer_name: str,
        customer_handle: Optional[str] = None,
        avatar_url: Optional[str] = None,
        metadata_info: Optional[Dict[str, Any]] = None,
    ) -> CustomerModel:
        pass


class CustomerRepository(BaseRepository[CustomerModel], ICustomerRepository):
    """Concrete SQLAlchemy repository for CustomerModel."""

    def __init__(self, session: AsyncSession):
        super().__init__(CustomerModel, session)

    async def get_by_platform_customer_id(
        self, user_id: uuid.UUID, platform: str, platform_customer_id: str
    ) -> Optional[CustomerModel]:
        result = await self.session.execute(
            select(CustomerModel).where(
                CustomerModel.user_id == user_id,
                CustomerModel.platform == platform,
                CustomerModel.platform_customer_id == platform_customer_id,
            )
        )
        return result.scalars().first()

    async def upsert_customer(
        self,
        *,
        user_id: uuid.UUID,
        platform: str,
        platform_customer_id: str,
        customer_name: str,
        customer_handle: Optional[str] = None,
        avatar_url: Optional[str] = None,
        metadata_info: Optional[Dict[str, Any]] = None,
    ) -> CustomerModel:
        existing = await self.get_by_platform_customer_id(user_id, platform, platform_customer_id)
        if existing:
            existing.customer_name = customer_name
            if customer_handle:
                existing.customer_handle = customer_handle
            if avatar_url:
                existing.avatar_url = avatar_url
            if metadata_info:
                existing.metadata_info = {**(existing.metadata_info or {}), **metadata_info}
            await self.session.flush()
            return existing

        customer = CustomerModel(
            user_id=user_id,
            platform=platform,
            platform_customer_id=platform_customer_id,
            customer_name=customer_name,
            customer_handle=customer_handle,
            avatar_url=avatar_url,
            metadata_info=metadata_info or {},
        )
        return await self.create(customer)
