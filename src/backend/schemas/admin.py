from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid
from pydantic import BaseModel, Field


class AdminMetricsSummary(BaseModel):
    total_users: int
    verified_users: int
    unverified_users: int
    admin_count: int
    creator_count: int
    total_posts: int
    published_posts: int
    scheduled_posts: int
    failed_posts: int
    draft_posts: int
    connected_social_accounts: int
    platform_breakdown: Dict[str, int]


class SystemHealthStatus(BaseModel):
    database: str
    gemini_ai: str
    active_media_provider: str
    environment: str
    server_time: datetime


class AdminOverviewResponse(BaseModel):
    metrics: AdminMetricsSummary
    system: SystemHealthStatus
    recent_registrations: List[Dict[str, Any]]
    recent_published_posts: List[Dict[str, Any]]


class AdminUserListItem(BaseModel):
    id: str
    name: str
    email: str
    role: str
    is_verified: bool
    is_active: bool
    created_at: datetime
    connected_platforms: List[str]
    total_posts: int


class AdminUserListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    users: List[AdminUserListItem]


class AdminUserDetailResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    is_verified: bool
    is_active: bool
    created_at: datetime
    connected_accounts: List[Dict[str, Any]]
    post_counts: Dict[str, int]
    recent_posts: List[Dict[str, Any]]


class AdminUpdateUserRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|creator|user|pro)$", description="New role for the user")


class AdminUpdateUserStatusRequest(BaseModel):
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


class AdminPostListItem(BaseModel):
    id: str
    user_id: str
    author_name: str
    author_email: str
    workspace: str
    status: str
    created_at: datetime
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    has_media: bool
    media_provider: Optional[str] = None
    linkedin_preview: Optional[str] = None
    x_preview: Optional[str] = None


class AdminPostListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    posts: List[AdminPostListItem]


class AdminBroadcastRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=150)
    announcement_title: str = Field(..., min_length=3, max_length=150)
    body_text: str = Field(..., min_length=10)
    call_to_action_url: Optional[str] = None
    call_to_action_label: Optional[str] = None
    target_role: Optional[str] = Field(None, description="Optional filter by role ('user', 'creator', etc.). None sends to all verified users.")


class AdminBroadcastResponse(BaseModel):
    dispatched_count: int
    failed_count: int
    message: str
