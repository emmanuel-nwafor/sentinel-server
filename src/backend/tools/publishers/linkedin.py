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


class LinkedInPublisher(BaseSocialPublisher):
    """
    LinkedIn OAuth 2.0 & Community/Share REST Publisher.
    Publishes directly from Sentinel's server to LinkedIn with zero external app redirects.
    """

    OAUTH_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    OAUTH_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
    USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
    IMAGES_API_URL = "https://api.linkedin.com/rest/images?action=initializeUpload"
    POSTS_API_URL = "https://api.linkedin.com/rest/posts"
    DEFAULT_SCOPES = ["openid", "profile", "email", "w_member_social"]
    MAX_POST_LENGTH = 3000

    @property
    def platform(self) -> SocialPlatform:
        return SocialPlatform.LINKEDIN

    def is_oauth_configured(self) -> bool:
        return bool(settings.LINKEDIN_CLIENT_ID and settings.LINKEDIN_CLIENT_SECRET)

    def build_authorization_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.LINKEDIN_CLIENT_ID or "DEMO_LINKEDIN_CLIENT_ID",
            "redirect_uri": redirect_uri or settings.LINKEDIN_REDIRECT_URI,
            "state": state,
            "scope": " ".join(self.DEFAULT_SCOPES),
        }
        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: Optional[str] = None
    ) -> OAuthTokenBundle:
        if not self.is_oauth_configured():
            raise SocialPublishError(
                "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET must be set in backend/.env."
            )

        target_redirect = redirect_uri or settings.LINKEDIN_REDIRECT_URI
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                self.OAUTH_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.LINKEDIN_CLIENT_ID,
                    "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                    "redirect_uri": target_redirect,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code >= 400:
                raise SocialPublishError(
                    f"LinkedIn token exchange failed ({token_resp.status_code}): {token_resp.text}"
                )

            token_data = token_resp.json()
            access_token = token_data["access_token"]

            profile_resp = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if profile_resp.status_code >= 400:
                raise SocialPublishError(
                    f"LinkedIn profile fetch failed ({profile_resp.status_code}): {profile_resp.text}"
                )

            profile = profile_resp.json()
            person_id = profile.get("sub")
            if not person_id:
                raise SocialPublishError("LinkedIn userinfo response did not include member 'sub'.")

            return OAuthTokenBundle(
                access_token=access_token,
                refresh_token=token_data.get("refresh_token"),
                expires_in=token_data.get("expires_in"),
                platform_account_id=person_id,
                account_name=profile.get("name") or "LinkedIn Member",
                account_handle=profile.get("email"),
                scopes=self.DEFAULT_SCOPES,
            )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokenBundle:
        """Exchange refresh token for fresh LinkedIn access token."""
        if not self.is_oauth_configured():
            raise SocialPublishError("LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET required.")

        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                self.OAUTH_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.LINKEDIN_CLIENT_ID,
                    "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code >= 400:
                raise SocialPublishError(
                    f"LinkedIn token refresh failed ({token_resp.status_code}): {token_resp.text}"
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
            raise SocialPublishError("LinkedIn post text cannot be empty.")
        if len(cleaned) > self.MAX_POST_LENGTH:
            raise SocialPublishError(
                f"LinkedIn post exceeds {self.MAX_POST_LENGTH} characters ({len(cleaned)} given)."
            )

    def _rest_headers(self, access_token: str, version: Optional[str] = None) -> Dict[str, str]:
        v = version if version is not None else (settings.LINKEDIN_API_VERSION or "202411")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        if v:
            cleaned_v = v.strip()
            # If 8-digit date string like 20250101 was configured, convert to 6-digit YYYYMM
            if len(cleaned_v) > 6:
                cleaned_v = cleaned_v[:6]
            headers["LinkedIn-Version"] = cleaned_v
        return headers

    async def _upload_image_asset(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        owner_urn: str,
        image_url: str,
    ) -> str:
        """
        LinkedIn 3-step media upload:
        1) Initialize upload slot to get uploadUrl + image URN.
        2) Stream image bytes from Cloudinary URL.
        3) PUT binary payload directly to LinkedIn's uploadUrl.
        """
        init_resp = await client.post(
            self.IMAGES_API_URL,
            headers=self._rest_headers(access_token),
            json={"initializeUploadRequest": {"owner": owner_urn}},
        )
        if init_resp.status_code >= 400:
            raise SocialPublishError(
                f"LinkedIn image upload init failed ({init_resp.status_code}): {init_resp.text}"
            )

        value = init_resp.json().get("value", {})
        upload_url = value.get("uploadUrl")
        image_urn = value.get("image")
        if not upload_url or not image_urn:
            raise SocialPublishError("LinkedIn image init response missing uploadUrl or image URN.")

        image_bytes, content_type = await self._download_media_bytes(image_url)
        put_resp = await client.put(
            upload_url,
            content=image_bytes,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": content_type,
            },
        )
        if put_resp.status_code >= 400:
            raise SocialPublishError(
                f"LinkedIn binary image upload failed ({put_resp.status_code}): {put_resp.text}"
            )
        return image_urn

    async def publish(
        self,
        account: SocialAccountModel,
        access_token: str,
        text: str,
        media: Optional[Dict[str, Any]] = None,
    ) -> PlatformPublishResult:
        self.validate_content(text, media)

        if account.is_sandbox:
            share_urn = f"urn:li:share:{self._timestamp_id('sandbox')}"
            return self._build_sandbox_result(
                remote_post_id=share_urn,
                post_url=f"https://www.linkedin.com/feed/update/{share_urn}/",
            )

        author_urn = (
            account.platform_account_id
            if account.platform_account_id.startswith("urn:li:")
            else f"urn:li:person:{account.platform_account_id}"
        )

        payload: Dict[str, Any] = {
            "author": author_urn,
            "commentary": text.strip(),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        # Try configured version first, then fallback to active releases if 426 NONEXISTENT_VERSION occurs
        candidate_versions = [None, "202411", "202410", "202409", "202408", "202405", "202401", ""]
        last_error = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            if media and media.get("url"):
                if media.get("type") == "image":
                    image_urn = await self._upload_image_asset(
                        client, access_token, author_urn, media["url"]
                    )
                    payload["content"] = {"media": {"id": image_urn}}
                else:
                    raise SocialPublishError(
                        "Live LinkedIn video upload requires multipart initialization; attach an image or use sandbox mode for video demos."
                    )

            for ver in candidate_versions:
                headers = self._rest_headers(access_token, version=ver)
                post_resp = await client.post(
                    self.POSTS_API_URL,
                    headers=headers,
                    json=payload,
                )
                if post_resp.status_code == 426 and "NONEXISTENT_VERSION" in post_resp.text:
                    last_error = f"LinkedIn post publish failed (426): {post_resp.text}"
                    continue
                elif post_resp.status_code >= 400:
                    raise SocialPublishError(
                        f"LinkedIn post publish failed ({post_resp.status_code}): {post_resp.text}"
                    )
                else:
                    # Successfully posted to LinkedIn!
                    post_urn = post_resp.headers.get("x-restli-id") or f"urn:li:share:{self._timestamp_id('live')}"
                    return PlatformPublishResult(
                        platform=self.platform,
                        success=True,
                        remote_post_id=post_urn,
                        post_url=f"https://www.linkedin.com/feed/update/{post_urn}/",
                        is_sandbox=False,
                        published_at=datetime.now(timezone.utc),
                    )

            if last_error:
                raise SocialPublishError(last_error)

    async def delete_post(
        self,
        account: SocialAccountModel,
        access_token: str,
        remote_post_id: str,
    ) -> bool:
        """
        Delete a post via LinkedIn Posts API DELETE /rest/posts/{postUrn}
        Requires w_member_social scope.
        """
        if account.is_sandbox:
            return True

        from urllib.parse import quote
        encoded_urn = quote(remote_post_id, safe="")
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(
                f"{self.POSTS_API_URL}/{encoded_urn}",
                headers=self._rest_headers(access_token),
            )
            return resp.status_code in (200, 204)
