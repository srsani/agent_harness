from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import random
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from agent_harness.config import settings


@lru_cache(maxsize=1)
def _build_langfuse_client():
    """Return a process-wide singleton Langfuse client.

    Each `Langfuse(...)` instance wires up its own OpenTelemetry span processor and
    registers its own `atexit` shutdown hook against shared OTel SDK state. Building a
    fresh client per run (as this used to do) means a `run-all` sweep across N
    architectures registers N independent shutdown hooks that all race to tear down
    that shared state at interpreter exit -- a plausible cause of the segfault-on-exit
    ("Garbage-collecting", no Python frame) seen after benchmark runs. Memoizing to a
    single client, shut down exactly once via `_shutdown_langfuse_client` below, avoids
    the race entirely and also matches the SDK's own documented usage pattern (build
    once, reuse for the app's lifetime, shut down once at exit).
    """
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    try:
        from langfuse import Langfuse  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None

    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_host,
    )
    atexit.register(_shutdown_langfuse_client, client)
    return client


def _shutdown_langfuse_client(client: Any) -> None:
    try:
        client.shutdown()
    except Exception:  # noqa: BLE001 -- best-effort cleanup at interpreter exit
        pass


def shutdown_tracing() -> None:
    """Explicitly flush and shut down the shared Langfuse client, if one was built.

    Safe to call even if no client was ever created (e.g. Langfuse isn't configured) --
    it's a no-op in that case. Intended to be called right before a hard process exit
    (`os._exit`) that skips Python's normal `atexit`/GC-based cleanup; see `cli.main()`.
    """
    if _build_langfuse_client.cache_info().currsize == 0:
        return
    client = _build_langfuse_client()
    if client is not None:
        _shutdown_langfuse_client(client)


def _to_preview(value: Any, *, max_chars: int = 4000) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= max_chars else f"{text[:max_chars]}...[truncated]"


def _extract_run_artifacts(result: Any) -> dict[str, Any]:
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
    )

    tool_calls: list[dict[str, Any]] = []
    tool_returns: list[dict[str, Any]] = []
    reasoning: list[str] = []
    timeline: list[dict[str, Any]] = []

    for msg in result.all_messages():
        if isinstance(msg, ModelResponse):
            timeline.append(
                {
                    "kind": "model-response",
                    "timestamp": str(msg.timestamp),
                    "model_name": msg.model_name,
                    "parts": [
                        getattr(part, "part_kind", type(part).__name__) for part in msg.parts
                    ],
                }
            )
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    tool_calls.append(
                        {
                            "tool_name": part.tool_name,
                            "tool_call_id": part.tool_call_id,
                            "args_json": part.args_as_json_str(),
                            "tool_kind": getattr(part, "tool_kind", None),
                            "provider_name": getattr(part, "provider_name", None),
                        }
                    )
                elif isinstance(part, ThinkingPart):
                    reasoning.append(part.content)
        elif isinstance(msg, ModelRequest):
            timeline.append(
                {
                    "kind": "model-request",
                    "timestamp": str(msg.timestamp),
                    "parts": [
                        getattr(part, "part_kind", type(part).__name__) for part in msg.parts
                    ],
                }
            )
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    tool_returns.append(
                        {
                            "tool_name": part.tool_name,
                            "tool_call_id": part.tool_call_id,
                            "outcome": part.outcome,
                            "content": _to_preview(part.content),
                            "timestamp": str(part.timestamp),
                        }
                    )

    returns_by_call_id = {ret["tool_call_id"]: ret for ret in tool_returns}
    tool_steps = [
        {"call": call, "return": returns_by_call_id.get(call["tool_call_id"])}
        for call in tool_calls
    ]

    return {
        "tool_calls": tool_calls,
        "tool_returns": tool_returns,
        "tool_steps": tool_steps,
        "reasoning": [_to_preview(text) for text in reasoning],
        "timeline": timeline,
    }


