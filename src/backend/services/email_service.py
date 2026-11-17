from abc import ABC, abstractmethod
import logging
from typing import List, Optional
import httpx
from backend.core.config import settings
from backend.services.email_template_service import email_renderer

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when an external email provider fails to deliver an email."""


class IEmailService(ABC):
    """Abstract Strategy Interface for transactional and marketing email delivery."""

    @abstractmethod
    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        """Deliver a 6-digit verification code email."""
        pass

    @abstractmethod
    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        """Deliver a welcome onboarding email to a newly verified user."""
        pass

    @abstractmethod
    async def send_password_reset_email(self, to_email: str, user_name: str, reset_code: str) -> None:
        """Deliver a password reset code email."""
        pass

    @abstractmethod
    async def send_security_alert(
        self,
        to_email: str,
        user_name: str,
        alert_title: str,
        device_info: str = "Chrome on macOS",
        location_info: str = "San Francisco, CA, USA",
        ip_address: str = "192.0.2.1",
    ) -> None:
        """Deliver a security event alert email."""
        pass

    @abstractmethod
    async def send_post_published(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        post_excerpt: str,
        post_url: str = "https://sentinel.ai/posts",
    ) -> None:
        """Deliver a post published success notification email."""
        pass

    @abstractmethod
    async def send_post_failed(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        error_message: str,
        post_excerpt: Optional[str] = None,
    ) -> None:
        """Deliver a post publishing failure alert email."""
        pass

    @abstractmethod
    async def send_unread_inbox_alert(
        self,
        to_email: str,
        user_name: str,
        customer_name: str,
        customer_handle: str,
        platform: str,
        message_preview: str,
        suggested_reply: Optional[str] = None,
    ) -> None:
        """Deliver an alert for pending customer messages in Sentinel Inbox."""
        pass

    @abstractmethod
    async def send_weekly_digest(
        self,
        to_email: str,
        user_name: str,
        total_posts: int = 14,
        total_inquiries: int = 52,
        time_saved_hours: str = "7.5h",
        ai_insight: Optional[str] = None,
    ) -> None:
        """Deliver a weekly operations summary email."""
        pass

    @abstractmethod
    async def send_marketing_announcement(
        self,
        to_email: str,
        user_name: str,
        headline: str,
        announcement_body: str,
        bullet_points: Optional[List[str]] = None,
        cta_text: str = "Explore What's New &rarr;",
        cta_url: str = "https://sentinel.ai",
    ) -> None:
        """Deliver a marketing or feature update email."""
        pass

    @abstractmethod
    async def send_promotional_offer(
        self,
        to_email: str,
        user_name: str,
        discount_label: str = "Special 40% Off Annual Plan",
        coupon_code: str = "CREATOR40",
    ) -> None:
        """Deliver a promotional discount campaign email."""
        pass

    @abstractmethod
    async def send_onboarding_tips(self, to_email: str, user_name: str) -> None:
        """Deliver creator educational playbook tips."""
        pass

    @abstractmethod
    async def send_reengagement(self, to_email: str, user_name: str) -> None:
        """Deliver a win-back email to re-engage inactive creators."""
        pass

    @abstractmethod
    async def send_subscription_confirmation(
        self,
        to_email: str,
        user_name: str,
        tier_name: str = "Sentinel Pro",
        amount_paid: str = "$228.00 / year",
    ) -> None:
        """Deliver a subscription confirmation receipt email."""
        pass

    @abstractmethod
    async def send_usage_limit_warning(
        self,
        to_email: str,
        user_name: str,
        current_usage: int,
        total_limit: int,
    ) -> None:
        """Deliver a quota warning email when approaching free monthly limits."""
        pass

    @abstractmethod
    async def send_custom_template_email(
        self,
        to_email: str,
        user_name: str,
        subject: str,
        template_name: str,
        context: dict,
    ) -> None:
        """Deliver an email compiled from any template in templates/email/."""
        pass


class ConsoleEmailService(IEmailService):
    """
    Development Email Service.
    Prints rendered email alerts to the terminal when no external provider is configured.
    """

    async def send_otp_email(self, to_email: str, user_name: str, otp_code: str) -> None:
        banner = (
            f"\n{'=' * 58}\n"
            f"  [DEV EMAIL] Sentinel Verification OTP\n"
            f"  To: {user_name} <{to_email}>\n"
            f"  Code: {otp_code}  (expires in {settings.OTP_EXPIRE_MINUTES} minutes)\n"
            f"{'=' * 58}\n"
        )
        print(banner, flush=True)
        logger.info("Sent dev OTP email to %s", to_email)

    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        print(f"[DEV EMAIL] Welcome to Sentinel delivered to {user_name} <{to_email}>")

    async def send_password_reset_email(self, to_email: str, user_name: str, reset_code: str) -> None:
        print(f"[DEV EMAIL] Password reset code {reset_code} delivered to {user_name} <{to_email}>")

    async def send_security_alert(
        self,
        to_email: str,
        user_name: str,
        alert_title: str,
        device_info: str = "Chrome on macOS",
        location_info: str = "San Francisco, CA, USA",
        ip_address: str = "192.0.2.1",
    ) -> None:
        print(f"[DEV EMAIL] Security Alert ({alert_title}) delivered to {user_name} <{to_email}>")

    async def send_post_published(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        post_excerpt: str,
        post_url: str = "https://sentinel.ai/posts",
    ) -> None:
        print(f"[DEV EMAIL] Post live on {platform_name} delivered to {user_name} <{to_email}>")

    async def send_post_failed(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        error_message: str,
        post_excerpt: Optional[str] = None,
    ) -> None:
        print(f"[DEV EMAIL] Post failed on {platform_name} delivered to {user_name} <{to_email}>: {error_message}")

    async def send_unread_inbox_alert(
        self,
        to_email: str,
        user_name: str,
        customer_name: str,
        customer_handle: str,
        platform: str,
        message_preview: str,
        suggested_reply: Optional[str] = None,
    ) -> None:
        print(f"[DEV EMAIL] Inquiry from {customer_name} ({platform}) delivered to {user_name} <{to_email}>")

    async def send_weekly_digest(
        self,
        to_email: str,
        user_name: str,
        total_posts: int = 14,
        total_inquiries: int = 52,
        time_saved_hours: str = "7.5h",
        ai_insight: Optional[str] = None,
    ) -> None:
        print(f"[DEV EMAIL] Weekly Digest delivered to {user_name} <{to_email}>")

    async def send_marketing_announcement(
        self,
        to_email: str,
        user_name: str,
        headline: str,
        announcement_body: str,
        bullet_points: Optional[List[str]] = None,
        cta_text: str = "Explore What's New &rarr;",
        cta_url: str = "https://sentinel.ai",
    ) -> None:
        print(f"[DEV EMAIL] Marketing to {user_name} <{to_email}>: {headline}")

    async def send_promotional_offer(
        self,
        to_email: str,
        user_name: str,
        discount_label: str = "Special 40% Off Annual Plan",
        coupon_code: str = "CREATOR40",
    ) -> None:
        print(f"[DEV EMAIL] Offer {discount_label} ({coupon_code}) delivered to {user_name} <{to_email}>")

    async def send_onboarding_tips(self, to_email: str, user_name: str) -> None:
        print(f"[DEV EMAIL] Onboarding Tips delivered to {user_name} <{to_email}>")

    async def send_reengagement(self, to_email: str, user_name: str) -> None:
        print(f"[DEV EMAIL] Win-back re-engagement delivered to {user_name} <{to_email}>")

    async def send_subscription_confirmation(
        self,
        to_email: str,
        user_name: str,
        tier_name: str = "Sentinel Pro",
        amount_paid: str = "$228.00 / year",
    ) -> None:
        print(f"[DEV EMAIL] Subscription confirmation ({tier_name}) delivered to {user_name} <{to_email}>")

    async def send_usage_limit_warning(
        self,
        to_email: str,
        user_name: str,
        current_usage: int,
        total_limit: int,
    ) -> None:
        print(f"[DEV EMAIL] Usage warning ({current_usage}/{total_limit}) delivered to {user_name} <{to_email}>")

    async def send_custom_template_email(
        self,
        to_email: str,
        user_name: str,
        subject: str,
        template_name: str,
        context: dict,
    ) -> None:
        print(f"[DEV EMAIL] Custom template {template_name} to {user_name} <{to_email}>: {subject}")


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
        html = email_renderer.render_otp(user_name, otp_code, settings.OTP_EXPIRE_MINUTES)
        await self._send(to_email, f"{otp_code} is your Sentinel verification code", html)

    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        html = email_renderer.render_welcome(user_name)
        await self._send(to_email, f"Welcome to Sentinel, {user_name}! 🚀", html)

    async def send_password_reset_email(self, to_email: str, user_name: str, reset_code: str) -> None:
        html = email_renderer.render_password_reset(user_name, reset_code)
        await self._send(to_email, f"{reset_code} is your Sentinel password recovery code", html)

    async def send_security_alert(
        self,
        to_email: str,
        user_name: str,
        alert_title: str,
        device_info: str = "Chrome on macOS",
        location_info: str = "San Francisco, CA, USA",
        ip_address: str = "192.0.2.1",
    ) -> None:
        html = email_renderer.render_security_alert(
            user_name=user_name,
            alert_title=alert_title,
            device_info=device_info,
            location_info=location_info,
            ip_address=ip_address,
        )
        await self._send(to_email, f"Security Alert: {alert_title}", html)

    async def send_post_published(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        post_excerpt: str,
        post_url: str = "https://sentinel.ai/posts",
    ) -> None:
        html = email_renderer.render_post_published(user_name, platform_name, post_excerpt, post_url)
        await self._send(to_email, f"Your post is live on {platform_name}! 🚀", html)

    async def send_post_failed(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        error_message: str,
        post_excerpt: Optional[str] = None,
    ) -> None:
        html = email_renderer.render_post_failed(user_name, platform_name, error_message, post_excerpt)
        await self._send(to_email, f"Action Needed: Post delivery failed on {platform_name}", html)

    async def send_unread_inbox_alert(
        self,
        to_email: str,
        user_name: str,
        customer_name: str,
        customer_handle: str,
        platform: str,
        message_preview: str,
        suggested_reply: Optional[str] = None,
    ) -> None:
        html = email_renderer.render_unread_inbox_alert(
            user_name=user_name,
            customer_name=customer_name,
            customer_handle=customer_handle,
            platform=platform,
            message_preview=message_preview,
            suggested_reply=suggested_reply,
        )
        await self._send(to_email, f"New inquiry from {customer_name} on {platform}", html)

    async def send_weekly_digest(
        self,
        to_email: str,
        user_name: str,
        total_posts: int = 14,
        total_inquiries: int = 52,
        time_saved_hours: str = "7.5h",
        ai_insight: Optional[str] = None,
    ) -> None:
        html = email_renderer.render_weekly_digest(
            user_name=user_name,
            total_posts=total_posts,
            total_inquiries=total_inquiries,
            time_saved_hours=time_saved_hours,
            ai_insight=ai_insight,
        )
        await self._send(to_email, "Your Weekly Sentinel Summary 📈", html)

    async def send_marketing_announcement(
        self,
        to_email: str,
        user_name: str,
        headline: str,
        announcement_body: str,
        bullet_points: Optional[List[str]] = None,
        cta_text: str = "Explore What's New &rarr;",
        cta_url: str = "https://sentinel.ai",
    ) -> None:
        html = email_renderer.render_marketing_announcement(
            user_name=user_name,
            headline=headline,
            announcement_body=announcement_body,
            bullet_points=bullet_points,
            cta_text=cta_text,
            cta_url=cta_url,
        )
        await self._send(to_email, f"Sentinel: {headline}", html)

    async def send_promotional_offer(
        self,
        to_email: str,
        user_name: str,
        discount_label: str = "Special 40% Off Annual Plan",
        coupon_code: str = "CREATOR40",
    ) -> None:
        html = email_renderer.render_promotional_offer(
            user_name=user_name,
            discount_label=discount_label,
            coupon_code=coupon_code,
        )
        await self._send(to_email, f"Exclusive Offer: {discount_label} on Sentinel Pro", html)

    async def send_onboarding_tips(self, to_email: str, user_name: str) -> None:
        html = email_renderer.render_onboarding_tips(user_name=user_name)
        await self._send(to_email, "3 strategies to 10x your social distribution with Sentinel", html)

    async def send_reengagement(self, to_email: str, user_name: str) -> None:
        html = email_renderer.render_reengagement(user_name=user_name)
        await self._send(to_email, f"We miss you in Sentinel, {user_name}! 👋", html)

    async def send_subscription_confirmation(
        self,
        to_email: str,
        user_name: str,
        tier_name: str = "Sentinel Pro",
        amount_paid: str = "$228.00 / year",
    ) -> None:
        html = email_renderer.render_subscription_confirmation(
            user_name=user_name,
            tier_name=tier_name,
            amount_paid=amount_paid,
        )
        await self._send(to_email, f"You're officially on {tier_name}! 🎉", html)

    async def send_usage_limit_warning(
        self,
        to_email: str,
        user_name: str,
        current_usage: int,
        total_limit: int,
    ) -> None:
        percentage = f"{int((current_usage / max(total_limit, 1)) * 100)}%"
        html = email_renderer.render_usage_limit_warning(
            user_name=user_name,
            current_usage=current_usage,
            total_limit=total_limit,
            percentage_used=percentage,
        )
        await self._send(to_email, f"You've used {percentage} of your monthly AI quota", html)

    async def send_custom_template_email(
        self,
        to_email: str,
        user_name: str,
        subject: str,
        template_name: str,
        context: dict,
    ) -> None:
        html = email_renderer.render(template_name, context)
        await self._send(to_email, subject, html)


class BrevoEmailService(IEmailService):
    """Production Email Service using Brevo's v3 Transactional Email REST API."""

    BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str, sender_email: str, sender_name: str = "Sentinel"):
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
        html = email_renderer.render_otp(user_name, otp_code, settings.OTP_EXPIRE_MINUTES)
        await self._send(to_email, user_name, f"{otp_code} is your Sentinel verification code", html)

    async def send_welcome_email(self, to_email: str, user_name: str) -> None:
        html = email_renderer.render_welcome(user_name)
        await self._send(to_email, user_name, f"Welcome to Sentinel, {user_name}! 🚀", html)

    async def send_password_reset_email(self, to_email: str, user_name: str, reset_code: str) -> None:
        html = email_renderer.render_password_reset(user_name, reset_code)
        await self._send(to_email, user_name, f"{reset_code} is your Sentinel password recovery code", html)

    async def send_security_alert(
        self,
        to_email: str,
        user_name: str,
        alert_title: str,
        device_info: str = "Chrome on macOS",
        location_info: str = "San Francisco, CA, USA",
        ip_address: str = "192.0.2.1",
    ) -> None:
        html = email_renderer.render_security_alert(
            user_name=user_name,
            alert_title=alert_title,
            device_info=device_info,
            location_info=location_info,
            ip_address=ip_address,
        )
        await self._send(to_email, user_name, f"Security Alert: {alert_title}", html)

    async def send_post_published(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        post_excerpt: str,
        post_url: str = "https://sentinel.ai/posts",
    ) -> None:
        html = email_renderer.render_post_published(user_name, platform_name, post_excerpt, post_url)
        await self._send(to_email, user_name, f"Your post is live on {platform_name}! 🚀", html)

    async def send_post_failed(
        self,
        to_email: str,
        user_name: str,
        platform_name: str,
        error_message: str,
        post_excerpt: Optional[str] = None,
    ) -> None:
        html = email_renderer.render_post_failed(user_name, platform_name, error_message, post_excerpt)
        await self._send(to_email, user_name, f"Action Needed: Post delivery failed on {platform_name}", html)

    async def send_unread_inbox_alert(
        self,
        to_email: str,
        user_name: str,
        customer_name: str,
        customer_handle: str,
        platform: str,
        message_preview: str,
        suggested_reply: Optional[str] = None,
    ) -> None:
        html = email_renderer.render_unread_inbox_alert(
            user_name=user_name,
            customer_name=customer_name,
            customer_handle=customer_handle,
            platform=platform,
            message_preview=message_preview,
            suggested_reply=suggested_reply,
        )
        await self._send(to_email, user_name, f"New inquiry from {customer_name} on {platform}", html)

    async def send_weekly_digest(
        self,
        to_email: str,
        user_name: str,
        total_posts: int = 14,
        total_inquiries: int = 52,
        time_saved_hours: str = "7.5h",
        ai_insight: Optional[str] = None,
    ) -> None:
        html = email_renderer.render_weekly_digest(
            user_name=user_name,
            total_posts=total_posts,
            total_inquiries=total_inquiries,
            time_saved_hours=time_saved_hours,
            ai_insight=ai_insight,
        )
        await self._send(to_email, user_name, "Your Weekly Sentinel Summary 📈", html)

    async def send_marketing_announcement(
        self,
        to_email: str,
        user_name: str,
        headline: str,
        announcement_body: str,
        bullet_points: Optional[List[str]] = None,
        cta_text: str = "Explore What's New &rarr;",
        cta_url: str = "https://sentinel.ai",
    ) -> None:
        html = email_renderer.render_marketing_announcement(
            user_name=user_name,
            headline=headline,
            announcement_body=announcement_body,
            bullet_points=bullet_points,
            cta_text=cta_text,
            cta_url=cta_url,
        )
        await self._send(to_email, user_name, f"Sentinel: {headline}", html)

    async def send_promotional_offer(
        self,
        to_email: str,
        user_name: str,
        discount_label: str = "Special 40% Off Annual Plan",
        coupon_code: str = "CREATOR40",
    ) -> None:
        html = email_renderer.render_promotional_offer(
            user_name=user_name,
            discount_label=discount_label,
            coupon_code=coupon_code,
        )
        await self._send(to_email, user_name, f"Exclusive Offer: {discount_label} on Sentinel Pro", html)

    async def send_onboarding_tips(self, to_email: str, user_name: str) -> None:
        html = email_renderer.render_onboarding_tips(user_name=user_name)
        await self._send(to_email, user_name, "3 strategies to 10x your social distribution with Sentinel", html)

    async def send_reengagement(self, to_email: str, user_name: str) -> None:
        html = email_renderer.render_reengagement(user_name=user_name)
        await self._send(to_email, user_name, f"We miss you in Sentinel, {user_name}! 👋", html)

    async def send_subscription_confirmation(
        self,
        to_email: str,
        user_name: str,
        tier_name: str = "Sentinel Pro",
        amount_paid: str = "$228.00 / year",
    ) -> None:
        html = email_renderer.render_subscription_confirmation(
            user_name=user_name,
            tier_name=tier_name,
            amount_paid=amount_paid,
        )
        await self._send(to_email, user_name, f"You're officially on {tier_name}! 🎉", html)

    async def send_usage_limit_warning(
        self,
        to_email: str,
        user_name: str,
        current_usage: int,
        total_limit: int,
    ) -> None:
        percentage = f"{int((current_usage / max(total_limit, 1)) * 100)}%"
        html = email_renderer.render_usage_limit_warning(
            user_name=user_name,
            current_usage=current_usage,
            total_limit=total_limit,
            percentage_used=percentage,
        )
        await self._send(to_email, user_name, f"You've used {percentage} of your monthly AI quota", html)

    async def send_custom_template_email(
        self,
        to_email: str,
        user_name: str,
        subject: str,
        template_name: str,
        context: dict,
    ) -> None:
        html = email_renderer.render(template_name, context)
        await self._send(to_email, user_name, subject, html)


def get_email_service() -> IEmailService:
    """Factory returning Brevo or Resend in production, or ConsoleEmailService in dev."""
    if settings.BREVO_API_KEY:
        sender = settings.BREVO_SENDER_EMAIL or "noreply@sentinel.ai"
        return BrevoEmailService(
            api_key=settings.BREVO_API_KEY,
            sender_email=sender,
            sender_name="Sentinel",
        )
    if settings.RESEND_API_KEY:
        return ResendEmailService(
            api_key=settings.RESEND_API_KEY,
            sender=settings.EMAIL_FROM,
        )
    return ConsoleEmailService()