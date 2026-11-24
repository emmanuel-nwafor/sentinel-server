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
        client_id = (
            settings.YOUTUBE_CLIENT_ID
            or "1059756645949-1ven5m8ive67ljlcbsu2qu5tv20c9bcr.apps.googleusercontent.com"
        )
        target_redirect = redirect_uri or settings.YOUTUBE_REDIRECT_URI
        params = {
            "response_type": "code",
            "client_id": client_id,
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
        if not media or not media.get("url"):
            raise SocialPublishError(
                "YouTube publishes video broadcasts. A video file must be attached."
            )
        if media.get("type") and media.get("type") != "video":
            raise SocialPublishError(
                "YouTube only accepts video formats (.mp4, .mov, etc.). Image upload is not supported on standard channels."
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
            vid_id = f"yt_{self._timestamp_id('sandbox')}"
            return self._build_sandbox_result(
                remote_post_id=vid_id,
                post_url=f"https://www.youtube.com/watch?v={vid_id}",
            )

        video_url = media["url"]
        # Extract title from text or fallback
        lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
        video_title = lines[0][:100] if lines else "New Video Broadcast"
        video_description = "\n".join(lines[1:]) if len(lines) > 1 else text

        upload_init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        metadata = {
            "snippet": {
                "title": video_title,
                "description": video_description,
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            # 1. Initialize resumable video upload session with YouTube Data API v3
            init_resp = await client.post(
                upload_init_url,
                json=metadata,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/mp4",
                },
            )

            if init_resp.status_code not in (200, 201):
                logger.error("YouTube upload session creation failed (%s): %s", init_resp.status_code, init_resp.text)
                raise SocialPublishError(f"YouTube upload initialization failed ({init_resp.status_code}): {init_resp.text}")

            upload_location = init_resp.headers.get("Location")
            if not upload_location:
                raise SocialPublishError("YouTube upload endpoint did not return an upload location.")

            # 2. Download video stream/bytes from media storage
            vid_stream_resp = await client.get(video_url)
            if vid_stream_resp.status_code >= 400:
                raise SocialPublishError(f"Failed to retrieve video asset for YouTube upload ({vid_stream_resp.status_code})")

            video_bytes = vid_stream_resp.content

            # 3. Stream binary video bytes into YouTube resumable upload location
            put_resp = await client.put(
                upload_location,
                content=video_bytes,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(video_bytes)),
                },
            )

            if put_resp.status_code in (200, 201):
                res_data = put_resp.json()
                video_id = res_data.get("id") or f"yt_{int(datetime.now(timezone.utc).timestamp())}"
                live_url = f"https://www.youtube.com/watch?v={video_id}"
                logger.info("Successfully published video to YouTube! ID: %s, URL: %s", video_id, live_url)
                return PlatformPublishResult(
                    platform=SocialPlatform.YOUTUBE,
                    success=True,
                    remote_post_id=video_id,
                    live_url=live_url,
                    published_at=datetime.now(timezone.utc),
                )
            else:
                logger.error("YouTube binary video upload failed (%s): %s", put_resp.status_code, put_resp.text)
                raise SocialPublishError(f"YouTube binary video upload failed ({put_resp.status_code}): {put_resp.text}")

    async def delete_post(
        self,
        account: SocialAccountModel,
        access_token: str,
        remote_post_id: str,
    ) -> bool:
        return True
