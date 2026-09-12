"""Does a model actually pick the right tool from these descriptions?

The tool schemas come from the real server, so this measures what an agent is
offered, not a copy of it that can drift. Nothing is executed: the model is asked
what it would call, and the answer is scored.

Run it against a weak local model. If a 7B model picks correctly, a commercial
agent will; and when it does not, the fault is almost always the tool
descriptions rather than the model, which is the point of measuring.

    poetry run python evals/scenario_runner.py --model qwen2.5-coder:7b

Exits non-zero when the pass rate falls below the threshold, so this can gate a
merge instead of being run when someone remembers.

Two different things are measured and kept apart. Whether the right tool is
chosen is ours to fix, in the descriptions. Whether the choice arrives as a
structured tool call is the model's build: qwen2.5-coder under Ollama answers
with the correct JSON in its message body and leaves tool_calls empty, which says
nothing about our schemas. Pass --require-structured when testing a model that
does support native calls and the distinction should be enforced.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ansible_mcp.config import Settings
from ansible_mcp.server import build_application

SCENARIOS = Path(__file__).parent / "scenarios.yaml"
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11435")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
DEFAULT_THRESHOLD = 0.8  # baseline is 86% on both local models
REQUEST_TIMEOUT = 180.0

SYSTEM_PROMPT = """\
You control an Ansible server through the tools you are given. When the user asks
for something that a tool does, call that tool. When no tool fits, answer in
words and call nothing. Never call a tool that changes or destroys state unless
the user asked for that specific change.
"""


@dataclass
class Scenario:
    """One prompt and what the model is expected to do with it."""

    id: str
    level: str
    language: str
    prompt: str
    expect: str | None = None
    forbidden: list[str] = field(default_factory=list)
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Judgement:
    """How one scenario went."""

    scenario: Scenario
    called: str | None
    arguments: dict[str, Any]
    structured: bool
    verdict: str
    note: str = ""

    @property
    def passed(self) -> bool:
        """Whether this scenario counts as a pass."""
        return self.verdict == "pass"


def load_scenarios(path: Path = SCENARIOS) -> list[Scenario]:
    """Read the scenario file."""
    raw = yaml.safe_load(path.read_text())
    return [Scenario(**entry) for entry in raw]


async def tool_schemas() -> list[dict[str, Any]]:
    """Return the server's own tool definitions, in the shape Ollama expects."""
    application = build_application(Settings(data_dir=Path("/tmp/ansible-mcp-eval")))
    tools = await application.server.list_tools()
    await application.engine.dispose()
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


def judge(
    scenario: Scenario, called: str | None, arguments: dict[str, Any], *, structured: bool
) -> Judgement:
    """Score one answer against what the scenario asked for."""
    if called in scenario.forbidden:
        return Judgement(
            scenario,
            called,
            arguments,
            structured,
            "forbidden",
            f"called {called}, which this prompt must not trigger",
        )

    if scenario.expect is None:
        if called is None:
            return Judgement(scenario, called, arguments, structured, "pass", "no tool called")
        return Judgement(
            scenario,
            called,
            arguments,
            structured,
            "fail",
            f"called {called} where no tool was needed",
        )

    if called is None:
        return Judgement(
            scenario,
            called,
            arguments,
            structured,
            "no-call",
            f"expected {scenario.expect}, nothing was called",
        )
    if called != scenario.expect:
        return Judgement(
            scenario,
            called,
            arguments,
            structured,
            "wrong-tool",
            f"expected {scenario.expect}, got {called}",
        )

    missing = {
        name: wanted
        for name, wanted in scenario.arguments.items()
        if str(arguments.get(name)) != str(wanted)
    }
    if missing:
        return Judgement(
            scenario,
            called,
            arguments,
            structured,
            "bad-arguments",
            f"expected {missing}, got {dict(arguments)}",
        )

    return Judgement(scenario, called, arguments, structured, "pass")


