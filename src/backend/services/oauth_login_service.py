from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlencode
import httpx
from backend.core.config import settings
from backend.core.security import (
    create_access_token,
    create_oauth_state_token,
    token_cipher,
    verify_oauth_state_token,
)
from backend.models.oauth_identity import OAuthIdentityModel, OAuthLoginProvider
from backend.models.social_account import SocialPlatform
from backend.models.user import UserModel
from backend.tools.publishers import OAuthTokenBundle, PublisherFactory, SocialPublishError
from backend.unit_of_work.base import IUnitOfWork


class GoogleOAuthClient:
    """Google OpenID Connect (OIDC) client for Sign in with Google."""

    OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
    DEFAULT_SCOPES = ["openid", "profile", "email"]

    def is_oauth_configured(self) -> bool:
        return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)

    def build_authorization_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID or "DEMO_GOOGLE_CLIENT_ID",
            "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(self.DEFAULT_SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: Optional[str] = None
    ) -> OAuthTokenBundle:
        if not self.is_oauth_configured():
            raise SocialPublishError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in backend/.env."
            )

        target_redirect = redirect_uri or settings.GOOGLE_REDIRECT_URI
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                self.OAUTH_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": target_redirect,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code >= 400:
                raise SocialPublishError(
                    f"Google token exchange failed ({token_resp.status_code}): {token_resp.text}"
                )

            token_data = token_resp.json()
            access_token = token_data["access_token"]

            profile_resp = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if profile_resp.status_code >= 400:
                raise SocialPublishError(
                    f"Google profile fetch failed ({profile_resp.status_code}): {profile_resp.text}"
                )

            profile = profile_resp.json()
            return OAuthTokenBundle(
                access_token=access_token,
                refresh_token=token_data.get("refresh_token"),
                expires_in=token_data.get("expires_in"),
                platform_account_id=profile["sub"],
                account_name=profile.get("name") or "Google User",
                account_handle=profile.get("email"),
                scopes=self.DEFAULT_SCOPES,
            )


class OAuthLoginService:
    """
    Coordinates Social Login (Google, LinkedIn, X) and automatically connects
    LinkedIn / X publishing tokens into `social_accounts` in a single atomic transaction.
    """

    _AUTO_CONNECT_PLATFORMS = {
        OAuthLoginProvider.LINKEDIN: SocialPlatform.LINKEDIN,
        OAuthLoginProvider.X: SocialPlatform.X,
    }

    def __init__(self):
        self._google_client = GoogleOAuthClient()

    def get_provider_client(self, provider: OAuthLoginProvider):
        if provider == OAuthLoginProvider.GOOGLE:
            return self._google_client
        return PublisherFactory.get_publisher(SocialPlatform(provider.value))

    def build_login_start(
        self, provider: OAuthLoginProvider, redirect_uri: Optional[str] = None
    ) -> dict:
        client = self.get_provider_client(provider)
        state = create_oauth_state_token(
            user_id="oauth_login",
            platform=f"login:{provider.value}",
        )
        return {
            "provider": provider,
            "authorization_url": client.build_authorization_url(
                state=state,
                redirect_uri=redirect_uri,
            ),
            "state": state,
            "configured": client.is_oauth_configured(),
            "auto_connects_publishing": provider in self._AUTO_CONNECT_PLATFORMS,
        }

    @staticmethod
    def verify_login_state(state: str, provider: OAuthLoginProvider) -> bool:
        sub = verify_oauth_state_token(state, expected_platform=f"login:{provider.value}")
        return sub == "oauth_login"

    async def authenticate_with_bundle(
        self,
        *,
        uow: IUnitOfWork,
        provider: OAuthLoginProvider,
        bundle: OAuthTokenBundle,
        is_sandbox: bool = False,
    ) -> Tuple[str, UserModel, List[str]]:
        identity = await uow.oauth_identities.get_by_provider_identity(
            provider=provider.value,
            provider_user_id=bundle.platform_account_id,
        )

        verified_email = (
            bundle.account_handle.lower().strip()
            if bundle.account_handle and "@" in bundle.account_handle
            else None
        )

        user: Optional[UserModel] = None
        if identity:
            user = await uow.users.get_by_id(identity.user_id)

        if not user and verified_email:
            user = await uow.users.get_by_email(verified_email)

        if not user:
            fallback_email = (
                verified_email
                or f"{provider.value}_{bundle.platform_account_id}@oauth.sentinel.local"
            )
            user = UserModel(
                name=bundle.account_name,
                email=fallback_email,
                hashed_password=None,
                role="user",
                is_verified=True,
            )
            await uow.users.create(user)
        elif not user.is_verified:
            user.is_verified = True

        if not identity:
            await uow.oauth_identities.create(
                OAuthIdentityModel(
                    user_id=user.id,
                    provider=provider.value,
                    provider_user_id=bundle.platform_account_id,
                    email=verified_email,
                )
            )

        auto_connected: List[str] = []
        target_platform = self._AUTO_CONNECT_PLATFORMS.get(provider)
        if target_platform:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=bundle.expires_in)
                if bundle.expires_in
                else None
            )
            await uow.social_accounts.upsert_account(
                user_id=user.id,
                platform=target_platform.value,
                platform_account_id=bundle.platform_account_id,
                account_name=bundle.account_name,
                account_handle=bundle.account_handle,
                encrypted_access_token=token_cipher.encrypt(bundle.access_token),
                encrypted_refresh_token=(
                    token_cipher.encrypt(bundle.refresh_token)
                    if bundle.refresh_token
                    else None
                ),
                token_expires_at=expires_at,
                scopes=bundle.scopes,
                is_sandbox=is_sandbox,
            )
            auto_connected.append(target_platform.value)

        await uow.commit()
        jwt_token = create_access_token(data={"sub": str(user.id), "email": user.email})
        return jwt_token, user, auto_connected


oauth_login_service = OAuthLoginService()
