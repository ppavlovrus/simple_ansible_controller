"""Accepting the shapes an agent actually sends.

A tool signature says `playbook: str`, and an agent that has just been handed a
playbook as YAML sends the parsed structure instead, because to it those are the
same thing. Strictly that is a schema violation, and the strict answer is a
pydantic error the agent cannot act on: it repeats the call unchanged, and the
job never completes. That was measured, not guessed.

So equivalent forms are accepted and normalized here. This is not guessing at
intent: a list of plays and the YAML text of that list are the same document, an
empty string and no tags are the same absence. Anything genuinely ambiguous is
still refused, with a message that says what shape to send.
"""

from __future__ import annotations

from typing import Any

import yaml

from ansible_mcp.server.errors import UsageError


def as_yaml_text(value: Any, field: str) -> str:
    """Return YAML text, whether it arrived as text or as a parsed document.

    Args:
        value: the text of a YAML document, or the document itself.
        field: argument name, used in the refusal.

    Returns:
        The document as text.

    Raises:
        UsageError: if the value is neither text nor a structure.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list | dict):
        return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, default_flow_style=False)
    message = f"{field} should be YAML text (or the parsed document), not {type(value).__name__}"
    raise UsageError(message)


def as_text(value: Any, field: str) -> str:
    """Return plain text, rejecting a structure with an explanation."""
    if isinstance(value, str):
        return value
    if isinstance(value, list | dict):
        return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
    message = f"{field} should be text, not {type(value).__name__}"
    raise UsageError(message)


def as_list(value: Any, field: str) -> list[str]:
    """Return a list of strings, treating absence and emptiness alike.

    ``None``, an empty string and an empty list all mean "none of these", which
    is how an agent filling in a template tends to express it.
    """
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item) for item in value]
    message = f"{field} should be a list of strings, not {type(value).__name__}"
    raise UsageError(message)


def as_mapping(value: Any, field: str) -> dict[str, Any]:
    """Return a mapping, parsing one that arrived as JSON or YAML text.

    Raises:
        UsageError: if the value is not a mapping and does not parse into one.
    """
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = yaml.safe_load(value)
        except yaml.YAMLError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        message = (
            f"{field} should be an object, for example "
            f'{{"inventory": "[all]\\nhost1"}}, not the bare text {value[:40]!r}'
        )
        raise UsageError(message)
    message = f"{field} should be an object, not {type(value).__name__}"
    raise UsageError(message)
