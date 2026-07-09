from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_harness.tasks.tool_selection_benchmark import score_tool_selection

NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][0-2]\d:[0-5]\d:[0-5]\d)?")


def _flatten_scalars(value: Any) -> list[Any]:
    if isinstance(value, dict):
        out: list[Any] = []
        for v in value.values():
            out.extend(_flatten_scalars(v))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_flatten_scalars(item))
        return out
    return [value]


def _extract_expected_facts(expected: Any) -> tuple[list[str], list[float]]:
    texts: list[str] = []
    numbers: list[float] = []
    for scalar in _flatten_scalars(expected):
        if scalar is None:
            continue
        if isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
            numbers.append(float(scalar))
            continue
        text = str(scalar).strip()
        if not text:
            continue
        if ISO_DATE_RE.fullmatch(text):
            continue
        if len(text) >= 3:
            texts.append(text.lower())
    return texts, numbers


def _extract_output_numbers(output: str) -> list[float]:
    values: list[float] = []
    for token in NUMBER_RE.findall(output):
        token = token.replace("$", "").replace(",", "").strip()
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def _num_in_expected(x: float, expected: list[float], rel_tol: float = 0.01) -> bool:
    for y in expected:
        if math.isclose(x, y, rel_tol=rel_tol, abs_tol=1e-3):
            return True
    return False


def _overall_score(correctness: float | None, groundedness: float | None) -> float | None:
    if correctness is None or groundedness is None:
        return None
    if correctness <= 0 or groundedness <= 0:
        return 0.0
    return round((2 * correctness * groundedness) / (correctness + groundedness), 4)


def _score_output(output: str, expected: Any, deterministic: bool) -> dict[str, Any]:
    out_lower = output.lower()
    empty_output = len(output.strip()) == 0
    refusal_markers = [
        "don't have access",
        "do not have access",
        "i don't have access",
        "cannot access",
        "need access",
        "provide sample data",
    ]
    refused = any(marker in out_lower for marker in refusal_markers)

    if not deterministic:
        return {
            "scorable": False,
            "correctness": None,
            "groundedness": None,
            "hallucination_rate": None,
            "overall_score": None,
            "details": {"reason": "non-deterministic task"},
        }

    expected_texts, expected_numbers = _extract_expected_facts(expected)
    output_numbers = _extract_output_numbers(output)

    matched_texts = [t for t in expected_texts if t in out_lower]
    matched_numbers = [n for n in expected_numbers if _num_in_expected(n, output_numbers)]

    text_total = len(expected_texts)
    num_total = len(expected_numbers)

    text_score = (len(matched_texts) / text_total) if text_total else 1.0
    num_score = (len(matched_numbers) / num_total) if num_total else 1.0

    weighted_total = text_total + num_total
    if weighted_total:
        correctness = ((text_score * text_total) + (num_score * num_total)) / weighted_total
    else:
        correctness = 1.0

    if refused or empty_output:
        correctness = 0.0

    claimed_unique_numbers = sorted(set(output_numbers))
    unsupported_numbers = [
        x for x in claimed_unique_numbers if not _num_in_expected(x, expected_numbers)
    ]

    hallucination_rate = (
        len(unsupported_numbers) / len(claimed_unique_numbers) if claimed_unique_numbers else 0.0
    )
    groundedness = 1.0 - hallucination_rate

    if refused or empty_output:
        groundedness = 0.0
        hallucination_rate = 1.0

    correctness = round(correctness, 4)
    groundedness = round(groundedness, 4)
    hallucination_rate = round(hallucination_rate, 4)

    return {
        "scorable": True,
        "correctness": correctness,
        "groundedness": groundedness,
        "hallucination_rate": hallucination_rate,
        "overall_score": _overall_score(correctness, groundedness),
        "details": {
            "refused_or_no_data": (refused or empty_output),
            "empty_output": empty_output,
            "expected_text_facts": text_total,
            "matched_text_facts": len(matched_texts),
            "expected_numeric_facts": num_total,
            "matched_numeric_facts": len(matched_numbers),
            "claimed_numeric_values": len(claimed_unique_numbers),
            "unsupported_numeric_values": len(unsupported_numbers),
        },
    }


