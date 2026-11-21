from datetime import datetime, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import httpx
from backend.core.config import settings
from backend.models.social_account import SocialAccountModel, SocialPlatform
from backend.schemas.social import PlatformPublishResult
from backend.tools.publishers.base import (
    BaseSocialPublisher,
    OAuthTokenBundle,
    SocialPublishError,
)


class XPublisher(BaseSocialPublisher):
    """
    X (Twitter) API v2 Publisher.
    Executes server-side tweet creation via OAuth 2.0 Bearer token inside Sentinel.
    """

    OAUTH_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
    OAUTH_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
    USERS_ME_URL = "https://api.twitter.com/2/users/me"
    TWEETS_URL = "https://api.twitter.com/2/tweets"
    DEFAULT_SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access"]
    MAX_POST_LENGTH = 280

    @property
    def platform(self) -> SocialPlatform:
        return SocialPlatform.X

    def is_oauth_configured(self) -> bool:
        return bool(settings.X_CLIENT_ID and settings.X_CLIENT_SECRET)

    def build_authorization_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.X_CLIENT_ID or "DEMO_X_CLIENT_ID",
            "redirect_uri": redirect_uri or settings.X_REDIRECT_URI,
            "scope": " ".join(self.DEFAULT_SCOPES),
            "state": state,
            "code_challenge": "challenge",
            "code_challenge_method": "plain",
        }
        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: Optional[str] = None
    ) -> OAuthTokenBundle:
        if not self.is_oauth_configured():
            raise SocialPublishError("X_CLIENT_ID and X_CLIENT_SECRET must be set in backend/.env.")

        target_redirect = redirect_uri or settings.X_REDIRECT_URI
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                self.OAUTH_TOKEN_URL,
                auth=(settings.X_CLIENT_ID, settings.X_CLIENT_SECRET),
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": target_redirect,
                    "code_verifier": "challenge",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code >= 400:
                raise SocialPublishError(
                    f"X token exchange failed ({token_resp.status_code}): {token_resp.text}"
                )

            token_data = token_resp.json()
            access_token = token_data["access_token"]

            me_resp = await client.get(
                f"{self.USERS_ME_URL}?user.fields=profile_image_url",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if me_resp.status_code >= 400:
                raise SocialPublishError(
                    f"X profile fetch failed ({me_resp.status_code}): {me_resp.text}"
                )

            user_data = me_resp.json().get("data", {})
            raw_pic = user_data.get("profile_image_url")
            pic = raw_pic.replace("_normal.", "_400x400.") if raw_pic else None
            return OAuthTokenBundle(
                access_token=access_token,
                refresh_token=token_data.get("refresh_token"),
                expires_in=token_data.get("expires_in"),
                platform_account_id=user_data["id"],
                account_name=user_data.get("name") or "X User",
                account_handle=f"@{user_data['username']}" if user_data.get("username") else None,
                profile_picture_url=pic,
                scopes=self.DEFAULT_SCOPES,
            )

    async def get_profile_picture(self, access_token: str) -> Optional[str]:
        """Fetch user's live profile picture URL from Twitter/X API v2."""
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    f"{self.USERS_ME_URL}?user.fields=profile_image_url",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    pic = data.get("profile_image_url")
                    if pic:
                        return pic.replace("_normal.", "_400x400.")
        except Exception:
            pass
        return None

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokenBundle:
        """Exchange stored refresh token for fresh OAuth 2.0 access and refresh tokens."""
        if not self.is_oauth_configured():
            raise SocialPublishError("X_CLIENT_ID and X_CLIENT_SECRET are required for token refresh.")

        auth = (settings.X_CLIENT_ID, settings.X_CLIENT_SECRET) if settings.X_CLIENT_SECRET else None
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if not auth:
            data["client_id"] = settings.X_CLIENT_ID

        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                self.OAUTH_TOKEN_URL,
                auth=auth,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code >= 400:
                raise SocialPublishError(
                    f"X token refresh failed ({token_resp.status_code}): {token_resp.text}"
                )

            token_data = token_resp.json()
            return OAuthTokenBundle(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token") or refresh_token,
                expires_in=token_data.get("expires_in"),
                platform_account_id="",
                account_name="",
                scopes=self.DEFAULT_SCOPES,
            )

    def validate_content(self, text: str, media: Optional[Dict[str, Any]] = None) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            raise SocialPublishError("X post text cannot be empty.")
        if len(cleaned) > self.MAX_POST_LENGTH:
            raise SocialPublishError(
                f"X post exceeds {self.MAX_POST_LENGTH} characters ({len(cleaned)} given)."
            )

    async def publish(
        self,
        account: SocialAccountModel,
        access_token: str,
        text: str,
        media: Optional[Dict[str, Any]] = None,
    ) -> PlatformPublishResult:
        self.validate_content(text, media)

        if account.is_sandbox:
            tweet_id = self._timestamp_id("x_tweet")
            handle = (account.account_handle or "sentinel").lstrip("@")
            return self._build_sandbox_result(
                remote_post_id=tweet_id,
                post_url=f"https://x.com/{handle}/status/{tweet_id}",
            )

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.TWEETS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"text": text.strip()},
            )
            if resp.status_code == 402:
                raise SocialPublishError(
                    "X API credits depleted (402 Payment Required). Your X Developer Project is set to 'Pay Per Use' with $0 balance. Please add credits at console.x.com or switch project tier."
                )
            if resp.status_code >= 400:
                raise SocialPublishError(
                    f"X publish failed ({resp.status_code}): {resp.text}"
                )

            tweet_id = resp.json().get("data", {}).get("id", self._timestamp_id("x"))
            handle = (account.account_handle or "i/web").lstrip("@")
            return PlatformPublishResult(
                platform=self.platform,
                success=True,
                remote_post_id=tweet_id,
                post_url=f"https://x.com/{handle}/status/{tweet_id}",
                is_sandbox=False,
                published_at=datetime.now(timezone.utc),
            )

    async def delete_post(
        self,
        account: SocialAccountModel,
        access_token: str,
        remote_post_id: str,
    ) -> bool:
        """
        Delete a tweet via X API v2 DELETE /2/tweets/:id
        Requires OAuth 2.0 user-context with tweet.write scope.
        """
        if account.is_sandbox:
            return True

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(
                f"{self.TWEETS_URL}/{remote_post_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return resp.status_code in (200, 204)
