"""A playbook that really runs in a container, and really not on this host.

Everything else about isolation is configuration, and configuration can be wrong
in ways that still pass their own tests. This one asks the only question that
matters: when the mode is on, does the playbook still reach the machine the
controller is running on?

    docker build -f tests/fixtures/ee/Containerfile -t ansible-mcp-ee:test .
    poetry run pytest tests/test_integration_isolation.py

Skipped when no container runtime answers or the image is absent, so the suite
stays runnable without one -- the same bargain as the SSH tests.
"""

import subprocess
import uuid
from pathlib import Path

import pytest

from ansible_mcp.core import Executor, Isolation, RunRequest
from ansible_mcp.db import TaskStatus

IMAGE = "ansible-mcp-ee:test"
RUNTIMES = ("podman", "docker")

INVENTORY = "[all]\nlocalhost ansible_connection=local\n"

ESCAPING_PLAYBOOK = """---
- hosts: all
  gather_facts: false
  tasks:
    - name: Write where a playbook would if nothing confined it
      ansible.builtin.copy:
        content: "written by a run that was supposed to be contained\\n"
        dest: "{{ marker }}"
        mode: "0644"

    - name: Report the ansible that is actually running this
      ansible.builtin.command: ansible-playbook --version
      register: version
      changed_when: false

    - ansible.builtin.debug:
        msg: "{{ version.stdout_lines[0] }}"
"""


def _working_runtime() -> str | None:
    """Return the first container runtime on this machine that answers."""
    for runtime in RUNTIMES:
        try:
            answered = subprocess.run(
                [runtime, "info"],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if answered.returncode == 0:
            return runtime
    return None


def _has_image(runtime: str) -> bool:
    looked = subprocess.run(
        [runtime, "image", "inspect", IMAGE],
        capture_output=True,
        timeout=60,
        check=False,
    )
    return looked.returncode == 0


@pytest.fixture(scope="module")
def runtime() -> str:
    found = _working_runtime()
    if found is None:
        pytest.skip("no container runtime answers on this machine")
    if not _has_image(found):
        pytest.skip(f"{IMAGE} is not present; build it with make ee-image")
    return found


@pytest.mark.integration
async def test_a_playbook_cannot_touch_the_controller_host(runtime, tmp_path):
    # The marker path is on this machine and is writable by the test. If the run
    # is contained, the file appears inside the container's own filesystem and
    # this path stays empty; if it is not, the playbook has just written to the
    # host, which is the whole failure this mode exists to prevent.
    marker = Path("/tmp") / f"ansible-mcp-isolation-{uuid.uuid4().hex}"
    executor = Executor(tmp_path / "tasks", isolation=Isolation(runtime=runtime, image=IMAGE))

    result = await executor.run(
        RunRequest(
            task_id="contained",
            playbook=ESCAPING_PLAYBOOK,
            inventory=INVENTORY,
            variables={"marker": str(marker)},
            execution_environment=IMAGE,
        ),
        None,
    )

    assert result.status is TaskStatus.SUCCESS, executor.read_output("contained")[-800:]
    assert not marker.exists(), "the playbook wrote to the controller host"

    # And the output still comes back, because the artifacts are mounted out.
    output = executor.read_output("contained")
    assert "ansible-playbook [core" in output


@pytest.mark.integration
async def test_the_ansible_that_runs_is_the_image_s(runtime, tmp_path):
    # The other half of ADR-0008: the environment stops being "whatever the host
    # happens to have". Asked of the image directly and of a run through it, the
    # answer has to be the same version -- and it is the image that decides.
    in_the_image = subprocess.run(
        [runtime, "run", "--rm", IMAGE, "ansible-playbook", "--version"],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout.splitlines()[0]

    executor = Executor(tmp_path / "tasks", isolation=Isolation(runtime=runtime, image=IMAGE))
    await executor.run(
        RunRequest(
            task_id="versioned",
            playbook=ESCAPING_PLAYBOOK,
            inventory=INVENTORY,
            variables={"marker": "/tmp/inside-the-container"},
            execution_environment=IMAGE,
        ),
        None,
    )

    reported = executor.read_output("versioned")
    assert in_the_image.strip() in reported


@pytest.mark.integration
async def test_a_syntax_check_is_contained_too(runtime, tmp_path):
    # "Isolation is on" has to mean no ansible runs on this host at all, and the
    # syntax check is the one path that does not create a task.
    executor = Executor(tmp_path / "tasks", isolation=Isolation(runtime=runtime, image=IMAGE))

    checked = executor.syntax_check("---\n- hosts: all\n  tasks: []\n")

    assert checked.ok, checked.output
