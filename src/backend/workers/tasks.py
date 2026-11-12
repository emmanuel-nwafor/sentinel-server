import logging
from typing import Dict, Any, Optional
from arq.connections import RedisSettings
from backend.core.config import settings
from backend.tools.media_and_social import SocialPublisherTool

logger = logging.getLogger(__name__)


async def publish_scheduled_post_job(
    ctx: Dict[Any, Any],
    post_id: str,
    linkedin_text: Optional[str] = None,
    x_text: Optional[str] = None,
    media_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ARQ Distributed Background Task.
    Executed by the worker at the scheduled timestamp, completely replacing n8n.
    """
    logger.info(f"[Worker] Executing scheduled post job for post_id={post_id}")
    publisher = SocialPublisherTool()
    results = {}

    if linkedin_text:
        results["linkedin"] = await publisher.publish_to_linkedin(linkedin_text, media_url)

    if x_text:
        results["x"] = await publisher.publish_to_x(x_text, media_url)

    logger.info(f"[Worker] Post {post_id} published successfully: {results}")
    return {"post_id": post_id, "status": "published", "results": results}


class WorkerSettings:
    functions = [publish_scheduled_post_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
