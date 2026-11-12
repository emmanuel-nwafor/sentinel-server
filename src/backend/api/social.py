from datetime import datetime, timedelta, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.core.config import settings
from backend.core.security import (
    create_oauth_state_token,
    verify_oauth_state_token,
    token_cipher,
)
from backend.models.social_account import SocialAccountModel, SocialPlatform
from backend.models.user import UserModel
from backend.schemas.social import (
    OAuthExchangeRequest,
    OAuthStartResponse,
    SandboxConnectRequest,
    SocialAccountResponse,
)
from backend.tools.publishers import PublisherFactory, SocialPublishError
from backend.unit_of_work.base import IUnitOfWork
from backend.api.deps import get_current_user, get_uow

router = APIRouter(prefix="/social", tags=["Social Connections"])


def _serialize_social_account(account: SocialAccountModel) -> SocialAccountResponse:
    return SocialAccountResponse(
        id=str(account.id),
        platform=SocialPlatform(account.platform),
        platform_account_id=account.platform_account_id,
        account_name=account.account_name,
        account_handle=account.account_handle,
        scopes=account.scopes or [],
        is_active=account.is_active,
        is_sandbox=account.is_sandbox,
        token_expires_at=account.token_expires_at,
        updated_at=account.updated_at,
    )


async def _persist_oauth_bundle(
    uow: IUnitOfWork,
    user_id: uuid.UUID,
    platform: SocialPlatform,
    code: str,
    redirect_uri: Optional[str],
) -> SocialAccountModel:
    publisher = PublisherFactory.get_publisher(platform)
    try:
        bundle = await publisher.exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
    except SocialPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=bundle.expires_in)
        if bundle.expires_in
        else None
    )

    account = await uow.social_accounts.upsert_account(
        user_id=user_id,
        platform=platform.value,
        platform_account_id=bundle.platform_account_id,
        account_name=bundle.account_name,
        account_handle=bundle.account_handle,
        encrypted_access_token=token_cipher.encrypt(bundle.access_token),
        encrypted_refresh_token=(
            token_cipher.encrypt(bundle.refresh_token) if bundle.refresh_token else None
        ),
        token_expires_at=expires_at,
        scopes=bundle.scopes,
        is_sandbox=False,
    )
    await uow.commit()
    return account


@router.get("/accounts", response_model=List[SocialAccountResponse])
async def list_connected_accounts(
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """List all social accounts connected by the current user inside Sentinel."""
    accounts = await uow.social_accounts.list_by_user(current_user.id)
    return [_serialize_social_account(acc) for acc in accounts]


@router.get("/connect/{platform}", response_model=OAuthStartResponse)
async def start_oauth_connection(
    platform: SocialPlatform,
    redirect_uri: Optional[str] = Query(None),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Generate an OAuth 2.0 authorization URL and signed state token
    for an in-app browser/modal consent flow inside Sentinel.
    """
    publisher = PublisherFactory.get_publisher(platform)
    state = create_oauth_state_token(user_id=str(current_user.id), platform=platform.value)
    auth_url = publisher.build_authorization_url(state=state, redirect_uri=redirect_uri)
    configured = publisher.is_oauth_configured()

    notes = (
        None
        if configured
        else f"{platform.value} client keys are not configured in backend/.env yet. Use /sandbox in development."
    )

    return OAuthStartResponse(
        platform=platform,
        authorization_url=auth_url,
        state=state,
        configured=configured,
        sandbox_available=settings.ENVIRONMENT == "development",
        notes=notes,
    )


@router.post("/callback/{platform}", response_model=SocialAccountResponse)
async def exchange_oauth_callback(
    platform: SocialPlatform,
    payload: OAuthExchangeRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Mobile-initiated OAuth code exchange (from Expo AuthSession / WebBrowser)."""
    state_user_id = verify_oauth_state_token(payload.state, platform.value)
    if not state_user_id or state_user_id != str(current_user.id):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state token.")

    account = await _persist_oauth_bundle(
        uow=uow,
        user_id=current_user.id,
        platform=platform,
        code=payload.code,
        redirect_uri=payload.redirect_uri,
    )
    return _serialize_social_account(account)


@router.get("/callback/{platform}", response_model=SocialAccountResponse)
async def browser_oauth_callback(
    platform: SocialPlatform,
    code: str = Query(...),
    state: str = Query(...),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Browser redirect OAuth callback using the signed state parameter to identify the user."""
    state_user_id = verify_oauth_state_token(state, platform.value)
    if not state_user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state token.")

    try:
        user_uuid = uuid.UUID(state_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed user reference in OAuth state.")

    account = await _persist_oauth_bundle(
        uow=uow,
        user_id=user_uuid,
        platform=platform,
        code=code,
        redirect_uri=None,
    )
    return _serialize_social_account(account)


@router.post(
    "/connect/{platform}/sandbox",
    response_model=SocialAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_sandbox_account(
    platform: SocialPlatform,
    payload: SandboxConnectRequest = SandboxConnectRequest(),
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Connect a realistic sandbox account in development mode so end-to-end
    in-app publishing can be tested immediately without external App Review.
    """
    if settings.ENVIRONMENT != "development":
        raise HTTPException(
            status_code=403,
            detail="Sandbox social connections are only permitted in development environment.",
        )

    publisher = PublisherFactory.get_publisher(platform)
    default_name = payload.account_name or f"{current_user.name} ({platform.value.title()} Sandbox)"
    default_handle = payload.account_handle or f"@{current_user.email.split('@')[0]}"

    account = await uow.social_accounts.upsert_account(
        user_id=current_user.id,
        platform=platform.value,
        platform_account_id=f"sandbox_{platform.value}_{str(current_user.id)[:8]}",
        account_name=default_name,
        account_handle=default_handle,
        encrypted_access_token=token_cipher.encrypt(f"sandbox_token_{platform.value}"),
        encrypted_refresh_token=None,
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=60),
        scopes=getattr(publisher, "DEFAULT_SCOPES", []),
        is_sandbox=True,
    )
    await uow.commit()
    return _serialize_social_account(account)


@router.delete("/accounts/{platform}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_social_account(
    platform: SocialPlatform,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Disconnect a social platform from Sentinel."""
    deleted = await uow.social_accounts.delete_by_user_and_platform(
        user_id=current_user.id,
        platform=platform.value,
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No connected {platform.value} account found.",
        )
    await uow.commit()
