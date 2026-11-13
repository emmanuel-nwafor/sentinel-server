from abc import ABC, abstractmethod
import logging
import httpx
from backend.core.config import settings
from backend.services.email_template_service import email_renderer

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when an external email provider fails to deliver an email."""


class IEmailService(ABC):
    """Abstract Strategy Interface for transactional email delivery."""

    @abstractmethod
    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        """Deliver a 6-digit verification code email."""
        pass

    @abstractmethod
    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        """Deliver a welcome onboarding email to a newly verified user."""
        pass


class ConsoleEmailService(IEmailService):
    """
    Development Email Service.
    Prints rendered email alerts to the terminal when no external provider is configured.
    """

    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        banner = (
            f"\n{'=' * 54}\n"
            f"  [DEV EMAIL] Dispatch Verification OTP\n"
            f"  To: {user_name} <{to_email}>\n"
            f"  Code: {otp_code}  (expires in {settings.OTP_EXPIRE_MINUTES} minutes)\n"
            f"{'=' * 54}\n"
        )
        print(banner, flush=True)
        logger.info("Sent dev OTP email to %s", to_email)

    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        banner = (
            f"\n{'=' * 54}\n"
            f"  [DEV EMAIL] Welcome to Dispatch!\n"
            f"  To: {user_name} <{to_email}>\n"
            f"  Welcome message delivered to newly verified user.\n"
            f"{'=' * 54}\n"
        )
        print(banner, flush=True)
        logger.info("Sent dev welcome email to %s", to_email)


class ResendEmailService(IEmailService):
    """Production Email Service using the Resend transactional HTTP API."""

    RESEND_API_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str):
        self._api_key = api_key
        self._sender = sender

    async def _send(self, to_email: str, subject: str, html_content: str) -> None:
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
                    "subject": subject,
                    "html": html_content,
                },
            )
            if resp.status_code >= 400:
                raise EmailDeliveryError(
                    f"Resend API error ({resp.status_code}): {resp.text}"
                )

    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        html_body = email_renderer.render_otp(
            user_name=user_name,
            otp_code=otp_code,
            expire_minutes=settings.OTP_EXPIRE_MINUTES,
        )
        await self._send(
            to_email=to_email,
            subject=f"{otp_code} is your Dispatch verification code",
            html_content=html_body,
        )

    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        html_body = email_renderer.render_welcome(user_name=user_name)
        await self._send(
            to_email=to_email,
            subject=f"Welcome to Dispatch, {user_name}! 🚀",
            html_content=html_body,
        )


class BrevoEmailService(IEmailService):
    """Production Email Service using Brevo's v3 Transactional Email REST API."""

    BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str, sender_email: str, sender_name: str = "Dispatch"):
        self._api_key = api_key
        self._sender_email = sender_email
        self._sender_name = sender_name

    async def _send(self, to_email: str, to_name: str, subject: str, html_content: str) -> None:
        payload = {
            "sender": {"name": self._sender_name, "email": self._sender_email},
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "htmlContent": html_content,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self.BREVO_API_URL,
                headers={
                    "api-key": self._api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                logger.error("Brevo API error (%d): %s", resp.status_code, resp.text)
                raise EmailDeliveryError(f"Brevo email delivery failed ({resp.status_code}): {resp.text}")

    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        html_content = email_renderer.render_otp(
            user_name=user_name,
            otp_code=otp_code,
            expire_minutes=settings.OTP_EXPIRE_MINUTES,
        )
        await self._send(
            to_email=to_email,
            to_name=user_name,
            subject=f"{otp_code} is your Dispatch verification code",
            html_content=html_content,
        )
        logger.info("Sent Dispatch OTP email to %s", to_email)

    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        html_content = email_renderer.render_welcome(
            user_name=user_name,
            dashboard_url="https://dispatch.io",
        )
        await self._send(
            to_email=to_email,
            to_name=user_name,
            subject=f"Welcome to Dispatch, {user_name}! 🚀",
            html_content=html_content,
        )
        logger.info("Sent Dispatch welcome onboarding email to %s", to_email)


def get_email_service() -> IEmailService:
    """Factory returning Brevo or Resend in production, or ConsoleEmailService in dev."""
    if settings.BREVO_API_KEY:
        sender = settings.BREVO_SENDER_EMAIL or "noreply@dispatch.io"
        return BrevoEmailService(
            api_key=settings.BREVO_API_KEY,
            sender_email=sender,
            sender_name="Dispatch",
        )
    if settings.RESEND_API_KEY:
        return ResendEmailService(
            api_key=settings.RESEND_API_KEY,
            sender=settings.EMAIL_FROM,
        )
    return ConsoleEmailService()
