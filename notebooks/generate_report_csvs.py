"""Generate CSV summaries from a directory of agent-harness `*_scored.json` reports.

Produces two CSVs inside the given reports directory:
  - full_matrix_summary.csv   one row per (task, architecture) combo
  - architecture_summary.csv  one row per architecture, aggregated across tasks

Usage:
    python notebooks/generate_report_csvs.py [reports_dir]

If no directory is given, defaults to reports/20260707_full-matrix relative
to the repo root.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import statistics
import sys
from typing import Any

DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports",
    "20260707_full-matrix",
)

# Tie-break priority for "tasks won" when two architectures score identically
# on the same task (e.g. two architectures both hit 1.0). Architectures not
# listed here sort after these, alphabetically.
ARCH_PRIORITY = [
    "enterprise-react",
    "enterprise-codemode",
    "enterprise-mcp-react",
    "enterprise-mcp-codemode",
    "enterprise-sql-react",
    "enterprise-sql-codemode",
    "enterprise-react-toolsearch",
    "enterprise-codemode-toolsearch",
    "enterprise-mcp-react-native",
    "enterprise-react-thinking",
    "enterprise-codemode-thinking",
    "enterprise-react-120",
    "enterprise-codemode-120",
    "enterprise-mcp-react-120",
    "enterprise-react-toolsearch-120",
    "enterprise-categorized-search",
]


def _arch_sort_key(arch: str) -> tuple[int, str]:
    if arch in ARCH_PRIORITY:
        return (ARCH_PRIORITY.index(arch), arch)
    return (len(ARCH_PRIORITY), arch)


def load_results(reports_dir: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Load every `*_scored.json` file in reports_dir into a (task, architecture) -> row map.

    Handles both `run-all` mode files (a `results` list covering many
    architectures) and single `run` mode files (one result at the top level).
    """
    data: dict[tuple[str, str], dict[str, Any]] = {}

    def add_result(r: dict[str, Any]) -> None:
        scores = r.get("scores") or {}
        tool_sel = r.get("tool_selection") or {}
        data[(r["task"], r["architecture"])] = {
            "ok": r["ok"],
            "score": scores.get("overall_score"),
            "correctness": scores.get("correctness"),
            "groundedness": scores.get("groundedness"),
            "hallucination_rate": scores.get("hallucination_rate"),
            "elapsed": r["elapsed_seconds"],
            "error": (r.get("error") or "").replace("\n", " "),
            "tool_recall": tool_sel.get("tool_recall"),
            "tool_precision": tool_sel.get("tool_precision"),
            "total_tool_calls": tool_sel.get("total_tool_calls"),
            "distractor_call_count": tool_sel.get("distractor_call_count"),
            "fabricated_call_count": tool_sel.get("fabricated_call_count"),
        }

    for path in glob.glob(os.path.join(reports_dir, "*_scored.json")):
        with open(path) as fh:
            payload = json.load(fh)
        if "results" in payload:
            for result in payload["results"]:
                add_result(result)
        else:
            add_result(payload)

    return data


def write_full_matrix_csv(data: dict[tuple[str, str], dict[str, Any]], out_path: str) -> int:
    rows = [
        {
            "task": task,
            "architecture": arch,
            "ok": d["ok"],
            "score": d["score"],
            "correctness": d["correctness"],
            "groundedness": d["groundedness"],
            "hallucination_rate": d["hallucination_rate"],
            "elapsed_seconds": round(d["elapsed"], 2),
            "tool_recall": d["tool_recall"],
            "tool_precision": d["tool_precision"],
            "total_tool_calls": d["total_tool_calls"],
            "distractor_call_count": d["distractor_call_count"],
            "fabricated_call_count": d["fabricated_call_count"],
            "error": d["error"],
        }
        for (task, arch), d in data.items()
    ]
    rows.sort(key=lambda r: (r["task"], r["architecture"]))

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def write_architecture_summary_csv(
    data: dict[tuple[str, str], dict[str, Any]], out_path: str
) -> int:
    tasks = sorted({task for task, _ in data})
    archs = sorted({arch for _, arch in data if arch != "minimal"}, key=_arch_sort_key)

    rows = []
    for arch in archs:
        adj_scores, raw_scores, elapsed_ok = [], [], []
        recalls, precisions = [], []
        total_calls = total_distractor = total_fabricated = 0
        ok_count = 0
        for task in tasks:
            d = data.get((task, arch))
            if d is None:
                continue
            score = d["score"] if d["score"] is not None else 0.0
            adj_scores.append(score)
            if d["ok"]:
                ok_count += 1
                raw_scores.append(score)
                elapsed_ok.append(d["elapsed"])
            if d.get("tool_recall") is not None:
                recalls.append(d["tool_recall"])
                precisions.append(d["tool_precision"])
                total_calls += d.get("total_tool_calls") or 0
                total_distractor += d.get("distractor_call_count") or 0
                total_fabricated += d.get("fabricated_call_count") or 0

        wins = sum(
            1
            for task in tasks
            if arch
            == max(
                archs,
                key=lambda a: (data.get((task, a), {}).get("score") or 0.0),
            )
        )

        rows.append(
            {
                "architecture": arch,
                "reliability_adjusted_score": round(sum(adj_scores) / len(adj_scores), 4)
                if adj_scores
                else 0,
                "raw_score_when_ok": round(sum(raw_scores) / len(raw_scores), 4)
                if raw_scores
                else 0,
                "ok_rate": f"{ok_count}/{len(tasks)}",
                "avg_elapsed_seconds": round(sum(elapsed_ok) / len(elapsed_ok), 1)
                if elapsed_ok
                else 0,
                "median_elapsed_seconds": round(statistics.median(elapsed_ok), 1)
                if elapsed_ok
                else 0,
                "tasks_won": wins,
                "avg_tool_recall": round(sum(recalls) / len(recalls), 4) if recalls else None,
                "avg_tool_precision": round(sum(precisions) / len(precisions), 4)
                if precisions
                else None,
                "distractor_call_rate": round(total_distractor / total_calls, 4)
                if total_calls
                else None,
                "fabricated_call_rate": round(total_fabricated / total_calls, 4)
                if total_calls
                else None,
            }
        )

    rows.sort(key=lambda r: -r["reliability_adjusted_score"])

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main() -> None:
    reports_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    reports_dir = os.path.abspath(reports_dir)

    if not os.path.isdir(reports_dir):
        raise SystemExit(f"Reports directory not found: {reports_dir}")

    data = load_results(reports_dir)
    if not data:
        raise SystemExit(f"No *_scored.json results found in {reports_dir}")

    full_matrix_path = os.path.join(reports_dir, "full_matrix_summary.csv")
    architecture_path = os.path.join(reports_dir, "architecture_summary.csv")

    n_full = write_full_matrix_csv(data, full_matrix_path)
    n_arch = write_architecture_summary_csv(data, architecture_path)

    print(f"Wrote {n_full} rows to {full_matrix_path}")
    print(f"Wrote {n_arch} rows to {architecture_path}")


if __name__ == "__main__":
    main()
