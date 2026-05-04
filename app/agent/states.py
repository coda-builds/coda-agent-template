"""
State definitions and YAML loader for the conversation state machine.

Each state is a plain Python dataclass built from the YAML config.
No business logic lives here — only data structures and deserialization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Transition:
    """
    A conditional edge in the state graph.

    Attributes:
        condition:  Human-readable description of when to take this edge.
                    The LLM classifier uses this text to decide.
        next_state: The name of the target state.
        priority:   Lower number = evaluated first when multiple conditions are met.
    """

    condition: str
    next_state: str
    priority: int = 0


@dataclass
class State:
    """
    A single node in the conversation state machine.

    Attributes:
        name:           Unique identifier (e.g. "GREETING").
        description:    One-sentence description of the state's purpose.
        system_prompt:  Full system prompt injected when the agent is in this state.
        transitions:    Ordered list of edges to other states.
        is_terminal:    If True, the conversation is considered complete.
        max_turns:      Optional per-state turn limit before auto-advancing.
        fallback_state: State to advance to if max_turns is exceeded.
    """

    name: str
    description: str
    system_prompt: str
    transitions: List[Transition] = field(default_factory=list)
    is_terminal: bool = False
    max_turns: Optional[int] = None
    fallback_state: Optional[str] = None


@dataclass
class AgentConfig:
    """Top-level config object deserialized from agent_config.yaml."""

    agent_name: str
    agent_description: str
    initial_state: str
    states: Dict[str, State]

    def get_state(self, name: str) -> State:
        if name not in self.states:
            raise ValueError(f"Unknown state '{name}'. Available: {list(self.states.keys())}")
        return self.states[name]

    def validate(self) -> None:
        """Validate referential integrity of the state graph."""
        errors: List[str] = []

        if self.initial_state not in self.states:
            errors.append(f"initial_state '{self.initial_state}' is not defined in states.")

        for state_name, state in self.states.items():
            for t in state.transitions:
                if t.next_state not in self.states:
                    errors.append(
                        f"State '{state_name}' has a transition to unknown state '{t.next_state}'."
                    )
            if state.fallback_state and state.fallback_state not in self.states:
                errors.append(
                    f"State '{state_name}' has unknown fallback_state '{state.fallback_state}'."
                )

        if errors:
            raise ValueError("Agent config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

        logger.info(
            "Agent config '%s' validated: %d states, initial='%s'",
            self.agent_name,
            len(self.states),
            self.initial_state,
        )


def load_agent_config(config_path: str | Path) -> AgentConfig:
    """
    Load and validate an AgentConfig from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        A validated AgentConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError:        If the config fails validation.
        yaml.YAMLError:    If the file is not valid YAML.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Agent config not found at: {path.resolve()}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError("agent_config.yaml must contain a YAML mapping at the top level.")

    states: Dict[str, State] = {}
    for state_data in raw.get("states", []):
        transitions = [
            Transition(
                condition=t["condition"],
                next_state=t["next_state"],
                priority=t.get("priority", 0),
            )
            for t in state_data.get("transitions", [])
        ]
        # Sort by priority ascending so lower numbers are evaluated first.
        transitions.sort(key=lambda t: t.priority)

        state = State(
            name=state_data["name"],
            description=state_data["description"],
            system_prompt=state_data["system_prompt"],
            transitions=transitions,
            is_terminal=state_data.get("is_terminal", False),
            max_turns=state_data.get("max_turns"),
            fallback_state=state_data.get("fallback_state"),
        )
        states[state.name] = state

    config = AgentConfig(
        agent_name=raw.get("agent_name", "Agent"),
        agent_description=raw.get("agent_description", ""),
        initial_state=raw["initial_state"],
        states=states,
    )
    config.validate()
    return config
