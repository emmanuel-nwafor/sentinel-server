import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.config import settings
from backend.core.database import get_db_session
from backend.models.user import UserModel
from backend.models.post import PostModel
from backend.models.social_account import SocialAccountModel
from backend.schemas.admin import (
    AdminBroadcastRequest,
    AdminBroadcastResponse,
    AdminMetricsSummary,
    AdminOverviewResponse,
    AdminPostListItem,
    AdminPostListResponse,
    AdminUpdateUserRoleRequest,
    AdminUpdateUserStatusRequest,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    SystemHealthStatus,
)
from backend.services.email_service import get_email_service
from backend.tools.media_and_social import CloudflareR2Tool, MuxTool, CloudinaryTool
from backend.api.deps import get_current_admin_user, get_uow
from backend.unit_of_work.base import IUnitOfWork

router = APIRouter(prefix="/admin", tags=["Admin Operations"])
logger = logging.getLogger(__name__)

r2_tool = CloudflareR2Tool()
cloudinary_tool = CloudinaryTool()
mux_tool = MuxTool()


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(
    admin: UserModel = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    High-level operational overview for executive and ops dashboards:
    User distribution, post status distribution, connected social platform stats, and system health.
    """
    # 1. User metrics
    total_users = await session.scalar(select(func.count(UserModel.id))) or 0
    verified_users = await session.scalar(select(func.count(UserModel.id)).where(UserModel.is_verified == True)) or 0
    unverified_users = total_users - verified_users
    admin_count = await session.scalar(select(func.count(UserModel.id)).where(UserModel.role == "admin")) or 0
    creator_count = await session.scalar(select(func.count(UserModel.id)).where(UserModel.role == "creator")) or 0

    # 2. Post metrics
    total_posts = await session.scalar(select(func.count(PostModel.id))) or 0
    published_posts = await session.scalar(select(func.count(PostModel.id)).where(PostModel.status == "published")) or 0
    scheduled_posts = await session.scalar(select(func.count(PostModel.id)).where(PostModel.status == "scheduled")) or 0
    failed_posts = await session.scalar(select(func.count(PostModel.id)).where(PostModel.status == "failed")) or 0
    draft_posts = await session.scalar(select(func.count(PostModel.id)).where(PostModel.status == "draft")) or 0

    # 3. Social connections
    total_accounts = await session.scalar(select(func.count(SocialAccountModel.id))) or 0
    platforms_query = select(SocialAccountModel.platform, func.count(SocialAccountModel.id)).group_by(SocialAccountModel.platform)
    platform_rows = (await session.execute(platforms_query)).all()
    platform_breakdown = {row[0]: row[1] for row in platform_rows}

    # 4. Recent registrations
    recent_users_q = select(UserModel).order_by(desc(UserModel.created_at)).limit(5)
    recent_users = (await session.execute(recent_users_q)).scalars().all()
    recent_registrations = [
        {
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_verified": u.is_verified,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in recent_users
    ]

    # 5. Recent published posts
    recent_posts_q = (
        select(PostModel, UserModel)
        .join(UserModel, PostModel.user_id == UserModel.id)
        .where(PostModel.status == "published")
        .order_by(desc(PostModel.published_at))
        .limit(5)
    )
    recent_posts_rows = (await session.execute(recent_posts_q)).all()
    recent_published = [
        {
            "id": str(p.id),
            "author_name": u.name,
            "author_email": u.email,
            "workspace": p.workspace,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "has_media": bool(p.media),
        }
        for p, u in recent_posts_rows
    ]

    # Active media provider detection
    if r2_tool.is_configured:
        active_media = "Cloudflare R2 (Primary)"
    elif mux_tool.is_configured and cloudinary_tool.is_configured:
        active_media = "Hybrid (MUX Videos + Cloudinary Images)"
    elif mux_tool.is_configured:
        active_media = "MUX (Videos only)"
    else:
        active_media = "Development Sandbox"

    gemini_status = "Active (gemini-3.5-flash-lite)" if settings.GEMINI_API_KEY else "Fallback Mode"

    return AdminOverviewResponse(
        metrics=AdminMetricsSummary(
            total_users=total_users,
            verified_users=verified_users,
            unverified_users=unverified_users,
            admin_count=admin_count,
            creator_count=creator_count,
            total_posts=total_posts,
            published_posts=published_posts,
            scheduled_posts=scheduled_posts,
            failed_posts=failed_posts,
            draft_posts=draft_posts,
            connected_social_accounts=total_accounts,
            platform_breakdown=platform_breakdown,
        ),
        system=SystemHealthStatus(
            database="Neon PostgreSQL (Async SQLAlchemy 2.0 Pool)",
            gemini_ai=gemini_status,
            active_media_provider=active_media,
            environment=settings.ENVIRONMENT,
            server_time=datetime.now(timezone.utc),
        ),
        recent_registrations=recent_registrations,
        recent_published_posts=recent_published,
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    query: Optional[str] = Query(None, description="Search by name or email"),
    role: Optional[str] = Query(None, description="Filter by role (user, creator, admin, pro)"),
    is_verified: Optional[bool] = Query(None, description="Filter by verification state"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: UserModel = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Search and paginate registered platform users with attached platform & post counts.
    """
    stmt = select(UserModel)

    if query:
        clean = f"%{query.strip().lower()}%"
        stmt = stmt.where(or_(UserModel.name.ilike(clean), UserModel.email.ilike(clean)))
    if role:
        stmt = stmt.where(UserModel.role == role.lower())
    if is_verified is not None:
        stmt = stmt.where(UserModel.is_verified == is_verified)

    # Count total matching
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    # Fetch slice
    stmt = stmt.order_by(desc(UserModel.created_at)).limit(limit).offset(offset)
    users = (await session.execute(stmt)).scalars().all()

    # Enrich with platforms and posts count
    user_items: List[AdminUserListItem] = []
    for u in users:
        # Connected platforms
        plat_q = select(SocialAccountModel.platform).where(
            SocialAccountModel.user_id == u.id,
            SocialAccountModel.is_active == True,
        )
        platforms = [p for p in (await session.execute(plat_q)).scalars().all()]

        # Total posts
        post_count_q = select(func.count(PostModel.id)).where(PostModel.user_id == u.id)
        post_count = await session.scalar(post_count_q) or 0

        user_items.append(
            AdminUserListItem(
                id=str(u.id),
                name=u.name,
                email=u.email,
                role=u.role,
                is_verified=u.is_verified,
                is_active=True,
                created_at=u.created_at,
                connected_platforms=platforms,
                total_posts=post_count,
            )
        )

    return AdminUserListResponse(
        total=total,
        limit=limit,
        offset=offset,
        users=user_items,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user_detail(
    user_id: uuid.UUID,
    admin: UserModel = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Full operational profile for a single user: connected social accounts, post statuses, and recent posts.
    """
    user = await session.get(UserModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Connected accounts
    acc_q = select(SocialAccountModel).where(SocialAccountModel.user_id == user.id)
    accounts = (await session.execute(acc_q)).scalars().all()
    connected_accounts = [
        {
            "id": str(a.id),
            "platform": a.platform,
            "account_name": a.account_name,
            "account_handle": a.account_handle,
            "is_active": a.is_active,
            "is_sandbox": a.is_sandbox,
            "token_expires_at": a.token_expires_at.isoformat() if a.token_expires_at else None,
        }
        for a in accounts
    ]

    # Post counts
    status_counts_q = select(PostModel.status, func.count(PostModel.id)).where(PostModel.user_id == user.id).group_by(PostModel.status)
    status_counts = {row[0]: row[1] for row in (await session.execute(status_counts_q)).all()}

    # Recent posts
    recent_p_q = select(PostModel).where(PostModel.user_id == user.id).order_by(desc(PostModel.created_at)).limit(5)
    recent_posts = (await session.execute(recent_p_q)).scalars().all()
    recent_posts_list = [
        {
            "id": str(p.id),
            "workspace": p.workspace,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "media_url": p.media.get("url") if p.media else None,
        }
        for p in recent_posts
    ]

    return AdminUserDetailResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        is_verified=user.is_verified,
        is_active=True,
        created_at=user.created_at,
        connected_accounts=connected_accounts,
        post_counts=status_counts,
        recent_posts=recent_posts_list,
    )


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: uuid.UUID,
    payload: AdminUpdateUserRoleRequest,
    admin: UserModel = Depends(get_current_admin_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Promote or update a user's role (e.g. promote to 'admin', 'creator', or 'pro').
    """
    user = await uow.users.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user.role
    user.role = payload.role.lower()
    await uow.commit()

    return {
        "message": f"User {user.email} role updated from {old_role} to {user.role}.",
        "user_id": str(user.id),
        "role": user.role,
    }


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: uuid.UUID,
    payload: AdminUpdateUserStatusRequest,
    admin: UserModel = Depends(get_current_admin_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Manually toggle a user's verification status or active flag.
    """
    user = await uow.users.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.is_verified is not None:
        user.is_verified = payload.is_verified
    await uow.commit()

    return {
        "message": f"User {user.email} status updated.",
        "user_id": str(user.id),
        "is_verified": user.is_verified,
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    admin: UserModel = Depends(get_current_admin_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Deactivate and delete a user account and purge active session tokens.
    """
    user = await uow.users.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own active admin account.")

    # Remove associated social accounts and posts
    await uow.social_accounts.delete_user_accounts(user.id)
    await uow.users.delete(user.id)
    await uow.commit()

    return {
        "message": f"User {user.email} and all associated credentials removed successfully.",
        "user_id": str(user.id),
    }


@router.get("/posts", response_model=AdminPostListResponse)
async def list_global_posts(
    status: Optional[str] = Query(None, description="Filter by status (published, draft, scheduled, failed)"),
    workspace: Optional[str] = Query(None, description="Filter by workspace (content, hr, etc.)"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: UserModel = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Global post moderation feed across all users on the platform.
    """
    stmt = select(PostModel, UserModel).join(UserModel, PostModel.user_id == UserModel.id)

    if status:
        stmt = stmt.where(PostModel.status == status.lower())
    if workspace:
        stmt = stmt.where(PostModel.workspace == workspace.lower())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    stmt = stmt.order_by(desc(PostModel.created_at)).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()

    items: List[AdminPostListItem] = []
    for post, author in rows:
        plan = post.content_plan or {}
        linkedin_preview = (plan.get("linkedin") or {}).get("headline") if isinstance(plan, dict) else None
        x_preview = (plan.get("x") or {}).get("text") if isinstance(plan, dict) else None

        items.append(
            AdminPostListItem(
                id=str(post.id),
                user_id=str(author.id),
                author_name=author.name,
                author_email=author.email,
                workspace=post.workspace,
                status=post.status,
                created_at=post.created_at,
                scheduled_at=post.scheduled_at,
                published_at=post.published_at,
                has_media=bool(post.media),
                media_provider=(post.media or {}).get("provider") if post.media else None,
                linkedin_preview=linkedin_preview,
                x_preview=x_preview,
            )
        )

    return AdminPostListResponse(
        total=total,
        limit=limit,
        offset=offset,
        posts=items,
    )


@router.delete("/posts/{post_id}")
async def admin_delete_post(
    post_id: uuid.UUID,
    admin: UserModel = Depends(get_current_admin_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Moderation endpoint: forcibly remove a broken, infringing, or flagged post.
    """
    post = await uow.posts.get_by_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    await uow.posts.delete(post.id)
    await uow.commit()

    return {"message": f"Post {post_id} removed by admin.", "post_id": str(post_id)}


@router.post("/broadcast", response_model=AdminBroadcastResponse)
async def broadcast_announcement(
    payload: AdminBroadcastRequest,
    admin: UserModel = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Broadcast a system announcement or product update to registered verified users via Brevo transactional emails.
    """
    query = select(UserModel).where(UserModel.is_verified == True)
    if payload.target_role:
        query = query.where(UserModel.role == payload.target_role.lower())

    recipients = (await session.execute(query)).scalars().all()
    if not recipients:
        return AdminBroadcastResponse(
            dispatched_count=0,
            failed_count=0,
            message="No verified users found matching target criteria.",
        )

    email_service = get_email_service()
    dispatched = 0
    failed = 0

    for user in recipients:
        try:
            await email_service.send_marketing_announcement_email(
                to_email=user.email,
                user_name=user.name,
                announcement_title=payload.announcement_title,
                announcement_body=payload.body_text,
                cta_label=payload.call_to_action_label or "Open Dispatch",
                cta_url=payload.call_to_action_url or "https://dispatch.io",
            )
            dispatched += 1
        except Exception as exc:
            logger.warning("Broadcast delivery failed for %s: %s", user.email, exc)
            failed += 1

    return AdminBroadcastResponse(
        dispatched_count=dispatched,
        failed_count=failed,
        message=f"Broadcast complete. Dispatched {dispatched} emails ({failed} failed).",
    )
