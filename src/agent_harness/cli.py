from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent_harness.registry import get_harness, get_task, list_harnesses, list_tasks
from agent_harness.runners.base import RunResult

app = typer.Typer(
    name="agent-bench",
    help="Compare agent harnesses and agentic architectures.",
    no_args_is_help=True,
)
console = Console()


@app.command("list")
def list_all() -> None:
    """List harnesses, architectures, and tasks."""
    table = Table(title="Harnesses & Architectures")
    table.add_column("Harness")
    table.add_column("Architecture")
    table.add_column("Description")

    for harness in list_harnesses().values():
        for arch_name, arch_desc in harness.architectures.items():
            table.add_row(harness.name, arch_name, arch_desc)
    console.print(table)

    task_table = Table(title="Tasks")
    task_table.add_column("Name")
    task_table.add_column("Prompt preview", overflow="fold")
    for name, prompt in list_tasks().items():
        preview = prompt[:120] + ("…" if len(prompt) > 120 else "")
        task_table.add_row(name, preview)
    console.print(task_table)


@app.command("run")
def run_single(
    harness: str = typer.Option(..., help="Harness name, e.g. pydantic-ai"),
    architecture: str = typer.Option(..., help="Architecture variant name"),
    task: str = typer.Option(..., help="Task name from the registry"),
    output: Path | None = typer.Option(
        None, help="Optional JSON output path for the benchmark result."
    ),
) -> None:
    """Run one harness + architecture + task combination."""
    spec = get_harness(harness)
    if architecture not in spec.architectures:
        available = ", ".join(spec.architectures)
        raise typer.BadParameter(f"Unknown architecture '{architecture}'. Choose: {available}")

    prompt = get_task(task)
    session_id = _make_session_id("run", harness, task)
    runner = spec.factory(architecture)
    result = runner.run(prompt, session_id=session_id)
    result.task = task

    _print_result(result)
    if output is not None:
        _write_json_report(output, {"session_id": session_id, **_result_to_dict(result)})
    if result.error:
        raise typer.Exit(code=1)


@app.command("run-all")
def run_all(
    harness: str = typer.Option(..., help="Harness name"),
    task: str = typer.Option(..., help="Task name"),
    output: Path | None = typer.Option(
        None, help="Optional JSON output path for benchmark summary + results."
    ),
) -> None:
    """Run every architecture for a harness against one task."""
    spec = get_harness(harness)
    prompt = get_task(task)
    session_id = _make_session_id("run-all", harness, task)
    results = []

    for arch_name in spec.architectures:
        console.rule(f"[bold]{harness}[/] / {arch_name}")
        runner = spec.factory(arch_name)
        result = runner.run(prompt, session_id=session_id)
        result.task = task
        results.append(result)
        _print_result(result)

    _print_summary(results)
    if output is not None:
        payload = {
            "mode": "run-all",
            "session_id": session_id,
            "harness": harness,
            "task": task,
            "results": [_result_to_dict(r) for r in results],
        }
        _write_json_report(output, payload)


def _make_session_id(mode: str, harness: str, task: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"agent-bench:{mode}:{harness}:{task}:{timestamp}:{uuid4().hex[:8]}"


def _print_result(result) -> None:
    if result.error:
        console.print(Panel(result.error, title="Error", border_style="red"))
        return
    console.print(
        Panel(
            result.output,
            title=f"{result.harness} / {result.architecture} ({result.elapsed_seconds:.1f}s)",
            border_style="green",
        )
    )


def _print_summary(results) -> None:
    table = Table(title="Summary")
    table.add_column("Architecture")
    table.add_column("Status")
    table.add_column("Time (s)")
    table.add_column("Output preview", overflow="fold")

    for r in results:
        status = "OK" if r.ok else "FAIL"
        preview = (r.output or r.error or "")[:80]
        table.add_row(r.architecture, status, f"{r.elapsed_seconds:.1f}", preview)
    console.print(table)


def _result_to_dict(result: RunResult) -> dict:
    return {
        "harness": result.harness,
        "architecture": result.architecture,
        "task": result.task,
        "prompt": result.prompt,
        "output": result.output,
        "started_at": result.started_at.isoformat(),
        "elapsed_seconds": result.elapsed_seconds,
        "metadata": result.metadata,
        "error": result.error,
        "ok": result.ok,
    }


def _write_json_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"[green]Saved JSON report:[/] {path}")


if __name__ == "__main__":
    app()
