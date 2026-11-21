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
        connected_profiles_info: list = None,
        user_context: dict = None,
    ) -> CopilotChatResponse:
        user_msg = request.message.strip()
        user_msg_lower = user_msg.lower()

        # Build live connected profiles summary from Neon DB
        profiles_desc = []
        for p in (connected_profiles_info or []):
            plat = p.get("platform", "").capitalize()
            name = p.get("account_name", "Creator")
            handle = p.get("account_handle", "—")
            active = "Active & Ready" if p.get("is_active") else "Inactive"
            profiles_desc.append(f"• {plat}: {name} ({handle}) — [{active}]")
        profiles_str = "\n".join(profiles_desc) if profiles_desc else "No connected accounts found."

        user_name = (user_context or {}).get("name") or "Emmanuel Onyekachi"
        user_niche = (user_context or {}).get("niche") or "Software Engineer, AI Engineer, AI Automation & Scalable Architecture"

        # Agentic Architecture: Tools (Function Declarations)
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="draft_post_plan",
                        description="Synthesize high-performing, platform-tailored post variants for LinkedIn, X (Twitter), and Instagram based on the user's topic, raw notes, or draft. Use this whenever the user asks to draft, write, compose, enhance, or create a post.",
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "topic_or_draft": types.Schema(
                                    type="STRING",
                                    description="The core topic, raw notes, or draft content to enhance and turn into social posts.",
                                ),
                                "angle": types.Schema(
                                    type="STRING",
                                    description="Optional technical angle, contrarian perspective, or strategic hook.",
                                ),
                            },
                            required=["topic_or_draft"],
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="publish_post_to_social",
                        description="Autonomously publish a post live to a connected social platform (LinkedIn, X, or Instagram). Use this ONLY when the user explicitly asks to post, publish, or dispatch directly.",
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "platform": types.Schema(
                                    type="STRING",
                                    description="Target platform: 'linkedin', 'x', or 'instagram'.",
                                ),
                                "content": types.Schema(
                                    type="STRING",
                                    description="The post content to publish.",
                                ),
                            },
                            required=["platform"],
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="get_connected_accounts_info",
                        description="Retrieve details about the user's connected social media accounts (handles, status). Use this ONLY when the user explicitly asks to check or list their connected accounts or profiles.",
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={},
                        ),
                    ),
                ]
            )
        ]

        system_instruction = f"""
You are the Dispatch Autonomous Social Operator — an elite Head of Content and Technical Co-Pilot.

USER BACKGROUND MEMORY (RAG & PERSISTENT CONTEXT):
- User Name: {user_name}
- Professional Niche & Identity: {user_niche}
- Core Topics: Distributed Systems, Scalable Architectures, AI Agents, Engineering Automation, Modern Full-Stack Development
- Target Audience: Tech founders, senior software engineers, system architects, AI builders
- Tone: High-conviction, opinionated, witty, charismatic, and technical with zero corporate buzzword fluff.

CONNECTED SOCIAL CHANNELS (DATABASE STATE):
{profiles_str}

CORE OPERATING PRINCIPLES:
1. Tool Calling:
   - When the user asks to write, draft, synthesize, enhance, compose, or creates a post (or provides raw notes from the composer), invoke `draft_post_plan`.
   - When the user asks to publish or post directly to their live feeds, invoke `publish_post_to_social`.
   - When the user explicitly asks about their accounts, handles, or connection status, invoke `get_connected_accounts_info`.
   - For technical questions (system design, architecture trade-offs, code, career, debate), respond conversationally as an elite technical co-pilot.
2. Background Memory:
   - You ALREADY know who the user is from USER BACKGROUND MEMORY. DO NOT recite or list their profile, niche, or handles unless they explicitly ask for it!
   - Every post you draft MUST reflect their real niche ({user_niche}) rather than generic business jargon.
3. Clean Formatting:
   - Format with clean GitHub markdown. Never use raw escaped backslashes like \\n or robotic asterisk prefixes (* **).
"""

        # Fast Tool-Calling Execution Loop
        if self.client:
            models_to_try = [
                "gemini-3.1-flash-lite",
                "gemini-2.5-pro",
                "gemini-3-flash-preview",
                "gemini-pro-latest",
                "gemini-flash-latest",
            ]
            for model_name in models_to_try:
                try:
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

                    contents_payload.append(f"User Message: {user_msg}")
                    if brand_voice_prompt:
                        contents_payload.append(f"[Custom Brand Voice Persona]:\n{brand_voice_prompt}")

                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=contents_payload,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=tools,
                            temperature=0.4,
                        ),
                    )

                    candidate = response.candidates[0]
                    parts = candidate.content.parts if candidate and candidate.content else []

                    # Check for tool/function calls
                    for part in parts:
                        if part.function_call:
                            fn_name = part.function_call.name
                            fn_args = part.function_call.args or {}
                            logger.info("Agent invoked tool: %s with args: %s", fn_name, fn_args)

                            if fn_name == "draft_post_plan":
                                topic = fn_args.get("topic_or_draft") or user_msg
                                gen_req = ContentGenerationRequest(
                                    prompt=f"{topic} (Niche: {user_niche})",
                                    workspace=request.workspace,
                                )
                                plan = await self.execute(gen_req, brand_voice_prompt=brand_voice_prompt)
                                return CopilotChatResponse(
                                    type="plan",
                                    reply=f"Synthesized a multi-platform distribution plan tailored for your active channels and {user_niche} niche. Review, attach any media, and dispatch live below!",
                                    plan=plan,
                                    suggested_actions=["⚡ Make Punchier (<280)", "🎯 Stronger Hook", "📊 Add System Metrics"],
                                )

                            elif fn_name == "get_connected_accounts_info":
                                reply_text = f"Here are your connected social accounts retrieved from Sentinel:\n\n{profiles_str}\n\nAll set and ready for autonomous dispatch! Would you like me to draft a post for one of these?"
                                return CopilotChatResponse(
                                    type="advice",
                                    reply=reply_text,
                                    plan=None,
                                    suggested_actions=["Draft a LinkedIn post", "Draft an 𝕏 thread", "How to boost reach this week?"],
                                )

                            elif fn_name == "publish_post_to_social":
                                target_plat = fn_args.get("platform", "linkedin")
                                return CopilotChatResponse(
                                    type="advice",
                                    reply=f"Publishing initiated for {target_plat}.",
                                    plan=None,
                                    auto_dispatched=True,
                                    published_platform=target_plat,
                                )

                    # If no function call, return conversational response
                    text_parts = [p.text for p in parts if p.text]
                    if text_parts:
                        full_reply = clean_text_formatting(" ".join(text_parts))
                        return CopilotChatResponse(
                            type="advice",
                            reply=full_reply,
                            plan=None,
                            suggested_actions=[
                                "Draft a technical post on this",
                                "How to format this for LinkedIn?",
                                "Check my connected accounts",
                            ],
                        )
                except Exception as exc:
                    logger.warning("Gemini model %s failed (%s); trying next model...", model_name, exc)
                    continue

        # Dynamic topic-tailored fallback if models are temporarily unavailable
        topic_clean = re.sub(r"^(what|how|why|tell\s+me|generate|write|draft|compose)\s+(is|about|regarding)?\s*", "", user_msg, flags=re.IGNORECASE).strip()
        topic = topic_clean[:50] if topic_clean else "system architecture"

        # If user explicitly asked to draft or enhance
        if any(w in user_msg_lower for w in ["draft", "write", "post", "enhance", "compose", "sharding"]):
            gen_req = ContentGenerationRequest(prompt=f"{topic} (Niche: {user_niche})", workspace=request.workspace)
            plan = self._generate_deterministic_fallback(gen_req)
            return CopilotChatResponse(
                type="plan",
                reply=f"Generated an architectural distribution plan focused on {topic} for your engineering niche.",
                plan=plan,
                suggested_actions=["⚡ Make Punchier (<280)", "🎯 Stronger Hook", "📊 Add System Metrics"],
            )

        fallback_reply = (
            f"Here is the architectural takeaway on **{topic}**:\n\n"
            f"• **The Core Trade-off**: At scale, premature optimization hurts velocity. Keep boundaries clean and establish clear query patterns before sharding or decoupling.\n"
            f"• **Distribution Strategy**: On LinkedIn, lead with a strong counter-intuitive engineering truth. On 𝕏, keep it dense with high signal.\n\n"
            f"Want me to draft a dedicated post or multi-platform thread on this right now?"
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
            "gemini-2.5-pro",
            "gemini-3-flash-preview",
            "gemini-pro-latest",
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
        topic = re.sub(r"^(draft|write|generate|compose|create|post)\s+(a\s+post|a\s+thread|something)?\s*(about|regarding|on)?\s*", "", clean_prompt, flags=re.IGNORECASE).strip()
        if not topic:
            topic = clean_prompt[:40]

        tag_topic = re.sub(r"[^A-Za-z0-9]", "", topic.title())[:20]

        return GeneratedContentPlan(
            intent_summary=f"Technical distribution blueprint: {topic}",
            linkedin=LinkedInPostVariant(
                headline=f"Most engineers approach {topic} the wrong way.",
                body=(
                    f"When scaling modern architectures, the bottleneck with {topic} is rarely raw compute.\n\n"
                    "It almost always comes down to 3 core trade-offs:\n"
                    f"• Data boundaries: Sharding or partitioning before query patterns settle leads to distributed join nightmares.\n"
                    "• Consistency vs. Latency: Choosing strong consistency when eventual consistency would 10x your throughput.\n"
                    "• Operational observability: If you can't trace cross-node latency in real time, you're flying blind.\n\n"
                    f"The teams winning in production aren't over-engineering—they are designing {topic} for graceful degradation."
                ),
                call_to_action="What has been your biggest architectural lesson when tackling this? Drop your thoughts below 👇",
                hashtags=[f"#{tag_topic}", "#SystemDesign", "#SoftwareEngineering", "#Architecture", "#DevCommunity"],
            ),
            x=XPostVariant(
                text=f"Most teams over-engineer {topic} before understanding their query patterns.\n\nKeep boundaries clean, prioritize latency where it matters, and never shard before you measure.",
                hashtags=[f"#{tag_topic}", "#SystemDesign"],
            ),
            instagram=InstagramPostVariant(
                caption=f"Breaking down {topic} for engineers building systems that scale.\n\nSwipe through for the 3 architectural rules we live by before shipping to production.",
                call_to_action="Bookmark this for your next system design review.",
                hashtags=[f"#{tag_topic}", "#Engineering", "#TechLeaders", "#BuildInPublic", "#Developers"],
                media_guidance="Dark minimalist architecture diagram showing clean data partitioning and microservice boundaries.",
            ),
            suggested_media_prompt=(
                f"Minimalist technical system architecture diagram illustrating {topic}, dark navy and neon cyan palette, clean vector lines"
            ),
            rationale=f"Opinionated, high-conviction technical breakdown tailored directly to {topic}.",
        )
