from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CustomerSummaryResponse(BaseModel):
    id: str
    platform: str
    platform_customer_id: str
    customer_name: str
    customer_handle: Optional[str] = None
    avatar_url: Optional[str] = None
    metadata_info: Optional[Dict[str, Any]] = None


class MessageItemResponse(BaseModel):
    id: str
    conversation_id: str
    sender_type: str
    sender_name: str
    text: str
    media_url: Optional[str] = None
    is_read: bool
    ai_suggested_reply: Optional[str] = None
    sent_at: datetime


class ConversationListItemResponse(BaseModel):
    id: str
    platform: str
    channel_type: str
    status: str
    unread_count: int
    last_message_at: datetime
    last_message_preview: str
    customer: CustomerSummaryResponse


class ConversationDetailResponse(BaseModel):
    id: str
    platform: str
    channel_type: str
    status: str
    unread_count: int
    last_message_at: datetime
    customer: CustomerSummaryResponse
    messages: List[MessageItemResponse]


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Message reply text")
    media_url: Optional[str] = Field(None, description="Optional image/media attachment URL")


class UpdateConversationStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(open|pending|resolved|archived)$")


class SupportReplySuggestionResponse(BaseModel):
    suggested_reply: str = Field(description="Polite, high-converting customer service reply")
    intent_detected: str = Field(description="Classified customer intent (e.g. sizing, pricing, shipping)")
    confidence_score: float = Field(ge=0.0, le=1.0)
    recommended_action: str = Field(description="Recommended next step for the store owner")
