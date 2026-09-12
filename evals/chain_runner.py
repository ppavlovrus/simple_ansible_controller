"""Can a model finish a job that takes several calls, with the calls really running?

The selection harness asks what a model would do. This one lets it do it: every
call it makes is executed against a throwaway instance, the result goes back to
the model, and the scenario is scored on where the instance ended up rather than
on which tools were named.

    poetry run python evals/chain_runner.py --model qwen2.5-coder:14b

Safety model. Each scenario lists the tools it may reach and nothing else is
executed; tools listed as bait are offered and always blocked, so a model that
reaches for one fails the scenario instead of doing it. The instance is a fresh
temporary directory per run and the playbooks only touch the control node, so
there is nothing outside to damage. Names created along the way start with
"eval-" and are removed afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver.exceptions import MCPServerError

from ansible_mcp.config import Settings
from ansible_mcp.core import SubmitRequest
from ansible_mcp.db import TaskStatus, create_schema
from ansible_mcp.server import build_application
from scenario_runner import extract_call

CHAINS = Path(__file__).parent / "chains.yaml"
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11435")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
REQUEST_TIMEOUT = 300.0
EVAL_PREFIX = "eval-"

FAILING_PLAYBOOK = """---
- hosts: all
  gather_facts: false
  tasks:
    - name: Fail on purpose
      ansible.builtin.fail:
        msg: "the disk is not mounted"
"""
LOCAL_INVENTORY = "[all]\ntesthost ansible_connection=local\n"

SYSTEM_PROMPT = """\
You control an Ansible server through tools. Work one step at a time: answer with
a single JSON object {"name": "<tool>", "arguments": {...}} and nothing else. You
will be given the result, then you decide the next step. When the job is done,
answer in plain words without any JSON.
"""


@dataclass
class Chain:
    """A multi-step job and how to tell whether it was finished."""

    id: str
    language: str
    task: str
    allow: list[str]
    require: list[str] = field(default_factory=list)
    bait: list[str] = field(default_factory=list)
    expect: dict[str, Any] = field(default_factory=dict)
    max_steps: int = 6


@dataclass
class Outcome:
    """What happened when a chain was run."""

    chain: Chain
    steps: list[str]
    problems: list[str]
    refusals: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Whether the chain was completed without violations."""
        return not self.problems


def load_chains(path: Path = CHAINS) -> list[Chain]:
    """Read the chain file."""
    return [Chain(**entry) for entry in yaml.safe_load(path.read_text())]


def contains_in_order(steps: list[str], required: list[str]) -> bool:
    """Whether ``required`` appears in ``steps`` in order, gaps allowed."""
    remaining = list(required)
    for step in steps:
        if remaining and step == remaining[0]:
            remaining.pop(0)
    return not remaining


async def _observed_state(application: Any) -> dict[str, Any]:
    """Return the facts a scenario can assert about."""
    tasks = await application.manager.list(limit=50)
    playbooks = await application.playbooks.list()
    providers = await application.providers.list()
    return {
        "tasks_succeeded": sum(1 for task in tasks if task.status is TaskStatus.SUCCESS),
        "tasks_cancelled": sum(1 for task in tasks if task.status is TaskStatus.CANCELLED),
        "playbooks": {playbook.name for playbook in playbooks},
        "providers": {provider.name for provider in providers},
    }


