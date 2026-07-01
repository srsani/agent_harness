from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class RunResult:
    harness: str
    architecture: str
    task: str
    prompt: str
    output: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    elapsed_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class AgentRunner(ABC):
    """Build and run an agent for a given architecture variant."""

    harness_name: str
    architecture_name: str

    @abstractmethod
    def run(self, prompt: str, *, session_id: str | None = None) -> RunResult:
        """Execute the agent with the given user prompt."""
