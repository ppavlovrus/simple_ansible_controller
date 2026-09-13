"""The REST surface as a person with curl meets it.

Every test goes through the application that is actually served -- token check,
mounted MCP endpoint and all -- rather than the routes alone, because how the
two surfaces sit on one port is exactly what could break.
"""

import asyncio
import json

import httpx
import pytest

from ansible_mcp.api import API_PREFIX
from ansible_mcp.config import Settings
from ansible_mcp.db import create_schema
from ansible_mcp.server import build_application
from ansible_mcp.server.http import build_http_app

TOKEN = "correct-horse-battery-staple"

ECHOING_PLAYBOOK = """---
- name: Echo a secret the careless way
  hosts: all
  gather_facts: false
  tasks:
    - name: Print it
      ansible.builtin.debug:
        msg: "connecting with {{ db_password }} as {{ db_user }}"
"""

# Valid YAML and a list of plays, so the store's own shallow check passes it:
# only Ansible's --syntax-check knows that "tusks" is not a key.
BROKEN_PLAYBOOK = """---
- name: Missing its tasks key entirely
  hosts: all
  tusks:
    - name: Typo
      ansible.builtin.debug: {}
"""

# Not a list of plays at all, which is what the shallow check is for.
NOT_A_PLAYBOOK = "install the thing on the servers, please"


@pytest.fixture
async def served(tmp_path):
    """The whole HTTP application, reachable without a real socket."""
    settings = Settings(
        data_dir=tmp_path / "state",
        transport="streamable-http",
        host="0.0.0.0",
        api_key=TOKEN,
    )
    application = build_application(settings)
    await create_schema(application.engine)
    transport = httpx.ASGITransport(app=build_http_app(application, settings))
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://testserver{API_PREFIX}",
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as client:
        yield application, client, transport
    await application.manager.shutdown()
    await application.engine.dispose()


@pytest.fixture
def client(served):
    _application, client, _transport = served
    return client


async def finished(client, task_id, timeout=60):
    """Poll a run the way a script would, and return its final status."""
    async with asyncio.timeout(timeout):
        while True:
            run = (await client.get(f"/runs/{task_id}")).json()
            if run["status"] in {"success", "failed", "cancelled"}:
                return run
            await asyncio.sleep(0.2)


async def test_a_run_is_created_accepted_and_addressable(client, local_playbook, local_inventory):
    response = await client.post(
        "/runs",
        json={"playbook": local_playbook, "inventory": local_inventory},
    )

    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "pending"
    # A script should not have to build the URL of what it just created.
    assert response.headers["location"] == f"{API_PREFIX}/runs/{created['task_id']}"

    assert (await finished(client, created["task_id"]))["status"] == "success"


async def test_a_run_started_over_rest_is_the_same_run_over_mcp(
    served,
    local_playbook,
    local_inventory,
):
    # The two surfaces are two doors onto one controller. If they were wired to
    # different service objects this would pass over REST and find nothing here.
    application, client, _transport = served
    created = (
        await client.post(
            "/runs",
            json={"playbook": local_playbook, "inventory": local_inventory},
        )
    ).json()

    result = await application.server.call_tool("get_task_status", {"task_id": created["task_id"]})
    seen = json.loads("".join(block.text for block in result.content if block.type == "text"))

    assert seen["task_id"] == created["task_id"]


async def test_check_mode_is_carried_through_and_reported(client, local_playbook, local_inventory):
    created = (
        await client.post(
            "/runs",
            json={"playbook": local_playbook, "inventory": local_inventory, "check": True},
        )
    ).json()

    assert created["check_mode"] is True
    # "succeeded" reads as "applied" unless the answer says otherwise.
    assert (await finished(client, created["task_id"]))["check_mode"] is True