def extract_call(message: dict[str, Any]) -> tuple[str | None, dict[str, Any], bool]:
    """Pull a tool call out of a reply, structured or not.

    A model that names the right tool in prose has understood the descriptions
    but cannot be driven, so the two cases are told apart rather than merged.
    """
    calls = message.get("tool_calls") or []
    if calls:
        function = calls[0].get("function", {})
        raw_arguments = function.get("arguments") or {}
        if isinstance(raw_arguments, str):
            try:
                raw_arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                raw_arguments = {}
        return function.get("name"), dict(raw_arguments), True

    content = message.get("content") or ""
    try:
        payload = json.loads(content[content.index("{") : content.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None, {}, False
    if isinstance(payload, dict):
        name = payload.get("name") or payload.get("tool")
        if isinstance(name, str):
            arguments = payload.get("arguments") or payload.get("parameters") or {}
            return name, dict(arguments) if isinstance(arguments, dict) else {}, False
    return None, {}, False


async def ask(
    client: httpx.AsyncClient,
    host: str,
    model: str,
    scenario: Scenario,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send one scenario to the model and return its reply message."""
    response = await client.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": scenario.prompt},
            ],
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return dict(response.json().get("message") or {})


async def run(
    host: str,
    model: str,
    threshold: float,
    only: str | None,
    *,
    require_structured: bool = False,
) -> int:
    """Run every scenario and print the report. Returns a process exit code."""
    scenarios = [s for s in load_scenarios() if only is None or only in {s.id, s.level}]
    tools = await tool_schemas()
    print(f"model {model} against {len(tools)} tools, {len(scenarios)} scenarios\n")

    judgements: list[Judgement] = []
    # trust_env=False: a SOCKS proxy in the environment would swallow a request
    # to a loopback port.
    async with httpx.AsyncClient(trust_env=False) as client:
        for scenario in scenarios:
            try:
                message = await ask(client, host, model, scenario, tools)
            except httpx.HTTPError as error:
                print(f"  {scenario.id}: cannot reach {host}: {error}")
                return 2
            called, arguments, structured = extract_call(message)
            judgement = judge(scenario, called, arguments, structured=structured)
            if require_structured and called is not None and not structured:
                judgement = Judgement(
                    scenario,
                    called,
                    arguments,
                    structured,
                    "unstructured",
                    f"chose {called} but answered in prose instead of calling it",
                )
            judgements.append(judgement)
            mark = "ok  " if judgement.passed else "FAIL"
            unstructured = "" if structured or called is None else " [as text, not a tool call]"
            print(f"  {mark} {scenario.id} ({scenario.level}/{scenario.language})")
            if judgement.note or unstructured:
                print(f"       {judgement.note}{unstructured}")

    return report(judgements, threshold)


def report(judgements: list[Judgement], threshold: float) -> int:
    """Print the summary and decide the exit code."""
    passed = sum(1 for judgement in judgements if judgement.passed)
    total = len(judgements)
    rate = passed / total if total else 0.0

    print(f"\n{passed}/{total} passed ({rate:.0%})")

    by_level: dict[str, list[Judgement]] = {}
    for judgement in judgements:
        by_level.setdefault(judgement.scenario.level, []).append(judgement)
    for level, group in sorted(by_level.items()):
        good = sum(1 for judgement in group if judgement.passed)
        print(f"  {level:9} {good}/{len(group)}")

    verdicts: dict[str, int] = {}
    for judgement in judgements:
        if not judgement.passed:
            verdicts[judgement.verdict] = verdicts.get(judgement.verdict, 0) + 1
    if verdicts:
        print(
            "  failures: "
            + ", ".join(f"{name} {count}" for name, count in sorted(verdicts.items()))
        )

    unstructured = sum(1 for j in judgements if j.called and not j.structured)
    if unstructured:
        print(
            f"\n  {unstructured}/{total} answers named the tool in prose rather than emitting a\n"
            f"  tool call. That is this model build, not these descriptions: the choice was\n"
            f"  right and the JSON was well formed. Re-run with --require-structured against a\n"
            f"  model with native tool support to hold it to that too.",
        )

    if rate < threshold:
        print(f"\nbelow the {threshold:.0%} threshold")
        return 1
    return 0


def main() -> int:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help="Ollama endpoint")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model to test")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="fail below this pass rate",
    )
    parser.add_argument("--only", help="run one scenario id, or one level")
    parser.add_argument(
        "--require-structured",
        action="store_true",
        help="count a prose answer as a failure even when the tool choice is right",
    )
    arguments = parser.parse_args()
    return asyncio.run(
        run(
            arguments.host,
            arguments.model,
            arguments.threshold,
            arguments.only,
            require_structured=arguments.require_structured,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
