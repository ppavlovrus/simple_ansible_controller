"""Isolation as a configuration: who decides, what is recorded, what is refused.

The run that actually happens in a container is in
tests/test_integration_isolation.py, because it needs a container runtime. What
is here needs none: it pins the decisions ADR-0016 makes, and those are the part
that can be got wrong quietly.
"""

import json

import pytest
from mcp.server.mcpserver.exceptions import MCPServerError

from ansible_mcp.config import Settings
from ansible_mcp.core import Executor, Isolation, SubmitRequest, TaskManager
from ansible_mcp.db import create_schema
from ansible_mcp.server import build_application, ensure_isolation_is_usable

IMAGE = "example.invalid/ee:test"


@pytest.fixture
async def isolated(tmp_path, session_factory):
    """A manager that runs playbooks in a container, without running any."""
    executor = Executor(tmp_path / "tasks", isolation=Isolation(runtime="podman", image=IMAGE))
    return TaskManager(session_factory, executor)


@pytest.fixture
async def on_the_host(tmp_path, session_factory):
    """A manager with isolation off, which is the default."""
    return TaskManager(session_factory, Executor(tmp_path / "tasks"))


def test_credentials_are_mounted_where_ssh_actually_looks(tmp_path, monkeypatch):
    # Learned by running it: ssh does not read HOME to find keys, it asks the
    # password database for the home of whoever it is running as. With one mount
    # at the home we set, ssh went on reading /root/.ssh, offered nothing, and
    # every isolated run against a real host ended in "Permission denied
    # (publickey)".
    home = tmp_path / "service-home"
    (home / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    executor = Executor(tmp_path / "tasks", isolation=Isolation(runtime="podman", image=IMAGE))
    arguments = executor._containerized(None)

    destinations = [mount.split(":")[1] for mount in arguments["container_volume_mounts"]]
    assert destinations == ["/root/.ssh", "/home/runner/.ssh"]
    assert all(mount.endswith(":ro") for mount in arguments["container_volume_mounts"])
    # And the home the container is given is the one directory it can write to.
    assert arguments["container_options"] == ["-e", "HOME=/runner"]


def test_nothing_is_mounted_when_the_service_has_no_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))

    executor = Executor(tmp_path / "tasks", isolation=Isolation(runtime="podman", image=IMAGE))

    assert executor._containerized(None)["container_volume_mounts"] == []


def test_nothing_is_containerized_when_isolation_is_off(tmp_path):
    assert Executor(tmp_path / "tasks")._containerized(None) == {}


def test_a_run_takes_the_configured_image_when_it_names_none():
    assert Isolation(runtime="podman", image=IMAGE).image_for(None) == IMAGE


def test_a_run_may_name_a_different_image():
    assert Isolation(runtime="podman", image=IMAGE).image_for("other:1") == "other:1"


async def test_the_task_records_where_it_will_run(isolated, local_playbook, local_inventory):
    # Resolved when the row is written, not when the run starts: "where" is part
    # of reproducing a run, like the playbook and the inventory (ADR-0005).
    task_id = await isolated.submit(
        SubmitRequest(playbook=local_playbook, inventory=local_inventory),
    )

    task = await isolated.get(task_id)

    assert task.execution_environment == IMAGE


async def test_a_named_image_is_what_gets_recorded(isolated, local_playbook, local_inventory):
    task_id = await isolated.submit(
        SubmitRequest(
            playbook=local_playbook,
            inventory=local_inventory,
            execution_environment="other:1",
        ),
    )

    assert (await isolated.get(task_id)).execution_environment == "other:1"


async def test_without_isolation_a_run_records_no_environment(
    on_the_host,
    local_playbook,
    local_inventory,
):
    task_id = await on_the_host.submit(
        SubmitRequest(playbook=local_playbook, inventory=local_inventory),
    )
    await on_the_host.wait(task_id, timeout=60)

    assert (await on_the_host.get(task_id)).execution_environment is None


async def test_naming_an_image_cannot_switch_isolation_on(
    on_the_host,
    local_playbook,
    local_inventory,
):
    # The dangerous direction is the other one -- a caller stepping out of the
    # sandbox -- but a caller believing it is inside one when it is not is the
    # same mistake, so this is refused at the tool rather than ignored here.
    task_id = await on_the_host.submit(
        SubmitRequest(
            playbook=local_playbook,
            inventory=local_inventory,
            execution_environment="other:1",
        ),
    )
    await on_the_host.wait(task_id, timeout=60)

    assert (await on_the_host.get(task_id)).execution_environment is None


@pytest.fixture
async def application(tmp_path):
    app = build_application(Settings(data_dir=tmp_path / "state"))
    await create_schema(app.engine)
    yield app
    await app.manager.shutdown()
    await app.engine.dispose()


async def call(app, tool, **arguments):
    try:
        result = await app.server.call_tool(tool, arguments)
    except MCPServerError as error:
        return {"error": str(error)}
    return json.loads("".join(b.text for b in result.content if b.type == "text"))


async def test_asking_for_an_image_where_nothing_isolates_is_refused(
    application,
    local_playbook,
    local_inventory,
):
    payload = await call(
        application,
        "run_playbook",
        playbook=local_playbook,
        inventory=local_inventory,
        execution_environment="other:1",
    )

    assert "runs playbooks on the controller host itself" in payload["error"]
    assert "switched on by the operator" in payload["error"]
    assert (await call(application, "list_tasks"))["returned"] == 0


def test_isolation_without_an_image_is_refused_at_startup():
    with pytest.raises(RuntimeError, match="ANSIBLE_MCP_EXECUTION_IMAGE"):
        ensure_isolation_is_usable(Settings(isolation=True))


def test_isolation_without_its_runtime_is_refused_at_startup(monkeypatch):
    # The operator turned this on to keep playbooks off the host. Finding out at
    # the first run, from inside a failed playbook, is not how they should learn
    # that it never happened.
    monkeypatch.setattr("shutil.which", lambda _name: None)

    with pytest.raises(RuntimeError, match="podman was not found"):
        ensure_isolation_is_usable(Settings(isolation=True, execution_image=IMAGE))


def test_a_blank_image_reads_as_no_image():
    assert Settings(execution_image="   ").execution_image is None


def test_isolation_off_is_not_gated_at_all(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)

    ensure_isolation_is_usable(Settings(isolation=False, execution_image=IMAGE))
