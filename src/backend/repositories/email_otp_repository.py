from abc import abstractmethod
from datetime import datetime, timezone
from typing import Optional
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.email_otp import EmailOtpModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IEmailOtpRepository(IBaseRepository[EmailOtpModel]):
    """Abstract repository contract for email verification OTP records."""

    @abstractmethod
    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[EmailOtpModel]:
        pass

    @abstractmethod
    async def upsert_otp(
        self,
        *,
        user_id: uuid.UUID,
        otp_hash: str,
        expires_at: datetime,
    ) -> EmailOtpModel:
        pass

    @abstractmethod
    async def delete_by_user_id(self, user_id: uuid.UUID) -> bool:
        pass


class EmailOtpRepository(BaseRepository[EmailOtpModel], IEmailOtpRepository):
    """Concrete SQLAlchemy repository for EmailOtpModel."""

    def __init__(self, session: AsyncSession):
        super().__init__(EmailOtpModel, session)

    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[EmailOtpModel]:
        result = await self.session.execute(
            select(EmailOtpModel).where(EmailOtpModel.user_id == user_id)
        )
        return result.scalars().first()

    async def upsert_otp(
        self,
        *,
        user_id: uuid.UUID,
        otp_hash: str,
        expires_at: datetime,
    ) -> EmailOtpModel:
        now = datetime.now(timezone.utc)
        existing = await self.get_by_user_id(user_id)
        if existing:
            existing.otp_hash = otp_hash
            existing.expires_at = expires_at
            existing.attempts = 0
            existing.last_sent_at = now
            await self.session.flush()
            return existing

        otp_record = EmailOtpModel(
            user_id=user_id,
            otp_hash=otp_hash,
            expires_at=expires_at,
            attempts=0,
            last_sent_at=now,
        )
        return await self.create(otp_record)

    async def delete_by_user_id(self, user_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(EmailOtpModel).where(EmailOtpModel.user_id == user_id)
        )
        return (result.rowcount or 0) > 0
