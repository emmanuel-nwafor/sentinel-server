from abc import abstractmethod
from typing import Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.brand_profile import UserBrandProfileModel
from backend.repositories.base import IBaseRepository, BaseRepository


class IBrandProfileRepository(IBaseRepository[UserBrandProfileModel]):
    @abstractmethod
    async def get_by_user(self, user_id: uuid.UUID) -> Optional[UserBrandProfileModel]:
        pass

    @abstractmethod
    async def upsert_profile(
        self,
        user_id: uuid.UUID,
        full_name: str,
        headline: str,
        about: str,
        niche: str,
        target_audience: str,
        tone: str,
        core_topics: list,
        skills: list,
        current_company: Optional[str] = None,
        education: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        raw_input: Optional[str] = None,
        source_type: str = "linkedin_enrichment",
    ) -> UserBrandProfileModel:
        pass


class BrandProfileRepository(BaseRepository[UserBrandProfileModel], IBrandProfileRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(UserBrandProfileModel, session)

    async def get_by_user(self, user_id: uuid.UUID) -> Optional[UserBrandProfileModel]:
        result = await self.session.execute(
            select(UserBrandProfileModel).where(UserBrandProfileModel.user_id == user_id)
        )
        return result.scalars().first()

    async def upsert_profile(
        self,
        user_id: uuid.UUID,
        full_name: str,
        headline: str,
        about: str,
        niche: str,
        target_audience: str,
        tone: str,
        core_topics: list,
        skills: list,
        current_company: Optional[str] = None,
        education: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        raw_input: Optional[str] = None,
        source_type: str = "linkedin_enrichment",
    ) -> UserBrandProfileModel:
        existing = await self.get_by_user(user_id)
        if existing:
            existing.full_name = full_name
            existing.headline = headline
            existing.about = about
            existing.niche = niche
            existing.target_audience = target_audience
            existing.tone = tone
            existing.core_topics = core_topics
            existing.skills = skills
            existing.current_company = current_company
            existing.education = education
            existing.linkedin_url = linkedin_url
            existing.raw_input = raw_input
            existing.source_type = source_type
            return existing

        profile = UserBrandProfileModel(
            user_id=user_id,
            full_name=full_name,
            headline=headline,
            about=about,
            niche=niche,
            target_audience=target_audience,
            tone=tone,
            core_topics=core_topics,
            skills=skills,
            current_company=current_company,
            education=education,
            linkedin_url=linkedin_url,
            raw_input=raw_input,
            source_type=source_type,
        )
        self.session.add(profile)
        return profile