async def test_the_logs_of_a_run_are_readable_and_resumable(
    client,
    local_playbook,
    local_inventory,
):
    created = (
        await client.post(
            "/runs",
            json={"playbook": local_playbook, "inventory": local_inventory},
        )
    ).json()
    await finished(client, created["task_id"])

    first = (await client.get(f"/runs/{created['task_id']}/logs", params={"tail": 5})).json()
    assert first["returned_lines"] > 0
    assert "executor reached testhost" in first["output"]

    nothing_new = (
        await client.get(
            f"/runs/{created['task_id']}/logs",
            params={"after_line": first["next_line"]},
        )
    ).json()
    assert nothing_new["returned_lines"] == 0


async def test_a_secret_does_not_reach_a_curl_caller_either(client, local_inventory):
    # AGENTS.md: a new surface that returns text goes through redaction, and a
    # test proves it. The playbook prints the password itself, without no_log.
    created = (
        await client.post(
            "/runs",
            json={
                "playbook": ECHOING_PLAYBOOK,
                "inventory": local_inventory,
                "variables": {"db_password": "hunter2", "db_user": "postgres"},
            },
        )
    ).json()
    await finished(client, created["task_id"])

    logs = (await client.get(f"/runs/{created['task_id']}/logs", params={"tail": 100})).json()

    assert "hunter2" not in logs["output"]
    assert "postgres" in logs["output"]


async def test_runs_can_be_listed_and_filtered(client, local_playbook, local_inventory):
    created = (
        await client.post(
            "/runs",
            json={"playbook": local_playbook, "inventory": local_inventory},
        )
    ).json()
    await finished(client, created["task_id"])

    listed = (await client.get("/runs", params={"status": "success"})).json()

    assert [run["task_id"] for run in listed["tasks"]] == [created["task_id"]]
    assert listed["returned"] == 1


async def test_a_run_that_is_not_here_is_a_404(client):
    response = await client.get("/runs/nothing-like-it")

    assert response.status_code == 404
    assert response.json() == {"error": "no task with id 'nothing-like-it'"}


async def test_naming_two_sources_is_refused_with_the_same_words_as_mcp(client, local_playbook):
    response = await client.post(
        "/runs",
        json={"playbook": local_playbook, "inventory": "[all]\nhost1", "provider": "lab"},
    )

    assert response.status_code == 400
    assert "both inventory and provider were given" in response.json()["error"]


async def test_a_malformed_playbook_is_refused_before_a_run_exists(client, local_inventory):
    response = await client.post(
        "/runs",
        json={"playbook": NOT_A_PLAYBOOK, "inventory": local_inventory},
    )

    assert response.status_code == 400
    assert (await client.get("/runs")).json()["returned"] == 0


async def test_a_misspelled_field_is_refused_rather_than_ignored(client, local_inventory):
    # Silently dropping an unknown field is how a run ends up doing something
    # other than what was asked: "cheque" would have meant a real run.
    response = await client.post(
        "/runs",
        json={"playbook_name": "whatever", "inventory": local_inventory, "cheque": True},
    )

    assert response.status_code == 400
    assert "cheque" in response.json()["error"]


async def test_the_caps_are_the_operations_own(client):
    assert (await client.get("/runs", params={"limit": 0})).status_code == 400
    assert "capped at 100" in (await client.get("/runs", params={"limit": 101})).json()["error"]


