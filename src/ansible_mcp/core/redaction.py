"""Keeping secrets out of what leaves the process.

Ansible prints whatever a task hands it. A playbook that uses a password in a
`debug` message, or fails with the password in the failed command line, puts that
password in the output, and the output is exactly what an agent asks for when a
run goes wrong. `no_log` is the proper fix and belongs in the playbook, but it is
the caller's discipline, not something we can rely on.

So two passes run over anything on its way out. Values this run was given as
secret-looking variables are replaced literally, which is the accurate pass; and
a handful of patterns catch shapes that are secrets regardless of where they came
from.

This is damage control, not a guarantee. A secret that reaches the output in a
form we do not recognize, or split across lines, gets through. The point is that
the common case, where a variable named `db_password` is echoed back, does not
quietly hand the value to whoever reads the logs.
"""

from __future__ import annotations

import re
from typing import Any

PLACEHOLDER = "[redacted]"

# Variable names whose values are treated as secrets. Deliberately broad: a
# false positive costs a redacted value in a log, a false negative costs a leak.
SECRET_NAME_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "auth",
)

# Shapes that are secrets whatever they are called.
PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        PLACEHOLDER,
    ),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), rf"\1 {PLACEHOLDER}"),
    (
        re.compile(
            r"(?i)\b(password|passwd|token|secret|api[_-]?key)\b(\s*[:=]\s*)"
            r"(?!\[redacted\])(\"[^\"]+\"|'[^']+'|\S+)",
        ),
        rf"\1\2{PLACEHOLDER}",
    ),
    # ansible-playbook's own way of passing a password on a command line.
    (re.compile(r"(--\w*pass(?:word)?)(=|\s+)(\S+)"), rf"\1\2{PLACEHOLDER}"),
)

MINIMUM_SECRET_LENGTH = 4


def is_secret_name(name: str) -> bool:
    """Whether a variable of this name should have its value treated as secret."""
    lowered = name.lower()
    return any(hint in lowered for hint in SECRET_NAME_HINTS)


def secret_values(variables: dict[str, Any]) -> tuple[str, ...]:
    """Return the values worth hiding from output.

    Very short values are skipped: redacting a two-character string would blank
    out unrelated text everywhere it happens to appear.
    """
    values = []
    for name, value in variables.items():
        if not is_secret_name(name) or not isinstance(value, str):
            continue
        if len(value) >= MINIMUM_SECRET_LENGTH:
            values.append(value)
    # Longest first, so a secret that contains another is replaced whole.
    return tuple(sorted(set(values), key=len, reverse=True))


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Replace known secret values and secret-shaped text with a placeholder.

    Args:
        text: what is about to leave the process.
        secrets: exact values to remove, from :func:`secret_values`.

    Returns:
        The text with secrets replaced.
    """
    if not text:
        return text

    for secret in secrets:
        text = text.replace(secret, PLACEHOLDER)
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_variables(variables: dict[str, Any]) -> dict[str, Any]:
    """Return variables with secret-looking entries replaced.

    Used when a run's variables are shown back to a caller: the names are useful
    for understanding a run, the values are not worth the risk.
    """
    return {
        name: PLACEHOLDER if is_secret_name(name) else value for name, value in variables.items()
    }
