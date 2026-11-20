from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from backend.models.social_account import SocialPlatform
from backend.schemas.content import MediaAsset, WorkspaceType, PostStatus


class CreateManualPostRequest(BaseModel):
    content: str
    platforms: List[str] = Field(default_factory=lambda: ["x"])
    hashtags: Optional[List[str]] = Field(default_factory=list)
    media: Optional[MediaAsset] = None
    workspace: WorkspaceType = WorkspaceType.CONTENT
    is_scheduled: bool = False
    scheduled_at: Optional[datetime] = None


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


class AudienceCommentReply(BaseModel):
    id: str
    author_name: str
    author_handle: str
    avatar_text: Optional[str] = None
    time_ago: str = "Just now"
    content: str
    replying_to_handle: Optional[str] = None
    likes_count: int = 0
    is_liked: bool = False


class AudienceCommentItem(BaseModel):
    id: str
    author_name: str
    author_handle: str
    avatar_text: Optional[str] = None
    time_ago: str = "Just now"
    content: str
    likes_count: int = 0
    is_liked: bool = False
    user_reply_text: Optional[str] = None
    is_replied: bool = False
    replies: List[AudienceCommentReply] = Field(default_factory=list)


class AddCommentRequest(BaseModel):
    content: str
    author_name: Optional[str] = None
    author_handle: Optional[str] = None
    parent_comment_id: Optional[str] = None
    replying_to_handle: Optional[str] = None


class PostLikeResponse(BaseModel):
    post_id: str
    likes_count: int
    is_liked: bool


class CommentLikeResponse(BaseModel):
    comment_id: str
    likes_count: int
    is_liked: bool


class DeletePostResponse(BaseModel):
    status: str
    post_id: str
    message: str
    remote_deletions: Optional[Dict[str, bool]] = None


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
    failure_reason: Optional[str] = None
    views_count: int = 0
    likes_count: int = 0
    comments_count: int = 0
    is_liked: bool = False
    audience_comments: List[AudienceCommentItem] = Field(default_factory=list)
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