@dataclass
class TracedAgent:
    """Thin wrapper that traces each run_sync call in Langfuse."""

    agent: Any
    trace_name: str = "agent-harness.agent.run"
    trace_metadata: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    model_name: str | None = None
    require_langfuse: bool = False
    last_trace_id: str | None = None
    last_observation_id: str | None = None
    last_trace_url: str | None = None
    _langfuse_client: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._langfuse_client = _build_langfuse_client()
        if self.require_langfuse and self._langfuse_client is None:
            if not settings.langfuse_public_key or not settings.langfuse_secret_key:
                raise RuntimeError(
                    "Langfuse is required. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env."
                )
            raise RuntimeError(
                "Langfuse is required. Install dependencies with "
                "`uv sync --extra pydantic-ai --extra dev`."
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.agent, name)

    def flush(self) -> None:
        if self._langfuse_client is not None:
            self._langfuse_client.flush()

    def run_sync(self, *args: Any, **kwargs: Any) -> Any:
        self.last_trace_id = None
        self.last_observation_id = None
        self.last_trace_url = None

        prompt = args[0] if args else kwargs.get("user_prompt", "")
        input_text = str(prompt)
        sampled_out = random.random() > settings.langfuse_trace_sample_rate

        def _run_plain() -> Any:
            return self.agent.run_sync(*args, **kwargs)

        def _run_traced() -> Any:
            started = time.perf_counter()
            trace_metadata = dict(self.trace_metadata)
            if self.session_id is not None:
                trace_metadata["langfuse_session_id"] = self.session_id

            with self._langfuse_client.start_as_current_observation(
                as_type="generation",
                name=self.trace_name,
                model=self.model_name or settings.agent_bench_model,
                input=input_text,
                metadata=trace_metadata,
            ) as generation:
                self._set_trace_session_id(generation)
                self.last_trace_id = generation.trace_id
                self.last_observation_id = generation.id
                try:
                    self.last_trace_url = self._langfuse_client.get_trace_url(
                        trace_id=generation.trace_id
                    )
                except TypeError:
                    # Backward compatibility for SDK variants with positional signature.
                    self.last_trace_url = self._langfuse_client.get_trace_url(generation.trace_id)
                result = self.agent.run_sync(*args, **kwargs)
                metadata = {
                    **trace_metadata,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "detailed_tracing_enabled": settings.langfuse_detailed_tracing,
                }

                if settings.langfuse_detailed_tracing:
                    artifacts = _extract_run_artifacts(result)

                    # Add one child span per tool call to visualize execution flow in Langfuse.
                    for idx, step in enumerate(artifacts["tool_steps"], start=1):
                        call = step["call"]
                        ret = step["return"]
                        with generation.start_as_current_observation(
                            as_type="span",
                            name=f"tool.{idx}.{call['tool_name']}",
                            input=call["args_json"],
                            metadata={
                                "tool_call_id": call["tool_call_id"],
                                "tool_kind": call["tool_kind"],
                                "provider_name": call["provider_name"],
                            },
                        ) as tool_span:
                            if ret is not None:
                                tool_span.update(
                                    output=ret["content"],
                                    metadata={
                                        "outcome": ret["outcome"],
                                        "timestamp": ret["timestamp"],
                                    },
                                )
                            else:
                                tool_span.update(metadata={"outcome": "missing-return"})

                    metadata.update(
                        {
                            "tool_calls": artifacts["tool_calls"],
                            "tool_returns": artifacts["tool_returns"],
                            "timeline": artifacts["timeline"],
                            "reasoning": artifacts["reasoning"],
                        }
                    )

                generation.update(
                    output=str(result.output),
                    metadata=metadata,
                )
                return result

        runner = _run_plain if (self._langfuse_client is None or sampled_out) else _run_traced
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(runner).result()
        except RuntimeError:
            return runner()
        finally:
            if self._langfuse_client is not None and settings.langfuse_flush_each_run:
                self._langfuse_client.flush()

    def _set_trace_session_id(self, observation: Any) -> None:
        if self.session_id is None:
            return

        try:
            from langfuse._client.attributes import LangfuseOtelSpanAttributes

            observation._otel_span.set_attribute(
                LangfuseOtelSpanAttributes.TRACE_SESSION_ID,
                self.session_id,
            )
        except Exception:
            # Session id is still kept in trace metadata when SDK internals differ.
            return


def build_traced_agent(
    model: Any,
    *,
    trace_name: str = "agent-harness.agent.run",
    trace_metadata: dict[str, Any] | None = None,
    **agent_kwargs: Any,
) -> TracedAgent:
    from pydantic_ai import Agent

    return TracedAgent(
        agent=Agent(model, **agent_kwargs),
        trace_name=trace_name,
        trace_metadata=trace_metadata or {},
        model_name=settings.agent_bench_model,
        require_langfuse=False,
    )
