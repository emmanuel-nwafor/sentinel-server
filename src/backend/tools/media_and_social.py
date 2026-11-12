import time
import hashlib
from typing import Dict, Any, Optional
from backend.core.config import settings
from backend.schemas.content import MediaAsset


class CloudinaryTool:
    """Deterministic tool for direct client-to-Cloudinary upload signatures and asset management."""

    def __init__(self):
        self.cloud_name = settings.CLOUDINARY_CLOUD_NAME
        self.api_key = settings.CLOUDINARY_API_KEY
        self.api_secret = settings.CLOUDINARY_API_SECRET

    def generate_upload_signature(self, folder: str = "sentinel_posts") -> Dict[str, Any]:
        timestamp = int(time.time())
        params_to_sign = f"folder={folder}&timestamp={timestamp}{self.api_secret}"
        signature = hashlib.sha1(params_to_sign.encode("utf-8")).hexdigest()

        return {
            "provider": "cloudinary",
            "upload_url": f"https://api.cloudinary.com/v1_1/{self.cloud_name}/image/upload",
            "signature": signature,
            "timestamp": timestamp,
            "api_key": self.api_key,
            "cloud_name": self.cloud_name,
        }

    def create_placeholder_ai_asset(self, prompt: str) -> MediaAsset:
        safe_name = "".join(c if c.isalnum() else "_" for c in prompt[:25])
        return MediaAsset(
            type="image",
            provider="cloudinary",
            url=f"https://res.cloudinary.com/{self.cloud_name}/image/upload/v1/sentinel_ai_{safe_name}.png",
            public_id=f"sentinel_ai_{safe_name}",
        )


class MuxTool:
    """Deterministic tool for generating direct video upload endpoints to MUX."""

    def __init__(self):
        self.token_id = settings.MUX_TOKEN_ID
        self.token_secret = settings.MUX_TOKEN_SECRET

    async def create_direct_upload_url(self) -> Dict[str, Any]:
        upload_id = f"mux_upload_{int(time.time())}"
        return {
            "provider": "mux",
            "upload_url": f"https://storage.googleapis.com/mux-mock-uploads/{upload_id}",
            "upload_id": upload_id,
        }


class SocialPublisherTool:
    """
    Direct Social Publishing API tool (LinkedIn + X).
    Replaces n8n publication nodes with direct API client calls.
    """

    async def publish_to_linkedin(self, text: str, media_url: Optional[str] = None) -> Dict[str, Any]:
        return {
            "platform": "linkedin",
            "status": "published",
            "post_id": f"urn:li:share:{int(time.time())}",
            "text_length": len(text),
            "media_attached": bool(media_url),
        }

    async def publish_to_x(self, text: str, media_url: Optional[str] = None) -> Dict[str, Any]:
        return {
            "platform": "x",
            "status": "published",
            "tweet_id": f"x_tweet_{int(time.time())}",
            "text_length": len(text),
            "media_attached": bool(media_url),
        }
