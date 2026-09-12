"""The eval harness itself: scoring, parsing, and the scenario file.

No model is involved here. This guards the harness so a green eval run means the
model did well rather than that the scorer stopped noticing.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

from scenario_runner import (
    Scenario,
    extract_call,
    judge,
    load_scenarios,
    report,
)


def scenario(**overrides) -> Scenario:
    defaults = {
        "id": "example",
        "level": "select",
        "language": "en",
        "prompt": "do the thing",
        "expect": "run_playbook",
    }
    return Scenario(**{**defaults, **overrides})


def test_the_scenario_file_parses_and_is_not_trivial():
    scenarios = load_scenarios()

    assert len(scenarios) >= 20
    assert {s.level for s in scenarios} == {"select", "sibling", "argument", "negative"}
    assert {s.language for s in scenarios} == {"en", "ru"}
    # Negative scenarios are the ones that catch damage, so require a real share.
    assert sum(1 for s in scenarios if s.level == "negative") >= 5


def test_scenario_ids_are_unique():
    identifiers = [s.id for s in load_scenarios()]

    assert len(identifiers) == len(set(identifiers))


def test_every_scenario_names_tools_that_exist():
    from ansible_mcp.server.tools import playbooks, providers, tasks

    sources = " ".join(
        Path(module.__file__).read_text() for module in (tasks, playbooks, providers)
    )
    for entry in load_scenarios():
        for name in [entry.expect, *entry.forbidden]:
            if name is not None:
                assert f"async def {name}(" in sources, f"{entry.id} names unknown tool {name}"


def test_choosing_the_expected_tool_passes():
    verdict = judge(scenario(), "run_playbook", {}, structured=True)

    assert verdict.passed


def test_choosing_another_tool_fails():
    verdict = judge(scenario(), "cancel_task", {}, structured=True)

    assert not verdict.passed
    assert verdict.verdict == "wrong-tool"


def test_calling_nothing_when_a_tool_was_expected_fails():
    verdict = judge(scenario(), None, {}, structured=True)

    assert verdict.verdict == "no-call"


def test_a_forbidden_tool_fails_even_if_it_is_the_expected_one():
    # A prompt can expect a tool and forbid another; forbidden wins outright.
    verdict = judge(
        scenario(expect="list_tasks", forbidden=["cancel_task"]),
        "cancel_task",
        {},
        structured=True,
    )

    assert verdict.verdict == "forbidden"


def test_calling_nothing_passes_when_nothing_was_expected():
    verdict = judge(scenario(expect=None), None, {}, structured=True)

    assert verdict.passed


def test_calling_something_fails_when_nothing_was_expected():
    verdict = judge(scenario(expect=None), "get_playbook", {}, structured=True)

    assert verdict.verdict == "fail"


def test_expected_arguments_must_match():
    entry = scenario(arguments={"task_id": "abc", "tail": 500})

    assert judge(entry, "run_playbook", {"task_id": "abc", "tail": 500}, structured=True).passed
    assert judge(entry, "run_playbook", {"task_id": "abc"}, structured=True).verdict == (
        "bad-arguments"
    )


def test_arguments_are_compared_as_text_so_500_matches_500():
    entry = scenario(arguments={"tail": 500})

    assert judge(entry, "run_playbook", {"tail": "500"}, structured=True).passed


def test_extra_arguments_are_allowed():
    entry = scenario(arguments={"task_id": "abc"})

    assert judge(entry, "run_playbook", {"task_id": "abc", "tail": 10}, structured=True).passed


def test_a_native_tool_call_is_read():
    called, arguments, structured = extract_call(
        {"tool_calls": [{"function": {"name": "get_task_logs", "arguments": {"tail": 20}}}]},
    )

    assert (called, arguments, structured) == ("get_task_logs", {"tail": 20}, True)


def test_arguments_given_as_a_json_string_are_read():
    _called, arguments, structured = extract_call(
        {"tool_calls": [{"function": {"name": "get_task_logs", "arguments": '{"tail": 20}'}}]},
    )

    assert arguments == {"tail": 20}
    assert structured is True


def test_a_tool_named_in_prose_is_read_but_marked_unstructured():
    called, arguments, structured = extract_call(
        {"content": 'Sure, I will call {"name": "get_task_status", "arguments": {"task_id": "a"}}'},
    )

    assert called == "get_task_status"
    assert arguments == {"task_id": "a"}
    assert structured is False


def test_prose_without_a_call_reads_as_no_call():
    called, _arguments, structured = extract_call(
        {"content": "A role is reusable, a playbook is not."}
    )

    assert called is None
    assert structured is False


def test_malformed_json_in_prose_reads_as_no_call():
    called, _arguments, _structured = extract_call({"content": "{not json at all"})

    assert called is None


@pytest.mark.parametrize(
    ("passes", "total", "threshold", "expected_code"),
    [(10, 10, 0.8, 0), (8, 10, 0.8, 0), (7, 10, 0.8, 1), (0, 1, 0.5, 1)],
)
def test_the_threshold_decides_the_exit_code(passes, total, threshold, expected_code, capsys):
    judgements = [
        judge(scenario(), "run_playbook" if index < passes else "cancel_task", {}, structured=True)
        for index in range(total)
    ]

    code = report(judgements, threshold)

    capsys.readouterr()
    assert code == expected_code


# The chain harness: ordering, allowlists and state checks. No model involved.


def chain(**overrides):
    from chain_runner import Chain

    defaults = {
        "id": "example",
        "language": "en",
        "task": "do the multi-step thing",
        "allow": ["run_playbook", "get_task_status"],
    }
    return Chain(**{**defaults, **overrides})


def test_the_chain_file_parses():
    from chain_runner import load_chains

    chains = load_chains()

    assert len(chains) >= 3
    for entry in chains:
        assert entry.require, f"{entry.id} requires no step, so it cannot fail"
        assert entry.allow, f"{entry.id} allows no tool"
        # Every required step must be allowed, or the scenario is unpassable.
        assert set(entry.require) <= set(entry.allow), entry.id


def test_required_steps_may_have_gaps_between_them():
    from chain_runner import contains_in_order

    assert contains_in_order(
        ["save_playbook", "list_playbooks", "run_playbook"], ["save_playbook", "run_playbook"]
    )


def test_required_steps_out_of_order_do_not_count():
    from chain_runner import contains_in_order

    assert not contains_in_order(
        ["run_playbook", "save_playbook"], ["save_playbook", "run_playbook"]
    )


def test_a_missing_required_step_does_not_count():
    from chain_runner import contains_in_order

    assert not contains_in_order(["save_playbook"], ["save_playbook", "run_playbook"])


def test_expectations_compare_against_observed_state():
    from chain_runner import _check_expectations

    state = {
        "tasks_succeeded": 1,
        "tasks_cancelled": 0,
        "playbooks": {"eval-hello"},
        "providers": set(),
    }

    assert _check_expectations({"playbook_stored": "eval-hello", "tasks_succeeded": 1}, state) == []
    assert _check_expectations({"playbook_stored": "missing"}, state) == [
        "playbook 'missing' was not stored",
    ]
    assert _check_expectations({"tasks_cancelled": 1}, state) == [
        "tasks_cancelled: wanted 1, ended with 0",
    ]
    assert _check_expectations({"provider_configured": "eval-local"}, state) == [
        "provider 'eval-local' was not configured",
    ]


def test_an_outcome_with_problems_fails():
    from chain_runner import Outcome

    assert Outcome(chain(), ["run_playbook"], []).passed
    assert not Outcome(chain(), ["run_playbook"], ["called something forbidden"]).passed
