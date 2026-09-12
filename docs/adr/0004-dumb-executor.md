# ADR-0004: The controller does not generate playbooks

## Status

Accepted (2026-09-12)

## Context

The prototype generated Ansible playbooks from natural language with an LLM and
validated them against a list of dangerous patterns. That was the original point
of the project.

Two things changed. First, the caller is now itself an agent with a model behind
it, so generating a playbook inside the controller means running a second, weaker
model with less context than the caller has. Second, safety checks based on
pattern matching give the illusion of a guarantee: `rm -rf` is caught, an
equivalent `file:` task with `state: absent` is not.

## Decision

The controller executes; it does not generate, rewrite or judge playbooks. The
LLM integration and the pattern-based safety validation are removed rather than
ported. Guardrails belong in the calling agent and in the playbooks themselves.

## Consequences

+ No model provider, API key or token budget inside a piece of infrastructure.
+ The controller stays predictable: the same input produces the same run.
+ One responsibility, so the tool surface stays small.
- Nothing stops a caller from running a destructive playbook. The honest answers
  are isolation (ADR-0008) and an audit trail, not a pattern blocklist.

## Alternatives considered

- **Keep generation as an optional feature.** Rejected: optional or not, it drags
  in provider credentials, prompt maintenance and a support burden for output
  quality that is not ours to promise.
- **Keep the safety validator without generation.** Rejected: it inspects
  playbook text for known-bad strings, which is trivially bypassed and misleads
  the operator into trusting it.
