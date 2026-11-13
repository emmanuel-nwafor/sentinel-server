from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Locate templates/email directory relative to backend package
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

# Initialize Jinja2 environment (cached at module level)
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


class EmailTemplateRenderer:
    """
    Centralized email template rendering engine for Dispatch.
    Works similarly to EJS in Node.js, compiling reusable HTML layouts with dynamic context.
    """

    def __init__(self, env: Environment = _jinja_env):
        self._env = env

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render any template in templates/email/ with the provided dictionary context."""
        template = self._env.get_template(template_name)
        return template.render(**context)

    def render_otp(self, user_name: str, otp_code: str, expire_minutes: int = 15) -> str:
        """Render the 6-digit OTP verification template."""
        return self.render(
            "otp_verification.html",
            {
                "subject": f"{otp_code} is your Dispatch verification code",
                "user_name": user_name,
                "otp_code": otp_code,
                "expire_minutes": expire_minutes,
            },
        )

    def render_welcome(self, user_name: str, dashboard_url: str = "https://dispatch.io") -> str:
        """Render the welcome onboarding email template."""
        return self.render(
            "welcome.html",
            {
                "subject": f"Welcome to Dispatch, {user_name}! 🚀",
                "user_name": user_name,
                "dashboard_url": dashboard_url,
            },
        )

    def render_password_reset(self, user_name: str, reset_code: str, expire_minutes: int = 15) -> str:
        """Render the password reset code template."""
        return self.render(
            "password_reset.html",
            {
                "subject": f"{reset_code} is your Dispatch password reset code",
                "user_name": user_name,
                "reset_code": reset_code,
                "expire_minutes": expire_minutes,
            },
        )

    def render_marketing_announcement(
        self,
        *,
        user_name: str,
        headline: str,
        announcement_body: str,
        campaign_tag: str = "Product Announcement",
        hero_image_url: str = None,
        bullet_points: list = None,
        cta_text: str = "Explore What's New &rarr;",
        cta_url: str = "https://dispatch.io",
    ) -> str:
        """Render a marketing or product feature announcement email."""
        return self.render(
            "marketing_announcement.html",
            {
                "subject": f"Dispatch: {headline}",
                "user_name": user_name,
                "headline": headline,
                "announcement_body": announcement_body,
                "campaign_tag": campaign_tag,
                "hero_image_url": hero_image_url,
                "bullet_points": bullet_points or [],
                "cta_text": cta_text,
                "cta_url": cta_url,
            },
        )

    def render_weekly_digest(
        self,
        *,
        user_name: str,
        total_posts: int = 12,
        total_inquiries: int = 48,
        time_saved_hours: str = "6.5h",
        ai_insight: str = None,
    ) -> str:
        """Render the weekly performance digest email."""
        return self.render(
            "weekly_digest.html",
            {
                "subject": f"Your Weekly Dispatch Summary 📈",
                "user_name": user_name,
                "total_posts": total_posts,
                "total_inquiries": total_inquiries,
                "time_saved_hours": time_saved_hours,
                "ai_insight": ai_insight,
            },
        )

    def render_post_published(
        self,
        *,
        user_name: str,
        platform_name: str,
        post_excerpt: str,
        post_url: str = "https://dispatch.io/posts",
    ) -> str:
        """Render post published success notification."""
        return self.render(
            "post_published.html",
            {
                "subject": f"Your post is live on {platform_name}! 🚀",
                "user_name": user_name,
                "platform_name": platform_name,
                "post_excerpt": post_excerpt,
                "post_url": post_url,
            },
        )

    def render_unread_inbox_alert(
        self,
        *,
        user_name: str,
        customer_name: str,
        customer_handle: str,
        platform: str,
        message_preview: str,
        suggested_reply: str = None,
        conversation_url: str = "https://dispatch.io/inbox",
    ) -> str:
        """Render an alert for pending customer messages in Dispatch Inbox."""
        return self.render(
            "unread_inbox_alert.html",
            {
                "subject": f"New inquiry from {customer_name} on {platform}",
                "user_name": user_name,
                "customer_name": customer_name,
                "customer_handle": customer_handle,
                "platform": platform,
                "message_preview": message_preview,
                "suggested_reply": suggested_reply,
                "conversation_url": conversation_url,
            },
        )


# Global singleton instance
email_renderer = EmailTemplateRenderer()
