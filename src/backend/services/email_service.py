from abc import ABC, abstractmethod
import logging
import httpx
from backend.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when an external email provider fails to deliver an OTP email."""


class IEmailService(ABC):
    """Abstract Strategy Interface for transactional email delivery."""

    @abstractmethod
    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        pass


class ConsoleEmailService(IEmailService):
    """
    Development Email Service.
    Prints the 6-digit OTP to the server terminal when RESEND_API_KEY is not configured.
    """

    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        banner = (
            f"\n{'=' * 54}\n"
            f"  [DEV EMAIL] Sentinel Verification OTP\n"
            f"  To: {user_name} <{to_email}>\n"
            f"  Code: {otp_code}  (expires in {settings.OTP_EXPIRE_MINUTES} minutes)\n"
            f"{'=' * 54}\n"
        )
        print(banner, flush=True)
        logger.info("Sent dev OTP email to %s", to_email)


class ResendEmailService(IEmailService):
    """Production Email Service using the Resend transactional HTTP API."""

    RESEND_API_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str):
        self._api_key = api_key
        self._sender = sender

    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        html_body = (
            f"<p>Hi {user_name},</p>"
            f"<p>Your Sentinel verification code is: "
            f"<strong style='font-size:20px;letter-spacing:3px;'>{otp_code}</strong></p>"
            f"<p>This code expires in {settings.OTP_EXPIRE_MINUTES} minutes.</p>"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self.RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self._sender,
                    "to": [to_email],
                    "subject": "Your Sentinel Verification Code",
                    "html": html_body,
                },
            )
            if resp.status_code >= 400:
                raise EmailDeliveryError(
                    f"Resend API error ({resp.status_code}): {resp.text}"
                )


def get_email_service() -> IEmailService:
    """Factory returning ResendEmailService in production or ConsoleEmailService in dev."""
    if settings.RESEND_API_KEY:
        return ResendEmailService(
            api_key=settings.RESEND_API_KEY,
            sender=settings.EMAIL_FROM,
        )
    return ConsoleEmailService()
