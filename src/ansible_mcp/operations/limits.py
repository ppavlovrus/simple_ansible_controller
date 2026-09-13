"""What an answer is capped at, wherever it is asked for.

Filling the caller's context is a failure mode of its own (ADR-0002), and a
human piping a log into a terminal is no better served by an unbounded answer.
The caps therefore belong to the operation rather than to one surface, so MCP
and REST cannot drift into disagreeing about how much is too much.
"""

from __future__ import annotations

MAX_TASKS_PER_CALL = 100
MAX_PLAYBOOKS_PER_CALL = 100
MAX_LOG_LINES_PER_CALL = 2000
DEFAULT_LOG_LINES = 100
PLAYBOOK_PREVIEW_LINES = 40
INVENTORY_PREVIEW_LINES = 80
MAX_CHECK_OUTPUT_LINES = 200
