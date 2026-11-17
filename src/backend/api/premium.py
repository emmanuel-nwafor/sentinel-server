from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.core.config import settings
from backend.models.brand_voice import BrandVoiceModel
from backend.models.user import UserModel
from backend.schemas.premium import (
    BrandVoiceCreateRequest,
    BrandVoiceUpdateRequest,
    BrandVoiceResponse,
    SubscriptionStatusResponse,
    PlanFeatureComparisonResponse,
)
from backend.services.premium_service import PremiumService
from backend.unit_of_work.base import IUnitOfWork
from backend.api.deps import get_current_user, get_uow

router = APIRouter(prefix="/premium", tags=["Premium & Monetization"])


def _serialize_brand_voice(model: BrandVoiceModel) -> BrandVoiceResponse:
    return BrandVoiceResponse(
        id=str(model.id),
        user_id=str(model.user_id),
        name=model.name,
        tone=model.tone,
        target_audience=model.target_audience,
        key_pillars=model.key_pillars or [],
        taboo_words=model.taboo_words or [],
        signature_cta=model.signature_cta,
        sample_post=model.sample_post,
        is_default=model.is_default,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    current_user: UserModel = Depends(get_current_user),
):
    """
    Check the current user's subscription tier, quotas, and feature flags.
    Notice `enforcement_active` indicates whether paywalls are strictly enforced.
    """
    remaining = max(0, current_user.monthly_ai_quota_limit - current_user.monthly_ai_quota_used)
    unlocked = PremiumService.get_unlocked_features_for_user(current_user)

    return SubscriptionStatusResponse(
        tier=current_user.tier,
        is_premium=current_user.is_premium,
        subscription_status=current_user.subscription_status or "active",
        premium_expires_at=current_user.premium_expires_at,
        monthly_ai_quota_used=current_user.monthly_ai_quota_used,
        monthly_ai_quota_limit=current_user.monthly_ai_quota_limit,
        quota_remaining=remaining,
        enforcement_active=PremiumService.is_enforcement_active(),
        features_unlocked=unlocked,
    )


@router.get("/plans", response_model=PlanFeatureComparisonResponse)
async def get_tier_plans():
    """Returns available tier plans, pricing, and feature comparison breakdown."""
    return PlanFeatureComparisonResponse(
        plans=PremiumService.get_tier_plans(),
        enforcement_active=PremiumService.is_enforcement_active(),
    )


# -----------------------------------------------------------------------------
# Brand Voice Personas (Flagship Premium Feature)
# -----------------------------------------------------------------------------
@router.get("/brand-voices", response_model=List[BrandVoiceResponse])
async def list_brand_voices(
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """List all saved AI Brand Voice Personas for the current user."""
    voices = await uow.brand_voices.list_by_user(current_user.id)
    return [_serialize_brand_voice(v) for v in voices]


@router.post(
    "/brand-voices",
    response_model=BrandVoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand_voice(
    payload: BrandVoiceCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Create a new AI Brand Voice Persona.
    (Gated when ENABLE_PREMIUM_ENFORCEMENT=True; accessible to all when False).
    """
    access = PremiumService.check_feature_access(current_user, "brand_voice")
    if not access.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=access.reason,
        )

    # Check if this is the user's first voice; if so, make it default automatically
    existing_voices = await uow.brand_voices.list_by_user(current_user.id)
    make_default = payload.is_default or len(existing_voices) == 0

    new_voice = BrandVoiceModel(
        user_id=current_user.id,
        name=payload.name.strip(),
        tone=payload.tone.strip(),
        target_audience=payload.target_audience.strip(),
        key_pillars=payload.key_pillars,
        taboo_words=payload.taboo_words,
        signature_cta=payload.signature_cta,
        sample_post=payload.sample_post,
        is_default=make_default,
    )

    created = await uow.brand_voices.create(new_voice)
    await uow.commit()

    if make_default and len(existing_voices) > 0:
        await uow.brand_voices.set_default(current_user.id, created.id)
        await uow.commit()

    return _serialize_brand_voice(created)


@router.put("/brand-voices/{voice_id}", response_model=BrandVoiceResponse)
async def update_brand_voice(
    voice_id: str,
    payload: BrandVoiceUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Update an existing Brand Voice Persona."""
    try:
        voice_uuid = uuid.UUID(voice_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid voice identifier")

    voice = await uow.brand_voices.get_by_id(voice_uuid)
    if not voice or voice.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Brand voice not found")

    if payload.name is not None:
        voice.name = payload.name.strip()
    if payload.tone is not None:
        voice.tone = payload.tone.strip()
    if payload.target_audience is not None:
        voice.target_audience = payload.target_audience.strip()
    if payload.key_pillars is not None:
        voice.key_pillars = payload.key_pillars
    if payload.taboo_words is not None:
        voice.taboo_words = payload.taboo_words
    if payload.signature_cta is not None:
        voice.signature_cta = payload.signature_cta
    if payload.sample_post is not None:
        voice.sample_post = payload.sample_post

    await uow.commit()

    if payload.is_default:
        await uow.brand_voices.set_default(current_user.id, voice_uuid)
        await uow.commit()

    return _serialize_brand_voice(voice)


@router.post("/brand-voices/{voice_id}/default", response_model=BrandVoiceResponse)
async def set_default_brand_voice(
    voice_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Set a brand voice as the default for AI generation."""
    try:
        voice_uuid = uuid.UUID(voice_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid voice identifier")

    voice = await uow.brand_voices.get_by_id(voice_uuid)
    if not voice or voice.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Brand voice not found")

    updated = await uow.brand_voices.set_default(current_user.id, voice_uuid)
    await uow.commit()
    return _serialize_brand_voice(updated)


@router.delete("/brand-voices/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_voice(
    voice_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Delete a brand voice persona."""
    try:
        voice_uuid = uuid.UUID(voice_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid voice identifier")

    voice = await uow.brand_voices.get_by_id(voice_uuid)
    if not voice or voice.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Brand voice not found")

    await uow.brand_voices.delete(voice_uuid)
    await uow.commit()


# -----------------------------------------------------------------------------
# Developer Tier Simulator
# -----------------------------------------------------------------------------
@router.post("/dev-toggle")
async def dev_toggle_premium(
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Developer helper: Toggles `is_premium` between True and False on the current user
    to test both free and paid subscriber flows instantly.
    """
    user = await uow.users.get_by_id(current_user.id)
    user.is_premium = not user.is_premium
    user.tier = "pro" if user.is_premium else "free"
    await uow.commit()

    return {
        "message": f"User premium status toggled to: {user.is_premium}",
        "tier": user.tier,
        "is_premium": user.is_premium,
    }
