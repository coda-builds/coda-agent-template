"""
Chat and conversation management endpoints.

POST /chat                                    — send a message, get a reply
GET  /conversations/{conversation_id}         — fetch full conversation history
POST /conversations/{conversation_id}/reset   — soft-reset to initial state
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationResetRequest,
    ConversationSummary,
    MessageRecord,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the agent",
    description=(
        "Send a user message. Omit `conversation_id` to start a new conversation. "
        "Include it to continue an existing one."
    ),
)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    state_machine = request.app.state.state_machine

    try:
        response = await state_machine.process_message(
            user_message=body.message,
            conversation_id=body.conversation_id,
            metadata=body.metadata,
        )
    except ValueError as exc:
        # e.g. conversation not found, invalid state name
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        # e.g. OpenRouter rate limit, Supabase error
        logger.error("process_message failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except Exception as exc:
        logger.error("Unexpected error in /chat: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        )

    return response


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationSummary,
    summary="Get conversation history",
    description="Retrieve full message history and metadata for a conversation.",
)
async def get_conversation(request: Request, conversation_id: str) -> ConversationSummary:
    db_svc = request.app.state.supabase_service

    conv = await db_svc.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found.",
        )

    raw_messages = await db_svc.get_messages(conversation_id)
    messages = [
        MessageRecord(
            role=m["role"],
            content=m["content"],
            state=m.get("state"),
            created_at=m.get("created_at"),
        )
        for m in raw_messages
    ]

    return ConversationSummary(
        conversation_id=conv["id"],
        current_state=conv["current_state"],
        turn_count=conv["turn_count"],
        created_at=conv.get("created_at"),
        updated_at=conv.get("updated_at"),
        metadata=conv.get("metadata"),
        messages=messages,
    )


@router.post(
    "/conversations/{conversation_id}/reset",
    response_model=ConversationSummary,
    summary="Reset a conversation to its initial state",
    description=(
        "Soft-reset: resets the current_state and turn_count but preserves message history. "
        "Useful for testing or when a user wants to start over."
    ),
)
async def reset_conversation(
    request: Request,
    conversation_id: str,
    body: ConversationResetRequest,
) -> ConversationSummary:
    db_svc = request.app.state.supabase_service
    agent_config = request.app.state.agent_config

    conv = await db_svc.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found.",
        )

    await db_svc.update_conversation(
        conversation_id=conversation_id,
        current_state=agent_config.initial_state,
        turn_count=0,
    )

    if body.reason:
        # Record the reset as a system message in the history
        await db_svc.save_message(
            conversation_id=conversation_id,
            role="system",
            content=f"[RESET] {body.reason}",
            state=agent_config.initial_state,
        )

    updated_conv = await db_svc.get_conversation(conversation_id)
    raw_messages = await db_svc.get_messages(conversation_id)
    messages = [
        MessageRecord(
            role=m["role"],
            content=m["content"],
            state=m.get("state"),
            created_at=m.get("created_at"),
        )
        for m in raw_messages
    ]

    return ConversationSummary(
        conversation_id=conversation_id,
        current_state=updated_conv["current_state"],
        turn_count=updated_conv["turn_count"],
        created_at=updated_conv.get("created_at"),
        updated_at=updated_conv.get("updated_at"),
        metadata=updated_conv.get("metadata"),
        messages=messages,
    )
