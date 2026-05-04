"""
Prompt construction helpers.

All prompt logic is centralised here to make it easy to iterate on
without touching the state machine or service layer.
"""

from __future__ import annotations

from typing import List, Dict


def build_transition_classifier_prompt(
    current_state_name: str,
    current_state_description: str,
    transitions: list,  # List[Transition]
    conversation_history: List[Dict[str, str]],
    last_assistant_message: str,
) -> str:
    """
    Build the prompt sent to the LLM to decide which state to transition to.

    Returns a string that asks the model to output exactly one state name.
    """
    transition_lines = "\n".join(
        f"  {i+1}. Transition to '{t.next_state}' if: {t.condition}"
        for i, t in enumerate(transitions)
    )
    history_snippet = "\n".join(
        f"  [{m['role'].upper()}]: {m['content']}" for m in conversation_history[-6:]
    )

    return f"""You are a state-machine classifier for a conversational AI agent.

Current state: {current_state_name}
State description: {current_state_description}

Last assistant message:
"{last_assistant_message}"

Recent conversation (last 6 turns):
{history_snippet}

Available transitions:
{transition_lines}

Task: Based on the conversation above, decide whether the agent should transition to a new state.
Rules:
- Reply with ONLY the name of the next state (e.g. "ORDER_INQUIRY").
- If none of the transition conditions are met, reply with "{current_state_name}" to stay in the current state.
- Do NOT include any explanation, punctuation, or extra text — just the state name.

State name:"""


def build_chat_messages(
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    user_message: str,
) -> List[Dict[str, str]]:
    """
    Assemble the messages array sent to the OpenRouter chat completion endpoint.

    Args:
        system_prompt:        The active state's system prompt.
        conversation_history: List of prior {role, content} dicts (already trimmed).
        user_message:         The latest user message.

    Returns:
        A list of message dicts ready for the OpenRouter API.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    return messages


def trim_history(
    history: List[Dict[str, str]],
    max_turns: int = 20,
) -> List[Dict[str, str]]:
    """
    Keep only the most recent `max_turns` complete turn-pairs (user + assistant)
    to stay within the model's context window.

    A 'turn' is one user message plus one assistant reply.
    """
    # Each turn = 2 messages; keep the last max_turns * 2 messages.
    max_messages = max_turns * 2
    if len(history) <= max_messages:
        return history
    return history[-max_messages:]
