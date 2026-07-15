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
    architecture_selector: Callable[[str], list[str]] | None = None
    """Optional hook returning which architecture names apply to a given task name.

    Defaults to every registered architecture when unset. Harnesses use this to
    keep `run-all` from pairing architectures with tasks they structurally cannot
    answer (e.g. a tool-less CodeMode variant against a database task).
    """

    def architectures_for_task(self, task_name: str) -> list[str]:
        if self.architecture_selector is not None:
            return self.architecture_selector(task_name)
        return list(self.architectures)


def _load_pydantic_ai() -> HarnessSpec:
    from agent_harness.harnesses.pydantic_ai.runners import (
        ARCHITECTURE_BUILDERS,
        architectures_for_task,
        make_runner,
    )

    return HarnessSpec(
        name="pydantic-ai",
        description="Pydantic AI + pydantic-ai-harness capability library",
        architectures={name: desc for name, (desc, _) in ARCHITECTURE_BUILDERS.items()},
        factory=make_runner,
        optional_deps="pydantic-ai",
        architecture_selector=architectures_for_task,
    )


def _load_smolagents() -> HarnessSpec:
    from agent_harness.harnesses.smolagents.runners import (
        ARCHITECTURE_BUILDERS,
        architectures_for_task,
        make_runner,
    )

    return HarnessSpec(
        name="smolagents",
        description="Hugging Face smolagents CodeAgent (https://github.com/huggingface/smolagents)",
        architectures={name: desc for name, (desc, _) in ARCHITECTURE_BUILDERS.items()},
        factory=make_runner,
        optional_deps="smolagents",
        architecture_selector=architectures_for_task,
    )


def _harness_loaders() -> dict[str, Callable[[], HarnessSpec]]:
    return {"pydantic-ai": _load_pydantic_ai, "smolagents": _load_smolagents}


def get_harness(name: str) -> HarnessSpec:
    loaders = _harness_loaders()
    if name not in loaders:
        available = ", ".join(sorted(loaders))
        raise KeyError(f"Unknown harness '{name}'. Available: {available}")
    return loaders[name]()


def list_harnesses() -> dict[str, HarnessSpec]:
    """Eagerly load every registered harness, skipping ones whose optional dependency group
    (see each loader's `import` and `optional_deps`) isn't installed -- so `agent-bench list`
    still works if e.g. only `--extra pydantic-ai` (not `--extra smolagents`) was synced.
    """
    specs: dict[str, HarnessSpec] = {}
    for name, loader in _harness_loaders().items():
        try:
            specs[name] = loader()
        except ImportError:
            continue
    return specs


def get_task(name: str) -> str:
    if name not in TASKS:
        available = ", ".join(sorted(TASKS))
        raise KeyError(f"Unknown task '{name}'. Available: {available}")
    return TASKS[name]


def list_tasks() -> dict[str, str]:
    return dict(TASKS)
