from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from backend.models.social_account import SocialPlatform
from backend.schemas.content import MediaAsset, WorkspaceType, PostStatus


class UpdatePostRequest(BaseModel):
    linkedin_text: Optional[str] = None
    linkedin_hashtags: Optional[List[str]] = None
    x_text: Optional[str] = None
    x_hashtags: Optional[List[str]] = None
    instagram_text: Optional[str] = None
    instagram_hashtags: Optional[List[str]] = None
    media: Optional[MediaAsset] = None


class SchedulePostRequest(BaseModel):
    scheduled_at: Optional[datetime] = None  # None means publish immediately
    platforms: List[SocialPlatform] = Field(
        default_factory=lambda: [SocialPlatform.LINKEDIN],
        description="Target platforms to publish inside Sentinel",
    )


class PostDetailResponse(BaseModel):
    id: str
    user_id: str
    workspace: WorkspaceType
    status: PostStatus
    original_prompt: str
    linkedin_text: Optional[str] = None
    linkedin_hashtags: List[str] = Field(default_factory=list)
    x_text: Optional[str] = None
    x_hashtags: List[str] = Field(default_factory=list)
    instagram_text: Optional[str] = None
    instagram_hashtags: List[str] = Field(default_factory=list)
    media: Optional[MediaAsset] = None
    publish_results: Optional[Dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
