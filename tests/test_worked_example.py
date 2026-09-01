"""
Proves the offline Match Advisor worked example (examples/match_advisor_worked_example.py)
actually drives the real Strands Agent through five real tool calls and produces an
answer consistent with the real matching/dedup/escalation engines -- with zero
network access and zero API key, exactly like the rest of the offline test suite.
"""

from examples.match_advisor_worked_example import run_worked_example
from src.scripted_model import ScriptedAdvisorModel


def test_worked_example_runs_five_tools_and_terminates(capsys):
    answer = run_worked_example()

    captured = capsys.readouterr()
    # All five tools were actually invoked by the real Strands event loop (not just described).
    for tool_name in [
        "category_match_impl",
        "geo_distance_impl",
        "score_match_impl",
        "duplicate_check_impl",
        "sla_check_impl",
    ]:
        assert f"calling tool: {tool_name}" in captured.out
        assert f"{tool_name} real result:" in captured.out

    # The final answer cites real, non-fabricated tool outputs.
    assert "score=0.8" in answer
    assert "category_match_impl" in answer
    assert "BREACHED" in answer or "not yet breached" in answer
    assert "coordinator" in answer.lower()


def test_scripted_advisor_model_requires_trailing_text_step():
    import pytest

    with pytest.raises(ValueError):
        ScriptedAdvisorModel([("tool", "category_match_impl", {"category_a": "water", "category_b": "water"})])
