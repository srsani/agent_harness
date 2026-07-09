#!/usr/bin/env bash
# One-off helper: run enterprise-codemode-toolsearch-120 and
# enterprise-codemode-categorized-search across all 30 120-tool-scale tasks and
# score each result, to fill out the CodeMode-at-scale rows missing from
# reports/20260708_scale-benchmark. Not meant to be a permanent script.
set -uo pipefail

REPORT_DIR="reports/20260708_scale-benchmark"
GROUND_TRUTH="$REPORT_DIR/ground-truth.json"

TASKS=(
  finance-budget-detail-10
  finance-budget-variance-10
  finance-capex-summary-2025
  finance-expense-breakdown-2025
  finance-forecast-vs-actual-rd-2025
  finance-search-department-expenses-rd
  marketing-campaign-detail-5
  marketing-campaign-roi-5
  marketing-channel-spend-365d
  marketing-funnel-5
  marketing-search-webinar
  marketing-top-campaigns-conversion
  procurement-late-deliveries-365d
  procurement-po-detail-50
  procurement-search-software-highrating
  procurement-spend-summary-2025
  procurement-supplier-detail-10
  procurement-supplier-performance-10
  support-agent-profile-5
  support-csat-90d
  support-open-tickets-priority
  support-resolution-stats-180d
  support-search-urgent-open
  support-tickets-for-module-8
  workforce-attrition-3-365d
  workforce-employee-detail-10
  workforce-headcount-3
  workforce-open-positions
  workforce-review-summary-10
  workforce-search-finance-analysts
)

ARCHITECTURES=(
  enterprise-codemode-toolsearch-120
  enterprise-codemode-categorized-search
)

# CodeMode's sandboxed run_code call can occasionally hang outright (a model-written
# infinite loop, or a local-model generation that never terminates) rather than fail
# fast -- observed directly during this run (enterprise-codemode-toolsearch-120 /
# finance-expense-breakdown-2025 sat at ~0% CPU for 13+ minutes with an established but
# idle connection to the local model server). A hard per-run wall-clock cap turns that
# failure mode into a recorded timeout instead of stalling the whole 60-run batch.
RUN_TIMEOUT_SECONDS=180

for arch in "${ARCHITECTURES[@]}"; do
  for task in "${TASKS[@]}"; do
    out="$REPORT_DIR/extra_${task}_${arch}.json"
    scored="$REPORT_DIR/extra_${task}_${arch}_scored.json"
    if [[ -f "$scored" ]]; then
      echo "=== SKIP (already scored) ${task} / ${arch} ==="
      continue
    fi
    echo "=== ${task} / ${arch} ==="
    # Invoke the venv binary directly (not `uv run agent-bench`) so gtimeout's KILL
    # targets the actual agent-bench process instead of an intermediate `uv` wrapper
    # that doesn't reliably propagate the signal to its child.
    gtimeout --signal=KILL "${RUN_TIMEOUT_SECONDS}s" .venv/bin/agent-bench run \
      --harness pydantic-ai \
      --architecture "$arch" \
      --task "$task" \
      --output "$out"
    rc=$?
    if [[ $rc -eq 137 || $rc -eq 124 ]]; then
      echo "!!! TIMEOUT after ${RUN_TIMEOUT_SECONDS}s, synthesizing failure result"
      python3 - "$out" "$arch" "$task" "$RUN_TIMEOUT_SECONDS" <<'PYEOF'
import json, sys, datetime
out, arch, task, timeout_s = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
payload = {
    "harness": "pydantic-ai",
    "architecture": arch,
    "task": task,
    "prompt": "",
    "output": "",
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "elapsed_seconds": float(timeout_s),
    "metadata": {"tool_calls": []},
    "error": f"TimeoutError: run exceeded {timeout_s}s wall-clock cap (hung, killed by benchmark harness)",
    "ok": False,
}
with open(out, "w") as fh:
    json.dump(payload, fh, indent=2)
PYEOF
    elif [[ $rc -ne 0 ]]; then
      echo "!!! run failed (exit $rc), scoring anyway if json exists"
    fi
    if [[ -f "$out" ]]; then
      uv run python scripts/score_report.py \
        --report "$out" \
        --ground-truth "$GROUND_TRUTH" \
        --output "$scored"
    else
      echo "!!! no output json for ${task} / ${arch}, skipping score"
    fi
  done
done

echo "=== ALL DONE ==="