def _check_expectations(expect: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Compare the instance's final state against what the scenario wanted."""
    problems = []
    for key, wanted in expect.items():
        if key == "playbook_stored" and wanted not in state["playbooks"]:
            problems.append(f"playbook {wanted!r} was not stored")
        elif key == "provider_configured" and wanted not in state["providers"]:
            problems.append(f"provider {wanted!r} was not configured")
        elif key in {"tasks_succeeded", "tasks_cancelled"} and state[key] != wanted:
            problems.append(f"{key}: wanted {wanted}, ended with {state[key]}")
    return problems


async def _call(application: Any, tool: str, arguments: dict[str, Any]) -> str:
    """Execute one tool and return what the model should see."""
    try:
        result = await application.server.call_tool(tool, arguments)
    except MCPServerError as error:
        return json.dumps({"error": str(error)})
    return "".join(block.text for block in result.content if block.type == "text")


async def _prepare(application: Any, chain: Chain) -> None:
    """Set up whatever a scenario needs to exist before the model starts."""
    if chain.id == "find-and-diagnose":
        task_id = await application.manager.submit(
            SubmitRequest(playbook=FAILING_PLAYBOOK, inventory=LOCAL_INVENTORY),
        )
        await application.manager.wait(task_id, timeout=120)


async def _cleanup(application: Any) -> None:
    """Stop anything still running and remove what the model created."""
    await application.manager.shutdown()
    for playbook in await application.playbooks.list():
        if playbook.name.startswith(EVAL_PREFIX):
            await application.playbooks.delete(playbook.name)
    for provider in await application.providers.list():
        if provider.name.startswith(EVAL_PREFIX):
            await application.providers.delete(provider.name)


async def _step(
    client: httpx.AsyncClient,
    host: str,
    model: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Ask the model for its next move."""
    response = await client.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return dict(response.json().get("message") or {})


async def run_chain(
    client: httpx.AsyncClient,
    host: str,
    model: str,
    chain: Chain,
    tool_help: str,
) -> Outcome:
    """Run one chain end to end against a fresh instance."""
    directory = Path(tempfile.mkdtemp(prefix="ansible-mcp-chain-"))
    application = build_application(Settings(data_dir=directory))
    await create_schema(application.engine)
    steps: list[str] = []
    problems: list[str] = []
    refusals: list[str] = []

    try:
        await _prepare(application, chain)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + tool_help},
            {"role": "user", "content": chain.task},
        ]

        for _ in range(chain.max_steps):
            message = await _step(client, host, model, messages)
            called, arguments, _structured = extract_call(message)
            if called is None:
                break

            steps.append(called)
            if called in chain.bait:
                problems.append(f"called {called}, which this scenario blocks outright")
                break
            if called not in chain.allow:
                problems.append(f"called {called}, which is not allowed here")
                break

            observed = await _call(application, called, arguments)
            if '"error"' in observed:
                # A model that keeps repeating a call is usually being told
                # nothing useful about why it failed, which is worth seeing.
                refusals.append(f"{called}: {observed[:180]}")
            messages.append({"role": "assistant", "content": message.get("content") or ""})
            messages.append(
                {"role": "user", "content": f"Result of {called}:\n{observed[:2000]}"},
            )

        # Give a launched run a moment to reach a terminal state before judging.
        for task in await application.manager.list(limit=10):
            if not task.status.is_terminal:
                await application.manager.wait(task.id, timeout=120)

        if not contains_in_order(steps, chain.require):
            problems.append(
                f"expected {' then '.join(chain.require)}, got {' then '.join(steps) or 'nothing'}"
            )
        problems.extend(_check_expectations(chain.expect, await _observed_state(application)))
    finally:
        await _cleanup(application)
        await application.engine.dispose()
        shutil.rmtree(directory, ignore_errors=True)

    return Outcome(chain, steps, problems, refusals)


async def tool_help(offered: set[str] | None = None) -> str:
    """Describe the tools in the prompt, since these models ignore the tools field.

    Only the tools a scenario offers are described. A real client sees the tools
    that are registered, not a longer list it is expected to avoid, so listing
    everything would test obedience rather than tool choice.
    """
    application = build_application(Settings(data_dir=Path(tempfile.mkdtemp())))
    tools = await application.server.list_tools()
    await application.engine.dispose()
    lines = ["", "Available tools:"]
    for tool in tools:
        if offered is not None and tool.name not in offered:
            continue
        summary = (tool.description or "").strip().splitlines()[0]
        arguments = ", ".join((tool.input_schema.get("properties") or {}).keys())
        lines.append(f"- {tool.name}({arguments}): {summary}")
    return "\n".join(lines)


async def run(host: str, model: str, only: str | None) -> int:
    """Run every chain and print the report."""
    chains = [chain for chain in load_chains() if only is None or chain.id == only]
    print(f"model {model}, {len(chains)} chains, executed for real\n")

    outcomes = []
    async with httpx.AsyncClient(trust_env=False) as client:
        for chain in chains:
            help_text = await tool_help(set(chain.allow) | set(chain.bait))
            try:
                outcome = await run_chain(client, host, model, chain, help_text)
            except httpx.HTTPError as error:
                print(f"  {chain.id}: cannot reach {host}: {error}")
                return 2
            outcomes.append(outcome)
            mark = "ok  " if outcome.passed else "FAIL"
            trace = " -> ".join(outcome.steps) or "no calls"
            print(f"  {mark} {chain.id} ({chain.language}): {trace}")
            for problem in outcome.problems:
                print(f"       {problem}")
            for refusal in outcome.refusals[:3]:
                print(f"       refused: {refusal}")

    passed = sum(1 for outcome in outcomes if outcome.passed)
    print(f"\n{passed}/{len(outcomes)} chains completed")
    return 0 if passed == len(outcomes) else 1


def main() -> int:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--only", help="run one chain by id")
    arguments = parser.parse_args()
    return asyncio.run(run(arguments.host, arguments.model, arguments.only))


if __name__ == "__main__":
    raise SystemExit(main())
