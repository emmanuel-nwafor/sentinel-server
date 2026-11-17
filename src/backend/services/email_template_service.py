from pathlib import Path
from typing import Any, Dict, List, Optional
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
    Centralized production email template rendering engine for Sentinel.
    Compiles fully responsive, Outlook/Gmail/Apple Mail compatible HTML templates
    with dynamic context variables.
    """

    def __init__(self, env: Environment = _jinja_env):
        self._env = env

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render any template in templates/email/ with the provided dictionary context."""
        template = self._env.get_template(template_name)
        # Ensure default branding if not provided
        context.setdefault("brand_name", "Sentinel")
        context.setdefault("current_year", "2026")
        return template.render(**context)

    # -------------------------------------------------------------------------
    # Authentication & Security
    # -------------------------------------------------------------------------
    def render_otp(
        self,
        user_name: str,
        otp_code: str,
        expire_minutes: int = 10,
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the 6-digit OTP verification template."""
        return self.render(
            "otp_verification.html",
            {
                "subject": f"{otp_code} is your {brand_name} verification code",
                "preheader": f"Your 6-digit verification code is {otp_code}. Valid for {expire_minutes} minutes.",
                "user_name": user_name,
                "otp_code": otp_code,
                "expire_minutes": expire_minutes,
                "brand_name": brand_name,
                "header_badge": "Verification",
            },
        )

    def render_welcome(
        self,
        user_name: str,
        dashboard_url: str = "https://sentinel.ai/dashboard",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the welcome onboarding email template."""
        return self.render(
            "welcome.html",
            {
                "subject": f"Welcome to {brand_name}, {user_name}! 🚀",
                "preheader": f"Your {brand_name} account is verified and ready. Start automating your social operations.",
                "user_name": user_name,
                "dashboard_url": dashboard_url,
                "brand_name": brand_name,
                "header_badge": "Welcome",
            },
        )

    def render_password_reset(
        self,
        user_name: str,
        reset_code: str,
        expire_minutes: int = 15,
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the password reset code template."""
        return self.render(
            "password_reset.html",
            {
                "subject": f"{reset_code} is your {brand_name} password recovery code",
                "preheader": f"Use code {reset_code} to reset your password. Expires in {expire_minutes} minutes.",
                "user_name": user_name,
                "reset_code": reset_code,
                "expire_minutes": expire_minutes,
                "brand_name": brand_name,
                "header_badge": "Security",
            },
        )

    def render_security_alert(
        self,
        user_name: str,
        alert_title: str = "New sign-in detected on your account",
        alert_description: Optional[str] = None,
        event_time: str = "Just now (UTC)",
        device_info: str = "Chrome on macOS",
        location_info: str = "San Francisco, CA, USA",
        ip_address: str = "192.0.2.1",
        lock_account_url: str = "https://sentinel.ai/security/sessions",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render a security event alert email (new device login, credential update)."""
        return self.render(
            "security_alert.html",
            {
                "subject": f"Security Alert: {alert_title}",
                "preheader": f"A new sign-in was recorded for {user_name} from {device_info}.",
                "user_name": user_name,
                "alert_title": alert_title,
                "alert_description": alert_description,
                "event_time": event_time,
                "device_info": device_info,
                "location_info": location_info,
                "ip_address": ip_address,
                "lock_account_url": lock_account_url,
                "brand_name": brand_name,
                "header_badge": "Security Alert",
            },
        )

    # -------------------------------------------------------------------------
    # Publishing & Operations
    # -------------------------------------------------------------------------
    def render_post_published(
        self,
        user_name: str,
        platform_name: str,
        post_excerpt: str,
        post_url: str = "https://sentinel.ai/posts",
        published_time: Optional[str] = None,
        brand_name: str = "Sentinel",
    ) -> str:
        """Render post published success notification."""
        return self.render(
            "post_published.html",
            {
                "subject": f"Your post is live on {platform_name}! 🚀",
                "preheader": f"Successfully published to {platform_name}: {post_excerpt[:60]}...",
                "user_name": user_name,
                "platform_name": platform_name,
                "post_excerpt": post_excerpt,
                "post_url": post_url,
                "published_time": published_time,
                "brand_name": brand_name,
                "header_badge": "Live Post",
            },
        )

    def render_post_failed(
        self,
        user_name: str,
        platform_name: str,
        error_message: str,
        post_excerpt: Optional[str] = None,
        reconnect_url: str = "https://sentinel.ai/settings/connections",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render post publication failure alert."""
        return self.render(
            "post_failed.html",
            {
                "subject": f"Action Needed: Post delivery failed on {platform_name}",
                "preheader": f"Unable to publish post on {platform_name}. Reconnection required.",
                "user_name": user_name,
                "platform_name": platform_name,
                "error_message": error_message,
                "post_excerpt": post_excerpt,
                "reconnect_url": reconnect_url,
                "brand_name": brand_name,
                "header_badge": "Action Required",
            },
        )

    def render_unread_inbox_alert(
        self,
        user_name: str,
        customer_name: str,
        customer_handle: str,
        platform: str,
        message_preview: str,
        suggested_reply: Optional[str] = None,
        conversation_url: str = "https://sentinel.ai/inbox",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render an alert for pending customer inquiries in Sentinel Inbox."""
        return self.render(
            "unread_inbox_alert.html",
            {
                "subject": f"New inquiry from {customer_name} on {platform}",
                "preheader": f"Inquiry from {customer_handle} on {platform}: {message_preview[:60]}...",
                "user_name": user_name,
                "customer_name": customer_name,
                "customer_handle": customer_handle,
                "platform": platform,
                "message_preview": message_preview,
                "suggested_reply": suggested_reply,
                "conversation_url": conversation_url,
                "brand_name": brand_name,
                "header_badge": "Inbox Alert",
            },
        )

    def render_weekly_digest(
        self,
        user_name: str,
        total_posts: int = 14,
        total_inquiries: int = 52,
        time_saved_hours: str = "7.5h",
        ai_insight: Optional[str] = None,
        analytics_url: str = "https://sentinel.ai/analytics",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the weekly executive performance digest email."""
        return self.render(
            "weekly_digest.html",
            {
                "subject": f"Your Weekly {brand_name} Summary 📈",
                "preheader": f"Weekly digest: {total_posts} posts published, {total_inquiries} inquiries answered, {time_saved_hours} saved.",
                "user_name": user_name,
                "total_posts": total_posts,
                "total_inquiries": total_inquiries,
                "time_saved_hours": time_saved_hours,
                "ai_insight": ai_insight,
                "analytics_url": analytics_url,
                "brand_name": brand_name,
                "header_badge": "Weekly Digest",
            },
        )

    # -------------------------------------------------------------------------
    # Marketing & Growth
    # -------------------------------------------------------------------------
    def render_marketing_announcement(
        self,
        user_name: str,
        headline: str,
        announcement_body: str,
        campaign_tag: str = "Product Announcement",
        hero_image_url: Optional[str] = None,
        bullet_points: Optional[List[str]] = None,
        cta_text: str = "Explore What's New &rarr;",
        cta_url: str = "https://sentinel.ai",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render a product feature announcement email."""
        return self.render(
            "marketing_announcement.html",
            {
                "subject": f"{brand_name}: {headline}",
                "preheader": f"Check out what's new in {brand_name}: {headline}",
                "user_name": user_name,
                "headline": headline,
                "announcement_body": announcement_body,
                "campaign_tag": campaign_tag,
                "hero_image_url": hero_image_url,
                "bullet_points": bullet_points or [],
                "cta_text": cta_text,
                "cta_url": cta_url,
                "brand_name": brand_name,
                "header_badge": "Announcement",
            },
        )

    def render_promotional_offer(
        self,
        user_name: str,
        offer_headline: str = "Upgrade to Sentinel Pro: Special Early Creator Rate",
        discount_label: str = "Special 40% Off Annual Plan",
        discounted_price: str = "$19",
        coupon_code: str = "CREATOR40",
        expiry_date: str = "this Sunday at midnight",
        claim_url: str = "https://sentinel.ai/pricing?code=CREATOR40",
        cta_text: str = "Claim Your Pro Discount &rarr;",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render a marketing promotional offer or discount campaign email."""
        return self.render(
            "promotional_offer.html",
            {
                "subject": f"Exclusive offer for {user_name}: {discount_label} on {brand_name} Pro",
                "preheader": f"Claim {discount_label} with code {coupon_code}. Valid through {expiry_date}.",
                "user_name": user_name,
                "offer_headline": offer_headline,
                "discount_label": discount_label,
                "discounted_price": discounted_price,
                "coupon_code": coupon_code,
                "expiry_date": expiry_date,
                "claim_url": claim_url,
                "cta_text": cta_text,
                "brand_name": brand_name,
                "header_badge": "Special Offer",
            },
        )

    def render_onboarding_tips(
        self,
        user_name: str,
        create_post_url: str = "https://sentinel.ai/posts/new",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the creator playbook / educational onboarding tips email."""
        return self.render(
            "onboarding_tips.html",
            {
                "subject": f"3 strategies to 10x your social distribution with {brand_name}",
                "preheader": "How top creators use 60-second voice notes and batch scheduling to save 10+ hours a week.",
                "user_name": user_name,
                "create_post_url": create_post_url,
                "brand_name": brand_name,
                "header_badge": "Playbook",
            },
        )

    def render_reengagement(
        self,
        user_name: str,
        return_url: str = "https://sentinel.ai/dashboard",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the win-back re-engagement email for inactive creators."""
        return self.render(
            "reengagement.html",
            {
                "subject": f"We miss you in {brand_name}, {user_name}! 👋",
                "preheader": f"Jump back in: explore voice-to-post AI generation and multi-channel publishing in {brand_name}.",
                "user_name": user_name,
                "return_url": return_url,
                "brand_name": brand_name,
                "header_badge": "Welcome Back",
            },
        )

    # -------------------------------------------------------------------------
    # Monetization & Billing
    # -------------------------------------------------------------------------
    def render_subscription_confirmation(
        self,
        user_name: str,
        tier_name: str = "Sentinel Pro",
        amount_paid: str = "$228.00 / year",
        renewal_date: str = "November 13, 2027",
        dashboard_url: str = "https://sentinel.ai/dashboard",
        billing_portal_url: str = "https://sentinel.ai/settings/billing",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the subscription confirmation / welcome to Pro receipt email."""
        return self.render(
            "subscription_confirmation.html",
            {
                "subject": f"You're officially on {tier_name}! 🎉",
                "preheader": f"Confirmation of your {tier_name} subscription. All Pro features are active.",
                "user_name": user_name,
                "tier_name": tier_name,
                "amount_paid": amount_paid,
                "renewal_date": renewal_date,
                "dashboard_url": dashboard_url,
                "billing_portal_url": billing_portal_url,
                "brand_name": brand_name,
                "header_badge": "Pro Plan",
            },
        )

    def render_payment_failed(
        self,
        user_name: str,
        invoice_amount: str = "$29.00",
        card_brand: str = "Visa",
        card_last4: str = "4242",
        grace_period_days: int = 5,
        update_payment_url: str = "https://sentinel.ai/settings/billing",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the dunning payment failed notification."""
        return self.render(
            "payment_failed.html",
            {
                "subject": f"Action Required: Payment failed for your {brand_name} subscription",
                "preheader": f"Unable to charge card ending in {card_last4} for {invoice_amount}. Please update your payment method.",
                "user_name": user_name,
                "invoice_amount": invoice_amount,
                "card_brand": card_brand,
                "card_last4": card_last4,
                "grace_period_days": grace_period_days,
                "update_payment_url": update_payment_url,
                "brand_name": brand_name,
                "header_badge": "Billing Notice",
            },
        )

    def render_usage_limit_warning(
        self,
        user_name: str,
        current_usage: int = 40,
        total_limit: int = 50,
        percentage_used: str = "80%",
        reset_date: str = "the 1st of next month",
        upgrade_url: str = "https://sentinel.ai/pricing",
        usage_url: str = "https://sentinel.ai/settings/usage",
        brand_name: str = "Sentinel",
    ) -> str:
        """Render the free quota threshold warning with upgrade CTA."""
        return self.render(
            "usage_limit_warning.html",
            {
                "subject": f"You've used {percentage_used} of your monthly AI quota",
                "preheader": f"You have used {current_usage} of {total_limit} free AI post generations. Upgrade for unlimited access.",
                "user_name": user_name,
                "current_usage": current_usage,
                "total_limit": total_limit,
                "percentage_used": percentage_used,
                "reset_date": reset_date,
                "upgrade_url": upgrade_url,
                "usage_url": usage_url,
                "brand_name": brand_name,
                "header_badge": "Usage Notice",
            },
        )


# Global singleton instance
email_renderer = EmailTemplateRenderer()