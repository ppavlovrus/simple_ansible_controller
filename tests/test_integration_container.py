"""The documented container path: a mounted key, an inventory, a real host.

This is the first thing a real deployment has to get right and the last thing the
rest of the suite touches: everything else either runs on the control node or
reaches SSH from the developer's machine. Here the server itself is in a
container, the key arrives through a mount, and the hosts are other containers.

    ANSIBLE_MCP_API_KEY=$(openssl rand -hex 32) \\
        docker compose --profile controller up -d --wait
    ANSIBLE_MCP_API_KEY=<the same key> poetry run pytest tests/test_integration_container.py

Skipped unless that is up, so the suite stays runnable without Docker. A
documented path that nothing exercises drifts, which is why this is a test and
not a paragraph.
"""

import asyncio
import json
import os
import socket

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

CONTROLLER_URL = os.environ.get("ANSIBLE_MCP_URL", "http://127.0.0.1:8080")
API_KEY = os.environ.get("ANSIBLE_MCP_API_KEY", "")
POLL_ATTEMPTS = 60

PLAYBOOK = """---
- hosts: all
  gather_facts: false
  tasks:
    - name: Write a marker on the remote host
      ansible.builtin.copy:
        content: "reached from the container\\n"
        dest: /tmp/reached
        mode: "0644"

    - name: Read it back
      ansible.builtin.slurp:
        src: /tmp/reached
      register: back

    - name: Report what came back
      ansible.builtin.debug:
        msg: "{{ inventory_hostname }} holds {{ back.content | b64decode | trim }}"
"""

# Deliberately says nothing about keys: ssh finds the mounted one at its default
# path for this user. That is the claim being tested.
INVENTORY = """[hosts]
ansible_host_1
ansible_host_2

[hosts:vars]
ansible_user=root
ansible_ssh_common_args=-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
"""


def _controller_is_up() -> bool:
    """Whether the containerised controller answers on its port."""
    host, _, port = CONTROLLER_URL.removeprefix("http://").partition(":")
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex((host, int(port or 80))) == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not API_KEY or not _controller_is_up(),
        reason=(
            "the containerised controller is not up; run "
            "`ANSIBLE_MCP_API_KEY=... docker compose --profile controller up -d --wait` "
            "and pass the same key in the environment"
        ),
    ),
]


async def _payload(result) -> dict:
    return json.loads("".join(block.text for block in result.content if block.type == "text"))


async def test_a_playbook_reaches_real_hosts_from_inside_the_container():
    client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {API_KEY}"},
        trust_env=False,
        timeout=120,
    )
    async with (
        client,
        streamable_http_client(f"{CONTROLLER_URL}/mcp", http_client=client) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()

        started = await _payload(
            await session.call_tool("run_playbook", {"playbook": PLAYBOOK, "inventory": INVENTORY}),
        )
        task_id = started["task_id"]

        for _ in range(POLL_ATTEMPTS):
            status = await _payload(
                await session.call_tool("get_task_status", {"task_id": task_id}),
            )
            if status["status"] not in {"pending", "running"}:
                break
            await asyncio.sleep(1)

        logs = await _payload(
            await session.call_tool("get_task_logs", {"task_id": task_id, "tail": 40}),
        )

        assert status["status"] == "success", logs["output"][-1500:]
        for host in ("ansible_host_1", "ansible_host_2"):
            assert f"{host} holds reached from the container" in logs["output"]


async def test_the_containerised_endpoint_still_refuses_a_wrong_key():
    # The mount changes nothing about who may call: worth pinning here too,
    # because this is the deployment shape that is actually exposed.
    client = httpx.AsyncClient(headers={"Authorization": "Bearer wrong"}, trust_env=False)
    async with client:
        response = await client.post(f"{CONTROLLER_URL}/mcp", json={"jsonrpc": "2.0", "id": 1})

    assert response.status_code == 401
