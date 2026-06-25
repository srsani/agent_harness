from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent_harness.registry import get_harness, get_task, list_harnesses, list_tasks

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
) -> None:
    """Run one harness + architecture + task combination."""
    spec = get_harness(harness)
    if architecture not in spec.architectures:
        available = ", ".join(spec.architectures)
        raise typer.BadParameter(f"Unknown architecture '{architecture}'. Choose: {available}")

    prompt = get_task(task)
    runner = spec.factory(architecture)
    result = runner.run(prompt)
    result.task = task

    _print_result(result)
    if result.error:
        raise typer.Exit(code=1)


@app.command("run-all")
def run_all(
    harness: str = typer.Option(..., help="Harness name"),
    task: str = typer.Option(..., help="Task name"),
) -> None:
    """Run every architecture for a harness against one task."""
    spec = get_harness(harness)
    prompt = get_task(task)
    results = []

    for arch_name in spec.architectures:
        console.rule(f"[bold]{harness}[/] / {arch_name}")
        runner = spec.factory(arch_name)
        result = runner.run(prompt)
        result.task = task
        results.append(result)
        _print_result(result)

    _print_summary(results)


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


if __name__ == "__main__":
    app()
