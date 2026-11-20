import os
import json
import logging
from google import genai
from google.genai import types
from backend.core.config import settings
from backend.schemas.content import (
    ContentGenerationRequest,
    GeneratedContentPlan,
    LinkedInPostVariant,
    XPostVariant,
    InstagramPostVariant,
    CopilotChatRequest,
    CopilotChatResponse,
)

logger = logging.getLogger(__name__)


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

    async def chat(
        self,
        request: CopilotChatRequest,
        brand_voice_prompt: str = None,
    ) -> CopilotChatResponse:
        user_msg = request.message.strip()
        user_msg_lower = user_msg.lower()

        # Check if the prompt is an explicit command to draft/write a post or thread
        draft_triggers = [
            "draft", "write a post", "compose a post", "create a post", "craft a post",
            "generate post", "write a tweet", "write a thread", "dispatch a post",
            "make a post", "write post", "draft post", "announce our", "craft a",
        ]
        is_draft_request = any(t in user_msg_lower for t in draft_triggers) or len(user_msg) > 130

        if is_draft_request:
            gen_request = ContentGenerationRequest(
                prompt=user_msg,
                workspace=request.workspace,
            )
            plan = await self.execute(gen_request, brand_voice_prompt=brand_voice_prompt)
            return CopilotChatResponse(
                type="plan",
                reply="I've crafted an omnichannel distribution plan optimized for your connected platforms. Review the variants below and dispatch live whenever you are ready.",
                plan=plan,
                suggested_actions=["⚡ Make Punchier (<280)", "🎯 Stronger Hook", "📊 Add Data/Metrics"],
            )

        # Autonomous Social Media Operator Reasoning & Advice
        if self.client:
            try:
                system_instruction = """
                You are the Dispatch Autonomous Social Operator. You are not a generic chatbot or simple draft tool;
                you are an elite social operations partner for founders, software builders, and business creators on LinkedIn and 𝕏.

                Your personality:
                - Highly strategic, sharp, executive, and direct (like a top-tier Head of Growth & Communications).
                - Grounded in modern algorithmic reality: explain why comment velocity in the first 60 minutes matters on LinkedIn,
                  why external links kill organic reach (put links in comments), how dwell time works, and how to craft polarizing or high-signal 𝕏 hooks.
                - When asked about niche topics, audience engagement, or strategy, provide 2 to 3 concise, punchy bullet points followed by a concrete next action.
                - Keep total response under 200 words. Format with clean markdown bullets.
                """
                platforms_str = ", ".join(request.connected_platforms) if request.connected_platforms else "LinkedIn, 𝕏"
                prompt = (
                    f"Connected Channels: {platforms_str}\n"
                    f"User Inquiry: {user_msg}\n"
                )
                if brand_voice_prompt:
                    prompt += f"\nBrand Voice:\n{brand_voice_prompt}"

                models_to_try = [
                    settings.GEMINI_MODEL or "gemini-3.8-flash",
                    "gemini-3.8-flash",
                    "gemini-flash-latest",
                    "gemini-flash-lite-latest",
                ]
                for model_name in dict.fromkeys(models_to_try):
                    try:
                        resp = self.client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction,
                                temperature=0.6,
                            ),
                        )
                        reply_text = resp.text.strip()
                        return CopilotChatResponse(
                            type="advice",
                            reply=reply_text,
                            plan=None,
                            suggested_actions=[
                                "Draft LinkedIn Post on this",
                                "Draft 𝕏 Thread",
                                "Optimize Reach Strategy",
                            ],
                        )
                    except Exception as e:
                        logger.warning("Gemini chat model %s failed: %s", model_name, e)
            except Exception as e:
                logger.warning("Gemini chat failed (%s); using fallback response.", e)

        # High-signal fallback operator response
        fallback_reply = (
            f"Here is your strategic distribution breakdown for **{user_msg[:50]}**:\n\n"
            f"• **LinkedIn**: Maximize dwell time by opening with a high-contrast dilemma before offering the solution. Keep links out of the main post.\n"
            f"• **𝕏 (Twitter)**: Lead with a 1-sentence contrarian claim. Fast replies in the first 30 minutes boost algorithmic distribution.\n"
            f"• **Next Move**: Shall I draft a platform-native post or thread on this topic for you?"
        )
        return CopilotChatResponse(
            type="advice",
            reply=fallback_reply,
            plan=None,
            suggested_actions=["Draft LinkedIn Post on this", "Draft 𝕏 Thread", "Schedule Multi-Platform"],
        )

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
            settings.GEMINI_MODEL or "gemini-3.8-flash",
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
            "gemini-2.5-flash-lite",
            "gemini-2.5-pro",
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
