import os
import json
from google import genai
from google.genai import types
from backend.core.config import settings
from backend.schemas.content import (
    ContentGenerationRequest,
    GeneratedContentPlan,
    LinkedInPostVariant,
    XPostVariant,
    InstagramPostVariant,
)


class ContentOperatorAgent:
    """
    Dispatch Content Operator Agent:
    Transforms natural language intents into platform-native posts for LinkedIn, X, and Instagram
    using Gemini 2.5 Flash with strict Pydantic JSON schema extraction.
    """

    def __init__(self):
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None

    async def execute(
        self,
        request: ContentGenerationRequest,
        brand_voice_prompt: str = None,
    ) -> GeneratedContentPlan:
        if self.client:
            try:
                return await self._generate_with_llm(request, brand_voice_prompt)
            except Exception as exc:
                logger.warning("LLM generation failed (%s); using deterministic fallback.", exc)
        return self._generate_deterministic_fallback(request)

    async def _generate_with_llm(
        self,
        request: ContentGenerationRequest,
        brand_voice_prompt: str = None,
    ) -> GeneratedContentPlan:
        system_instruction = """
        You are the Sentinel Content Operator Agent for modern AI-driven businesses.
        Your mission is to take user prompts and elevate them into high-performing,
        platform-native social posts.

        Platform Guidelines:
        1. LinkedIn:
           - Professional, storytelling, or educational tone.
           - Hook first line that stops scrolling.
           - Formatted with whitespace and bullet points.
           - Clear call to action to spark meaningful comments.
           - 3 to 5 targeted industry hashtags.

        2. X (Twitter):
           - Punchy, high-signal, zero fluff.
           - Strict limit: must easily fit within 280 characters.
           - 1 to 2 hashtags maximum.

        3. Instagram:
           - Visual-first storytelling caption with conversational hook.
           - Clear call to action inviting saves, shares, or comments.
           - 5 to 8 relevant discoverability hashtags.
           - Practical media guidance describing what image or short video pairs best.

        4. Media Prompt:
           - Synthesize a photorealistic, modern visual prompt suitable for generating an image banner.
        """

        prompt_parts = [
            f"User Intent: {request.prompt}",
            f"Workspace: {request.workspace.value}",
        ]
        if brand_voice_prompt:
            prompt_parts.append(f"\n[Custom Brand Voice Persona Instructions]:\n{brand_voice_prompt}")

        prompt = "\n".join(prompt_parts)

        models_to_try = [
            settings.GEMINI_MODEL,
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
        ]
        last_error = None
        for model_name in dict.fromkeys(models_to_try):
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=GeneratedContentPlan,
                        temperature=0.7,
                    ),
                )
                data = json.loads(response.text)
                return GeneratedContentPlan(**data)
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini model %s failed (%s); trying fallback...", model_name, exc)
                continue

        raise last_error or RuntimeError("All Gemini models failed.")

    def _generate_deterministic_fallback(self, request: ContentGenerationRequest) -> GeneratedContentPlan:
        clean_prompt = request.prompt.strip()

        return GeneratedContentPlan(
            intent_summary=f"Strategic broadcast regarding: {clean_prompt[:60]}...",
            linkedin=LinkedInPostVariant(
                headline=f"🚀 The game is changing: {clean_prompt}",
                body=(
                    "In fast-moving businesses, agility isn't just about speed—it's about orchestration.\n\n"
                    "Here are 3 key principles we've learned:\n"
                    "• Automate operational friction without losing human oversight.\n"
                    "• Keep communication lines short, transparent, and data-driven.\n"
                    "• Focus energy where the highest leverage lies."
                ),
                call_to_action="How is your team approaching this shift this quarter? Let's discuss below 👇",
                hashtags=["#AIOperations", "#BusinessStrategy", "#FutureOfWork", "#Leadership"],
            ),
            x=XPostVariant(
                text=f"Agility isn't just speed—it's orchestration. {clean_prompt[:140]}",
                hashtags=["#AIBusiness", "#Strategy"],
            ),
            instagram=InstagramPostVariant(
                caption=f"Behind the scenes on how modern teams execute: {clean_prompt}",
                call_to_action="Save this for your next sprint planning session and drop your thoughts below.",
                hashtags=["#AIOperations", "#Founders", "#BusinessGrowth", "#Productivity", "#BuildInPublic"],
                media_guidance="Clean editorial 4:5 carousel or high-contrast dark studio graphic with concise headline overlay.",
            ),
            suggested_media_prompt=(
                f"Minimalist futuristic 3D render representing '{clean_prompt}', clean typography, dark theme lighting, 8k resolution"
            ),
            rationale="Structured around a LinkedIn storytelling hook, punchy X takeaway, and visual-first Instagram caption.",
        )
