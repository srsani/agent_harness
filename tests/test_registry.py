from agent_harness.registry import get_harness, get_task, list_harnesses, list_tasks


def test_list_harnesses_includes_pydantic_ai():
    names = list(list_harnesses())
    assert "pydantic-ai" in names


def test_pydantic_ai_architectures():
    spec = get_harness("pydantic-ai")
    assert "minimal" in spec.architectures
    assert "codemode" in spec.architectures


def test_tasks():
    assert "hello" in list_tasks()
    assert "17 + 25" in get_task("hello")
