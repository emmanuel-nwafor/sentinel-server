import os
import uuid
import shutil
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, File, UploadFile, Request, Form
from backend.models.user import UserModel
from backend.api.deps import get_current_user
from backend.tools.media_and_social import CloudinaryTool, MuxTool, CloudflareR2Tool
from backend.schemas.content import MediaAsset

router = APIRouter(prefix="/media", tags=["Media Tools"])

UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

r2_tool = CloudflareR2Tool()
cloudinary_tool = CloudinaryTool()
mux_tool = MuxTool()


@router.post("/upload", response_model=MediaAsset)
async def upload_media_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Direct mobile/web binary upload for images and videos.
    Saves file to static assets and returns a public HTTPS MediaAsset URL.
    """
    filename = file.filename or f"upload_{uuid.uuid4().hex}"
    ext = os.path.splitext(filename)[1].lower()

    content_type = (file.content_type or "").lower()
    is_video = "video" in content_type or ext in (".mp4", ".mov", ".avi", ".mkv", ".webm")
    media_type = "video" if is_video else "image"
    if not ext:
        ext = ".mp4" if is_video else ".jpg"

    unique_filename = f"{uuid.uuid4().hex}{ext}"
    target_path = UPLOAD_DIR / unique_filename

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Base URL construction
    base_url = str(request.base_url).rstrip("/")
    if "onrender.com" in base_url and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://", 1)

    public_url = f"{base_url}/static/uploads/{unique_filename}"

    return MediaAsset(
        type=media_type,
        url=public_url,
        provider="cloudinary",
        public_id=unique_filename,
        thumbnail_url=public_url if media_type == "image" else None,
    )


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
    provider: Optional[str] = Query(None, description="'auto', 'r2', 'cloudinary', or 'mux'"),
    filename: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Unified client-to-cloud upload authorization endpoint.
    - If provider is explicitly specified ('r2', 'mux', 'cloudinary'), uses that provider.
    - If provider is None or 'auto':
        * If Cloudflare R2 is configured (keys in .env): prioritizes Cloudflare R2 for all media.
        * Otherwise (fallback mode for MUX & Cloudinary):
            - 'video' -> MUX Direct Upload
            - 'image' -> Cloudinary Upload Signature
    """
    if media_type not in ("image", "video"):
        raise HTTPException(status_code=400, detail="Invalid media_type. Must be 'image' or 'video'.")

    selected_provider = provider.lower() if provider else "auto"

    if selected_provider == "r2":
        return r2_tool.generate_presigned_upload_url(
            media_type=media_type,
            filename=filename,
            content_type=content_type,
        )
    elif selected_provider == "mux":
        if media_type != "video":
            raise HTTPException(status_code=400, detail="MUX provider is only for video uploads.")
        return await mux_tool.create_direct_upload_url()
    elif selected_provider == "cloudinary":
        return cloudinary_tool.generate_upload_signature()
    else:
        # 'auto' mode:
        # 1. Primary Engine: Cloudflare R2 if configured in .env
        if r2_tool.is_configured:
            return r2_tool.generate_presigned_upload_url(
                media_type=media_type,
                filename=filename,
                content_type=content_type,
            )
        # 2. Active Fallback Engine: MUX for videos, Cloudinary for images
        if media_type == "video":
            return await mux_tool.create_direct_upload_url()
        else:
            return cloudinary_tool.generate_upload_signature()


@router.get("/mux/status/{upload_id}")
async def get_mux_upload_status(
    upload_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    """
    Check MUX video processing status and retrieve stream/mp4 playback URLs.
    """
    return await mux_tool.get_upload_status(upload_id)
