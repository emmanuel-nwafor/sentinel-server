from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.core.config import settings
from backend.core.security import (
    create_access_token,
    generate_otp_code,
    hash_otp,
    hash_password,
    verify_otp_hash,
    verify_password,
)
from backend.models.oauth_identity import OAuthLoginProvider
from backend.models.user import UserModel
from backend.schemas.auth import (
    LoginRequest,
    OAuthLoginCallbackRequest,
    OAuthLoginStartResponse,
    OAuthSandboxLoginRequest,
    OAuthTokenResponse,
    RegisterRequest,
    RegisterResponse,
    ResendOtpRequest,
    TokenResponse,
    UserResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from backend.services.email_service import EmailDeliveryError, get_email_service
from backend.services.oauth_login_service import oauth_login_service
from backend.tools.publishers import OAuthTokenBundle, SocialPublishError
from backend.unit_of_work.base import IUnitOfWork
from backend.api.deps import get_current_user, get_uow

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _serialize_user(user: UserModel) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        is_verified=user.is_verified,
    )


async def _issue_and_send_otp(uow: IUnitOfWork, user: UserModel) -> None:
    otp_code = generate_otp_code(length=6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    await uow.email_otps.upsert_otp(
        user_id=user.id,
        otp_hash=hash_otp(otp_code, user.email),
        expires_at=expires_at,
    )
    await uow.commit()

    email_service = get_email_service()
    try:
        await email_service.send_otp_email(
            to_email=user.email,
            user_name=user.name,
            otp_code=otp_code,
        )
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to deliver verification email: {exc}",
        ) from exc


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, uow: IUnitOfWork = Depends(get_uow)):
    existing_user = await uow.users.get_by_email(request.email)
    if existing_user:
        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A verified user with this email address already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account already registered and awaiting OTP verification. Call /auth/resend-otp.",
        )

    new_user = UserModel(
        name=request.name.strip(),
        email=request.email.lower().strip(),
        hashed_password=hash_password(request.password),
        role="user",
        is_verified=False,
    )
    await uow.users.create(new_user)
    await _issue_and_send_otp(uow, new_user)

    return RegisterResponse(
        message="Account created. Please check your email for your 6-digit verification code.",
        email=new_user.email,
        requires_verification=True,
    )


@router.post("/verify-otp", response_model=VerifyOtpResponse)
async def verify_otp(request: VerifyOtpRequest, uow: IUnitOfWork = Depends(get_uow)):
    user = await uow.users.get_by_email(request.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if user.is_verified:
        return VerifyOtpResponse(
            message="Email is already verified. You can log in.",
            email=user.email,
            verified=True,
        )

    otp_record = await uow.email_otps.get_by_user_id(user.id)
    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active verification code found. Please request a new OTP.",
        )

    now = datetime.now(timezone.utc)
    if otp_record.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new OTP.",
        )

    if otp_record.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP attempts exceeded. Please request a new OTP.",
        )

    if not verify_otp_hash(request.otp, user.email, otp_record.otp_hash):
        otp_record.attempts += 1
        await uow.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    user.is_verified = True
    await uow.email_otps.delete_by_user_id(user.id)
    await uow.commit()

    return VerifyOtpResponse(
        message="Email verified successfully. You can now log in.",
        email=user.email,
        verified=True,
    )


@router.post("/resend-otp", response_model=RegisterResponse)
async def resend_otp(request: ResendOtpRequest, uow: IUnitOfWork = Depends(get_uow)):
    user = await uow.users.get_by_email(request.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified. Please log in.",
        )

    existing_otp = await uow.email_otps.get_by_user_id(user.id)
    if existing_otp:
        elapsed = (datetime.now(timezone.utc) - existing_otp.last_sent_at).total_seconds()
        if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
            wait_seconds = int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait_seconds} seconds before requesting another code.",
            )

    await _issue_and_send_otp(uow, user)
    return RegisterResponse(
        message="A new 6-digit verification code has been sent to your email.",
        email=user.email,
        requires_verification=True,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, uow: IUnitOfWork = Depends(get_uow)):
    user = await uow.users.get_by_email(request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses social sign-in (Google/LinkedIn/X). Please continue with your social provider.",
        )

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your OTP before logging in.",
        )

    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return TokenResponse(access_token=token, user=_serialize_user(user))


@router.get("/oauth/{provider}", response_model=OAuthLoginStartResponse)
async def start_social_login(
    provider: OAuthLoginProvider,
    redirect_uri: Optional[str] = Query(None),
):
    """
    Generate an OAuth authorization URL + signed state for Continue with Google / LinkedIn / X.
    """
    info = oauth_login_service.build_login_start(provider=provider, redirect_uri=redirect_uri)
    return OAuthLoginStartResponse(
        **info,
        sandbox_available=settings.ENVIRONMENT == "development",
    )


@router.post("/oauth/{provider}/callback", response_model=OAuthTokenResponse)
async def complete_social_login(
    provider: OAuthLoginProvider,
    payload: OAuthLoginCallbackRequest,
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Exchange OAuth code, sign in or register the Sentinel user, and auto-connect
    LinkedIn / X publishing tokens in the same transaction.
    """
    if not oauth_login_service.verify_login_state(payload.state, provider):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth login state.")

    client = oauth_login_service.get_provider_client(provider)
    try:
        bundle = await client.exchange_code_for_tokens(
            code=payload.code,
            redirect_uri=payload.redirect_uri,
        )
    except SocialPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token, user, auto_connected = await oauth_login_service.authenticate_with_bundle(
        uow=uow,
        provider=provider,
        bundle=bundle,
        is_sandbox=False,
    )
    return OAuthTokenResponse(
        access_token=token,
        user=_serialize_user(user),
        auto_connected_platforms=auto_connected,
    )


@router.post("/oauth/{provider}/sandbox", response_model=OAuthTokenResponse)
async def sandbox_social_login(
    provider: OAuthLoginProvider,
    payload: OAuthSandboxLoginRequest = OAuthSandboxLoginRequest(),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Dev-only endpoint simulating Continue with Google / LinkedIn / X.
    Logs the user in and auto-connects LinkedIn/X publishing in one step.
    """
    if settings.ENVIRONMENT != "development":
        raise HTTPException(
            status_code=403,
            detail="Sandbox social login is only permitted in development environment.",
        )

    client = oauth_login_service.get_provider_client(provider)
    clean_slug = "".join(c.lower() if c.isalnum() else "_" for c in payload.name).strip("_") or "user"
    resolved_email = payload.email or f"{clean_slug}_{provider.value}@sandbox.sentinel.local"
    account_handle = (
        payload.handle
        if provider == OAuthLoginProvider.X
        else resolved_email
    )

    bundle = OAuthTokenBundle(
        access_token=f"sandbox_login_token_{provider.value}_{clean_slug}",
        platform_account_id=f"sandbox_{provider.value}_{clean_slug}",
        account_name=payload.name,
        account_handle=account_handle,
        expires_in=60 * 60 * 24 * 60,
        scopes=getattr(client, "DEFAULT_SCOPES", []),
    )
    token, user, auto_connected = await oauth_login_service.authenticate_with_bundle(
        uow=uow,
        provider=provider,
        bundle=bundle,
        is_sandbox=True,
    )
    return OAuthTokenResponse(
        access_token=token,
        user=_serialize_user(user),
        auto_connected_platforms=auto_connected,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserModel = Depends(get_current_user)):
    return _serialize_user(current_user)
