from datetime import datetime, timedelta, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from backend.core.config import settings
from backend.core.security import (
    create_oauth_state_token,
    verify_oauth_state_token,
    inspect_oauth_state_token,
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


def _render_oauth_callback_html(
    platform_name: str,
    status: str,
    message: str,
    deep_link: str = "dispatch://auth/callback",
) -> HTMLResponse:
    color = (
        "#0A66C2"
        if "linkedin" in platform_name.lower()
        else "#111418"
        if "x" in platform_name.lower()
        else "#E1306C"
    )
    is_ok = status == "success"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sentinel — {platform_name.title()} Connection</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #090a0f;
      color: #ffffff;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 24px;
      box-sizing: border-box;
      text-align: center;
    }}
    .card {{
      background: #141720;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 24px;
      padding: 40px 24px;
      max-width: 380px;
      width: 100%;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
    }}
    .icon {{
      width: 64px;
      height: 64px;
      border-radius: 32px;
      background: {color};
      color: #ffffff;
      font-size: 28px;
      line-height: 64px;
      margin: 0 auto 20px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    h1 {{
      font-size: 20px;
      margin: 0 0 10px;
      font-weight: 700;
    }}
    p {{
      color: #94a3b8;
      font-size: 14px;
      line-height: 1.5;
      margin: 0 0 28px;
    }}
    .btn {{
      display: inline-block;
      background: #1d9bf0;
      color: #ffffff;
      font-weight: 600;
      font-size: 15px;
      padding: 14px 28px;
      border-radius: 14px;
      text-decoration: none;
    }}
  </style>
  <script>
    setTimeout(function() {{
      window.location.href = "{deep_link}";
    }}, 400);
  </script>
</head>
<body>
  <div class="card">
    <div class="icon">{'✓' if is_ok else '✕'}</div>
    <h1>{platform_name.title()} {'Connected!' if is_ok else 'Connection Failed'}</h1>
    <p>{message}</p>
    <a href="{deep_link}" class="btn">Return to Sentinel</a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200 if is_ok else 400)


@router.get("/callback/{platform}")
async def browser_oauth_callback(
    platform: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Browser redirect OAuth callback. Exchanges code, updates database,
    and returns an HTML page that triggers deep linking back to the mobile app.
    """
    platform_name = platform.title()
    if error or not code or not state:
        err_msg = error_description or error or "Authorization code or state was missing."
        return _render_oauth_callback_html(
            platform_name=platform_name,
            status="error",
            message=f"Connection was cancelled or rejected by {platform_name}: {err_msg}",
            deep_link="dispatch://auth/callback?status=cancelled",
        )

    # Inspect state token
    state_info = inspect_oauth_state_token(state)
    if not state_info:
        return _render_oauth_callback_html(
            platform_name=platform_name,
            status="error",
            message="Your connection session expired or is invalid. Please return to Sentinel and try again.",
            deep_link="dispatch://auth/callback?status=error",
        )

    user_id_str = state_info.get("sub")
    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        return _render_oauth_callback_html(
            platform_name=platform_name,
            status="error",
            message="Malformed user reference in OAuth session.",
            deep_link="dispatch://auth/callback?status=error",
        )

    # Resolve platform safely
    try:
        resolved_platform = SocialPlatform(platform.lower())
    except ValueError:
        return _render_oauth_callback_html(
            platform_name=platform_name,
            status="error",
            message=f"Unsupported platform '{platform}'.",
            deep_link="dispatch://auth/callback?status=error",
        )

    try:
        account = await _persist_oauth_bundle(
            uow=uow,
            user_id=user_uuid,
            platform=resolved_platform,
            code=code,
            redirect_uri=None,
        )
        return _render_oauth_callback_html(
            platform_name=resolved_platform.value.title(),
            status="success",
            message=f"Your {resolved_platform.value.title()} account '{account.account_name}' is now linked to Sentinel.",
            deep_link=f"dispatch://auth/callback?status=success&platform={resolved_platform.value}&account={account.account_name}",
        )
    except Exception as exc:
        return _render_oauth_callback_html(
            platform_name=resolved_platform.value.title(),
            status="error",
            message=f"Failed to complete token exchange: {str(exc)}",
            deep_link=f"dispatch://auth/callback?status=error&error={str(exc)}",
        )


@router.get("/callback")
async def browser_oauth_callback_query(
    platform: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Universal query-based callback handler (e.g. /api/v1/social/callback?code=...&state=...)"""
    resolved_platform = platform
    if not resolved_platform and state:
        state_info = inspect_oauth_state_token(state)
        if state_info:
            state_p = state_info.get("platform", "")
            resolved_platform = state_p.replace("login:", "")
    return await browser_oauth_callback(
        platform=resolved_platform or "linkedin",
        code=code,
        state=state,
        error=error,
        error_description=error_description,
        uow=uow,
    )


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
