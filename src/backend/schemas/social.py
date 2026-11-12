from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from backend.models.social_account import SocialPlatform


class SocialAccountResponse(BaseModel):
    """Public representation of a connected social account (never returns tokens)."""

    id: str
    platform: SocialPlatform
    platform_account_id: str
    account_name: str
    account_handle: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    is_active: bool
    is_sandbox: bool
    token_expires_at: Optional[datetime] = None
    updated_at: datetime


class OAuthStartResponse(BaseModel):
    """Returned to the mobile app so it can open the in-app OAuth consent modal."""

    platform: SocialPlatform
    authorization_url: str
    state: str
    configured: bool
    sandbox_available: bool = True
    notes: Optional[str] = None


class OAuthExchangeRequest(BaseModel):
    """Sent by the mobile app or callback handler after user authorizes inside the modal."""

    code: str = Field(..., min_length=4)
    state: str = Field(..., min_length=8)
    redirect_uri: Optional[str] = None


class SandboxConnectRequest(BaseModel):
    """Creates a realistic local sandbox connection for testing in-app publishing immediately."""

    account_name: Optional[str] = Field(None, max_length=120)
    account_handle: Optional[str] = Field(None, max_length=120)


class PlatformPublishResult(BaseModel):
    """Outcome of publishing to a single social platform."""

    platform: SocialPlatform
    success: bool
    remote_post_id: Optional[str] = None
    post_url: Optional[str] = None
    is_sandbox: bool = False
    error: Optional[str] = None
    published_at: Optional[datetime] = None


class MultiPlatformPublishSummary(BaseModel):
    """Aggregated outcome across all requested platforms."""

    overall_status: str
    results: Dict[str, PlatformPublishResult]
