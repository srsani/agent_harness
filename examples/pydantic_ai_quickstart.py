"""Standalone quickstart mirroring pydantic-ai-harness docs.

Run:
    uv sync --extra pydantic-ai
    cp .env.example .env   # set ANTHROPIC_API_KEY
    uv run python examples/pydantic_ai_quickstart.py
"""

from agent_harness.config import settings
from agent_harness.harnesses.pydantic_ai.runners import make_runner


def main() -> None:
    runner = make_runner("codemode-mcp-search")
    prompt = (
        "Across the top Hacker News feed, find the highest-scored story with at least "
        "50 points. Summarize its title, score, and main theme in one paragraph."
    )
    print(f"Model: {settings.agent_bench_model}\n")
    result = runner.run(prompt)
    if result.error:
        raise SystemExit(result.error)
    print(result.output)


if __name__ == "__main__":
    main()
