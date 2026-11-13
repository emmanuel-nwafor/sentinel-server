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


# Global singleton instance
email_renderer = EmailTemplateRenderer()
