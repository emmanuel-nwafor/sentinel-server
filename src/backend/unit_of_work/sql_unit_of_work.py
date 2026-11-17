from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession
from backend.unit_of_work.base import IUnitOfWork
from backend.repositories.user_repository import UserRepository, IUserRepository
from backend.repositories.post_repository import PostRepository, IPostRepository
from backend.repositories.social_account_repository import (
    SocialAccountRepository,
    ISocialAccountRepository,
)
from backend.repositories.email_otp_repository import EmailOtpRepository, IEmailOtpRepository
from backend.repositories.oauth_identity_repository import (
    OAuthIdentityRepository,
    IOAuthIdentityRepository,
)
from backend.repositories.customer_repository import CustomerRepository, ICustomerRepository
from backend.repositories.conversation_repository import (
    ConversationRepository,
    IConversationRepository,
)
from backend.repositories.message_repository import MessageRepository, IMessageRepository
from backend.repositories.brand_voice_repository import BrandVoiceRepository, IBrandVoiceRepository


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """
    Concrete Unit of Work for Async SQLAlchemy.
    Guarantees atomic transactions across multiple repositories.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self) -> Self:
        self.users: IUserRepository = UserRepository(self._session)
        self.posts: IPostRepository = PostRepository(self._session)
        self.social_accounts: ISocialAccountRepository = SocialAccountRepository(self._session)
        self.email_otps: IEmailOtpRepository = EmailOtpRepository(self._session)
        self.oauth_identities: IOAuthIdentityRepository = OAuthIdentityRepository(self._session)
        self.customers: ICustomerRepository = CustomerRepository(self._session)
        self.conversations: IConversationRepository = ConversationRepository(self._session)
        self.messages: IMessageRepository = MessageRepository(self._session)
        self.brand_voices: IBrandVoiceRepository = BrandVoiceRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            await self.rollback()
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
