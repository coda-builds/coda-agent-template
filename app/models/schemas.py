"""
Pydantic schemas for all API request/response models.
These are the contracts between the HTTP layer and the agent core.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Inbound ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Body for POST /chat"""

    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="The user's message text.",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Existing conversation ID to continue. Omit to start a new conversation.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary key/value pairs stored alongside the conversation (e.g. user_id, locale).",
    )


class ConversationResetRequest(BaseModel):
    """Body for POST /conversations/{conversation_id}/reset"""

    reason: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Optional reason for the reset (stored in audit log).",
    )


# ── Outbound ──────────────────────────────────────────────────────────────────

class MessageRecord(BaseModel):
    """A single message in the conversation history."""

    role: str = Field(description="'user' or 'assistant'")
    content: str
    state: Optional[str] = Field(default=None, description="Agent state when this message was generated.")
    created_at: Optional[datetime] = None


class ChatResponse(BaseModel):
    """Response for POST /chat"""

    conversation_id: str
    reply: str = Field(description="The assistant's reply text.")
    current_state: str = Field(description="The agent state after processing this turn.")
    is_terminal: bool = Field(
        default=False,
        description="True when the conversation has reached a terminal state (e.g. CLOSED).",
    )
    turn_count: int = Field(description="Total number of turns in this conversation so far.")
    metadata: Optional[Dict[str, Any]] = None


class ConversationSummary(BaseModel):
    """Lightweight summary returned by GET /conversations/{conversation_id}"""

    conversation_id: str
    current_state: str
    turn_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    messages: List[MessageRecord] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str
    checks: Dict[str, str] = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
