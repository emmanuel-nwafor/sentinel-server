from typing import Dict, List, Optional, Tuple
import uuid
from backend.core.security import TokenCipher, token_cipher
from backend.models.post import PostModel
from backend.models.social_account import SocialPlatform
from backend.schemas.content import PostStatus
from backend.schemas.social import PlatformPublishResult
from backend.tools.publishers.base import ISocialPublisher, SocialPublishError
from backend.tools.publishers.linkedin import LinkedInPublisher
from backend.tools.publishers.x_twitter import XPublisher
from backend.tools.publishers.instagram import InstagramPublisher
from backend.unit_of_work.base import IUnitOfWork


class PublisherFactory:
    """
    Factory registry resolving a SocialPlatform enum to its concrete ISocialPublisher strategy.
    """

    _STRATEGIES: Dict[SocialPlatform, ISocialPublisher] = {
        SocialPlatform.LINKEDIN: LinkedInPublisher(),
        SocialPlatform.X: XPublisher(),
        SocialPlatform.INSTAGRAM: InstagramPublisher(),
    }

    @classmethod
    def get_publisher(cls, platform: SocialPlatform) -> ISocialPublisher:
        publisher = cls._STRATEGIES.get(platform)
        if not publisher:
            raise ValueError(f"Unsupported social platform: {platform}")
        return publisher


class SocialPublishingService:
    """
    Application service coordinating server-side multi-platform publishing inside Sentinel.
    Uses Unit of Work to load connected accounts, TokenCipher to decrypt tokens,
    and PublisherFactory to dispatch platform strategies with isolated error handling.
    """

    def __init__(self, cipher: TokenCipher = token_cipher):
        self._cipher = cipher

    @staticmethod
    def _extract_variant_text(post: PostModel, platform: SocialPlatform) -> Optional[str]:
        variant_map = {
            SocialPlatform.LINKEDIN: post.linkedin_variant,
            SocialPlatform.X: post.x_variant,
            SocialPlatform.INSTAGRAM: post.instagram_variant,
        }
        variant = variant_map.get(platform) or {}
        return variant.get("formatted_text")

    async def publish_post(
        self,
        uow: IUnitOfWork,
        user_id: uuid.UUID,
        post: PostModel,
        target_platforms: List[SocialPlatform],
    ) -> Tuple[PostStatus, Dict[str, dict]]:
        """
        Publish `post` across `target_platforms` via server-side REST calls.
        Returns (final_post_status, serialized_results_per_platform).
        """
        results: Dict[str, dict] = {}
        success_count = 0

        for platform in target_platforms:
            text = self._extract_variant_text(post, platform)
            if not text:
                results[platform.value] = PlatformPublishResult(
                    platform=platform,
                    success=False,
                    error=f"No generated or saved copy found for {platform.value}.",
                ).model_dump(mode="json")
                continue

            account = await uow.social_accounts.get_by_user_and_platform(user_id, platform.value)
            if not account or not account.is_active:
                results[platform.value] = PlatformPublishResult(
                    platform=platform,
                    success=False,
                    error=f"{platform.value} account is not connected. Connect it inside Sentinel first.",
                ).model_dump(mode="json")
                continue

            try:
                access_token = self._cipher.decrypt(account.encrypted_access_token)
                publisher = PublisherFactory.get_publisher(platform)
                result = await publisher.publish(
                    account=account,
                    access_token=access_token,
                    text=text,
                    media=post.media,
                )
                results[platform.value] = result.model_dump(mode="json")
                if result.success:
                    success_count += 1
            except (SocialPublishError, ValueError) as exc:
                results[platform.value] = PlatformPublishResult(
                    platform=platform,
                    success=False,
                    is_sandbox=account.is_sandbox,
                    error=str(exc),
                ).model_dump(mode="json")
            except Exception as exc:
                results[platform.value] = PlatformPublishResult(
                    platform=platform,
                    success=False,
                    is_sandbox=account.is_sandbox,
                    error=f"Unexpected {platform.value} publish error: {exc}",
                ).model_dump(mode="json")

        total = len(target_platforms)
        if total > 0 and success_count == total:
            final_status = PostStatus.PUBLISHED
        elif success_count > 0:
            final_status = PostStatus.PARTIALLY_PUBLISHED
        else:
            final_status = PostStatus.FAILED

        return final_status, results

    async def delete_published_post(
        self,
        uow: IUnitOfWork,
        user_id: uuid.UUID,
        post: PostModel,
    ) -> Dict[str, bool]:
        """
        Delete remote posts across connected social accounts if post was published.
        Returns map of platform -> success boolean.
        """
        results: Dict[str, bool] = {}
        publish_results = post.publish_results or {}

        for plat_str, res in publish_results.items():
            if not isinstance(res, dict) or not res.get("remote_post_id"):
                continue
            remote_id = res["remote_post_id"]
            try:
                platform = SocialPlatform(plat_str)
                account = await uow.social_accounts.get_by_user_and_platform(user_id, platform.value)
                if account and account.is_active:
                    access_token = self._cipher.decrypt(account.encrypted_access_token)
                    publisher = PublisherFactory.get_publisher(platform)
                    success = await publisher.delete_post(
                        account=account,
                        access_token=access_token,
                        remote_post_id=remote_id,
                    )
                    results[plat_str] = success
                else:
                    results[plat_str] = True
            except Exception:
                results[plat_str] = False

        return results
