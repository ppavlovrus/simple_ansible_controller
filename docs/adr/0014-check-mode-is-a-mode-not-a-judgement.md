# ADR-0014: Dry run and syntax check are executor modes, not judgement

## Status

Accepted (2026-09-12)

## Context

ADR-0004 says the controller does not generate, rewrite or judge playbooks, and
that the pattern-matching "safety validation" the prototype had was removed
rather than ported. That decision is what keeps the tool surface small and
honest.

It also left a real gap. An agent about to run a playbook against hosts nobody
has touched has no way to ask what it would do, and no way to find out that a
playbook is malformed except by running it and reading the failure. The eval
harness measured the consequence: asked to "check the syntax without running
it", both local models reached for whichever tool looked closest, because none
fitted.

The question is whether closing that gap contradicts ADR-0004.

## Decision

It does not, because neither addition is an opinion. Ansible already has both
modes; the controller exposes them and interprets nothing.

`run_playbook` takes `check` and `diff`, which are `--check` and `--diff`. A
check run connects to the hosts and reports what would change without changing
it. Both are recorded on the task and reported by `get_task_status`, because a
run that "succeeded" in check mode has applied nothing and a caller must not
have to guess which it was.

`check_playbook` runs `ansible-playbook --syntax-check` on text or on a stored
playbook. It connects to nothing, records no task, and answers `ok` plus
whatever Ansible said. It replaces the claim `save_playbook` used to make about
being the only structural check: that one is a YAML shape check and this one is
Ansible's own parser.

What stays out: any statement about whether a playbook is a good idea, safe, or
well written.

## Consequences

+ The agent can answer "what would this change" before changing anything, which
  is half of what a controller is for when the hosts are real.
+ A malformed playbook is caught by a read-only call instead of by a failed run,
  and the offending line comes back in the output.
+ A finished run states whether it was a dry run, so success cannot be misread.
- Two more tools' worth of description to keep accurate, and the eval baseline
  had to be re-taken.
- A check run is not a guarantee: modules differ in how faithfully they support
  check mode, and a playbook can behave differently when it actually writes.
  The docstring says so rather than implying a dress rehearsal is the
  performance.

## Alternatives considered

- **Leave it out, as ADR-0004 read literally.** Rejected: the gap was measured,
  not hypothetical, and refusing a mode Ansible already has is not restraint but
  an omission.
- **Integrate `ansible-lint`.** Rejected: a second toolchain to install and pin,
  and its findings are opinions about style. That is exactly what ADR-0004
  refuses, and an agent wanting a lint can run one itself.
- **A generic `ansible_args` passthrough.** Rejected: an unbounded surface. Every
  flag would become part of the contract without anyone deciding it should be,
  including flags that change where things run.
- **A separate `dry_run_playbook` tool instead of a flag.** Rejected: it would
  duplicate every argument of `run_playbook`, and the eval shows that
  near-identical sibling tools are where models pick wrong.
