"""
Supabase persistence service.

Manages two tables:
  - conversations : one row per session, tracking state + metadata
  - messages      : append-only log of all turns

Schema is defined in scripts/setup_supabase.sql.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import AsyncClient, acreate_client
from postgrest.exceptions import APIError

from app.config import Settings

logger = logging.getLogger(__name__)


class SupabaseService:
    """
    Async Supabase client wrapper.

    The client is created via `SupabaseService.create(settings)` to allow
    async initialisation before the app starts serving traffic.
    """

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @classmethod
    async def create(cls, settings: Settings) -> "SupabaseService":
        """Factory method — use this instead of __init__ directly."""
        client = await acreate_client(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_role_key,
        )
        return cls(client)

    # ── Conversations ─────────────────────────────────────────────────────────

    async def create_conversation(
        self,
        conversation_id: str,
        initial_state: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Insert a new conversation row and return it."""
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": conversation_id,
            "current_state": initial_state,
            "turn_count": 0,
            "metadata": json.dumps(metadata),
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = (
                await self._client.table("conversations")
                .insert(row)
                .execute()
            )
            data = result.data
            if not data:
                raise RuntimeError(f"Failed to create conversation '{conversation_id}'.")
            return self._parse_conversation(data[0])
        except APIError as exc:
            logger.error("Supabase create_conversation error: %s", exc)
            raise RuntimeError("Database error while creating conversation.") from exc

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a conversation by ID. Returns None if not found."""
        try:
            result = (
                await self._client.table("conversations")
                .select("*")
                .eq("id", conversation_id)
                .maybe_single()
                .execute()
            )
            if result is None:
                return None
            return self._parse_conversation(result.data)
        except APIError as exc:
            logger.error("Supabase get_conversation error: %s", exc)
            raise RuntimeError("Database error while fetching conversation.") from exc

    async def update_conversation(
        self,
        conversation_id: str,
        current_state: str,
        turn_count: int,
    ) -> None:
        """Update the state and turn count for an existing conversation."""
        try:
            await (
                self._client.table("conversations")
                .update(
                    {
                        "current_state": current_state,
                        "turn_count": turn_count,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .eq("id", conversation_id)
                .execute()
            )
        except APIError as exc:
            logger.error("Supabase update_conversation error: %s", exc)
            raise RuntimeError("Database error while updating conversation.") from exc

    # ── Messages ──────────────────────────────────────────────────────────────

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        state: str,
    ) -> None:
        """Append a message to the messages table."""
        try:
            await (
                self._client.table("messages")
                .insert(
                    {
                        "conversation_id": conversation_id,
                        "role": role,
                        "content": content,
                        "state": state,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .execute()
            )
        except APIError as exc:
            logger.error("Supabase save_message error: %s", exc)
            raise RuntimeError("Database error while saving message.") from exc

    async def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Return all messages for a conversation ordered oldest-first.
        """
        try:
            result = (
                await self._client.table("messages")
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .execute()
            )
            return result.data or []
        except APIError as exc:
            logger.error("Supabase get_messages error: %s", exc)
            raise RuntimeError("Database error while fetching messages.") from exc

    # ── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return True if Supabase is reachable."""
        try:
            await self._client.table("conversations").select("id").limit(1).execute()
            return True
        except Exception:
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_conversation(row: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON metadata string back to a dict if needed."""
        if isinstance(row.get("metadata"), str):
            try:
                row["metadata"] = json.loads(row["metadata"])
            except (json.JSONDecodeError, TypeError):
                row["metadata"] = {}
        return row
