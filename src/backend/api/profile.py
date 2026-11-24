import logging
import uuid
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from backend.core.config import settings
from backend.models.user import UserModel
from backend.models.brand_profile import UserBrandProfileModel
from backend.unit_of_work.base import IUnitOfWork
from backend.api.deps import get_current_user, get_uow

logger = logging.getLogger("dispatch.profile")
router = APIRouter(prefix="/profile", tags=["Profile & Brand Context"])


class ProfileEnrichRequest(BaseModel):
    raw_text: Optional[str] = Field(None, description="Pasted LinkedIn About, headline, CV text, or portfolio notes.")
    headline: Optional[str] = None
    about: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_type: str = "linkedin_enrichment"


class UserBrandProfileResponse(BaseModel):
    full_name: str
    headline: str
    about: str
    niche: str
    target_audience: str
    tone: str
    core_topics: List[str]
    skills: List[str]
    current_company: Optional[str] = None
    education: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_type: str


async def _extract_brand_context_with_llm(raw_text: str) -> dict:
    """Extract structured brand profile from raw pasted LinkedIn, CV, or bio text using Gemini."""
    client = None
    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
        except Exception as e:
            logger.warning("Gemini Client init failed: %s", e)

    if not client:
        return {
            "headline": raw_text[:120].strip(),
            "about": raw_text.strip(),
            "niche": "Software & AI Engineering",
            "target_audience": "Tech founders and senior software engineers",
            "tone": "Technical, authoritative, pragmatic",
            "core_topics": ["Software Engineering", "Full-Stack Development"],
            "skills": ["React.js", "JavaScript", "Python"],
            "current_company": None,
            "education": None,
        }

    prompt = f"""
Analyze the following user profile text (LinkedIn About / CV / bio / portfolio):

=== TEXT START ===
{raw_text}
=== TEXT END ===

Extract a structured Brand Profile in valid JSON with these exact keys:
{{
  "headline": "<punchy professional headline, e.g. Software Engineer at Foremade>",
  "about": "<clean, cohesive professional summary / about text>",
  "niche": "<precise professional niche, e.g. Fullstack & Mobile Engineering>",
  "target_audience": "<who this person speaks to on social platforms>",
  "tone": "<authoritative, technical, opinionated, etc.>",
  "core_topics": ["<topic 1>", "<topic 2>", "<topic 3>", "<topic 4>"],
  "skills": ["<skill 1>", "<skill 2>", "<skill 3>", "<skill 4>", "<skill 5>"],
  "current_company": "<current company or null>",
  "education": "<education details or null>"
}}
Return ONLY raw JSON with zero markdown code fences.
"""

    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
        "gemini-3-flash-preview",
        "gemini-pro-latest",
    ]

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            candidate = response.candidates[0] if response.candidates else None
            txt = candidate.content.parts[0].text if candidate and candidate.content else ""
            txt = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(txt)
            return data
        except Exception as exc:
            logger.warning("Model %s enrichment failed: %s", model_name, exc)
            continue

    return {
        "headline": raw_text[:120].strip(),
        "about": raw_text.strip(),
        "niche": "Fullstack Engineering",
        "target_audience": "Engineering teams and founders",
        "tone": "Technical and insightful",
        "core_topics": ["Software Architecture", "Product Development"],
        "skills": ["JavaScript", "React.js", "Backend Systems"],
        "current_company": None,
        "education": None,
    }


@router.get("/context", response_model=UserBrandProfileResponse)
async def get_user_brand_context(
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """Retrieve the unified persistent User Brand Profile from PostgreSQL."""
    profile = await uow.brand_profiles.get_by_user(current_user.id)
    if not profile:
        # Check if user has connected accounts to infer basic identity
        social_accs = await uow.social_accounts.list_by_user(current_user.id)
        li_acc = next((a for a in social_accs if a.platform == "linkedin"), None)
        x_acc = next((a for a in social_accs if a.platform == "x"), None)

        user_display_name = (
            current_user.name
            or (li_acc.account_name if li_acc else None)
            or (x_acc.account_name if x_acc else None)
            or "Creator"
        )
        headline = getattr(li_acc, "headline", "") if li_acc else ""
        li_url = (
            f"https://www.linkedin.com/in/{li_acc.account_handle}"
            if li_acc and li_acc.account_handle
            else None
        )

        return UserBrandProfileResponse(
            full_name=user_display_name,
            headline=headline or "",
            about="",
            niche="General Content Strategy",
            target_audience="Target professional audience",
            tone="Authentic, engaging, high-signal",
            core_topics=[],
            skills=[],
            current_company=None,
            education=None,
            linkedin_url=li_url,
            source_type="unconfigured",
        )

    return UserBrandProfileResponse(
        full_name=profile.full_name,
        headline=profile.headline,
        about=profile.about,
        niche=profile.niche,
        target_audience=profile.target_audience,
        tone=profile.tone,
        core_topics=profile.core_topics,
        skills=profile.skills,
        current_company=profile.current_company,
        education=profile.education,
        linkedin_url=profile.linkedin_url,
        source_type=profile.source_type,
    )


@router.post("/enrich", response_model=UserBrandProfileResponse)
async def enrich_user_brand_profile(
    payload: ProfileEnrichRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Enrich or update User Brand Profile in PostgreSQL.
    Accepts pasted LinkedIn About/headline, CV text, or manual notes,
    extracts structured identity via AI, and stores it for the Agent tool.
    """
    input_text = payload.raw_text or f"{payload.headline or ''}\n\n{payload.about or ''}".strip()
    if not input_text:
        raise HTTPException(status_code=400, detail="Please provide profile, About, or CV text to enrich.")

    extracted = await _extract_brand_context_with_llm(input_text)

    headline = payload.headline or extracted.get("headline") or "Software Engineer"
    about = payload.about or extracted.get("about") or input_text
    niche = extracted.get("niche") or "Fullstack Engineering"
    target_audience = extracted.get("target_audience") or "Tech founders and senior software engineers"
    tone = extracted.get("tone") or "Authoritative, educational, technical"
    core_topics = extracted.get("core_topics") or ["Software Engineering"]
    skills = extracted.get("skills") or ["React.js", "JavaScript", "Git"]
    current_company = extracted.get("current_company")
    education = extracted.get("education")

    profile = await uow.brand_profiles.upsert_profile(
        user_id=current_user.id,
        full_name=current_user.name or "Emmanuel Chinecherem",
        headline=headline,
        about=about,
        niche=niche,
        target_audience=target_audience,
        tone=tone,
        core_topics=core_topics,
        skills=skills,
        current_company=current_company,
        education=education,
        linkedin_url=payload.linkedin_url,
        raw_input=input_text,
        source_type=payload.source_type,
    )
    await uow.commit()

    return UserBrandProfileResponse(
        full_name=profile.full_name,
        headline=profile.headline,
        about=profile.about,
        niche=profile.niche,
        target_audience=profile.target_audience,
        tone=profile.tone,
        core_topics=profile.core_topics,
        skills=profile.skills,
        current_company=profile.current_company,
        education=profile.education,
        linkedin_url=profile.linkedin_url,
        source_type=profile.source_type,
    )
