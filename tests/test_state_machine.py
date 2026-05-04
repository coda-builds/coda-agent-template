"""
Unit tests for the state machine, state loader, and prompt builder.

These tests run without a live OpenRouter key or Supabase connection by mocking
all external I/O.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agent.states import AgentConfig, State, load_agent_config
from app.agent.prompts import build_transition_classifier_prompt, trim_history


# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_CONFIG_YAML = textwrap.dedent("""
agent_name: TestAgent
agent_description: A test agent.
initial_state: START

states:
  - name: START
    description: Initial state.
    system_prompt: "You are a helpful assistant."
    transitions:
      - condition: "User says goodbye."
        next_state: END
        priority: 1

  - name: END
    description: Terminal state.
    system_prompt: "Conversation is over."
    is_terminal: true
    transitions: []
""")


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    p = tmp_path / "agent_config.yaml"
    p.write_text(MINIMAL_CONFIG_YAML)
    return p


# ── load_agent_config ─────────────────────────────────────────────────────────

class TestLoadAgentConfig:
    def test_loads_valid_config(self, tmp_config: Path) -> None:
        config = load_agent_config(tmp_config)
        assert config.agent_name == "TestAgent"
        assert config.initial_state == "START"
        assert "START" in config.states
        assert "END" in config.states

    def test_transitions_parsed_correctly(self, tmp_config: Path) -> None:
        config = load_agent_config(tmp_config)
        start = config.states["START"]
        assert len(start.transitions) == 1
        t = start.transitions[0]
        assert t.next_state == "END"
        assert t.priority == 1

    def test_terminal_state_flagged(self, tmp_config: Path) -> None:
        config = load_agent_config(tmp_config)
        assert config.states["END"].is_terminal is True
        assert config.states["START"].is_terminal is False

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_agent_config(tmp_path / "does_not_exist.yaml")

    def test_raises_on_invalid_initial_state(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("agent_name: X\nagent_description: Y\ninitial_state: MISSING\nstates: []")
        with pytest.raises(ValueError, match="initial_state"):
            load_agent_config(bad)

    def test_raises_on_broken_transition_reference(self, tmp_path: Path) -> None:
        bad_yaml = textwrap.dedent("""
        agent_name: X
        agent_description: Y
        initial_state: START
        states:
          - name: START
            description: d
            system_prompt: p
            transitions:
              - condition: c
                next_state: NONEXISTENT
        """)
        bad = tmp_path / "bad.yaml"
        bad.write_text(bad_yaml)
        with pytest.raises(ValueError, match="NONEXISTENT"):
            load_agent_config(bad)


# ── AgentConfig.get_state ─────────────────────────────────────────────────────

class TestAgentConfigGetState:
    def test_returns_known_state(self, tmp_config: Path) -> None:
        config = load_agent_config(tmp_config)
        state = config.get_state("START")
        assert isinstance(state, State)
        assert state.name == "START"

    def test_raises_on_unknown_state(self, tmp_config: Path) -> None:
        config = load_agent_config(tmp_config)
        with pytest.raises(ValueError, match="Unknown state"):
            config.get_state("DOES_NOT_EXIST")


# ── trim_history ──────────────────────────────────────────────────────────────

class TestTrimHistory:
    def _make_history(self, num_pairs: int) -> list:
        history = []
        for i in range(num_pairs):
            history.append({"role": "user", "content": f"User message {i}"})
            history.append({"role": "assistant", "content": f"Assistant reply {i}"})
        return history

    def test_no_trim_when_under_limit(self) -> None:
        history = self._make_history(5)
        result = trim_history(history, max_turns=10)
        assert result == history

    def test_trims_to_max_turns(self) -> None:
        history = self._make_history(15)
        result = trim_history(history, max_turns=10)
        assert len(result) == 20  # 10 turns * 2 messages

    def test_keeps_most_recent_messages(self) -> None:
        history = self._make_history(10)
        result = trim_history(history, max_turns=3)
        # Last 3 pairs = last 6 messages
        assert result == history[-6:]

    def test_empty_history(self) -> None:
        assert trim_history([], max_turns=10) == []


# ── build_transition_classifier_prompt ───────────────────────────────────────

class TestBuildClassifierPrompt:
    def test_prompt_contains_state_name(self) -> None:
        transitions = [
            MagicMock(next_state="END", condition="User says bye"),
        ]
        prompt = build_transition_classifier_prompt(
            current_state_name="START",
            current_state_description="Initial state",
            transitions=transitions,
            conversation_history=[{"role": "user", "content": "hello"}],
            last_assistant_message="Hi there!",
        )
        assert "START" in prompt
        assert "END" in prompt
        assert "User says bye" in prompt

    def test_prompt_includes_last_assistant_message(self) -> None:
        transitions = [MagicMock(next_state="END", condition="bye")]
        prompt = build_transition_classifier_prompt(
            current_state_name="A",
            current_state_description="d",
            transitions=transitions,
            conversation_history=[],
            last_assistant_message="This is the last reply.",
        )
        assert "This is the last reply." in prompt
