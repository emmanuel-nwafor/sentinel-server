import logging
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

logger = logging.getLogger(__name__)


class InstagramPublisher(BaseSocialPublisher):
    """
    Instagram Graph API Publisher (2-Step Media Container -> Publish).
    Consumes public Cloudinary image or MUX video URLs directly from Meta's servers.
    """

    DEFAULT_SCOPES = [
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
    ]
    MAX_CAPTION_LENGTH = 2200

    @property
    def platform(self) -> SocialPlatform:
        return SocialPlatform.INSTAGRAM

    @property
    def _graph_base(self) -> str:
        return f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}"

    def is_oauth_configured(self) -> bool:
        return bool(settings.META_APP_ID and settings.META_APP_SECRET)

    def build_authorization_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        target_redirect = redirect_uri or settings.META_REDIRECT_URI
        params: Dict[str, Any] = {
            "client_id": settings.META_APP_ID or "1650463666534776",
            "config_id": settings.META_CONFIG_ID or "1886402302343483",
            "display": "popup",
            "override_default_response_type": "true",
            "redirect_uri": target_redirect,
            "response_type": "code",
            "state": state,
            "prompt": "login",
        }
        return f"https://www.facebook.com/dialog/oauth?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: Optional[str] = None
    ) -> OAuthTokenBundle:
        if not self.is_oauth_configured():
            raise SocialPublishError(
                "META_APP_ID and META_APP_SECRET must be set in backend/.env."
            )

        target_redirect = redirect_uri or settings.META_REDIRECT_URI
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.get(
                f"{self._graph_base}/oauth/access_token",
                params={
                    "client_id": settings.META_APP_ID or "1650463666534776",
                    "client_secret": settings.META_APP_SECRET,
                    "redirect_uri": target_redirect,
                    "code": code,
                },
            )
            if token_resp.status_code >= 400:
                raise SocialPublishError(
                    f"Meta token exchange failed ({token_resp.status_code}): {token_resp.text}"
                )

            token_data = token_resp.json()
            access_token = token_data["access_token"]

            ig_account = None
            avatar_url = None

            # 1. Primary Unified Login method: /me/assigned_instagram_accounts
            try:
                assigned_resp = await client.get(
                    f"{self._graph_base}/me/assigned_instagram_accounts",
                    params={
                        "fields": "id,username,name,profile_picture_url",
                        "access_token": access_token,
                    },
                )
                if assigned_resp.status_code == 200:
                    assigned_data = assigned_resp.json().get("data", [])
                    if assigned_data:
                        ig_account = assigned_data[0]
                        avatar_url = ig_account.get("profile_picture_url")
            except Exception as e:
                logger.warning("Failed to fetch assigned_instagram_accounts: %s", e)

            # 2. Fallback: Facebook Pages linked accounts
            if not ig_account:
                try:
                    pages_resp = await client.get(
                        f"{self._graph_base}/me/accounts",
                        params={
                            "fields": "id,name,instagram_business_account{id,username,name,profile_picture_url}",
                            "access_token": access_token,
                        },
                    )
                    if pages_resp.status_code == 200:
                        for page in pages_resp.json().get("data", []):
                            if page.get("instagram_business_account"):
                                ig_account = page["instagram_business_account"]
                                avatar_url = ig_account.get("profile_picture_url")
                                break
                except Exception as e:
                    logger.warning("Failed to fetch me/accounts: %s", e)

            # 3. Fallback: /me directly
            if not ig_account:
                try:
                    me_resp = await client.get(
                        f"{self._graph_base}/me",
                        params={
                            "fields": "id,name,username",
                            "access_token": access_token,
                        },
                    )
                    if me_resp.status_code == 200:
                        me_data = me_resp.json()
                        ig_account = {
                            "id": me_data.get("id"),
                            "username": me_data.get("username") or me_data.get("name"),
                            "name": me_data.get("name"),
                        }
                except Exception as e:
                    logger.warning("Failed to fetch me directly: %s", e)

            if not ig_account:
                raise SocialPublishError(
                    "No linked Instagram Professional or Creator account found. Please ensure you have accepted the tester invite or linked your Instagram account in Meta Unified Login."
                )

            # If avatar wasn't found yet, attempt /{id}?fields=profile_picture_url
            if not avatar_url and ig_account.get("id"):
                try:
                    pic_resp = await client.get(
                        f"{self._graph_base}/{ig_account['id']}",
                        params={
                            "fields": "profile_picture_url",
                            "access_token": access_token,
                        },
                    )
                    if pic_resp.status_code == 200:
                        avatar_url = pic_resp.json().get("profile_picture_url")
                except Exception:
                    pass

            return OAuthTokenBundle(
                access_token=access_token,
                expires_in=token_data.get("expires_in"),
                platform_account_id=str(ig_account["id"]),
                account_name=ig_account.get("name") or ig_account.get("username") or "Instagram Creator",
                account_handle=f"@{ig_account['username']}" if ig_account.get("username") else None,
                profile_picture_url=avatar_url,
                scopes=self.DEFAULT_SCOPES,
            )

    async def get_profile_picture(self, access_token: str) -> Optional[str]:
        """Fetch user's live Instagram profile picture URL."""
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    f"{self._graph_base}/me/assigned_instagram_accounts",
                    params={
                        "fields": "id,username,profile_picture_url",
                        "access_token": access_token,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data and data[0].get("profile_picture_url"):
                        return data[0]["profile_picture_url"]
        except Exception:
            pass
        return None

    def validate_content(self, text: str, media: Optional[Dict[str, Any]] = None) -> None:
        cleaned = (text or "").strip()
        if len(cleaned) > self.MAX_CAPTION_LENGTH:
            raise SocialPublishError(
                f"Instagram caption exceeds {self.MAX_CAPTION_LENGTH} characters ({len(cleaned)} given)."
            )
        if not media or not media.get("url"):
            raise SocialPublishError(
                "Instagram requires an attached image (Cloudinary) or video (MUX) URL to publish."
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
            ig_media_id = self._timestamp_id("ig_media")
            return self._build_sandbox_result(
                remote_post_id=ig_media_id,
                post_url=f"https://www.instagram.com/p/{ig_media_id}/",
            )

        assert media is not None
        container_params: Dict[str, Any] = {
            "caption": text.strip(),
            "access_token": access_token,
        }
        if media.get("type") == "video":
            container_params["media_type"] = "REELS"
            container_params["video_url"] = media["url"]
        else:
            container_params["image_url"] = media["url"]

        ig_user_id = account.platform_account_id
        async with httpx.AsyncClient(timeout=30.0) as client:
            container_resp = await client.post(
                f"{self._graph_base}/{ig_user_id}/media",
                data=container_params,
            )
            if container_resp.status_code >= 400:
                raise SocialPublishError(
                    f"Instagram container creation failed ({container_resp.status_code}): {container_resp.text}"
                )

            creation_id = container_resp.json().get("id")
            if not creation_id:
                raise SocialPublishError("Instagram container creation did not return an id.")

            publish_resp = await client.post(
                f"{self._graph_base}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": access_token},
            )
            if publish_resp.status_code >= 400:
                raise SocialPublishError(
                    f"Instagram publish failed ({publish_resp.status_code}): {publish_resp.text}"
                )

            media_id = publish_resp.json().get("id", creation_id)
            return PlatformPublishResult(
                platform=self.platform,
                success=True,
                remote_post_id=media_id,
                post_url=f"https://www.instagram.com/p/{media_id}/",
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
        Delete media via Instagram Graph API DELETE /{ig-media-id}
        """
        if account.is_sandbox:
            return True

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(
                f"{self._graph_base}/{remote_post_id}",
                params={"access_token": access_token},
            )
            return resp.status_code in (200, 204)