def _tool_selection_summary(scored_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate tool-selection precision/recall and distractor/fabricated call rates across a
    set of results, for the 120-tool scale benchmark (see `tool_selection_benchmark.py`).

    Skips results whose task isn't part of `TOOL_SELECTION_BENCHMARK` (e.g. `hn-research`) or
    that recorded no tool-call trace at all (harnesses/tasks predating tool-call capture).
    """
    scorable = [
        r["tool_selection"]
        for r in scored_results
        if r.get("tool_selection") is not None and r["tool_selection"].get("scorable")
    ]
    if not scorable:
        return None

    precisions = [s["tool_precision"] for s in scorable]
    recalls = [s["tool_recall"] for s in scorable]
    total_calls = sum(s["total_tool_calls"] for s in scorable)
    total_distractor_calls = sum(s["distractor_call_count"] for s in scorable)
    total_fabricated_calls = sum(s["fabricated_call_count"] for s in scorable)
    tasks_with_distractor = sum(1 for s in scorable if s["any_distractor_called"])
    tasks_with_fabricated = sum(1 for s in scorable if s["any_fabricated_called"])

    return {
        "scored_tasks": len(scorable),
        "avg_tool_precision": round(sum(precisions) / len(precisions), 4),
        "avg_tool_recall": round(sum(recalls) / len(recalls), 4),
        "total_tool_calls": total_calls,
        "total_distractor_calls": total_distractor_calls,
        "distractor_call_rate": round(total_distractor_calls / total_calls, 4) if total_calls else 0.0,
        "tasks_with_any_distractor_call": tasks_with_distractor,
        "tasks_with_any_distractor_call_pct": round(100 * tasks_with_distractor / len(scorable), 2),
        "total_fabricated_calls": total_fabricated_calls,
        "fabricated_call_rate": round(total_fabricated_calls / total_calls, 4) if total_calls else 0.0,
        "tasks_with_any_fabricated_call": tasks_with_fabricated,
        "tasks_with_any_fabricated_call_pct": round(100 * tasks_with_fabricated / len(scorable), 2),
    }


def _stability_summary(scored_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Summarize how much a set of repeated runs of the same architecture + task varied.

    LLM sampling is not fully deterministic, so identical (harness, architecture, task)
    combinations can still swing between correct, partially correct, and total failure
    across runs (see the `enterprise-codemode` / `adi-top-modules` reports this repo
    shipped with). `score_stdev` and `distinct_outputs` make that variance measurable
    instead of relying on a single run's score as ground truth.
    """
    if len(scored_results) < 2:
        return None

    ok_count = sum(1 for r in scored_results if r.get("ok"))
    distinct_outputs = len({(r.get("output") or "").strip() for r in scored_results})
    scores = [
        r["scores"]["overall_score"]
        for r in scored_results
        if r["scores"]["scorable"] and r["scores"]["overall_score"] is not None
    ]

    summary = {
        "runs": len(scored_results),
        "ok_rate": round(ok_count / len(scored_results), 4),
        "distinct_outputs": distinct_outputs,
        "avg_overall_score": round(sum(scores) / len(scores), 4) if scores else None,
        "score_stdev": round(statistics.pstdev(scores), 4) if len(scores) > 1 else (
            0.0 if scores else None
        ),
    }
    tool_selection = _tool_selection_summary(scored_results)
    if tool_selection is not None:
        summary["tool_selection"] = tool_selection
    return summary


def _score_single_result(
    result: dict[str, Any], task_name: str, gt_tasks: dict[str, Any]
) -> dict[str, Any]:
    tool_calls = (result.get("metadata") or {}).get("tool_calls") or []
    tool_selection = score_tool_selection(task_name, tool_calls)

    task_gt = gt_tasks.get(task_name)
    if task_gt is None:
        return {
            **result,
            "scores": {
                "scorable": False,
                "correctness": None,
                "groundedness": None,
                "hallucination_rate": None,
                "overall_score": None,
                "details": {"reason": f"task '{task_name}' missing in ground truth"},
            },
            "tool_selection": tool_selection,
        }

    deterministic = task_gt.get("type") not in ("external-dynamic", "conversational")
    expected = task_gt.get("expected")
    scored = _score_output(result.get("output", ""), expected, deterministic)
    return {**result, "scores": scored, "tool_selection": tool_selection}


def score_report(report: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    gt_tasks = ground_truth.get("tasks", {})
    mode = report.get("mode")

    if mode == "run-all":
        task_name = report.get("task")
        scored_results = [
            _score_single_result(result, task_name=task_name, gt_tasks=gt_tasks)
            for result in report.get("results", [])
        ]
        scorable = [r for r in scored_results if r["scores"]["scorable"]]
        correctness_vals = [
            r["scores"]["correctness"] for r in scorable if r["scores"]["correctness"] is not None
        ]
        grounded_vals = [
            r["scores"]["groundedness"] for r in scorable if r["scores"]["groundedness"] is not None
        ]
        halluc_vals = [
            r["scores"]["hallucination_rate"]
            for r in scorable
            if r["scores"]["hallucination_rate"] is not None
        ]
        overall_vals = [
            r["scores"]["overall_score"]
            for r in scorable
            if r["scores"]["overall_score"] is not None
        ]
        best_result = max(
            (r for r in scorable if r["scores"]["overall_score"] is not None),
            key=lambda r: r["scores"]["overall_score"],
            default=None,
        )
        best_overall_score = best_result["scores"]["overall_score"] if best_result else None
        best_architecture = (
            best_result["architecture"]
            if best_result and best_overall_score is not None and best_overall_score > 0
            else None
        )

        summary = {
            "scored_results": len(scorable),
            "overall_score_formula": "harmonic_mean(correctness, groundedness)",
            "avg_overall_score": round(sum(overall_vals) / len(overall_vals), 4)
            if overall_vals
            else None,
            "best_architecture": best_architecture,
            "best_overall_score": best_overall_score,
            "avg_correctness": round(sum(correctness_vals) / len(correctness_vals), 4)
            if correctness_vals
            else None,
            "avg_groundedness": round(sum(grounded_vals) / len(grounded_vals), 4)
            if grounded_vals
            else None,
            "avg_hallucination_rate": round(sum(halluc_vals) / len(halluc_vals), 4)
            if halluc_vals
            else None,
        }
        overall_tool_selection = _tool_selection_summary(scored_results)
        if overall_tool_selection is not None:
            summary["tool_selection"] = overall_tool_selection

        # When `--repeat N` was used, multiple results share the same architecture --
        # break out per-architecture stability (score variance, output diversity) so a
        # flaky architecture doesn't just silently average out against its own good runs.
        by_architecture: dict[str, list[dict[str, Any]]] = {}
        for r in scored_results:
            by_architecture.setdefault(r["architecture"], []).append(r)
        architecture_stability = {
            arch: stability
            for arch, arch_results in by_architecture.items()
            if (stability := _stability_summary(arch_results)) is not None
        }
        if architecture_stability:
            summary["architecture_stability"] = architecture_stability

        return {
            **report,
            "scored_at": datetime.now(UTC).isoformat(),
            "ground_truth_generated_at": ground_truth.get("generated_at"),
            "results": scored_results,
            "score_summary": summary,
        }

    if mode == "repeat":
        task_name = report.get("task")
        scored_results = [
            _score_single_result(result, task_name=task_name, gt_tasks=gt_tasks)
            for result in report.get("results", [])
        ]
        summary = _stability_summary(scored_results) or {
            "runs": len(scored_results),
            "ok_rate": None,
            "distinct_outputs": None,
            "avg_overall_score": None,
            "score_stdev": None,
        }
        summary["overall_score_formula"] = "harmonic_mean(correctness, groundedness)"

        return {
            **report,
            "scored_at": datetime.now(UTC).isoformat(),
            "ground_truth_generated_at": ground_truth.get("generated_at"),
            "results": scored_results,
            "score_summary": summary,
        }

    # mode == run (single object report)
    task_name = report.get("task")
    scored = _score_single_result(report, task_name=task_name, gt_tasks=gt_tasks)
    return {
        **scored,
        "scored_at": datetime.now(UTC).isoformat(),
        "ground_truth_generated_at": ground_truth.get("generated_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score benchmark report JSON against deterministic ground truth."
    )
    parser.add_argument(
        "--report", type=Path, required=True, help="Input benchmark report JSON path"
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("reports/ground-truth.json"),
        help="Ground truth JSON path (default: reports/ground-truth.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output scored JSON path (default: <report>_scored.json)",
    )
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    ground_truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    scored = score_report(report, ground_truth)

    output_path = args.output or args.report.with_name(f"{args.report.stem}_scored.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scored, indent=2), encoding="utf-8")
    print(f"Saved scored report to {output_path}")


if __name__ == "__main__":
    main()
