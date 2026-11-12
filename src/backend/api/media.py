from fastapi import APIRouter, HTTPException, Depends
from backend.models.user import UserModel
from backend.api.deps import get_current_user
from backend.tools.media_and_social import CloudinaryTool, MuxTool

router = APIRouter(prefix="/media", tags=["Media Tools"])

cloudinary_tool = CloudinaryTool()
mux_tool = MuxTool()


@router.post("/upload-signature")
async def get_media_upload_signature(
    media_type: str,
    current_user: UserModel = Depends(get_current_user),
):
    """
    Generate direct client-to-cloud upload signatures.
    - 'image' -> Cloudinary signature
    - 'video' -> MUX direct upload URL
    """
    if media_type == "image":
        return cloudinary_tool.generate_upload_signature()
    elif media_type == "video":
        return await mux_tool.create_direct_upload_url()
    else:
        raise HTTPException(status_code=400, detail="Invalid media_type. Must be 'image' or 'video'.")
