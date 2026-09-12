"""Secrets do not leave the process in output an agent reads."""

import pytest

from ansible_mcp.core import Executor, SubmitRequest, TaskManager, redact, redact_variables
from ansible_mcp.core.redaction import PLACEHOLDER, is_secret_name, secret_values

ECHOING_PLAYBOOK = """---
- name: Echo a secret the careless way
  hosts: all
  gather_facts: false
  tasks:
    - name: Print it
      ansible.builtin.debug:
        msg: "connecting with {{ db_password }} as {{ db_user }}"
"""


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("password", True),
        ("db_password", True),
        ("ansible_become_pass", False),  # 'pass' alone is too short a hint to match
        ("api_key", True),
        ("APIKEY", True),
        ("vault_token", True),
        ("private_key", True),
        ("auth_header", True),
        ("db_user", False),
        ("hosts", False),
        ("port", False),
    ],
)
def test_which_variable_names_hold_secrets(name, expected):
    assert is_secret_name(name) is expected


def test_only_long_enough_string_values_are_collected():
    values = secret_values(
        {
            "db_password": "hunter2",
            "api_key": "abc",  # too short to replace safely
            "token": 12345,  # not a string
            "db_user": "postgres",  # not a secret name
        },
    )

    assert values == ("hunter2",)


def test_longer_secrets_are_replaced_before_shorter_ones():
    secrets = secret_values({"password": "abcdefgh", "token": "abcd"})

    assert redact("abcdefgh and abcd", secrets) == f"{PLACEHOLDER} and {PLACEHOLDER}"


@pytest.mark.parametrize(
    ("text", "must_not_contain"),
    [
        ("password=hunter2", "hunter2"),
        ('token: "abc123def456"', "abc123def456"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9", "eyJhbGciOiJIUzI1NiJ9"),
        ("api_key = 0123456789abcdef", "0123456789abcdef"),
        ("ansible-playbook --vault-password=swordfish site.yml", "swordfish"),
        (
            "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjE\n"
            "-----END OPENSSH PRIVATE KEY-----",
            "b3BlbnNzaC1rZXktdjE",
        ),
    ],
)
def test_secret_shaped_text_is_redacted_without_knowing_the_value(text, must_not_contain):
    redacted = redact(text)

    assert must_not_contain not in redacted
    assert PLACEHOLDER in redacted


def test_ordinary_text_is_left_alone():
    text = "ok: [web1] => changed=false, 3 tasks, took 4.2s"

    assert redact(text) == text


def test_redacting_nothing_is_harmless():
    assert redact("", ("secret",)) == ""


def test_variable_values_are_hidden_but_names_are_kept():
    redacted = redact_variables({"db_password": "hunter2", "env": "staging"})

    assert redacted == {"db_password": PLACEHOLDER, "env": "staging"}


async def test_a_password_echoed_by_a_playbook_does_not_reach_the_caller(
    session_factory,
    tmp_path,
    local_inventory,
):
    manager = TaskManager(session_factory, Executor(tmp_path / "tasks"))
    task_id = await manager.submit(
        SubmitRequest(
            playbook=ECHOING_PLAYBOOK,
            inventory=local_inventory,
            variables={"db_password": "hunter2", "db_user": "postgres"},
        ),
    )
    await manager.wait(task_id, timeout=60)

    output = await manager.read_output(task_id)

    # The playbook printed it and Ansible wrote it to disk; the caller still
    # does not see it.
    assert "hunter2" not in output
    assert PLACEHOLDER in output
    # A non-secret variable is untouched, so the log stays useful.
    assert "postgres" in output


# Found by review: the generic pattern required a bare secret name, so every
# spelling that actually occurs went through untouched.
@pytest.mark.parametrize(
    "text",
    [
        "db_password: hunter2",
        "ansible_password=hunter2",
        '"login_password": "hunter2"',
        "{'vault_token': 'hunter2'}",
        "MYSQL_ROOT_PASSWORD=hunter2",
        "api_token: hunter2",
    ],
)
def test_a_prefixed_secret_name_is_redacted_too(text):
    redacted = redact(text)

    assert "hunter2" not in redacted
    assert PLACEHOLDER in redacted


def test_a_secret_in_ansible_json_output_is_redacted():
    # This is the shape a failing task actually prints.
    output = '"module_args": {"login_password": "hunter2", "login_user": "root"}'

    redacted = redact(output)

    assert "hunter2" not in redacted
    assert "root" in redacted
