import importlib.util
from pathlib import Path


def _load_score_report():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "score_report.py"
    spec = importlib.util.spec_from_file_location("score_report", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.score_report


score_report = _load_score_report()


def test_run_all_report_includes_overall_scores_and_best_architecture():
    ground_truth = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "tasks": {
            "sample": {
                "type": "deterministic-static",
                "expected": {"label": "alpha", "value": 10},
            }
        },
    }
    report = {
        "mode": "run-all",
        "harness": "demo",
        "task": "sample",
        "results": [
            {"architecture": "good", "output": "alpha 10"},
            {"architecture": "partial", "output": "alpha 99"},
        ],
    }

    scored = score_report(report, ground_truth)

    assert scored["results"][0]["scores"]["overall_score"] == 1.0
    assert scored["results"][1]["scores"]["overall_score"] == 0.0
    assert scored["score_summary"]["avg_overall_score"] == 0.5
    assert scored["score_summary"]["best_architecture"] == "good"
    assert scored["score_summary"]["best_overall_score"] == 1.0


def test_run_all_report_does_not_choose_best_architecture_when_all_scores_zero():
    ground_truth = {
        "tasks": {
            "sample": {
                "type": "deterministic-static",
                "expected": {"label": "alpha", "value": 10},
            }
        },
    }
    report = {
        "mode": "run-all",
        "harness": "demo",
        "task": "sample",
        "results": [
            {"architecture": "first", "output": ""},
            {"architecture": "second", "output": "I don't have access"},
        ],
    }

    scored = score_report(report, ground_truth)

    assert scored["score_summary"]["best_architecture"] is None
    assert scored["score_summary"]["best_overall_score"] == 0.0
