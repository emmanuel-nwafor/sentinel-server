from abc import ABC, abstractmethod
from typing import Self
from backend.repositories.user_repository import IUserRepository
from backend.repositories.post_repository import IPostRepository
from backend.repositories.social_account_repository import ISocialAccountRepository
from backend.repositories.email_otp_repository import IEmailOtpRepository
from backend.repositories.oauth_identity_repository import IOAuthIdentityRepository
from backend.repositories.customer_repository import ICustomerRepository
from backend.repositories.conversation_repository import IConversationRepository
from backend.repositories.message_repository import IMessageRepository
from backend.repositories.brand_voice_repository import IBrandVoiceRepository
from backend.repositories.brand_profile_repository import IBrandProfileRepository


class IUnitOfWork(ABC):
    """
    Abstract Unit of Work Interface.
    Manages atomic transaction boundaries across repositories.
    """

    users: IUserRepository
    posts: IPostRepository
    social_accounts: ISocialAccountRepository
    email_otps: IEmailOtpRepository
    oauth_identities: IOAuthIdentityRepository
    customers: ICustomerRepository
    conversations: IConversationRepository
    messages: IMessageRepository
    brand_voices: IBrandVoiceRepository
    brand_profiles: IBrandProfileRepository

    @abstractmethod
    async def __aenter__(self) -> Self:
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    @abstractmethod
    async def commit(self) -> None:
        pass

    @abstractmethod
    async def rollback(self) -> None:
        pass
