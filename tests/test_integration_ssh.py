"""A playbook run against real hosts over SSH.

Everything else runs against the control node with `connection: local`, which
proves the wiring but never touches SSH, a remote Python, or two hosts at once.
This does, using the containers from docker-compose.yml:

    make keygen && docker compose up -d

Skipped when those are not up, so the suite stays runnable without Docker.
"""

import socket
from pathlib import Path

import pytest

from ansible_mcp.core import Executor, SubmitRequest, TaskManager
from ansible_mcp.db import TaskStatus

HOSTS = ((2222, "ansible_host_1"), (2223, "ansible_host_2"))
KEY = Path(__file__).parent / "fixtures" / "keys" / "id_rsa"

PLAYBOOK = """---
- name: Touch a file on every test host
  hosts: all
  gather_facts: true
  tasks:
    - name: Write a marker
      ansible.builtin.copy:
        content: "{{ marker }}\\n"
        dest: /tmp/ansible-mcp-marker
        mode: "0644"

    - name: Read it back
      ansible.builtin.slurp:
        src: /tmp/ansible-mcp-marker
      register: readback

    - name: Report what came back
      ansible.builtin.debug:
        msg: "{{ inventory_hostname }} holds {{ readback.content | b64decode | trim }}"
"""

FAILING_PLAYBOOK = """---
- name: Fail on a remote host
  hosts: all
  gather_facts: false
  tasks:
    - name: Run something that exits non-zero
      ansible.builtin.command: /bin/false
"""


def _reachable(port: int) -> bool:
    """Whether something is listening on a loopback port."""
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not all(_reachable(port) for port, _ in HOSTS) or not KEY.exists(),
        reason="SSH test hosts are not up; run `make keygen && docker compose up -d`",
    ),
]


@pytest.fixture
def ssh_inventory() -> str:
    """An inventory pointing at the containers, with an absolute key path.

    Absolute because ansible-runner runs from its own private data directory, so
    a relative path in the inventory resolves somewhere unhelpful.
    """
    lines = ["[test_hosts]"]
    lines += [
        f"{name} ansible_host=127.0.0.1 ansible_port={port} ansible_user=root"
        for port, name in HOSTS
    ]
    lines += [
        "",
        "[test_hosts:vars]",
        f"ansible_ssh_private_key_file={KEY.resolve()}",
        "ansible_ssh_common_args=-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
        "ansible_python_interpreter=/usr/bin/python3",
        "",
    ]
    return "\n".join(lines)


@pytest.fixture
def manager(session_factory, tmp_path):
    return TaskManager(session_factory, Executor(tmp_path / "tasks"))


async def test_a_playbook_reaches_both_hosts_over_ssh(manager, ssh_inventory):
    task_id = await manager.submit(
        SubmitRequest(
            playbook=PLAYBOOK,
            inventory=ssh_inventory,
            variables={"marker": "written-by-the-integration-test"},
        ),
    )

    task = await manager.wait(task_id, timeout=300)
    output = await manager.read_output(task_id)

    assert task.status is TaskStatus.SUCCESS, output[-2000:]
    assert task.exit_code == 0
    # Both hosts ran, and the file written on each was read back from it.
    for _port, name in HOSTS:
        assert f"{name} holds written-by-the-integration-test" in output


async def test_a_remote_failure_is_reported_as_failed(manager, ssh_inventory):
    task_id = await manager.submit(
        SubmitRequest(playbook=FAILING_PLAYBOOK, inventory=ssh_inventory),
    )

    task = await manager.wait(task_id, timeout=300)

    assert task.status is TaskStatus.FAILED
    assert task.exit_code not in (0, None)


async def test_cancelling_a_run_on_real_hosts(manager, ssh_inventory):
    slow = """---
- hosts: all
  gather_facts: false
  tasks:
    - name: Sleep on the remote host
      ansible.builtin.command: sleep 60
      changed_when: false
"""
    task_id = await manager.submit(SubmitRequest(playbook=slow, inventory=ssh_inventory))
    import asyncio

    await asyncio.sleep(6)

    assert await manager.cancel(task_id) is True
    task = await manager.wait(task_id, timeout=120)

    assert task.status is TaskStatus.CANCELLED
