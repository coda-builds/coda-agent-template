"""
Core conversation state machine.

Orchestrates:
  1. Loading the current conversation state from persistence.
  2. Guard: reject messages on terminal conversations.
  3. Guard: enforce the global turn limit.
  4. Loading message history and trimming for context window.
  5. Generating an assistant reply via the LLM (OpenRouter).
  6. Persisting the new turn to Supabase.
  7. Running a lightweight LLM-based transition classifier.
  8. Handling per-state turn-limit fallback if needed.
  9. Persisting the updated state and returning structured output.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional, Tuple

from app.agent.prompts import (
    build_chat_messages,
    build_transition_classifier_prompt,
    trim_history,
)
from app.agent.states import AgentConfig, State
from app.models.schemas import ChatResponse
from app.services.openrouter_service import OpenRouterService
from app.services.supabase_service import SupabaseService

logger = logging.getLogger(__name__)


class StateMachine:
    """
    Manages a single agent's conversation lifecycle.

    One instance per application (shared across requests).
    All mutable state lives in Supabase, not in memory.
    """

    def __init__(
        self,
        config: AgentConfig,
        openrouter_service: OpenRouterService,
        supabase_service: SupabaseService,
        max_conversation_turns: int = 50,
    ) -> None:
        self.config = config
        self.llm = openrouter_service
        self.db = supabase_service
        self.max_conversation_turns = max_conversation_turns

    # ── Public interface ──────────────────────────────────────────────────────

    async def process_message(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> ChatResponse:
        """
        Process one user message and return the agent's reply.

        Args:
            user_message:     Raw text from the user.
            conversation_id:  Existing session ID, or None to create a new one.
            metadata:         Arbitrary key/value data stored with the conversation.

        Returns:
            A ChatResponse with the reply, new state, and turn count.
        """
        # 1. Load or create conversation
        conversation, is_new = await self._get_or_create_conversation(
            conversation_id=conversation_id,
            metadata=metadata,
        )
        conv_id: str = conversation["id"]
        current_state_name: str = conversation["current_state"]
        turn_count: int = conversation["turn_count"]

        # 2. Guard: reject messages on terminal conversations
        current_state: State = self.config.get_state(current_state_name)
        if current_state.is_terminal:
            return ChatResponse(
                conversation_id=conv_id,
                reply=(
                    "This conversation has ended. "
                    "Please start a new conversation if you need further help."
                ),
                current_state=current_state_name,
                is_terminal=True,
                turn_count=turn_count,
            )

        # 3. Guard: enforce global turn limit
        if turn_count >= self.max_conversation_turns:
            logger.warning(
                "Conv %s: max_conversation_turns=%d reached, rejecting message.",
                conv_id,
                self.max_conversation_turns,
            )
            return ChatResponse(
                conversation_id=conv_id,
                reply=(
                    "This conversation has reached its maximum length. "
                    "Please start a new conversation to continue."
                ),
                current_state=current_state_name,
                is_terminal=False,
                turn_count=turn_count,
            )

        # 4. Load message history and trim for context window
        history: List[Dict] = await self.db.get_messages(conv_id)
        trimmed_history = trim_history(
            [{"role": m["role"], "content": m["content"]} for m in history],
            max_turns=20,
        )

        # 5. Generate assistant reply
        messages = build_chat_messages(
            system_prompt=current_state.system_prompt,
            conversation_history=trimmed_history,
            user_message=user_message,
        )
        reply = await self.llm.chat_completion(messages=messages)

        # 6. Persist the new turn (user + assistant)
        new_turn_count = turn_count + 1
        await self.db.save_message(
            conversation_id=conv_id,
            role="user",
            content=user_message,
            state=current_state_name,
        )
        await self.db.save_message(
            conversation_id=conv_id,
            role="assistant",
            content=reply,
            state=current_state_name,
        )

        # 7. Determine next state
        next_state_name = await self._classify_transition(
            current_state=current_state,
            history=trimmed_history,
            last_assistant_message=reply,
        )

        # 8. Handle per-state turn limit fallback
        if (
            current_state.max_turns
            and current_state.fallback_state
            and new_turn_count >= current_state.max_turns
            and next_state_name == current_state_name
        ):
            logger.info(
                "Conv %s: max_turns=%d reached in state '%s', falling back to '%s'",
                conv_id,
                current_state.max_turns,
                current_state_name,
                current_state.fallback_state,
            )
            next_state_name = current_state.fallback_state

        next_state: State = self.config.get_state(next_state_name)

        # 9. Persist updated conversation state
        await self.db.update_conversation(
            conversation_id=conv_id,
            current_state=next_state_name,
            turn_count=new_turn_count,
        )

        if next_state_name != current_state_name:
            logger.info(
                "Conv %s: state transition %s → %s (turn %d)",
                conv_id,
                current_state_name,
                next_state_name,
                new_turn_count,
            )

        return ChatResponse(
            conversation_id=conv_id,
            reply=reply,
            current_state=next_state_name,
            is_terminal=next_state.is_terminal,
            turn_count=new_turn_count,
            metadata=conversation.get("metadata"),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_or_create_conversation(
        self,
        conversation_id: Optional[str],
        metadata: Optional[Dict],
    ) -> Tuple[Dict, bool]:
        """
        Return (conversation_row, is_new).
        If conversation_id is provided, fetch it; otherwise create a fresh one.
        """
        if conversation_id:
            conv = await self.db.get_conversation(conversation_id)
            if conv is None:
                raise ValueError(f"Conversation '{conversation_id}' not found.")
            return conv, False

        new_id = str(uuid.uuid4())
        conv = await self.db.create_conversation(
            conversation_id=new_id,
            initial_state=self.config.initial_state,
            metadata=metadata or {},
        )
        return conv, True

    async def _classify_transition(
        self,
        current_state: State,
        history: List[Dict],
        last_assistant_message: str,
    ) -> str:
        """
        Ask the LLM to decide whether to transition to a new state.

        Falls back to the current state if:
        - There are no transitions defined.
        - The LLM returns an invalid state name.
        - The LLM call fails.
        """
        if not current_state.transitions:
            return current_state.name

        classifier_prompt = build_transition_classifier_prompt(
            current_state_name=current_state.name,
            current_state_description=current_state.description,
            transitions=current_state.transitions,
            conversation_history=history,
            last_assistant_message=last_assistant_message,
        )

        try:
            raw = await self.llm.text_completion(prompt=classifier_prompt, max_tokens=32)
            candidate = raw.strip().upper().replace('"', "").replace("'", "")

            if candidate in self.config.states:
                return candidate

            # Try to find a close match (model may add whitespace or punctuation)
            for state_name in self.config.states:
                if state_name in candidate:
                    logger.debug(
                        "Transition classifier fuzzy-matched '%s' → '%s'",
                        candidate,
                        state_name,
                    )
                    return state_name

            logger.warning(
                "Transition classifier returned unknown state '%s'; staying in '%s'",
                candidate,
                current_state.name,
            )
            return current_state.name

        except Exception as exc:
            logger.error("Transition classifier failed: %s", exc, exc_info=True)
            return current_state.name
