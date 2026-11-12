from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.models.user import UserModel
from backend.models.post import PostModel
from backend.unit_of_work.base import IUnitOfWork
from backend.api.deps import get_uow, get_current_user
from backend.schemas.content import (
    ContentGenerationRequest,
    ContentGenerationResponse,
    WorkspaceType,
    PostStatus,
)
from backend.schemas.post_ops import UpdatePostRequest, SchedulePostRequest, PostDetailResponse
from backend.agents.content_operator import ContentOperatorAgent
from backend.tools.media_and_social import CloudinaryTool
from backend.tools.publishers import SocialPublishingService

router = APIRouter(prefix="/posts", tags=["Post Operations"])

agent = ContentOperatorAgent()
cloudinary_tool = CloudinaryTool()
publishing_service = SocialPublishingService()


def serialize_post_model(post: PostModel) -> PostDetailResponse:
    linkedin_dict = post.linkedin_variant or {}
    x_dict = post.x_variant or {}
    ig_dict = post.instagram_variant or {}

    return PostDetailResponse(
        id=str(post.id),
        user_id=str(post.user_id),
        workspace=WorkspaceType(post.workspace),
        status=PostStatus(post.status),
        original_prompt=post.original_prompt,
        linkedin_text=linkedin_dict.get("formatted_text"),
        linkedin_hashtags=linkedin_dict.get("hashtags", []),
        x_text=x_dict.get("formatted_text"),
        x_hashtags=x_dict.get("hashtags", []),
        instagram_text=ig_dict.get("formatted_text"),
        instagram_hashtags=ig_dict.get("hashtags", []),
        media=post.media,
        publish_results=post.publish_results,
        scheduled_at=post.scheduled_at,
        published_at=post.published_at,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


@router.post("/generate", response_model=ContentGenerationResponse, status_code=status.HTTP_201_CREATED)
async def generate_post(
    request: ContentGenerationRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Generate tailored LinkedIn and X post drafts from a natural language prompt.
    Saves state into PostgreSQL via Unit of Work / PostRepository.
    """
    plan = await agent.execute(request)

    final_media = request.media
    if not final_media and request.generate_image_prompt and plan.suggested_media_prompt:
        final_media = cloudinary_tool.create_placeholder_ai_asset(plan.suggested_media_prompt)

    new_post = PostModel(
        user_id=current_user.id,
        workspace=request.workspace.value,
        status=PostStatus.DRAFT.value,
        original_prompt=request.prompt,
        linkedin_variant={
            "formatted_text": plan.linkedin.formatted_text,
            "headline": plan.linkedin.headline,
            "body": plan.linkedin.body,
            "call_to_action": plan.linkedin.call_to_action,
            "hashtags": plan.linkedin.hashtags,
        },
        x_variant={
            "formatted_text": plan.x.formatted_text,
            "text": plan.x.text,
            "hashtags": plan.x.hashtags,
        },
        instagram_variant={
            "formatted_text": plan.instagram.formatted_text,
            "caption": plan.instagram.caption,
            "call_to_action": plan.instagram.call_to_action,
            "hashtags": plan.instagram.hashtags,
            "media_guidance": plan.instagram.media_guidance,
        },
        media=final_media.model_dump() if final_media else None,
        metadata_info={
            "intent_summary": plan.intent_summary,
            "rationale": plan.rationale,
            "suggested_media_prompt": plan.suggested_media_prompt,
        },
    )

    await uow.posts.create(new_post)
    await uow.commit()

    return ContentGenerationResponse(
        post_id=str(new_post.id),
        plan=plan,
        media=final_media,
        status=PostStatus.DRAFT,
    )


@router.get("", response_model=List[PostDetailResponse])
async def list_user_posts(
    workspace: Optional[WorkspaceType] = None,
    post_status: Optional[PostStatus] = Query(None, alias="status"),
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    posts = await uow.posts.get_user_posts(
        user_id=current_user.id,
        workspace=workspace.value if workspace else None,
        status=post_status.value if post_status else None,
    )
    return [serialize_post_model(p) for p in posts]


@router.get("/{post_id}", response_model=PostDetailResponse)
async def get_post_by_id(
    post_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return serialize_post_model(post)


@router.put("/{post_id}", response_model=PostDetailResponse)
async def update_post_draft(
    post_id: str,
    update_data: UpdatePostRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.status not in [PostStatus.DRAFT.value, PostStatus.FAILED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit post in '{post.status}' state.",
        )

    # Update variants
    if update_data.linkedin_text is not None or update_data.linkedin_hashtags is not None:
        li_dict = dict(post.linkedin_variant or {})
        if update_data.linkedin_text is not None:
            li_dict["formatted_text"] = update_data.linkedin_text
        if update_data.linkedin_hashtags is not None:
            li_dict["hashtags"] = update_data.linkedin_hashtags
        post.linkedin_variant = li_dict

    if update_data.x_text is not None or update_data.x_hashtags is not None:
        x_dict = dict(post.x_variant or {})
        if update_data.x_text is not None:
            x_dict["formatted_text"] = update_data.x_text
        if update_data.x_hashtags is not None:
            x_dict["hashtags"] = update_data.x_hashtags
        post.x_variant = x_dict

    if update_data.instagram_text is not None or update_data.instagram_hashtags is not None:
        ig_dict = dict(post.instagram_variant or {})
        if update_data.instagram_text is not None:
            ig_dict["formatted_text"] = update_data.instagram_text
        if update_data.instagram_hashtags is not None:
            ig_dict["hashtags"] = update_data.instagram_hashtags
        post.instagram_variant = ig_dict

    if update_data.media is not None:
        post.media = update_data.media.model_dump()

    await uow.commit()
    return serialize_post_model(post)


@router.post("/{post_id}/schedule", response_model=PostDetailResponse)
async def schedule_or_publish_post(
    post_id: str,
    schedule_data: SchedulePostRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    now = datetime.now(timezone.utc)
    scheduled_time = schedule_data.scheduled_at

    if scheduled_time and scheduled_time > now:
        post.status = PostStatus.SCHEDULED.value
        post.scheduled_at = scheduled_time
        post.metadata_info = {
            **(post.metadata_info or {}),
            "target_platforms": [p.value for p in schedule_data.platforms],
        }
    else:
        post.status = PostStatus.PUBLISHING.value
        final_status, results = await publishing_service.publish_post(
            uow=uow,
            user_id=current_user.id,
            post=post,
            target_platforms=schedule_data.platforms,
        )
        post.publish_results = results
        post.status = final_status.value
        if final_status in (PostStatus.PUBLISHED, PostStatus.PARTIALLY_PUBLISHED):
            post.published_at = now
            post.failure_reason = None
        else:
            errors = [
                f"{plat}: {res.get('error')}"
                for plat, res in results.items()
                if not res.get("success") and res.get("error")
            ]
            post.failure_reason = "; ".join(errors) if errors else "Publishing failed."

    await uow.commit()
    return serialize_post_model(post)
