from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from backend.models.user import UserModel
from backend.api.deps import get_current_user
from backend.tools.media_and_social import CloudinaryTool, MuxTool, CloudflareR2Tool

router = APIRouter(prefix="/media", tags=["Media Tools"])

r2_tool = CloudflareR2Tool()
cloudinary_tool = CloudinaryTool()
mux_tool = MuxTool()


@router.post("/r2-presigned-url")
async def get_r2_presigned_url(
    media_type: str = Query(..., description="'image' or 'video'"),
    filename: Optional[str] = Query(None, description="Original filename with extension"),
    content_type: Optional[str] = Query(None, description="MIME type e.g. video/mp4, image/jpeg"),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Generate an S3 pre-signed PUT URL for Cloudflare R2.
    The mobile app or browser sends a direct HTTP PUT with file bytes directly to this URL.
    Zero server bandwidth used.
    """
    if media_type not in ("image", "video"):
        raise HTTPException(status_code=400, detail="media_type must be 'image' or 'video'")
    return r2_tool.generate_presigned_upload_url(
        media_type=media_type,
        filename=filename,
        content_type=content_type,
    )


@router.post("/upload-signature")
async def get_media_upload_signature(
    media_type: str = Query(..., description="'image' or 'video'"),
    provider: Optional[str] = Query("r2", description="'r2', 'cloudinary', or 'mux'"),
    filename: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Unified client-to-cloud upload authorization endpoint.
    Defaults to Cloudflare R2 with fallback support for Cloudinary & Mux.
    """
    if provider == "r2":
        return r2_tool.generate_presigned_upload_url(
            media_type=media_type,
            filename=filename,
            content_type=content_type,
        )
    elif media_type == "image":
        return cloudinary_tool.generate_upload_signature()
    elif media_type == "video":
        return await mux_tool.create_direct_upload_url()
    else:
        raise HTTPException(status_code=400, detail="Invalid media_type. Must be 'image' or 'video'.")
