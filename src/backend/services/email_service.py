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


class BrevoEmailService(IEmailService):
    """Production Email Service using Brevo's v3 Transactional Email REST API."""

    BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str, sender_email: str, sender_name: str = "Sentinel"):
        self._api_key = api_key
        self._sender_email = sender_email
        self._sender_name = sender_name

    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        html_content = (
            f"<div style='font-family:sans-serif;max-width:500px;margin:auto;padding:24px;border:1px solid #eaeaea;border-radius:12px;'>"
            f"<h2 style='color:#111;'>Sentinel Verification</h2>"
            f"<p style='color:#555;'>Hi {user_name},</p>"
            f"<p style='color:#555;'>Your 6-digit Sentinel verification code is:</p>"
            f"<div style='background:#f4f4f5;padding:16px;text-align:center;font-size:28px;font-weight:bold;letter-spacing:6px;border-radius:8px;color:#09090b;margin:20px 0;'>"
            f"{otp_code}"
            f"</div>"
            f"<p style='color:#777;font-size:13px;'>This code expires in {settings.OTP_EXPIRE_MINUTES} minutes. If you did not request this code, please ignore this email.</p>"
            f"</div>"
        )

        payload = {
            "sender": {"name": self._sender_name, "email": self._sender_email},
            "to": [{"email": to_email, "name": user_name}],
            "subject": f"{otp_code} is your Sentinel verification code",
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
            logger.info("Sent real Brevo OTP email to %s", to_email)


def get_email_service() -> IEmailService:
    """Factory returning Brevo or Resend in production, or ConsoleEmailService in dev."""
    if settings.BREVO_API_KEY:
        sender = settings.BREVO_SENDER_EMAIL or "noreply@sentinel.app"
        return BrevoEmailService(
            api_key=settings.BREVO_API_KEY,
            sender_email=sender,
        )
    if settings.RESEND_API_KEY:
        return ResendEmailService(
            api_key=settings.RESEND_API_KEY,
            sender=settings.EMAIL_FROM,
        )
    return ConsoleEmailService()
