from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field


class BrandVoiceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="e.g. Founder Storyteller")
    tone: str = Field(..., min_length=2, max_length=255, description="e.g. authoritative, concise, analytical")
    target_audience: str = Field(..., min_length=2, max_length=255, description="e.g. Tech Founders & Engineering Leaders")
    key_pillars: List[str] = Field(default_factory=list, description="Core themes to focus on")
    taboo_words: List[str] = Field(default_factory=list, description="Cliche or banned words the AI must never use")
    signature_cta: Optional[str] = Field(None, max_length=255, description="Default sign-off question or CTA")
    sample_post: Optional[str] = Field(None, description="Gold-standard sample post the AI should emulate")
    is_default: bool = Field(default=False)


class BrandVoiceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    tone: Optional[str] = Field(None, min_length=2, max_length=255)
    target_audience: Optional[str] = Field(None, min_length=2, max_length=255)
    key_pillars: Optional[List[str]] = None
    taboo_words: Optional[List[str]] = None
    signature_cta: Optional[str] = None
    sample_post: Optional[str] = None
    is_default: Optional[bool] = None


class BrandVoiceResponse(BaseModel):
    id: str
    user_id: str
    name: str
    tone: str
    target_audience: str
    key_pillars: List[str]
    taboo_words: List[str]
    signature_cta: Optional[str] = None
    sample_post: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class SubscriptionStatusResponse(BaseModel):
    tier: str
    is_premium: bool
    subscription_status: str
    premium_expires_at: Optional[datetime] = None
    monthly_ai_quota_used: int
    monthly_ai_quota_limit: int
    quota_remaining: int
    enforcement_active: bool
    features_unlocked: List[str]


class PlanFeatureComparisonResponse(BaseModel):
    plans: dict
    enforcement_active: bool
