from agent_harness.tasks.builtins import TASKS
from agent_harness.tasks.routing_benchmark import (
    ANALYSIS,
    ARCHITECTURES,
    ROUTING_BENCHMARK,
)

_PREFIX_BY_ARCHITECTURE = {
    "minimal": "minimal-",
    "enterprise-react": "react-",
    "enterprise-codemode": "codemode-",
    "enterprise-mcp-react": "mcpreact-",
    "enterprise-mcp-codemode": "mcpcodemode-",
    "enterprise-sql-react": "sqlreact-",
    "enterprise-sql-codemode": "sqlcodemode-",
}


def test_all_seven_architectures_are_present():
    assert set(ROUTING_BENCHMARK.keys()) == set(ARCHITECTURES)
    assert len(ARCHITECTURES) == 7


def test_each_architecture_has_10_to_15_entries():
    for architecture, entries in ROUTING_BENCHMARK.items():
        assert 10 <= len(entries) <= 15, (architecture, len(entries))


def test_task_keys_match_expected_prefix_and_exist_in_builtins():
    for architecture, entries in ROUTING_BENCHMARK.items():
        prefix = _PREFIX_BY_ARCHITECTURE[architecture]
        for entry in entries:
            task_key = entry["task_key"]
            assert task_key.startswith(prefix), (architecture, task_key)
            assert task_key in TASKS
            assert entry["question"] == TASKS[task_key]


def test_task_keys_are_globally_unique_across_architectures():
    all_keys = [entry["task_key"] for entries in ROUTING_BENCHMARK.values() for entry in entries]
    assert len(all_keys) == len(set(all_keys))


def test_each_entry_lists_the_other_six_architectures_as_alternatives():
    for architecture, entries in ROUTING_BENCHMARK.items():
        expected_alternatives = set(ARCHITECTURES) - {architecture}
        for entry in entries:
            assert entry["ideal_architecture"] == architecture
            assert set(entry["alternatives"].keys()) == expected_alternatives
            assert all(isinstance(v, str) and v for v in entry["alternatives"].values())


def test_each_entry_has_a_nonempty_why_and_routing_signals():
    for entries in ROUTING_BENCHMARK.values():
        for entry in entries:
            assert isinstance(entry["why"], str) and entry["why"]
            assert entry["routing_signals"]
            assert all(isinstance(s, str) and s for s in entry["routing_signals"])


def test_analysis_covers_the_six_documented_comparisons():
    expected = {
        "minimal_vs_any_tool_architecture",
        "enterprise-react_vs_enterprise-codemode",
        "enterprise-mcp-react_vs_enterprise-mcp-codemode",
        "enterprise-sql-react_vs_enterprise-sql-codemode",
        "direct_typed_tools_vs_local_fastmcp_tools",
        "full_enterprise_tools_vs_sql_only_tools",
    }
    assert set(ANALYSIS.keys()) == expected
    for comparison in ANALYSIS.values():
        assert isinstance(comparison, dict)
        assert comparison
