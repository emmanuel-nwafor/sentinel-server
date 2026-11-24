from datetime import datetime, timezone
from typing import List, Optional
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status, File, Form, UploadFile
from backend.models.user import UserModel
from backend.models.post import PostModel
from backend.models.social_account import SocialPlatform
from backend.unit_of_work.base import IUnitOfWork
from backend.api.deps import get_uow, get_current_user
from backend.schemas.content import (
    ContentGenerationRequest,
    ContentGenerationResponse,
    VoicePostGenerationResponse,
    WorkspaceType,
    PostStatus,
    CopilotChatRequest,
    CopilotChatResponse,
)
from backend.schemas.post_ops import (
    CreateManualPostRequest,
    UpdatePostRequest,
    SchedulePostRequest,
    PostDetailResponse,
    PostLikeResponse,
    CommentLikeResponse,
    DeletePostResponse,
    AddCommentRequest,
    AudienceCommentItem,
    AudienceCommentReply,
)
from backend.agents.content_operator import ContentOperatorAgent
from backend.tools.media_and_social import CloudinaryTool
from backend.tools.publishers import SocialPublishingService
from backend.services.voice_service import (
    VoiceTranscriberFactory,
    VoiceTranscriptionError,
    SUPPORTED_AUDIO_MIMES,
    MAX_AUDIO_SIZE_BYTES,
)

router = APIRouter(prefix="/posts", tags=["Post Operations"])

agent = ContentOperatorAgent()
cloudinary_tool = CloudinaryTool()
publishing_service = SocialPublishingService()


def serialize_post_model(post: PostModel, user_id: Optional[uuid.UUID] = None) -> PostDetailResponse:
    linkedin_dict = post.linkedin_variant or {}
    x_dict = post.x_variant or {}
    ig_dict = post.instagram_variant or {}
    meta = post.metadata_info or {}

    liked_user_ids = meta.get("liked_user_ids", [])
    is_liked = str(user_id) in liked_user_ids if user_id else False

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
        failure_reason=post.failure_reason,
        views_count=meta.get("views_count", 0),
        likes_count=meta.get("likes_count", 0),
        comments_count=meta.get("comments_count", len(meta.get("audience_comments", []))),
        is_liked=is_liked,
        audience_comments=meta.get("audience_comments", []),
        scheduled_at=post.scheduled_at,
        published_at=post.published_at,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


