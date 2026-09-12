# ADR-0013: Accept equivalent argument shapes, refuse ambiguous ones

## Status

Accepted (2026-09-12)

## Context

`run_playbook` declares `playbook: str`. An agent that has just been handed a
playbook as YAML sends the parsed list of plays instead, because to it those are
the same document. It sends `tags: ""` where a list is declared, meaning "no
tags". It sends the inventory itself where an object holding the inventory
belongs.

Strictly these are schema violations, and the strict answer is a pydantic
validation error. Measured against a local model driving multi-step jobs, that
answer produced no progress at all: the model received a message about
`input_value=[{'hosts': 'all'...}]` and retried the identical call until the
step budget ran out. Three of four chains failed this way.

Two responses were available. Loosen the schemas so anything is accepted and
guessed at, or keep them strict and let the caller fail. Both are wrong for
different reasons: the first makes the tool unpredictable, the second makes it
unusable by the callers it was built for.

## Decision

Equivalent shapes are accepted and normalized in `server/coercion.py`. A list or
mapping where YAML text is declared is serialized back to YAML; `None`, an empty
string and an empty list all mean absence; a mapping sent as JSON or YAML text is
parsed.

Equivalence is the whole test. A list of plays and the YAML text of that list are
the same document, so it is taken. A bare inventory is not an object containing an
inventory, so it is refused — with an example of the object that was expected.

Nothing is inferred about intent. The layer converts between representations of
the same value; it never decides which value the caller meant.

## Consequences

+ A caller that sends the parsed document gets a run instead of a validation
  error it cannot act on.
+ The refusals that remain are about genuinely missing information, and they say
  what shape to send.
+ Chains that failed on shape now complete.
- One more layer between a tool signature and its body, so a signature no longer
  states the whole truth about accepted input. The docstrings say what is taken.
- The declared types are wider (`Any` on the coerced arguments), which mypy can
  no longer check for those parameters.

## Alternatives considered

- **Stay strict.** Rejected: the errors are written by pydantic for developers
  reading a stack trace, not for a caller deciding its next move, and the
  observed result was a retry loop rather than a corrected call.
- **Coerce everything, including the ambiguous cases.** Rejected: accepting a
  bare inventory as `config` would mean guessing which key it belongs under, and
  a wrong guess runs a playbook against the wrong hosts.
- **Rewrite the pydantic errors into friendlier text.** Rejected as the primary
  fix: it addresses the message rather than the mismatch, and the caller would
  still have to reformat a document it already has in a valid form.
- **Ask the caller to fix its formatting via the tool description.** Kept as
  well, not instead: the descriptions now say both shapes are accepted. A
  description that demands a specific representation of an identical value is
  friction without a reason.
