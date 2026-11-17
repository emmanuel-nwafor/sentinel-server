from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import logging
from backend.core.config import settings
from backend.models.user import UserModel

logger = logging.getLogger(__name__)


@dataclass
class FeatureAccessResult:
    allowed: bool
    reason: str
    is_bypass_active: bool
    feature: str
    tier_required: str = "pro"


class PremiumService:
    """
    Production-grade monetization and feature gating service.
    Designed so that when `ENABLE_PREMIUM_ENFORCEMENT = False`, all users
    have access (grace period / dev mode), and when `True`, strict tier checks
    and quotas apply automatically.
    """

    FEATURE_TIERS: Dict[str, str] = {
        "brand_voice": "pro",
        "priority_scheduling": "pro",
        "unlimited_publishing": "pro",
        "custom_analytics": "pro",
        "dedicated_operator": "enterprise",
        "webhook_integrations": "enterprise",
    }

    @classmethod
    def is_enforcement_active(cls) -> bool:
        return settings.ENABLE_PREMIUM_ENFORCEMENT

    @classmethod
    def check_feature_access(cls, user: UserModel, feature_key: str) -> FeatureAccessResult:
        tier_required = cls.FEATURE_TIERS.get(feature_key, "free")

        # If premium enforcement is turned OFF (current default), grant access cleanly
        if not cls.is_enforcement_active():
            return FeatureAccessResult(
                allowed=True,
                reason="Access granted (Premium enforcement currently inactive)",
                is_bypass_active=True,
                feature=feature_key,
                tier_required=tier_required,
            )

        # Enforcement is active: Check user tier & premium status
        if user.is_premium or user.tier in ["pro", "enterprise"]:
            return FeatureAccessResult(
                allowed=True,
                reason="Access granted via active subscription",
                is_bypass_active=False,
                feature=feature_key,
                tier_required=tier_required,
            )

        # Free tier: Check if feature is restricted to pro/enterprise
        if tier_required in ["pro", "enterprise"]:
            return FeatureAccessResult(
                allowed=False,
                reason=f"Feature '{feature_key}' requires a {tier_required.title()} subscription.",
                is_bypass_active=False,
                feature=feature_key,
                tier_required=tier_required,
            )

        # Quota check for standard free features
        if user.monthly_ai_quota_used >= user.monthly_ai_quota_limit:
            return FeatureAccessResult(
                allowed=False,
                reason=f"Monthly AI quota exceeded ({user.monthly_ai_quota_used}/{user.monthly_ai_quota_limit}).",
                is_bypass_active=False,
                feature=feature_key,
                tier_required="pro",
            )

        return FeatureAccessResult(
            allowed=True,
            reason="Access granted within free tier quota",
            is_bypass_active=False,
            feature=feature_key,
            tier_required="free",
        )

    @classmethod
    def get_tier_plans(cls) -> Dict[str, Any]:
        return {
            "free": {
                "name": "Starter / Free",
                "price": 0.0,
                "billing_period": "month",
                "monthly_quota": settings.DEFAULT_FREE_AI_QUOTA,
                "features": [
                    "Up to 50 AI post generations per month",
                    "Single-channel manual scheduling",
                    "Standard Gemini Flash content engine",
                    "Community support",
                ],
                "badge": "Current Default",
            },
            "pro": {
                "name": "Sentinel Pro",
                "price": settings.PRO_TIER_MONTHLY_PRICE,
                "billing_period": "month",
                "monthly_quota": "Unlimited",
                "features": [
                    "Unlimited multi-channel post generation",
                    "Custom AI Brand Voice Personas (Tone, Taboo Words, Pillars)",
                    "Voice-to-Post mobile recording with instant adaptation",
                    "Priority multi-channel auto-scheduling (LinkedIn, X, Instagram)",
                    "Unified Inbox with real-time AI reply suggestions",
                    "Weekly executive performance digests",
                ],
                "badge": "Most Popular",
            },
            "enterprise": {
                "name": "Sentinel Enterprise",
                "price": settings.ENTERPRISE_TIER_MONTHLY_PRICE,
                "billing_period": "month",
                "monthly_quota": "Unlimited Dedicated",
                "features": [
                    "Everything in Pro",
                    "Multi-account team workspaces and role-based permissions",
                    "Custom fine-tuned brand voice models",
                    "Dedicated SLA (99.95% uptime) & phone support",
                    "Custom webhooks and CRM integrations",
                ],
                "badge": "For Teams",
            },
        }

    @classmethod
    def get_unlocked_features_for_user(cls, user: UserModel) -> List[str]:
        if not cls.is_enforcement_active() or user.is_premium or user.tier in ["pro", "enterprise"]:
            return list(cls.FEATURE_TIERS.keys())
        return ["standard_generation", "manual_scheduling"]
