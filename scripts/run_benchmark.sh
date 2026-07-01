#!/usr/bin/env bash
set -euo pipefail

# One-stop helper for list/run/run-all benchmark flows.
# Examples:
#   ./scripts/run_benchmark.sh list
#   ./scripts/run_benchmark.sh run --architecture enterprise-react --task adi-function-analysis
#   ./scripts/run_benchmark.sh run-all --task adi-top-modules

MODE="run-all"
HARNESS="pydantic-ai"
ARCHITECTURE="enterprise-react"
TASK="adi-function-analysis"
SKIP_SETUP=0
SKIP_SEED=0
OUTPUT=""
SKIP_SCORE=0
GROUND_TRUTH_OUTPUT="reports/ground-truth.json"
SCORE_OUTPUT=""

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_benchmark.sh [list|run|run-all] [options]

Modes:
  list                  Show harnesses, architectures, tasks.
  run                   Run one harness+architecture+task.
  run-all               Run all architectures for one harness+task (default).

Options:
  --harness NAME        Harness name (default: pydantic-ai)
  --architecture NAME   Architecture for "run" mode (default: enterprise-react)
  --task NAME           Task name (default: adi-function-analysis)
  --output PATH         JSON report output path (default: reports/<timestamp>_...)
  --ground-truth PATH   Ground-truth JSON path (default: reports/ground-truth.json)
  --score-output PATH   Scored JSON output path (default: <report>_scored.json)
  --skip-score          Skip scoring report against ground truth
  --skip-setup          Skip dependency install + .env check
  --skip-seed           Skip database seeding
  -h, --help            Show this help
EOF
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    list|run|run-all)
      MODE="$1"
      shift
      ;;
  esac
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --harness)
      HARNESS="${2:-}"
      shift 2
      ;;
    --architecture)
      ARCHITECTURE="${2:-}"
      shift 2
      ;;
    --task)
      TASK="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --ground-truth)
      GROUND_TRUTH_OUTPUT="${2:-}"
      shift 2
      ;;
    --score-output)
      SCORE_OUTPUT="${2:-}"
      shift 2
      ;;
    --skip-score)
      SKIP_SCORE=1
      shift
      ;;
    --skip-setup)
      SKIP_SETUP=1
      shift
      ;;
    --skip-seed)
      SKIP_SEED=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$SKIP_SETUP" -eq 0 ]]; then
  echo "==> Installing dependencies"
  uv sync --extra pydantic-ai --extra dev

  if [[ ! -f ".env" ]]; then
    echo "==> Creating .env from .env.example"
    cp .env.example .env
    cat <<'EOF'
Created .env. Fill in your model provider keys and Langfuse keys, then rerun:
  LANGFUSE_PUBLIC_KEY
  LANGFUSE_SECRET_KEY
EOF
    exit 1
  fi
fi

if [[ "$MODE" == "list" ]]; then
  echo "==> Listing harnesses/architectures/tasks"
  uv run agent-bench list
  exit 0
fi

if [[ "$SKIP_SEED" -eq 0 ]]; then
  echo "==> Resetting and seeding test database"
  uv run python scripts/seed_db.py --reset
fi

if [[ "$SKIP_SCORE" -eq 0 ]]; then
  echo "==> Generating ground truth"
  uv run python scripts/generate_ground_truth.py --output "$GROUND_TRUTH_OUTPUT"
fi

case "$MODE" in
  run)
    if [[ -z "$OUTPUT" ]]; then
      TS="$(date +"%Y%m%d_%H%M%S")"
      OUTPUT="reports/${TS}_run_${HARNESS}_${ARCHITECTURE}_${TASK}.json"
    fi
    echo "==> Running single benchmark"
    uv run agent-bench run \
      --harness "$HARNESS" \
      --architecture "$ARCHITECTURE" \
      --task "$TASK" \
      --output "$OUTPUT"
    echo "==> JSON report: $OUTPUT"
    if [[ "$SKIP_SCORE" -eq 0 ]]; then
      if [[ -z "$SCORE_OUTPUT" ]]; then
        SCORE_OUTPUT="${OUTPUT%.json}_scored.json"
      fi
      uv run python scripts/score_report.py \
        --report "$OUTPUT" \
        --ground-truth "$GROUND_TRUTH_OUTPUT" \
        --output "$SCORE_OUTPUT"
      echo "==> Scored JSON report: $SCORE_OUTPUT"
    fi
    ;;
  run-all)
    if [[ -z "$OUTPUT" ]]; then
      TS="$(date +"%Y%m%d_%H%M%S")"
      OUTPUT="reports/${TS}_run-all_${HARNESS}_${TASK}.json"
    fi
    echo "==> Running benchmark across all architectures"
    uv run agent-bench run-all \
      --harness "$HARNESS" \
      --task "$TASK" \
      --output "$OUTPUT"
    echo "==> JSON report: $OUTPUT"
    if [[ "$SKIP_SCORE" -eq 0 ]]; then
      if [[ -z "$SCORE_OUTPUT" ]]; then
        SCORE_OUTPUT="${OUTPUT%.json}_scored.json"
      fi
      uv run python scripts/score_report.py \
        --report "$OUTPUT" \
        --ground-truth "$GROUND_TRUTH_OUTPUT" \
        --output "$SCORE_OUTPUT"
      echo "==> Scored JSON report: $SCORE_OUTPUT"
    fi
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    usage
    exit 1
    ;;
esac
