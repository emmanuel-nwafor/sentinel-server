import os
import json
import logging
import re
from typing import List, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
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


async def scrape_webpage_content(raw_url: str) -> Dict[str, Any]:
    """
    Real-time webpage scraper that extracts human-readable text,
    page title, meta descriptions, and architectural cues from any live website.
    """
    url = raw_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 DispatchAgent/2.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=14.0) as client:
            resp = await client.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "iframe", "footer", "form"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            meta_desc = ""
            meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
                "meta", attrs={"property": "og:description"}
            )
            if meta_tag and meta_tag.get("content"):
                meta_desc = meta_tag["content"].strip()

            headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])[:12]]
            body_text = " ".join(soup.stripped_strings)[:6000]

            return {
                "status": "success",
                "target_url": str(resp.url),
                "http_status": resp.status_code,
                "page_title": title,
                "meta_description": meta_desc,
                "key_headings": headings,
                "extracted_content": body_text,
            }
    except Exception as exc:
        logger.warning("Scraping failed for %s: %s", url, exc)
        return {
            "status": "error",
            "target_url": url,
            "error_detail": str(exc),
        }


class ContentOperatorAgent:
    """
    Dispatch Autonomous Content & Social Operator Agent:
    Capable of active tool calling, multi-turn reasoning, live webpage inspection,
    platform database analytics, and platform-native post dispatch.
    """

    def __init__(self):
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None

    async def execute(
        self,
        request: ContentGenerationRequest,
        brand_voice_prompt: str = None,
    ) -> GeneratedContentPlan:
        if not self.client:
            raise RuntimeError("Gemini AI client is not configured or API key is missing.")
        return await self._generate_with_llm(request, brand_voice_prompt)

    async def chat(
        self,
        request: CopilotChatRequest,
        brand_voice_prompt: str = None,
        connected_profiles_info: list = None,
        user_context: dict = None,
        recent_posts_info: list = None,
    ) -> CopilotChatResponse:
        user_msg = request.message.strip()

        # Build live connected profiles summary
        profiles_desc = []
        for p in (connected_profiles_info or []):
            plat = p.get("platform", "").capitalize()
            name = p.get("account_name", "Creator")
            handle = p.get("account_handle", "—")
            active = "Active & Ready" if p.get("is_active") else "Inactive"
            profiles_desc.append(f"• {plat}: {name} ({handle}) — [{active}]")
        profiles_str = (
            "\n".join(profiles_desc) if profiles_desc else "No connected accounts found."
        )

        user_name = (user_context or {}).get("name") or "Creator"
        user_niche = (user_context or {}).get("niche") or "Fullstack Engineering & AI Automation"

        # Agentic Tool Definitions
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="browse_website",
                        description=(
                            "Fetch, read, and inspect the real live content of any website or public URL "
                            "(e.g. personal portfolios like emstack.online, GitHub repositories, technical articles, "
                            "documentation, or company homepages). ALWAYS call this tool whenever the user provides "
                            "a URL or domain, or asks you to check, visit, go through, or analyze a website."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "url": types.Schema(
                                    type="STRING",
                                    description="The target URL or domain name (e.g., 'emstack.online' or 'https://github.com/...')",
                                ),
                            },
                            required=["url"],
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="draft_post_plan",
                        description=(
                            "Synthesize high-performing, platform-tailored post variants for LinkedIn, X (Twitter), "
                            "and Instagram. Invoke this ONLY when the user explicitly requests to draft, write, "
                            "compose, or generate social posts from a topic, draft, or analyzed website."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "topic_or_draft": types.Schema(
                                    type="STRING",
                                    description="The core topic or content to draft social posts from.",
                                ),
                                "angle": types.Schema(
                                    type="STRING",
                                    description="Optional angle or strategic focus.",
                                ),
                            },
                            required=["topic_or_draft"],
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="get_connected_accounts_info",
                        description=(
                            "Retrieve details about the user's currently connected social media accounts "
                            "(platforms, handles, connection readiness)."
                        ),
                        parameters=types.Schema(type="OBJECT", properties={}),
                    ),
                    types.FunctionDeclaration(
                        name="get_user_recent_posts",
                        description=(
                            "Retrieve the user's recently published or scheduled posts and engagement metrics "
                            "(likes, comments, views) from Dispatch."
                        ),
                        parameters=types.Schema(type="OBJECT", properties={}),
                    ),
                    types.FunctionDeclaration(
                        name="get_user_brand_context",
                        description=(
                            "Retrieve the user's verified brand memory, headline, bio, skills, and background."
                        ),
                        parameters=types.Schema(type="OBJECT", properties={}),
                    ),
                    types.FunctionDeclaration(
                        name="publish_post_to_social",
                        description=(
                            "Autonomously publish a post live to a connected social platform (LinkedIn, X, or Instagram). "
                            "Invoke this ONLY when the user explicitly commands to post, publish, or dispatch directly."
                        ),
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
                ]
            )
        ]

        headline = (user_context or {}).get("headline") or ""
        about_summary = (user_context or {}).get("about") or ""
        skills_str = ", ".join((user_context or {}).get("skills") or [])
        company = (user_context or {}).get("current_company") or ""
        edu = (user_context or {}).get("education") or ""
        li_info = (
            f"{(user_context or {}).get('linkedin_name')} ({(user_context or {}).get('linkedin_handle')})"
            if (user_context or {}).get("linkedin_handle")
            else "Not connected"
        )
        x_info = (
            f"{(user_context or {}).get('x_name')} ({(user_context or {}).get('x_handle')})"
            if (user_context or {}).get("x_handle")
            else "Not connected"
        )

        system_instruction = f"""
You are the Dispatch Autonomous Social Operator — an elite, witty, action-oriented Technical Co-Pilot and Head of Content.
You are NOT a passive chatbot; you have real-world operational tools to browse live websites, check accounts, analyze metrics, and execute actions.

CORE OPERATIONAL BEHAVIORS:
1. Active Web Browsing:
   - When the user provides a website URL or asks to "go through a website", "check this link", "read this domain", or mentions any site (e.g. emstack.online, github.com, etc.), you MUST invoke the `browse_website` tool to inspect the real content.
   - NEVER pretend or hallucinate that you visited a site without calling `browse_website`.
2. Respect User Command & Phase:
   - If the user says "go through it first", "do not generate anything yet", or asks for analysis/critique, DO NOT call `draft_post_plan`!
   - Instead, thoroughly inspect the website, provide an insightful breakdown (Hero Identity, Core Projects, Tech Stack, Systems Architecture, Strengths, and Strategic Opportunities), and ask the user how they would like to proceed.
   - ONLY call `draft_post_plan` when the user explicitly asks to draft, write, compose, or create posts.
3. Multi-Turn Conversation Memory:
   - Always remember previous turns in the conversation. When the user says "I said go through it first" or refers to something mentioned earlier, maintain complete continuity.
4. Voice & Style:
   - Clean, charismatic, concise, and professional.
   - Use clean Unicode bullet points (•) and clear headings. Avoid excessive bold asterisks.
   - The platform name is ALWAYS Dispatch.

CREATOR IDENTITY (MEMORY):
• Name: {user_name}
• Headline: {headline if headline else "Software Engineer & Builder"}
• Roles/Projects: {company if company else "Building high-performance web & mobile systems"}
• Education: {edu if edu else "Electrical and Electronics Engineering"}
• Verified Niche: {user_niche}
• Core Skills: {skills_str if skills_str else "React Native, TypeScript, Distributed Systems, Next.js, Node.js"}
• Verified LinkedIn: {li_info}
• Verified 𝕏: {x_info}

CONNECTED ACCOUNTS:
{profiles_str}
"""

        if not self.client:
            return CopilotChatResponse(
                type="advice",
                reply="⚠️ Gemini AI client is not configured. Please check your GEMINI_API_KEY in backend/.env.",
                plan=None,
                suggested_actions=["Check API keys", "Retry"],
            )

        # Build contents array from conversation history turns
        contents: List[types.Content] = []

        # Add recent conversation turns
        for turn in (request.conversation_history or [])[-6:]:
            role = "user" if turn.role == "user" else "model"
            if turn.text and turn.text.strip():
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=clean_text_formatting(turn.text))],
                    )
                )

        # Build current turn
        current_parts: List[types.Part] = []
        if request.media_url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as img_client:
                    img_resp = await img_client.get(request.media_url)
                    if img_resp.status_code == 200:
                        ctype = img_resp.headers.get("content-type") or "image/jpeg"
                        current_parts.append(
                            types.Part.from_bytes(data=img_resp.content, mime_type=ctype)
                        )
            except Exception as img_err:
                logger.warning("Multimodal image fetch failed: %s", img_err)

        current_parts.append(types.Part.from_text(text=user_msg))
        if brand_voice_prompt:
            current_parts.append(
                types.Part.from_text(text=f"[Custom Brand Voice Persona]:\n{brand_voice_prompt}")
            )

        contents.append(types.Content(role="user", parts=current_parts))

        models_to_try = [
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-pro-latest",
        ]

        last_error = None
        for model_name in models_to_try:
            try:
                # ReAct Tool Execution Loop (up to 4 autonomous iterations)
                for _ in range(4):
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=tools,
                            temperature=0.4,
                        ),
                    )

                    candidate = response.candidates[0] if response.candidates else None
                    if not candidate or not candidate.content:
                        break

                    parts = candidate.content.parts or []
                    contents.append(candidate.content)

                    # Inspect for function calls
                    function_calls = [p.function_call for p in parts if p.function_call]
                    if not function_calls:
                        # Reached terminal conversational answer
                        text_parts = [p.text for p in parts if p.text]
                        reply_text = clean_text_formatting(" ".join(text_parts))

                        # Contextual suggested action pills
                        actions = [
                            "Draft a high-impact post on this",
                            "Turn this into an 𝕏 thread",
                            "Check my connected accounts",
                        ]
                        if "emstack.online" in reply_text.lower() or "website" in reply_text.lower():
                            actions = [
                                "Draft post spotlighting GoEatOne",
                                "Write 𝕏 thread on my backend architecture",
                                "How should I position my services?",
                            ]

                        return CopilotChatResponse(
                            type="advice",
                            reply=reply_text,
                            plan=None,
                            suggested_actions=actions,
                        )

                    # Execute function calls
                    for fn in function_calls:
                        fn_name = fn.name
                        fn_args = fn.args or {}
                        logger.info("Dispatch Agent executing tool: %s with args: %s", fn_name, fn_args)

                        if fn_name == "browse_website":
                            url_to_browse = fn_args.get("url") or user_msg
                            tool_result = await scrape_webpage_content(url_to_browse)
                            resp_part = types.Part.from_function_response(
                                name=fn_name,
                                response={"result": tool_result},
                            )
                            contents.append(types.Content(role="user", parts=[resp_part]))

                        elif fn_name == "get_connected_accounts_info":
                            tool_result = {
                                "connected_accounts": profiles_desc,
                                "raw_profiles": connected_profiles_info or [],
                            }
                            resp_part = types.Part.from_function_response(
                                name=fn_name,
                                response={"result": tool_result},
                            )
                            contents.append(types.Content(role="user", parts=[resp_part]))

                        elif fn_name == "get_user_recent_posts":
                            tool_result = {
                                "recent_posts": recent_posts_info or [],
                                "total_retrieved": len(recent_posts_info or []),
                            }
                            resp_part = types.Part.from_function_response(
                                name=fn_name,
                                response={"result": tool_result},
                            )
                            contents.append(types.Content(role="user", parts=[resp_part]))

                        elif fn_name == "get_user_brand_context":
                            tool_result = {
                                "name": user_name,
                                "headline": headline,
                                "company": company,
                                "education": edu,
                                "skills": skills_str,
                                "about": about_summary,
                            }
                            resp_part = types.Part.from_function_response(
                                name=fn_name,
                                response={"result": tool_result},
                            )
                            contents.append(types.Content(role="user", parts=[resp_part]))

                        elif fn_name == "draft_post_plan":
                            topic = fn_args.get("topic_or_draft") or user_msg
                            gen_req = ContentGenerationRequest(
                                prompt=f"{topic} (Niche: {user_niche})",
                                workspace=request.workspace,
                            )
                            plan = await self.execute(gen_req, brand_voice_prompt=brand_voice_prompt)
                            return CopilotChatResponse(
                                type="plan",
                                reply=(
                                    f"Synthesized a multi-platform distribution plan tailored for your active channels "
                                    f"and {user_niche} niche. Review, attach any media, and dispatch live below!"
                                ),
                                plan=plan,
                                suggested_actions=[
                                    "⚡ Make Punchier (<280)",
                                    "🎯 Stronger Hook",
                                    "📊 Add System Metrics",
                                ],
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

            except Exception as exc:
                last_error = exc
                logger.warning("Gemini model %s encountered error (%s); trying fallback...", model_name, exc)
                continue

        error_detail = str(last_error) if last_error else "AI models temporarily unavailable"
        logger.error("All Gemini models failed: %s", error_detail)
        return CopilotChatResponse(
            type="advice",
            reply=f"⚠️ Something went wrong while connecting to the AI engine ({error_detail}). Please try again in a few moments.",
            plan=None,
            suggested_actions=["Retry request", "Check system status"],
        )

    async def _generate_with_llm(
        self,
        request: ContentGenerationRequest,
        brand_voice_prompt: str = None,
    ) -> GeneratedContentPlan:
        system_instruction = """
        You are the Dispatch Content Operator Agent for modern AI-driven businesses.
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
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-pro-latest",
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
