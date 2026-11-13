from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.core.config import settings
from backend.models.user import UserModel
from backend.models.conversation import ConversationModel
from backend.models.customer import CustomerModel
from backend.models.message import MessageModel
from backend.schemas.inbox import (
    ConversationDetailResponse,
    ConversationListItemResponse,
    CustomerSummaryResponse,
    MessageItemResponse,
    SendMessageRequest,
    SupportReplySuggestionResponse,
    UpdateConversationStatusRequest,
)
from backend.agents.support_operator import SupportOperatorAgent
from backend.services.reply_dispatcher import ReplyDispatcherFactory
from backend.unit_of_work.base import IUnitOfWork
from backend.api.deps import get_current_user, get_uow

router = APIRouter(prefix="/inbox", tags=["Social Inbox & Support"])

support_agent = SupportOperatorAgent()


def _serialize_customer(customer: CustomerModel) -> CustomerSummaryResponse:
    return CustomerSummaryResponse(
        id=str(customer.id),
        platform=customer.platform,
        platform_customer_id=customer.platform_customer_id,
        customer_name=customer.customer_name,
        customer_handle=customer.customer_handle,
        avatar_url=customer.avatar_url,
        metadata_info=customer.metadata_info,
    )


def _serialize_message(msg: MessageModel) -> MessageItemResponse:
    return MessageItemResponse(
        id=str(msg.id),
        conversation_id=str(msg.conversation_id),
        sender_type=msg.sender_type,
        sender_name=msg.sender_name,
        text=msg.text,
        media_url=msg.media_url,
        is_read=msg.is_read,
        ai_suggested_reply=msg.ai_suggested_reply,
        sent_at=msg.sent_at,
    )


def _serialize_conversation_item(conv: ConversationModel) -> ConversationListItemResponse:
    return ConversationListItemResponse(
        id=str(conv.id),
        platform=conv.platform,
        channel_type=conv.channel_type,
        status=conv.status,
        unread_count=conv.unread_count,
        last_message_at=conv.last_message_at,
        last_message_preview=conv.last_message_preview,
        customer=_serialize_customer(conv.customer),
    )


