import os
import json
import logging
import re
import httpx
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


def clean_text_formatting(text: str) -> str:
    if not text:
        return ""
    # Unescape literal backslashes like \n or \r\n
    cleaned = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    # Replace markdown bullet asterisks e.g. "* **Title:**" or "* Bullet" with Unicode bullet "• "
    cleaned = re.sub(r"^\s*[*•-]\s+\*\*(.*?)\*\*:\s*", r"• \1: ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[*•-]\s+", r"• ", cleaned, flags=re.MULTILINE)
    # Strip remaining bold/italic asterisks that clutter native mobile text
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
    return cleaned.strip()


def clean_hashtag_list(raw_tags: list) -> list:
    cleaned = []
    for tag in raw_tags or []:
        for part in re.split(r"[,;'\"]+", str(tag)):
            p_clean = part.strip().strip("'\"#")
            if p_clean and re.match(r"^[A-Za-z0-9_]+$", p_clean):
                cleaned.append(f"#{p_clean}")
    return list(dict.fromkeys(cleaned))


class ContentOperatorAgent:
    """
    Dispatch Content Operator Agent:
    Transforms natural language intents into platform-native posts for LinkedIn, X, and Instagram
    using Gemini with lightning-fast response times and natural real-time chat interactions.
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

        # Handle simple greetings and pleasantries naturally and immediately
        greetings = ["hello", "hi", "hey", "good morning", "good evening", "howdy", "sup"]
        if user_msg_lower in greetings or any(user_msg_lower == g for g in greetings):
            return CopilotChatResponse(
                type="advice",
                reply="Hello! I'm your Dispatch Copilot. I'm connected to your channels and ready to help you brainstorm topics, refine your hook, analyze audience distribution, or draft high-performing posts for LinkedIn and 𝕏. What are we working on today?",
                plan=None,
                suggested_actions=[
                    "Draft a post on our latest launch",
                    "How to boost LinkedIn reach this week?",
                    "Analyze my distribution strategy",
                ],
            )

        # Only trigger full multi-platform post generation if the user explicitly asks to draft or write
        explicit_draft_triggers = [
            "draft a post", "draft post", "write a post", "write post",
            "compose a post", "create a post", "craft a post", "generate a post",
            "write a tweet", "write a thread", "dispatch a post", "draft a thread",
            "draft linkedin", "write linkedin", "draft for linkedin",
        ]
        is_draft_request = any(t in user_msg_lower for t in explicit_draft_triggers)

        if is_draft_request:
            gen_request = ContentGenerationRequest(
                prompt=user_msg,
                workspace=request.workspace,
            )
            plan = await self.execute(gen_request, brand_voice_prompt=brand_voice_prompt)
            return CopilotChatResponse(
                type="plan",
                reply="Here is your multi-platform distribution plan tailored for your active channels. Review and dispatch live whenever you are ready.",
                plan=plan,
                suggested_actions=["⚡ Make Punchier (<280)", "🎯 Stronger Hook", "📊 Add Data/Metrics"],
            )

        # Real-time Interactive Chat & Strategic Operator Assistance
        if self.client:
            try:
                system_instruction = """
                You are the Dispatch Autonomous Social Operator, a real-time AI partner built directly into the Dispatch platform.
                You are conversational, insightful, executive, and direct (like a world-class Head of Growth).

                Core Behaviors:
                - Communicate naturally and responsively like Gemini.
                - Answer questions directly, brainstorm creative angles, critique ideas, and share tactical platform wisdom (LinkedIn comment velocity, 𝕏 dwell time, hook density).
                - Keep responses clean, concise, and punchy (1 to 3 short paragraphs or bullet points).
                - Do NOT dump generic post templates or boilerplate drafts unless the user explicitly tells you to draft a post.
                - Format with clean GitHub markdown. Never use escaped backslashes like \\n in your responses.
                """
                platforms_str = ", ".join(request.connected_platforms) if request.connected_platforms else "LinkedIn, 𝕏"
                prompt = (
                    f"Active Platforms: {platforms_str}\n"
                    f"User Message: {user_msg}\n"
                )
                if brand_voice_prompt:
                    prompt += f"\nBrand Voice Context:\n{brand_voice_prompt}"

                contents_payload: list = []
                if request.media_url:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as img_client:
                            img_resp = await img_client.get(request.media_url)
                            if img_resp.status_code == 200:
                                ctype = img_resp.headers.get("content-type") or "image/jpeg"
                                contents_payload.append(
                                    types.Part.from_bytes(data=img_resp.content, mime_type=ctype)
                                )
                    except Exception as img_err:
                        logger.warning("Multimodal image fetch failed: %s", img_err)

                contents_payload.append(prompt)

                # Prioritize fast, high-performance models
                models_to_try = [
                    "gemini-3.1-flash-lite",
                    "gemini-3.8-flash",
                    "gemini-flash-latest",
                ]
                for model_name in models_to_try:
                    try:
                        resp = self.client.models.generate_content(
                            model=model_name,
                            contents=contents_payload,
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction,
                                temperature=0.7,
                            ),
                        )
                        reply_text = clean_text_formatting(resp.text)
                        return CopilotChatResponse(
                            type="advice",
                            reply=reply_text,
                            plan=None,
                            suggested_actions=[
                                "Draft LinkedIn Post on this",
                                "Draft 𝕏 Thread",
                                "Refine Strategic Hook",
                            ],
                        )
                    except Exception as e:
                        logger.warning("Gemini model %s failed: %s", model_name, e)
            except Exception as e:
                logger.warning("Gemini chat failed (%s); using fallback response.", e)

        # Graceful conversational fallback
        fallback_reply = (
            f"Regarding **{user_msg[:60]}**:\n\n"
            f"• **Strategy**: Lead with a contrarian, high-signal takeaway to stop the feed scroll immediately.\n"
            f"• **Channel Nuance**: On LinkedIn, focus on professional lessons; on 𝕏, optimize for concise conviction.\n\n"
            f"Would you like me to draft a dedicated post or thread on this for you?"
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
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash",
            "gemini-flash-latest",
        ]
        last_error = None
        for model_name in models_to_try:
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
                # Clean up formatting signatures, escaped newlines and malformed hashtag strings
                if "linkedin" in data and isinstance(data["linkedin"], dict):
                    li = data["linkedin"]
                    li["headline"] = clean_text_formatting(li.get("headline", ""))
                    li["body"] = clean_text_formatting(li.get("body", ""))
                    li["call_to_action"] = clean_text_formatting(li.get("call_to_action", ""))
                    li["hashtags"] = clean_hashtag_list(li.get("hashtags", []))

                if "x" in data and isinstance(data["x"], dict):
                    x_var = data["x"]
                    x_var["text"] = clean_text_formatting(x_var.get("text", ""))
                    x_var["hashtags"] = clean_hashtag_list(x_var.get("hashtags", []))

                if "instagram" in data and isinstance(data["instagram"], dict):
                    ig = data["instagram"]
                    ig["caption"] = clean_text_formatting(ig.get("caption", ""))
                    ig["call_to_action"] = clean_text_formatting(ig.get("call_to_action", ""))
                    ig["media_guidance"] = clean_text_formatting(ig.get("media_guidance", ""))
                    ig["hashtags"] = clean_hashtag_list(ig.get("hashtags", []))

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