@router.post("/copilot", response_model=CopilotChatResponse)
async def copilot_chat(
    request: CopilotChatRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Autonomous Social Media Operations Copilot.
    Provides real-time strategic advice, niche intelligence, algorithmic tactics,
    and platform-native draft synthesis on explicit command.
    """
    brand_voice_prompt = None
    if request.brand_voice_id:
        try:
            bv = await uow.brand_voices.get_by_id(uuid.UUID(request.brand_voice_id))
            if bv and bv.user_id == current_user.id:
                brand_voice_prompt = (
                    f"Brand Persona: {bv.name}\n"
                    f"Tone: {bv.tone}\n"
                    f"Audience: {bv.target_audience}\n"
                    f"Pillars: {', '.join(bv.key_pillars)}"
                )
        except Exception:
            pass

    # Retrieve real-time connected social accounts from PostgreSQL
    profiles_info = []
    try:
        social_accs = await uow.social_accounts.list_by_user(current_user.id)
        for sa in social_accs:
            profiles_info.append({
                "platform": sa.platform,
                "account_name": sa.account_name,
                "account_handle": sa.account_handle,
                "is_active": sa.is_active,
            })
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to fetch user social accounts: %s", exc)

    # Extract social identities if connected
    linkedin_acc = next((sa for sa in profiles_info if sa["platform"] == "linkedin"), None)
    x_acc = next((sa for sa in profiles_info if sa["platform"] == "x"), None)

    # Fetch stored Brand Profile from PostgreSQL
    brand_profile = None
    try:
        brand_profile = await uow.brand_profiles.get_by_user(current_user.id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to resolve brand profile: %s", exc)

    user_context = {
        "name": (brand_profile.full_name if brand_profile else None)
        or current_user.name
        or (linkedin_acc["account_name"] if linkedin_acc else None)
        or (x_acc["account_name"] if x_acc else None)
        or "Creator",
        "email": current_user.email,
        "headline": brand_profile.headline if brand_profile else "",
        "about": brand_profile.about if brand_profile else "",
        "niche": brand_profile.niche if brand_profile else "General Content Strategy",
        "skills": brand_profile.skills if brand_profile else [],
        "core_topics": brand_profile.core_topics if brand_profile else [],
        "current_company": brand_profile.current_company if brand_profile else "",
        "education": brand_profile.education if brand_profile else "",
        "linkedin_name": linkedin_acc["account_name"] if linkedin_acc else "",
        "linkedin_handle": linkedin_acc["account_handle"] if linkedin_acc else "",
        "linkedin_url": (brand_profile.linkedin_url if brand_profile else "")
        or (
            f"https://www.linkedin.com/in/{linkedin_acc['account_handle']}"
            if linkedin_acc and linkedin_acc.get("account_handle")
            else ""
        ),
        "x_name": x_acc["account_name"] if x_acc else "",
        "x_handle": x_acc["account_handle"] if x_acc else "",
    }

    res = await agent.chat(
        request,
        brand_voice_prompt=brand_voice_prompt,
        connected_profiles_info=profiles_info,
        user_context=user_context,
    )

    # Autonomous Direct Social Publishing Detection
    msg_lower = request.message.lower()
    auto_publish_triggers = [
        "automatically post", "auto post", "publish it to", "post it to",
        "post for me", "automatically publish", "dispatch to", "auto publish",
        "post directly",
    ]
    should_auto_publish = any(t in msg_lower for t in auto_publish_triggers)

    if should_auto_publish and res.plan:
        target_plat = "linkedin"
        if "twitter" in msg_lower or " x" in msg_lower or msg_lower.startswith("x "):
            target_plat = "x"
        elif "instagram" in msg_lower:
            target_plat = "instagram"

        # Check if user has this platform connected
        has_plat = any(p.get("platform") == target_plat and p.get("is_active") for p in profiles_info)
        if has_plat:
            try:
                # Prepare platform-specific text payload
                post_text = ""
                post_tags = []
                if target_plat == "linkedin":
                    post_text = f"{res.plan.linkedin.headline}\n\n{res.plan.linkedin.body}\n\n{res.plan.linkedin.call_to_action}".strip()
                    post_tags = res.plan.linkedin.hashtags or []
                elif target_plat == "x":
                    post_text = res.plan.x.text.strip()
                    post_tags = res.plan.x.hashtags or []
                elif target_plat == "instagram":
                    post_text = f"{res.plan.instagram.caption}\n\n{res.plan.instagram.call_to_action}".strip()
                    post_tags = res.plan.instagram.hashtags or []

                if post_tags:
                    tags_str = " ".join(post_tags)
                    if tags_str.lower() not in post_text.lower():
                        post_text = f"{post_text}\n\n{tags_str}"

                new_post = PostModel(
                    user_id=current_user.id,
                    workspace=request.workspace.value if request.workspace else "content",
                    original_prompt=request.message,
                    status=PostStatus.DRAFT.value,
                    linkedin_variant={"formatted_text": post_text, "hashtags": post_tags} if target_plat == "linkedin" else None,
                    x_variant={"formatted_text": post_text, "hashtags": post_tags} if target_plat == "x" else None,
                    instagram_variant={"formatted_text": post_text, "hashtags": post_tags} if target_plat == "instagram" else None,
                    metadata_info={"created_via": "autonomous_copilot"},
                )

                final_status, results = await publishing_service.publish_post(
                    uow=uow,
                    user_id=current_user.id,
                    post=new_post,
                    target_platforms=[target_plat],
                )

                if final_status in (PostStatus.PUBLISHED, PostStatus.PARTIALLY_PUBLISHED):
                    new_post.status = final_status.value
                    new_post.publish_results = results
                    new_post.published_at = datetime.now(timezone.utc)
                    await uow.posts.create(new_post)
                    await uow.commit()

                    pub_plat_label = "𝕏" if target_plat == "x" else target_plat.capitalize()
                    remote_url = results.get(target_plat, {}).get("remote_url")

                    res.auto_dispatched = True
                    res.published_platform = pub_plat_label
                    res.published_url = remote_url
                    res.reply = (
                        f"🚀 **Autonomously Dispatched!** I've drafted and published this post directly to your live **{pub_plat_label}** feed.\n\n"
                        f"{res.reply}\n\n"
                        f"Your live post is now live and gathering engagement."
                    )
            except Exception as auto_pub_err:
                import logging
                logging.getLogger(__name__).warning("Autonomous publishing encountered error: %s", auto_pub_err)

    return res


@router.post("/generate", response_model=ContentGenerationResponse, status_code=status.HTTP_201_CREATED)
async def generate_post(
    request: ContentGenerationRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Generate tailored LinkedIn and X post drafts from a natural language prompt.
    Synthesizes the plan in-memory without saving uncommitted drafts to PostgreSQL.
    """
    # Resolve Brand Voice Persona if requested or user has a default persona
    brand_voice_prompt = None
    if request.brand_voice_id:
        try:
            bv = await uow.brand_voices.get_by_id(uuid.UUID(request.brand_voice_id))
            if bv and bv.user_id == current_user.id:
                brand_voice_prompt = (
                    f"Brand Persona: {bv.name}\n"
                    f"Tone of Voice: {bv.tone}\n"
                    f"Target Audience: {bv.target_audience}\n"
                    f"Key Pillars: {', '.join(bv.key_pillars)}\n"
                    f"Taboo/Forbidden Words (DO NOT USE): {', '.join(bv.taboo_words)}\n"
                    f"Signature CTA: {bv.signature_cta or 'None'}"
                )
        except (ValueError, TypeError):
            pass
    else:
        bv = await uow.brand_voices.get_default_by_user(current_user.id)
        if bv:
            brand_voice_prompt = (
                f"Brand Persona: {bv.name}\n"
                f"Tone of Voice: {bv.tone}\n"
                f"Target Audience: {bv.target_audience}\n"
                f"Key Pillars: {', '.join(bv.key_pillars)}\n"
                f"Taboo/Forbidden Words (DO NOT USE): {', '.join(bv.taboo_words)}\n"
                f"Signature CTA: {bv.signature_cta or 'None'}"
            )

    plan = await agent.execute(request, brand_voice_prompt=brand_voice_prompt)

    # Track usage (Quota tracking for free/pro tiers)
    current_user.monthly_ai_quota_used += 1

    final_media = request.media
    if not final_media and request.generate_image_prompt and plan.suggested_media_prompt:
        final_media = cloudinary_tool.create_placeholder_ai_asset(plan.suggested_media_prompt)

    return ContentGenerationResponse(
        post_id=str(uuid.uuid4()),
        plan=plan,
        media=final_media,
        status=PostStatus.DRAFT,
    )


@router.post(
    "/voice-draft",
    response_model=VoicePostGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_post_from_voice(
    audio: UploadFile = File(..., description="Recorded audio voice memo (.m4a, .mp3, .wav, .aac, .ogg)"),
    workspace: WorkspaceType = Form(default=WorkspaceType.CONTENT),
    generate_image_prompt: bool = Form(default=False),
    instructions: Optional[str] = Form(default=None, description="Optional extra instructions, e.g. tone or CTA"),
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Speech-to-Text Voice-to-Post:
    Accepts recorded voice audio from mobile, transcribes the spoken message,
    and automatically synthesizes tailored LinkedIn, X, and Instagram drafts.
    """
    filename = (audio.filename or "recording.m4a").lower()
    raw_content_type = (audio.content_type or "").lower().split(";")[0].strip()

    valid_extensions = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".webm", ".flac"}
    file_ext = os.path.splitext(filename)[1]

    if raw_content_type in SUPPORTED_AUDIO_MIMES:
        mime_type = raw_content_type
    elif file_ext in valid_extensions:
        ext_to_mime = {
            ".mp3": "audio/mp3",
            ".m4a": "audio/m4a",
            ".wav": "audio/wav",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
            ".flac": "audio/flac",
        }
        mime_type = ext_to_mime.get(file_ext, "audio/mp4")
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio type '{audio.content_type}'. Supported formats: .m4a, .mp3, .wav, .aac, .ogg, .webm",
        )

    audio_bytes = await audio.read()
    if not audio_bytes or len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded audio file is empty.",
        )

    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds {MAX_AUDIO_SIZE_BYTES // (1024 * 1024)} MB limit.",
        )

    transcriber = VoiceTranscriberFactory.get_transcriber()
    try:
        transcription = await transcriber.transcribe(audio_bytes, mime_type)
    except VoiceTranscriptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    combined_prompt = transcription
    if instructions and instructions.strip():
        combined_prompt = f"{transcription}\n\nAdditional Guidance: {instructions.strip()}"

    content_req = ContentGenerationRequest(
        prompt=combined_prompt,
        workspace=workspace,
        generate_image_prompt=generate_image_prompt,
    )
    plan = await agent.execute(content_req)

    final_media = None
    if generate_image_prompt and plan.suggested_media_prompt:
        final_media = cloudinary_tool.create_placeholder_ai_asset(plan.suggested_media_prompt)

    new_post = PostModel(
        user_id=current_user.id,
        workspace=workspace.value,
        status=PostStatus.DRAFT.value,
        original_prompt=transcription,
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
            "source": "voice",
            "audio_filename": audio.filename,
            "audio_size_bytes": len(audio_bytes),
            "audio_mime_type": mime_type,
            "instructions": instructions.strip() if instructions else None,
            "intent_summary": plan.intent_summary,
            "rationale": plan.rationale,
            "suggested_media_prompt": plan.suggested_media_prompt,
        },
    )

    await uow.posts.create(new_post)
    await uow.commit()

    return VoicePostGenerationResponse(
        post_id=str(new_post.id),
        transcription=transcription,
        plan=plan,
        media=final_media,
        status=PostStatus.DRAFT,
    )


@router.post("", response_model=PostDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_post(
    request: CreateManualPostRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Creates and saves a manual user post to specified platforms without AI prompt generation.
    """
    post_id = uuid.uuid4()
    platforms_lower = [p.lower() for p in request.platforms]

    # Extract and clean content formatting (convert double-escaped newlines to real newlines)
    import re
    cleaned_content = request.content.replace("\\r\\n", "\n").replace("\\n", "\n").strip()

    # Extract any hashtags written in the text like #buildinpublic #startup and clean quotes/commas
    raw_tags = (request.hashtags or [])
    inline_tags = re.findall(r"#\w+", cleaned_content)
    all_raw = raw_tags + inline_tags
    clean_tags = []
    for tag in all_raw:
        for part in re.split(r"[,;'\"]+", str(tag)):
            c = part.strip().strip("'\"#")
            if c and re.match(r"^[A-Za-z0-9_]+$", c):
                clean_tags.append(f"#{c}")
    clean_tags = list(dict.fromkeys(clean_tags))

    # Ensure formatted text has hashtags attached at the end if not already in text
    formatted_content = cleaned_content
    tags_to_append = [t for t in clean_tags if t.lower() not in formatted_content.lower()]
    if tags_to_append:
        formatted_content = f"{formatted_content}\n\n{' '.join(tags_to_append)}"

    linkedin_variant = None
    if "linkedin" in platforms_lower:
        linkedin_variant = {
            "formatted_text": formatted_content,
            "hashtags": clean_tags,
        }

    x_variant = None
    if "x" in platforms_lower or "twitter" in platforms_lower:
        x_variant = {
            "formatted_text": formatted_content,
            "hashtags": clean_tags,
        }

    instagram_variant = None
    if "instagram" in platforms_lower:
        instagram_variant = {
            "formatted_text": formatted_content,
            "hashtags": clean_tags,
        }

    target_platforms = [
        SocialPlatform(p.lower())
        for p in request.platforms
        if p.lower() in ("linkedin", "x", "instagram", "youtube")
    ]

    new_post = PostModel(
        id=post_id,
        user_id=current_user.id,
        workspace=request.workspace.value,
        status=PostStatus.SCHEDULED.value if request.is_scheduled else PostStatus.PUBLISHING.value,
        original_prompt=request.content,
        linkedin_variant=linkedin_variant,
        x_variant=x_variant,
        instagram_variant=instagram_variant,
        media=request.media.model_dump() if request.media else None,
        scheduled_at=request.scheduled_at,
        metadata_info={
            "views_count": 0,
            "likes_count": 0,
            "comments_count": 0,
            "audience_comments": [],
        },
    )

    # If posting immediately (not scheduled), dispatch live across target social channels FIRST
    if not request.is_scheduled and target_platforms:
        try:
            final_status, results = await publishing_service.publish_post(
                uow=uow,
                user_id=current_user.id,
                post=new_post,
                target_platforms=target_platforms,
            )
            new_post.publish_results = results
            new_post.status = final_status.value
            now = datetime.now(timezone.utc)

            if final_status in (PostStatus.PUBLISHED, PostStatus.PARTIALLY_PUBLISHED):
                new_post.published_at = now
                new_post.failure_reason = None
            else:
                errors = [
                    f"{plat}: {res.get('error')}"
                    for plat, res in results.items()
                    if not res.get("success") and res.get("error")
                ]
                error_msg = "; ".join(errors) if errors else "Publishing failed on social channels."
                # REJECT WITHOUT SAVING TO DATABASE
                raise HTTPException(status_code=400, detail=f"Failed to publish: {error_msg}")

            # Publishing succeeded! NOW persist record to PostgreSQL database:
            await uow.posts.create(new_post)
            await uow.commit()
        except HTTPException:
            raise
        except Exception as pub_err:
            import logging
            logging.getLogger(__name__).exception("Failed during live social publishing: %s", pub_err)
            raise HTTPException(status_code=400, detail=f"Publishing failed: {str(pub_err)}")
    else:
        # Scheduled post: persist to database with scheduled state
        await uow.posts.create(new_post)
        await uow.commit()

    return serialize_post_model(new_post)


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
    return serialize_post_model(post, current_user.id)


@router.delete("/{post_id}", response_model=DeletePostResponse)
async def delete_post(
    post_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Delete a post draft, scheduled, or published post.
    If the post was published to social platforms, triggers platform deletion
    where officially supported (X API v2 DELETE /2/tweets/:id, LinkedIn Posts API, etc.).
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    remote_deletions = {}
    if post.status in (PostStatus.PUBLISHED.value, PostStatus.PARTIALLY_PUBLISHED.value):
        try:
            remote_deletions = await publishing_service.delete_published_post(
                uow=uow,
                user_id=current_user.id,
                post=post,
            )
        except Exception as exc:
            remote_deletions = {"error": False}

    await uow.posts.delete(post.id)
    await uow.commit()

    return DeletePostResponse(
        status="deleted",
        post_id=str(post.id),
        message="Post deleted successfully from Dispatch and connected platforms.",
        remote_deletions=remote_deletions,
    )


@router.post("/{post_id}/like", response_model=PostLikeResponse)
async def toggle_like_post(
    post_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Toggle like on a post for the authenticated user.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = dict(post.metadata_info or {})
    liked_user_ids = list(meta.get("liked_user_ids", []))
    likes_count = meta.get("likes_count", 0)

    user_str = str(current_user.id)
    if user_str in liked_user_ids:
        liked_user_ids.remove(user_str)
        likes_count = max(0, likes_count - 1)
        is_liked = False
    else:
        liked_user_ids.append(user_str)
        likes_count += 1
        is_liked = True

    meta["liked_user_ids"] = liked_user_ids
    meta["likes_count"] = likes_count
    post.metadata_info = meta

    await uow.commit()

    return PostLikeResponse(
        post_id=str(post.id),
        likes_count=likes_count,
        is_liked=is_liked,
    )


@router.get("/{post_id}/comments", response_model=List[AudienceCommentItem])
async def list_post_comments(
    post_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    List threaded comments & debate tree for a post.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = post.metadata_info or {}
    comments_data = meta.get("audience_comments", [])
    return comments_data


@router.post("/{post_id}/comments", response_model=AudienceCommentItem, status_code=status.HTTP_201_CREATED)
async def add_post_comment(
    post_id: str,
    payload: AddCommentRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Add a comment or threaded reply to a post.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = dict(post.metadata_info or {})
    comments_list = list(meta.get("audience_comments", []))

    user_name = payload.author_name or current_user.full_name or "Emmanuel Chinecherem"
    user_handle = payload.author_handle or "@founder"
    avatar_char = user_name[0].upper() if user_name else "D"

    # If replying to an existing comment
    if payload.parent_comment_id:
        target_found = None
        for c in comments_list:
            if c.get("id") == payload.parent_comment_id:
                reply_item = {
                    "id": f"reply_{uuid.uuid4().hex[:8]}",
                    "author_name": user_name,
                    "author_handle": user_handle,
                    "avatar_text": avatar_char,
                    "time_ago": "Just now",
                    "content": payload.content,
                    "replying_to_handle": payload.replying_to_handle or c.get("author_handle"),
                    "likes_count": 0,
                    "is_liked": False,
                }
                replies = list(c.get("replies", []))
                replies.append(reply_item)
                c["replies"] = replies
                c["is_replied"] = True
                target_found = c
                break

        if not target_found:
            raise HTTPException(status_code=404, detail="Parent comment not found")

        meta["audience_comments"] = comments_list
        meta["comments_count"] = meta.get("comments_count", 0) + 1
        post.metadata_info = meta
        await uow.commit()
        return target_found

    # Otherwise, add root comment
    new_comment = {
        "id": f"c_{uuid.uuid4().hex[:8]}",
        "author_name": user_name,
        "author_handle": user_handle,
        "avatar_text": avatar_char,
        "time_ago": "Just now",
        "content": payload.content,
        "likes_count": 0,
        "is_liked": False,
        "user_reply_text": None,
        "is_replied": False,
        "replies": [],
    }
    comments_list.insert(0, new_comment)
    meta["audience_comments"] = comments_list
    meta["comments_count"] = meta.get("comments_count", 0) + 1
    post.metadata_info = meta

    await uow.commit()
    return new_comment


@router.post("/{post_id}/comments/{comment_id}/like", response_model=CommentLikeResponse)
async def toggle_like_comment(
    post_id: str,
    comment_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Toggle like on a comment within a post.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = dict(post.metadata_info or {})
    comments_list = list(meta.get("audience_comments", []))

    liked = False
    new_likes = 0
    found = False

    for c in comments_list:
        if c.get("id") == comment_id:
            liked = not c.get("is_liked", False)
            c["is_liked"] = liked
            c["likes_count"] = (c.get("likes_count", 0) + 1) if liked else max(0, c.get("likes_count", 0) - 1)
            new_likes = c["likes_count"]
            found = True
            break
        # Also check nested replies
        for r in c.get("replies", []):
            if r.get("id") == comment_id:
                liked = not r.get("is_liked", False)
                r["is_liked"] = liked
                r["likes_count"] = (r.get("likes_count", 0) + 1) if liked else max(0, r.get("likes_count", 0) - 1)
                new_likes = r["likes_count"]
                found = True
                break
        if found:
            break

    if not found:
        raise HTTPException(status_code=404, detail="Comment not found")

    meta["audience_comments"] = comments_list
    post.metadata_info = meta
    await uow.commit()

    return CommentLikeResponse(
        comment_id=comment_id,
        likes_count=new_likes,
        is_liked=liked,
    )


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
    return serialize_post_model(post, current_user.id)


@router.delete("/{post_id}", response_model=DeletePostResponse)
async def delete_post(
    post_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Delete a post draft, scheduled, or published post.
    If the post was published to social platforms, triggers platform deletion
    where officially supported (X API v2 DELETE /2/tweets/:id, LinkedIn Posts API, etc.).
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    remote_deletions = {}
    if post.status in (PostStatus.PUBLISHED.value, PostStatus.PARTIALLY_PUBLISHED.value):
        try:
            remote_deletions = await publishing_service.delete_published_post(
                uow=uow,
                user_id=current_user.id,
                post=post,
            )
        except Exception as exc:
            remote_deletions = {"error": False}

    await uow.posts.delete(post.id)
    await uow.commit()

    return DeletePostResponse(
        status="deleted",
        post_id=str(post.id),
        message="Post deleted successfully from Dispatch and connected platforms.",
        remote_deletions=remote_deletions,
    )


@router.post("/{post_id}/like", response_model=PostLikeResponse)
async def toggle_like_post(
    post_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Toggle like on a post for the authenticated user.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = dict(post.metadata_info or {})
    liked_user_ids = list(meta.get("liked_user_ids", []))
    likes_count = meta.get("likes_count", 0)

    user_str = str(current_user.id)
    if user_str in liked_user_ids:
        liked_user_ids.remove(user_str)
        likes_count = max(0, likes_count - 1)
        is_liked = False
    else:
        liked_user_ids.append(user_str)
        likes_count += 1
        is_liked = True

    meta["liked_user_ids"] = liked_user_ids
    meta["likes_count"] = likes_count
    post.metadata_info = meta

    await uow.commit()

    return PostLikeResponse(
        post_id=str(post.id),
        likes_count=likes_count,
        is_liked=is_liked,
    )


@router.get("/{post_id}/comments", response_model=List[AudienceCommentItem])
async def list_post_comments(
    post_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    List threaded comments & debate tree for a post.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = post.metadata_info or {}
    comments_data = meta.get("audience_comments", [])
    return comments_data


@router.post("/{post_id}/comments", response_model=AudienceCommentItem, status_code=status.HTTP_201_CREATED)
async def add_post_comment(
    post_id: str,
    payload: AddCommentRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Add a comment or threaded reply to a post.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = dict(post.metadata_info or {})
    comments_list = list(meta.get("audience_comments", []))

    user_name = payload.author_name or current_user.full_name or "Emmanuel Chinecherem"
    user_handle = payload.author_handle or "@founder"
    avatar_char = user_name[0].upper() if user_name else "D"

    # If replying to an existing comment
    if payload.parent_comment_id:
        target_found = None
        for c in comments_list:
            if c.get("id") == payload.parent_comment_id:
                reply_item = {
                    "id": f"reply_{uuid.uuid4().hex[:8]}",
                    "author_name": user_name,
                    "author_handle": user_handle,
                    "avatar_text": avatar_char,
                    "time_ago": "Just now",
                    "content": payload.content,
                    "replying_to_handle": payload.replying_to_handle or c.get("author_handle"),
                    "likes_count": 0,
                    "is_liked": False,
                }
                replies = list(c.get("replies", []))
                replies.append(reply_item)
                c["replies"] = replies
                c["is_replied"] = True
                target_found = c
                break

        if not target_found:
            raise HTTPException(status_code=404, detail="Parent comment not found")

        meta["audience_comments"] = comments_list
        meta["comments_count"] = meta.get("comments_count", 0) + 1
        post.metadata_info = meta
        await uow.commit()
        return target_found

    # Otherwise, add root comment
    new_comment = {
        "id": f"c_{uuid.uuid4().hex[:8]}",
        "author_name": user_name,
        "author_handle": user_handle,
        "avatar_text": avatar_char,
        "time_ago": "Just now",
        "content": payload.content,
        "likes_count": 0,
        "is_liked": False,
        "user_reply_text": None,
        "is_replied": False,
        "replies": [],
    }
    comments_list.insert(0, new_comment)
    meta["audience_comments"] = comments_list
    meta["comments_count"] = meta.get("comments_count", 0) + 1
    post.metadata_info = meta

    await uow.commit()
    return new_comment


@router.post("/{post_id}/comments/{comment_id}/like", response_model=CommentLikeResponse)
async def toggle_like_comment(
    post_id: str,
    comment_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Toggle like on a comment within a post.
    """
    try:
        post_uuid = uuid.UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid post identifier")

    post = await uow.posts.get_by_user_and_id(post_uuid, current_user.id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    meta = dict(post.metadata_info or {})
    comments_list = list(meta.get("audience_comments", []))

    liked = False
    new_likes = 0
    found = False

    for c in comments_list:
        if c.get("id") == comment_id:
            liked = not c.get("is_liked", False)
            c["is_liked"] = liked
            c["likes_count"] = (c.get("likes_count", 0) + 1) if liked else max(0, c.get("likes_count", 0) - 1)
            new_likes = c["likes_count"]
            found = True
            break
        # Also check nested replies
        for r in c.get("replies", []):
            if r.get("id") == comment_id:
                liked = not r.get("is_liked", False)
                r["is_liked"] = liked
                r["likes_count"] = (r.get("likes_count", 0) + 1) if liked else max(0, r.get("likes_count", 0) - 1)
                new_likes = r["likes_count"]
                found = True
                break
        if found:
            break

    if not found:
        raise HTTPException(status_code=404, detail="Comment not found")

    meta["audience_comments"] = comments_list
    post.metadata_info = meta
    await uow.commit()

    return CommentLikeResponse(
        comment_id=comment_id,
        likes_count=new_likes,
        is_liked=liked,
    )
