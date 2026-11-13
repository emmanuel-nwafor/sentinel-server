import json
import logging
import os
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from backend.core.config import settings
from backend.schemas.inbox import SupportReplySuggestionResponse

logger = logging.getLogger(__name__)


class SupportOperatorAgent:
    """
    Dispatch AI Support Co-Pilot:
    Analyzes incoming customer DMs/comments across Instagram, X, and LinkedIn,
    detects intent (sizing, shipping, pricing, product availability),
    and synthesizes high-converting, empathetic customer service replies.
    """

    def __init__(self):
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None

    async def generate_reply_suggestion(
        self,
        *,
        customer_name: str,
        platform: str,
        latest_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        store_context: str = "Premium handcrafted shoes and sneakers with nationwide express delivery and 30-day hassle-free exchanges.",
    ) -> SupportReplySuggestionResponse:
        if self.client:
            return await self._generate_with_llm(
                customer_name=customer_name,
                platform=platform,
                latest_message=latest_message,
                history=history or [],
                store_context=store_context,
            )
        return self._generate_fallback(
            customer_name=customer_name,
            platform=platform,
            latest_message=latest_message,
        )

    async def _generate_with_llm(
        self,
        *,
        customer_name: str,
        platform: str,
        latest_message: str,
        history: List[Dict[str, Any]],
        store_context: str,
    ) -> SupportReplySuggestionResponse:
        system_instruction = f"""
        You are Dispatch's AI Customer Support Co-Pilot for modern businesses and creators.
        Your goal is to help the business owner respond to customer DMs and comments promptly, warmly, and helpfully.

        Store Context: {store_context}

        Guidelines:
        1. Keep replies friendly, concise, and natural (1-3 sentences max).
        2. Greet the customer by their first name if available.
        3. Match the platform tone ({platform}):
           - Instagram: Warm, aesthetic, emoji-friendly.
           - X (Twitter): Direct, concise, fast.
           - LinkedIn: Professional, appreciative, structured.
        4. Always include a gentle next step (e.g. asking for their size, sharing delivery options, or offering an order link).
        """

        history_formatted = "\n".join(
            f"[{m.get('sender_type', 'user')}]: {m.get('text', '')}" for m in history[-5:]
        )
        prompt = (
            f"Customer Name: {customer_name}\n"
            f"Platform: {platform}\n"
            f"Recent Conversation History:\n{history_formatted}\n\n"
            f"Customer Latest Inquiry: \"{latest_message}\"\n\n"
            "Generate an optimal reply suggestion, identify the customer intent, and provide a recommended next action."
        )

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=SupportReplySuggestionResponse,
                    temperature=0.6,
                ),
            )
            data = json.loads(response.text)
            return SupportReplySuggestionResponse(**data)
        except Exception as exc:
            logger.warning("Gemini support operator error: %s. Falling back to rule-based suggestion.", exc)
            return self._generate_fallback(
                customer_name=customer_name,
                platform=platform,
                latest_message=latest_message,
            )

    def _generate_fallback(
        self,
        *,
        customer_name: str,
        platform: str,
        latest_message: str,
    ) -> SupportReplySuggestionResponse:
        first_name = customer_name.split()[0] if customer_name else "there"
        lower = latest_message.lower()

        if any(w in lower for w in ("size", "fit", "small", "large", "narrow", "wide", "tight")):
            return SupportReplySuggestionResponse(
                suggested_reply=(
                    f"Hi {first_name}! 😊 Our footwear fits true to size. If you normally wear size 42, "
                    "42 will be a perfect fit. What size are you looking for so I can check remaining stock for you?"
                ),
                intent_detected="sizing_guidance",
                confidence_score=0.92,
                recommended_action="Confirm customer shoe size and verify current inventory",
            )

        if any(w in lower for w in ("ship", "delivery", "arrive", "location", "lagos", "abuja", "state")):
            return SupportReplySuggestionResponse(
                suggested_reply=(
                    f"Hi {first_name}! 🚀 We offer express nationwide delivery (typically 24–48 hours) "
                    "with tracking and free exchanges. Which city are you ordering from?"
                ),
                intent_detected="shipping_and_delivery",
                confidence_score=0.95,
                recommended_action="Provide delivery timeline and request destination address",
            )

        if any(w in lower for w in ("price", "cost", "how much", "naira", "$", "discount", "promo")):
            return SupportReplySuggestionResponse(
                suggested_reply=(
                    f"Hi {first_name}! Thanks for checking out our collection. "
                    "Our handcrafted pairs start at our early-access launch rate with an extra 10% off your first order! "
                    "Which style caught your eye so I can send the direct checkout link?"
                ),
                intent_detected="pricing_and_discounts",
                confidence_score=0.94,
                recommended_action="Send current price sheet and early-access discount link",
            )

        return SupportReplySuggestionResponse(
            suggested_reply=(
                f"Hi {first_name}! Thanks for reaching out to us on {platform.title()} ✨ "
                "How can I help you today? Let me know if you need any details on our styles or sizing!"
            ),
            intent_detected="general_inquiry",
            confidence_score=0.85,
            recommended_action="Acknowledge inquiry and ask how we can best assist",
        )
