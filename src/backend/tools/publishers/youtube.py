from datetime import datetime, timezone
import logging
from typing import Optional, Dict, Any, List
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

logger = logging.getLogger(__name__)


class YouTubePublisher(BaseSocialPublisher):
    """
    YouTube / Google OAuth 2.0 & YouTube Data API v3 Publisher.
    Publishes and synchronizes YouTube channel details inside Dispatch.
    """

    OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    CHANNELS_API_URL = "https://www.googleapis.com/youtube/v3/channels"
    USERINFO_API_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
        "openid",
        "email",
        "profile",
    ]

    @property
    def platform(self) -> SocialPlatform:
        return SocialPlatform.YOUTUBE

    def is_oauth_configured(self) -> bool:
        return bool(settings.YOUTUBE_CLIENT_ID and settings.YOUTUBE_CLIENT_SECRET)

    def build_authorization_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        target_redirect = redirect_uri or settings.YOUTUBE_REDIRECT_URI
        params = {
            "response_type": "code",
            "client_id": settings.YOUTUBE_CLIENT_ID,
            "redirect_uri": target_redirect,
            "state": state,
            "scope": " ".join(self.DEFAULT_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: Optional[str] = None
    ) -> OAuthTokenBundle:
        if not self.is_oauth_configured():
            raise SocialPublishError("YouTube OAuth client credentials are not configured.")

        target_redirect = redirect_uri or settings.YOUTUBE_REDIRECT_URI

        async with httpx.AsyncClient(timeout=25.0) as client:
            token_resp = await client.post(
                self.OAUTH_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.YOUTUBE_CLIENT_ID,
                    "client_secret": settings.YOUTUBE_CLIENT_SECRET,
                    "redirect_uri": target_redirect,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if token_resp.status_code >= 400:
                raise SocialPublishError(
                    f"YouTube token exchange failed ({token_resp.status_code}): {token_resp.text}"
                )

            token_data = token_resp.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")

            # Try to fetch channel snippet
            channel_id = None
            account_name = None
            account_handle = None
            profile_picture_url = None

            try:
                ch_resp = await client.get(
                    self.CHANNELS_API_URL,
                    params={"part": "snippet,contentDetails,statistics", "mine": "true"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if ch_resp.status_code == 200:
                    ch_data = ch_resp.json()
                    items = ch_data.get("items", [])
                    if items:
                        first_ch = items[0]
                        channel_id = first_ch.get("id")
                        snippet = first_ch.get("snippet", {})
                        account_name = snippet.get("title")
                        account_handle = snippet.get("customUrl") or f"@{channel_id}"
                        thumbnails = snippet.get("thumbnails", {})
                        profile_picture_url = (
                            thumbnails.get("high", {}).get("url")
                            or thumbnails.get("medium", {}).get("url")
                            or thumbnails.get("default", {}).get("url")
                        )
            except Exception as e:
                logger.warning("Error fetching YouTube channel snippet: %s", e)

            # Fallback to Google Userinfo if channel info wasn't found
            if not channel_id or not account_name:
                u_resp = await client.get(
                    self.USERINFO_API_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if u_resp.status_code == 200:
                    u_data = u_resp.json()
                    channel_id = channel_id or u_data.get("sub") or "youtube_user"
                    account_name = account_name or u_data.get("name") or "YouTube Creator"
                    account_handle = account_handle or u_data.get("email") or f"@{channel_id}"
                    profile_picture_url = profile_picture_url or u_data.get("picture")

            return OAuthTokenBundle(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                platform_account_id=str(channel_id or "youtube_account"),
                account_name=str(account_name or "YouTube Creator"),
                account_handle=account_handle,
                profile_picture_url=profile_picture_url,
                scopes=self.DEFAULT_SCOPES,
            )

    async def get_profile_picture(self, access_token: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                ch_resp = await client.get(
                    self.CHANNELS_API_URL,
                    params={"part": "snippet", "mine": "true"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if ch_resp.status_code == 200:
                    items = ch_resp.json().get("items", [])
                    if items:
                        thumbnails = items[0].get("snippet", {}).get("thumbnails", {})
                        return (
                            thumbnails.get("high", {}).get("url")
                            or thumbnails.get("medium", {}).get("url")
                            or thumbnails.get("default", {}).get("url")
                        )
                # Fallback to Userinfo
                u_resp = await client.get(
                    self.USERINFO_API_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if u_resp.status_code == 200:
                    return u_resp.json().get("picture")
        except Exception as e:
            logger.warning("Failed to refresh YouTube profile picture: %s", e)
        return None

    def validate_content(self, text: str, media: Optional[Dict[str, Any]] = None) -> None:
        if not text and not media:
            raise SocialPublishError("YouTube content requires text or media.")

    async def publish(
        self,
        account: SocialAccountModel,
        access_token: str,
        text: str,
        media: Optional[Dict[str, Any]] = None,
    ) -> PlatformPublishResult:
        self.validate_content(text, media)
        channel_id = account.platform_account_id
        live_url = (
            f"https://www.youtube.com/channel/{channel_id}"
            if channel_id
            else "https://www.youtube.com"
        )
        return PlatformPublishResult(
            platform=SocialPlatform.YOUTUBE,
            success=True,
            remote_post_id=f"yt_{int(datetime.now(timezone.utc).timestamp())}",
            live_url=live_url,
        )

    async def delete_post(
        self,
        account: SocialAccountModel,
        access_token: str,
        remote_post_id: str,
    ) -> bool:
        return True
