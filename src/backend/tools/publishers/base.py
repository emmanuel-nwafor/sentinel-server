from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Optional, Dict, Any, List, Tuple
import httpx
from backend.models.social_account import SocialAccountModel, SocialPlatform
from backend.schemas.social import PlatformPublishResult


@dataclass
class OAuthTokenBundle:
    """Normalized OAuth token & identity payload returned after code exchange."""

    access_token: str
    platform_account_id: str
    account_name: str
    account_handle: Optional[str] = None
    profile_picture_url: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    scopes: List[str] = field(default_factory=list)


class SocialPublishError(Exception):
    """Domain exception raised when a social platform rejects validation or publishing."""


class ISocialPublisher(ABC):
    """
    Strategy Interface for Server-Side Social Media Publishers.
    Every supported social platform implements this single contract.
    """

    @property
    @abstractmethod
    def platform(self) -> SocialPlatform:
        pass

    @abstractmethod
    def is_oauth_configured(self) -> bool:
        pass

    @abstractmethod
    def build_authorization_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        pass

    @abstractmethod
    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: Optional[str] = None
    ) -> OAuthTokenBundle:
        pass

    @abstractmethod
    def validate_content(self, text: str, media: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    async def publish(
        self,
        account: SocialAccountModel,
        access_token: str,
        text: str,
        media: Optional[Dict[str, Any]] = None,
    ) -> PlatformPublishResult:
        pass

    @abstractmethod
    async def delete_post(
        self,
        account: SocialAccountModel,
        access_token: str,
        remote_post_id: str,
    ) -> bool:
        pass


class BaseSocialPublisher(ISocialPublisher, ABC):
    """Shared utilities for HTTP streaming, validation, and sandbox publishing."""

    async def delete_post(
        self,
        account: SocialAccountModel,
        access_token: str,
        remote_post_id: str,
    ) -> bool:
        """Default sandbox / base post deletion handler."""
        return True

    async def _download_media_bytes(self, url: str) -> Tuple[bytes, str]:
        """Download binary asset from Cloudinary or MUX URL for server-side upload."""
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url)
            # Resilient fallback for MUX static renditions
            if response.status_code >= 400 and "stream.mux.com" in url:
                for candidate in ["capped-1080p.mp4", "high.mp4", "medium.mp4", "low.mp4"]:
                    alt_url = "/".join(url.split("/")[:-1]) + f"/{candidate}"
                    if alt_url != url:
                        alt_resp = await client.get(alt_url)
                        if alt_resp.status_code < 400:
                            response = alt_resp
                            break
            if response.status_code >= 400:
                raise SocialPublishError(
                    f"Failed to fetch media asset from storage ({response.status_code})."
                )
            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.content, content_type

    def _build_sandbox_result(
        self,
        remote_post_id: str,
        post_url: str,
    ) -> PlatformPublishResult:
        return PlatformPublishResult(
            platform=self.platform,
            success=True,
            remote_post_id=remote_post_id,
            post_url=post_url,
            is_sandbox=True,
            published_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _timestamp_id(prefix: str) -> str:
        return f"{prefix}_{int(time.time() * 1000)}"
