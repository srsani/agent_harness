import importlib.util
from pathlib import Path


def _load_generate_ground_truth():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_ground_truth.py"
    spec = importlib.util.spec_from_file_location("generate_ground_truth", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_ground_truth


build_ground_truth = _load_generate_ground_truth()


def test_function_opportunity_ground_truth_includes_top_three_metric_rows():
    ground_truth = build_ground_truth()
    task = ground_truth["tasks"]["adi-function-opportunity"]

    assert task["type"] == "deterministic-sql"
    assert len(task["expected"]) == 3
    assert set(task["expected"][0]) == {
        "business_function",
        "revenue_6m",
        "unique_users_6m",
        "highest_revenue_module",
        "avg_module_rating",
        "low_adoption_modules",
    }
