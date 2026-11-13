from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class WorkspaceType(str, Enum):
    CONTENT = "content"
    HR = "hr"
    OPERATIONS = "operations"
    SALES = "sales"
    SUPPORT = "support"


class PostStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PARTIALLY_PUBLISHED = "partially_published"
    FAILED = "failed"


class MediaAsset(BaseModel):
    type: Literal["image", "video"]
    url: str
    provider: Literal["cloudinary", "mux"]
    public_id: Optional[str] = None
    thumbnail_url: Optional[str] = None


class LinkedInPostVariant(BaseModel):
    headline: str = Field(description="Captivating opening hook for professional readers")
    body: str = Field(description="Insightful, structured post body with takeaways")
    call_to_action: str = Field(description="Engaging question or prompt to drive comments")
    hashtags: List[str] = Field(default_factory=list, description="Targeted professional hashtags")

    @property
    def formatted_text(self) -> str:
        tag_str = " ".join(self.hashtags) if self.hashtags else ""
        return f"{self.headline}\n\n{self.body}\n\n{self.call_to_action}\n\n{tag_str}".strip()


class XPostVariant(BaseModel):
    text: str = Field(description="Concise, punchy copy within 280 characters")
    hashtags: List[str] = Field(default_factory=list, description="1-2 high-engagement tags")

    @property
    def formatted_text(self) -> str:
        tag_str = " ".join(self.hashtags) if self.hashtags else ""
        if tag_str:
            return f"{self.text}\n\n{tag_str}"
        return self.text


class InstagramPostVariant(BaseModel):
    caption: str = Field(description="Engaging visual-first caption optimized for Instagram feeds and reels")
    call_to_action: str = Field(description="Prompt encouraging saves, shares, or comments")
    hashtags: List[str] = Field(default_factory=list, description="5-8 discoverability hashtags")
    media_guidance: str = Field(description="Brief visual composition tip for the accompanying image or reel")

    @property
    def formatted_text(self) -> str:
        tag_str = " ".join(self.hashtags) if self.hashtags else ""
        parts = [self.caption, self.call_to_action]
        if tag_str:
            parts.append(tag_str)
        return "\n\n".join(p for p in parts if p).strip()


class GeneratedContentPlan(BaseModel):
    intent_summary: str = Field(description="Brief analysis of what the user wants to communicate")
    linkedin: LinkedInPostVariant
    x: XPostVariant
    instagram: InstagramPostVariant
    suggested_media_prompt: Optional[str] = Field(
        None, description="Visual prompt for generating an image if user requests AI media"
    )
    rationale: str = Field(description="Why this angle was chosen for maximum engagement")


class ContentGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=3, description="Natural language prompt describing post goal")
    workspace: WorkspaceType = Field(default=WorkspaceType.CONTENT)
    media: Optional[MediaAsset] = None
    generate_image_prompt: bool = Field(default=False)


class ContentGenerationResponse(BaseModel):
    post_id: str
    plan: GeneratedContentPlan
    media: Optional[MediaAsset] = None
    status: PostStatus


class VoicePostGenerationResponse(BaseModel):
    post_id: str
    transcription: str = Field(description="Clean transcribed speech from the recorded voice memo")
    plan: GeneratedContentPlan
    media: Optional[MediaAsset] = None
    status: PostStatus
