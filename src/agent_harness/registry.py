from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_harness.runners.base import AgentRunner
from agent_harness.tasks.builtins import TASKS


@dataclass(frozen=True)
class HarnessSpec:
    name: str
    description: str
    architectures: dict[str, str]  # name -> description
    factory: Callable[[str], AgentRunner]
    optional_deps: str


def _load_pydantic_ai() -> HarnessSpec:
    from agent_harness.harnesses.pydantic_ai.runners import (
        ARCHITECTURE_BUILDERS,
        make_runner,
    )

    return HarnessSpec(
        name="pydantic-ai",
        description="Pydantic AI + pydantic-ai-harness capability library",
        architectures={name: desc for name, (desc, _) in ARCHITECTURE_BUILDERS.items()},
        factory=make_runner,
        optional_deps="pydantic-ai",
    )


def _harness_loaders() -> dict[str, Callable[[], HarnessSpec]]:
    return {"pydantic-ai": _load_pydantic_ai}


def get_harness(name: str) -> HarnessSpec:
    loaders = _harness_loaders()
    if name not in loaders:
        available = ", ".join(sorted(loaders))
        raise KeyError(f"Unknown harness '{name}'. Available: {available}")
    return loaders[name]()


def list_harnesses() -> dict[str, HarnessSpec]:
    return {name: loader() for name, loader in _harness_loaders().items()}


def get_task(name: str) -> str:
    if name not in TASKS:
        available = ", ".join(sorted(TASKS))
        raise KeyError(f"Unknown task '{name}'. Available: {available}")
    return TASKS[name]


def list_tasks() -> dict[str, str]:
    return dict(TASKS)
