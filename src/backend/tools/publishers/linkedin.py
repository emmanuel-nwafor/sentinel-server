from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
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
    VIDEOS_API_URL = "https://api.linkedin.com/rest/videos?action=initializeUpload"
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
                profile_picture_url=profile.get("picture"),
                scopes=self.DEFAULT_SCOPES,
            )

    async def get_profile_picture(self, access_token: str) -> Optional[str]:
        """Fetch member's live profile picture URL from LinkedIn userinfo."""
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    self.USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if resp.status_code == 200:
                    return resp.json().get("picture")
        except Exception:
            pass
        return None

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
        v = version if version is not None else (settings.LINKEDIN_API_VERSION or "202611")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        if v:
            cleaned_v = v.strip()
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
        candidate_versions: Optional[List[str]] = None,
    ) -> str:
        """
        LinkedIn 3-step media upload:
        1) Initialize upload slot to get uploadUrl + image URN.
        2) Stream image bytes from storage/local disk.
        3) PUT binary payload directly to presigned uploadUrl (NO Authorization header).
        """
        versions = candidate_versions or [settings.LINKEDIN_API_VERSION or "202611"]
        init_resp = None
        for ver in versions:
            init_resp = await client.post(
                self.IMAGES_API_URL,
                headers=self._rest_headers(access_token, version=ver),
                json={"initializeUploadRequest": {"owner": owner_urn}},
            )
            if init_resp.status_code == 426 and "NONEXISTENT_VERSION" in init_resp.text:
                continue
            break

        if not init_resp or init_resp.status_code >= 400:
            err_text = init_resp.text if init_resp else "No response"
            err_code = init_resp.status_code if init_resp else 500
            raise SocialPublishError(f"LinkedIn image upload init failed ({err_code}): {err_text}")

        value = init_resp.json().get("value", {})
        upload_url = value.get("uploadUrl")
        image_urn = value.get("image")
        if not upload_url or not image_urn:
            raise SocialPublishError("LinkedIn image init response missing uploadUrl or image URN.")

        # Check local file or download from URL
        local_filename = image_url.split("/static/uploads/")[-1] if "/static/uploads/" in image_url else None
        local_path = (Path("static/uploads") / local_filename) if local_filename else None
        if local_path and local_path.exists():
            image_bytes = local_path.read_bytes()
            content_type = "image/png" if local_path.suffix.lower() == ".png" else "image/jpeg"
        else:
            image_bytes, content_type = await self._download_media_bytes(image_url)

        # Pre-signed S3 upload: DO NOT pass Authorization header
        put_resp = await client.put(
            upload_url,
            content=image_bytes,
            headers={
                "Content-Type": content_type or "image/jpeg",
            },
        )
        if put_resp.status_code >= 400:
            raise SocialPublishError(
                f"LinkedIn binary image upload failed ({put_resp.status_code}): {put_resp.text}"
            )
        return image_urn

    async def _upload_video_asset(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        owner_urn: str,
        video_url: str,
        candidate_versions: Optional[List[str]] = None,
    ) -> str:
        """
        LinkedIn 3-step video upload:
        1) Read/download binary video bytes from storage or local disk to determine exact size.
        2) Initialize video upload slot via POST /rest/videos?action=initializeUpload with fileSizeBytes.
        3) PUT binary video payload directly to presigned uploadUrl (NO Authorization header).
        4) Finalize video upload via POST /rest/videos?action=finalizeUpload.
        """
        # 1. Read video bytes first so we know exact fileSizeBytes
        local_filename = video_url.split("/static/uploads/")[-1] if "/static/uploads/" in video_url else None
        local_path = (Path("static/uploads") / local_filename) if local_filename else None
        if local_path and local_path.exists():
            video_bytes = local_path.read_bytes()
            content_type = "video/mp4"
        else:
            video_bytes, content_type = await self._download_media_bytes(video_url)

        file_size_bytes = len(video_bytes)
        versions = candidate_versions or [settings.LINKEDIN_API_VERSION or "202611"]

        # 2. Initialize video upload slot
        init_resp = None
        for ver in versions:
            init_resp = await client.post(
                self.VIDEOS_API_URL,
                headers=self._rest_headers(access_token, version=ver),
                json={
                    "initializeUploadRequest": {
                        "owner": owner_urn,
                        "fileSizeBytes": file_size_bytes,
                        "uploadCaptions": False,
                        "uploadThumbnail": False,
                    }
                },
            )
            if init_resp.status_code == 426 and "NONEXISTENT_VERSION" in init_resp.text:
                continue
            break

        if not init_resp or init_resp.status_code >= 400:
            err_text = init_resp.text if init_resp else "No response"
            err_code = init_resp.status_code if init_resp else 500
            raise SocialPublishError(f"LinkedIn video upload init failed ({err_code}): {err_text}")

        value = init_resp.json().get("value", {})
        instructions = value.get("uploadInstructions", [])
        video_urn = value.get("video")
        upload_token = value.get("uploadToken") or ""
        if not instructions or not video_urn:
            raise SocialPublishError("LinkedIn video init response missing uploadInstructions or video URN.")

        upload_url = instructions[0].get("uploadUrl")

        # 3. Pre-signed S3 upload: DO NOT pass Authorization header
        put_resp = await client.put(
            upload_url,
            content=video_bytes,
            headers={
                "Content-Type": content_type or "video/mp4",
            },
        )
        if put_resp.status_code >= 400:
            raise SocialPublishError(
                f"LinkedIn binary video upload failed ({put_resp.status_code}): {put_resp.text}"
            )

        etag = put_resp.headers.get("etag") or put_resp.headers.get("ETag") or ""
        etag_clean = etag.strip('"')

        # 4. Finalize video upload with LinkedIn Videos API
        finalize_url = "https://api.linkedin.com/rest/videos?action=finalizeUpload"
        for ver in versions:
            fin_resp = await client.post(
                finalize_url,
                headers=self._rest_headers(access_token, version=ver),
                json={
                    "finalizeUploadRequest": {
                        "video": video_urn,
                        "uploadToken": upload_token,
                        "uploadedPartIds": [etag_clean] if etag_clean else [],
                    }
                },
            )
            if fin_resp.status_code == 426 and "NONEXISTENT_VERSION" in fin_resp.text:
                continue
            break

        logger.info("LinkedIn video asset initialized and finalized: %s", video_urn)
        return video_urn

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

        # Dynamically compute rolling 14-month active LinkedIn versions (YYYYMM)
        now = datetime.now(timezone.utc)
        candidate_versions: List[str] = []
        if settings.LINKEDIN_API_VERSION:
            cleaned = settings.LINKEDIN_API_VERSION.strip()[:6]
            candidate_versions.append(cleaned)
        for i in range(14):
            y = now.year
            m = now.month - i
            while m <= 0:
                m += 12
                y -= 1
            ver_str = f"{y:04d}{m:02d}"
            if ver_str not in candidate_versions:
                candidate_versions.append(ver_str)

        last_error = None

        async with httpx.AsyncClient(timeout=60.0) as client:
            if media and media.get("url"):
                media_type = media.get("type", "image")
                if media_type == "video":
                    video_urn = await self._upload_video_asset(
                        client, access_token, author_urn, media["url"], candidate_versions=candidate_versions
                    )
                    payload["content"] = {"media": {"id": video_urn, "title": "Video Broadcast"}}
                else:
                    image_urn = await self._upload_image_asset(
                        client, access_token, author_urn, media["url"], candidate_versions=candidate_versions
                    )
                    payload["content"] = {"media": {"id": image_urn, "title": "Image Asset"}}

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

    async def fetch_comments(
        self, access_token: str, post_urn: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch comments on a LinkedIn post via LinkedIn Social Actions API.
        GET /rest/socialActions/{encodedUrn}/comments
        """
        from urllib.parse import quote
        encoded_urn = quote(post_urn, safe="")
        url = f"https://api.linkedin.com/rest/socialActions/{encoded_urn}/comments"
        comments: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    url,
                    headers=self._rest_headers(access_token),
                    params={"count": 50},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    elements = data.get("elements", [])
                    for el in elements:
                        comment_id = el.get("id") or el.get("$URN") or f"c_{self._timestamp_id()}"
                        actor = el.get("actor", "urn:li:person:unknown")
                        actor_id = actor.split(":")[-1] if ":" in actor else "user"
                        msg_obj = el.get("message", {})
                        text = msg_obj.get("text", "") if isinstance(msg_obj, dict) else str(msg_obj)
                        likes_summary = el.get("likesSummary", {})

                        created_ms = el.get("created", {}).get("time")
                        time_str = "Recently"
                        if created_ms:
                            try:
                                dt = datetime.fromtimestamp(created_ms / 1000.0, timezone.utc)
                                diff = (datetime.now(timezone.utc) - dt).total_seconds()
                                if diff < 3600:
                                    time_str = f"{max(1, int(diff // 60))}m ago"
                                elif diff < 86400:
                                    time_str = f"{int(diff // 3600)}h ago"
                                else:
                                    time_str = f"{int(diff // 86400)}d ago"
                            except Exception:
                                pass

                        comments.append({
                            "id": comment_id,
                            "author_name": f"LinkedIn User ({actor_id[:6]})",
                            "author_handle": f"@{actor_id[:10]}",
                            "avatar_text": "L",
                            "time_ago": time_str,
                            "content": text,
                            "likes_count": likes_summary.get("totalLikes", 0),
                            "is_liked": likes_summary.get("likedByCurrentUser", False),
                            "is_replied": False,
                            "user_reply_text": None,
                            "replies": [],
                        })
        except Exception as e:
            logger.warning("Failed to fetch LinkedIn comments for %s: %s", post_urn, e)

        return comments

    async def fetch_social_actions(
        self, access_token: str, post_urn: str
    ) -> Dict[str, Any]:
        """
        Fetch likes count and comments count via LinkedIn Social Actions API.
        GET /rest/socialActions/{encodedUrn}
        """
        from urllib.parse import quote
        encoded_urn = quote(post_urn, safe="")
        url = f"https://api.linkedin.com/rest/socialActions/{encoded_urn}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=self._rest_headers(access_token))
                if resp.status_code == 200:
                    data = resp.json()
                    likes_summary = data.get("likesSummary", {})
                    comments_summary = data.get("commentsSummary", {})
                    return {
                        "total_likes": likes_summary.get("totalLikes", 0),
                        "is_liked": likes_summary.get("likedByCurrentUser", False),
                        "total_comments": comments_summary.get("totalComments", 0),
                    }
        except Exception as e:
            logger.warning("Failed to fetch LinkedIn social actions for %s: %s", post_urn, e)
        return {}

    async def create_comment(
        self,
        access_token: str,
        author_urn: str,
        post_urn: str,
        text: str,
        parent_comment_urn: Optional[str] = None,
    ) -> Optional[str]:
        """
        Post a comment or reply to a LinkedIn post via LinkedIn Social Actions API.
        POST /rest/socialActions/{encodedUrn}/comments
        """
        from urllib.parse import quote
        encoded_urn = quote(post_urn, safe="")
        url = f"https://api.linkedin.com/rest/socialActions/{encoded_urn}/comments"

        payload: Dict[str, Any] = {
            "actor": author_urn,
            "message": {"text": text.strip()},
        }
        if parent_comment_urn:
            payload["parentComment"] = parent_comment_urn

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    url,
                    headers=self._rest_headers(access_token),
                    json=payload,
                )
                if resp.status_code in (200, 201):
                    return resp.headers.get("x-restli-id") or f"urn:li:comment:{self._timestamp_id()}"
                else:
                    logger.warning("LinkedIn comment create returned %s: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.warning("Failed to dispatch LinkedIn comment: %s", e)
        return None

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