async def test_a_run_can_be_cancelled_and_says_so_when_it_is_too_late(
    client,
    local_playbook,
    local_inventory,
):
    created = (
        await client.post(
            "/runs",
            json={"playbook": local_playbook, "inventory": local_inventory},
        )
    ).json()
    await finished(client, created["task_id"])

    # No confirm to pass: POST .../cancel is the statement of intent (ADR-0015).
    response = await client.post(f"/runs/{created['task_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["cancelled"] is False
    assert response.json()["status"] == "success"


async def test_a_playbook_is_stored_read_and_removed(client, local_playbook):
    saved = await client.put(
        "/playbooks/deploy",
        json={"content": local_playbook, "description": "the usual", "tags": ["lab"]},
    )
    assert saved.status_code == 200
    assert saved.json()["name"] == "deploy"

    read = (await client.get("/playbooks/deploy")).json()
    assert read["description"] == "the usual"
    assert "ansible.builtin.debug" in read["content"]

    assert (await client.get("/playbooks")).json()["returned"] == 1

    assert (await client.delete("/playbooks/deploy")).status_code == 200
    assert (await client.get("/playbooks/deploy")).status_code == 404


async def test_deleting_a_playbook_that_is_not_there_is_a_404(client):
    response = await client.delete("/playbooks/never-existed")

    assert response.status_code == 404
    assert response.json() == {"error": "no playbook stored as 'never-existed'"}


async def test_a_stored_playbook_can_be_run_by_name(client, local_playbook, local_inventory):
    await client.put("/playbooks/deploy", json={"content": local_playbook})

    created = (
        await client.post(
            "/runs",
            json={"playbook_name": "deploy", "inventory": local_inventory},
        )
    ).json()

    assert (await finished(client, created["task_id"]))["playbook_name"] == "deploy"


async def test_a_playbook_can_be_checked_without_being_stored_or_run(client, local_playbook):
    ok = await client.post("/syntax-checks", json={"playbook": local_playbook})
    assert ok.json()["ok"] is True

    broken = await client.post("/syntax-checks", json={"playbook": BROKEN_PLAYBOOK})
    assert broken.json()["ok"] is False
    assert broken.json()["output"]

    # Nothing was run, so nothing was recorded as a run.
    assert (await client.get("/runs")).json()["returned"] == 0


async def test_a_provider_is_configured_resolved_and_removed(client, local_inventory):
    added = await client.put(
        "/providers/lab",
        json={"plugin_type": "static", "config": {"inventory": local_inventory}},
    )
    assert added.status_code == 200
    assert added.json()["usable"] is True

    resolved = (await client.get("/providers/lab/inventory")).json()
    assert "testhost" in resolved["inventory"]

    listed = (await client.get("/providers")).json()
    assert [provider["name"] for provider in listed["configured"]] == ["lab"]
    assert any(plugin["plugin_type"] == "static" for plugin in listed["available_plugin_types"])

    assert (await client.delete("/providers/lab")).status_code == 200
    assert (await client.get("/providers/lab/inventory")).status_code == 400


async def test_a_run_can_take_its_inventory_from_a_provider(
    client,
    local_playbook,
    local_inventory,
):
    await client.put(
        "/providers/lab",
        json={"plugin_type": "static", "config": {"inventory": local_inventory}},
    )

    created = (
        await client.post("/runs", json={"playbook": local_playbook, "provider": "lab"})
    ).json()

    assert (await finished(client, created["task_id"]))["provider_name"] == "lab"


async def test_a_rest_call_is_recorded_under_the_name_the_tool_uses(
    served,
    local_playbook,
    local_inventory,
):
    # The audit log answers "what was done here". That answer must not depend on
    # which door the caller came through, so a REST run is a run_playbook entry
    # linked to the run it created, exactly as the tool call would be.
    application, client, _transport = served
    created = (
        await client.post(
            "/runs",
            json={"playbook": local_playbook, "inventory": local_inventory},
        )
    ).json()

    entries = await application.audit.recent(limit=10)
    started = next(entry for entry in entries if entry.tool == "run_playbook")

    assert started.outcome == "ok"
    assert started.task_id == created["task_id"]


async def test_a_refused_rest_call_is_recorded_as_refused(served):
    application, client, _transport = served

    await client.get("/runs/nothing-like-it")

    entry = next(e for e in await application.audit.recent(limit=10) if e.tool == "get_task_status")
    assert entry.outcome == "refused"


async def test_the_rest_surface_needs_the_token(served):
    _application, _client, transport = served

    # The same application, called the way anyone who found the port would.
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as anonymous:
        response = await anonymous.get(f"{API_PREFIX}/runs")

    assert response.status_code == 401
    assert response.json() == {"error": "a bearer token is required"}


async def test_the_schema_is_served_and_lists_the_routes(client):
    schema = (await client.get("/openapi.json")).json()

    assert f"{API_PREFIX}/runs" in schema["paths"]
    assert f"{API_PREFIX}/runs/{{task_id}}/logs" in schema["paths"]
    assert f"{API_PREFIX}/syntax-checks" in schema["paths"]