@router.get("/conversations", response_model=List[ConversationListItemResponse])
async def list_conversations(
    platform: Optional[str] = Query(None, description="Filter by platform: instagram, x, linkedin"),
    status: Optional[str] = Query(None, description="Filter by status: open, pending, resolved, archived"),
    search: Optional[str] = Query(None, description="Search by customer name, handle, or text"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    List unified customer conversation threads across Instagram, X, and LinkedIn.
    """
    conversations = await uow.conversations.list_by_user(
        user_id=current_user.id,
        platform=platform,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [_serialize_conversation_item(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_thread(
    conversation_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Get full conversation history and customer profile. Automatically marks thread as read.
    """
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid conversation identifier")

    thread = await uow.conversations.get_by_id_and_user(conv_uuid, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await uow.conversations.mark_as_read(conv_uuid, current_user.id)
    await uow.commit()

    return ConversationDetailResponse(
        id=str(thread.id),
        platform=thread.platform,
        channel_type=thread.channel_type,
        status=thread.status,
        unread_count=0,
        last_message_at=thread.last_message_at,
        customer=_serialize_customer(thread.customer),
        messages=[_serialize_message(m) for m in thread.messages],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_inbox_reply(
    conversation_id: str,
    payload: SendMessageRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Send an in-app reply directly back to the customer on Instagram/X/LinkedIn.
    Uses connected social tokens to dispatch without leaving Sentinel.
    """
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid conversation identifier")

    thread = await uow.conversations.get_by_id_and_user(conv_uuid, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation not found")

    social_account = await uow.social_accounts.get_by_user_and_platform(
        user_id=current_user.id,
        platform=thread.platform,
    )

    dispatcher = ReplyDispatcherFactory.get_dispatcher(thread.platform)
    dispatch_res = await dispatcher.dispatch_reply(
        account=social_account,
        conversation=thread,
        text=payload.text,
    )

    message = await uow.messages.add_message(
        conversation=thread,
        sender_type="user",
        sender_name=current_user.name,
        text=payload.text,
        media_url=payload.media_url,
        platform_message_id=dispatch_res.get("remote_id"),
        is_read=True,
    )
    await uow.commit()

    return _serialize_message(message)


@router.post(
    "/conversations/{conversation_id}/suggest-reply",
    response_model=SupportReplySuggestionResponse,
)
async def generate_ai_reply_suggestion(
    conversation_id: str,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Sentinel AI Support Co-Pilot:
    Analyzes conversation context and pre-drafts a polite, conversion-optimized reply.
    """
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid conversation identifier")

    thread = await uow.conversations.get_by_id_and_user(conv_uuid, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation not found")

    latest_customer_msg = None
    for msg in reversed(thread.messages):
        if msg.sender_type == "customer":
            latest_customer_msg = msg.text
            break

    if not latest_customer_msg:
        latest_customer_msg = thread.last_message_preview or "Hello!"

    history = [
        {"sender_type": m.sender_type, "text": m.text}
        for m in thread.messages[-6:]
    ]

    suggestion = await support_agent.generate_reply_suggestion(
        customer_name=thread.customer.customer_name,
        platform=thread.platform,
        latest_message=latest_customer_msg,
        history=history,
    )
    return suggestion


@router.patch("/conversations/{conversation_id}/status", response_model=ConversationListItemResponse)
async def update_conversation_status(
    conversation_id: str,
    payload: UpdateConversationStatusRequest,
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Update thread status: open, pending, resolved, archived.
    """
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid conversation identifier")

    thread = await uow.conversations.update_status(
        conversation_id=conv_uuid,
        user_id=current_user.id,
        status=payload.status,
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await uow.commit()
    return _serialize_conversation_item(thread)


@router.post("/sandbox/seed", response_model=List[ConversationListItemResponse], status_code=status.HTTP_201_CREATED)
async def seed_sandbox_inbox(
    current_user: UserModel = Depends(get_current_user),
    uow: IUnitOfWork = Depends(get_uow),
):
    """
    Development endpoint:
    Seeds 3 realistic customer inquiries (Instagram DM, X DM, LinkedIn Comment)
    with pre-computed AI co-pilot reply suggestions so the frontend can be built and demonstrated immediately.
    """
    if settings.ENVIRONMENT != "development":
        raise HTTPException(
            status_code=403,
            detail="Sandbox seed endpoint is only permitted in development environment.",
        )

    now = datetime.now(timezone.utc)

    # 1. Instagram customer (Shoe Sizing & Shipping)
    c1 = await uow.customers.upsert_customer(
        user_id=current_user.id,
        platform="instagram",
        platform_customer_id="ig_buyer_101",
        customer_name="Sarah Jenkins",
        customer_handle="@sarah_j_style",
        avatar_url="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150",
        metadata_info={"preferred_size": "EU 42", "interested_in": "Handcrafted Leather Chelsea Boots"},
    )
    t1 = await uow.conversations.get_or_create_thread(
        user_id=current_user.id,
        customer_id=c1.id,
        platform="instagram",
        channel_type="dm",
    )
    await uow.messages.add_message(
        conversation=t1,
        sender_type="customer",
        sender_name="Sarah Jenkins",
        text="Hi! Do you have the Chelsea boots in size 42 and can you ship to Lekki, Lagos?",
        ai_suggested_reply="Hi Sarah! 😊 Yes, we have size 42 in stock and offer 24-hour express delivery to Lekki. Would you like me to reserve a pair for you?",
        sent_at=now,
    )

    # 2. X (Twitter) customer (Pricing & Early Adopter Discount)
    c2 = await uow.customers.upsert_customer(
        user_id=current_user.id,
        platform="x",
        platform_customer_id="x_buyer_202",
        customer_name="Daniel Okon",
        customer_handle="@dan_tech_kicks",
        avatar_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150",
        metadata_info={"interest": "Running Shoes Launch"},
    )
    t2 = await uow.conversations.get_or_create_thread(
        user_id=current_user.id,
        customer_id=c2.id,
        platform="x",
        channel_type="dm",
    )
    await uow.messages.add_message(
        conversation=t2,
        sender_type="customer",
        sender_name="Daniel Okon",
        text="How much for the handcrafted running shoes with the early bird launch discount?",
        ai_suggested_reply="Hey Daniel! Our handcrafted running shoes start at launch pricing with 20% off for early adopters. Want me to send your checkout link?",
        sent_at=now,
    )

    # 3. LinkedIn customer (Corporate / Bulk Order Inquiry)
    c3 = await uow.customers.upsert_customer(
        user_id=current_user.id,
        platform="linkedin",
        platform_customer_id="li_buyer_303",
        customer_name="Marcus Vance",
        customer_handle="marcus-vance-ops",
        avatar_url="https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150",
        metadata_info={"role": "Head of People & Operations", "company": "Vance Logistics"},
    )
    t3 = await uow.conversations.get_or_create_thread(
        user_id=current_user.id,
        customer_id=c3.id,
        platform="linkedin",
        channel_type="comment",
    )
    await uow.messages.add_message(
        conversation=t3,
        sender_type="customer",
        sender_name="Marcus Vance",
        text="Great to see sustainable craftsmanship in athletic footwear. What's the turnaround time for corporate bulk orders of 50+ pairs?",
        ai_suggested_reply="Hi Marcus, thank you! For corporate orders of 50+ pairs, our typical production and delivery window is 10–14 business days with custom branding. Let's connect directly to share our corporate catalog.",
        sent_at=now,
    )

    await uow.commit()

    seeded = await uow.conversations.list_by_user(user_id=current_user.id, limit=10)
    return [_serialize_conversation_item(c) for c in seeded]
