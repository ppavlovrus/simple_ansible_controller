# ADR-0008: Run in a given container image, but do not manage images

## Status

Accepted (2026-09-12)

## Context

Two gaps in the design share one answer. Reproducibility is incomplete: the
playbook and the inventory are snapshotted (ADR-0005), but the `ansible-core`
version and the installed collections are whatever the host happens to have. And
a dumb executor (ADR-0004) has no guardrails at all, because we deliberately
removed the fake ones.

Running the playbook inside a prepared container image closes both: the
environment becomes part of the run's definition, and execution moves off the
host into a sandbox. `ansible-runner` supports this natively, so the cost is
wiring parameters through, not building a subsystem.

The temptation is to keep going: an image catalogue, registry credentials, pull
policies, an image build pipeline. That is a large platform's job and would
dissolve the reason this project exists.

## Decision

A task may name a container image, and the run happens inside it, isolated from
the host. That is the entire feature.

The image is the operator's responsibility: it must already be present on the
host. The project does not build images, does not store them, does not talk to
registries and keeps no catalogue.

The mode is off by default, because requiring a container runtime would break the
promise of ADR-0003. It is meant for native installations (package plus systemd).
When the controller itself runs in a container, launching containers requires
access to the runtime socket, which is effectively root on the host and destroys
the isolation being sought, so the mode stays off there.

## Consequences

+ Reproducibility extends to the execution environment.
+ An agent running arbitrary playbooks can be confined to a sandbox, which is the
  only cheap answer to the weakest point of the design.
+ Images are interchangeable with those used by larger platforms, so moving up is
  cheaper.
- A container runtime becomes a prerequisite for anyone enabling it.
- Debugging is harder: paths, keys and artifacts live inside the container, so
  the artifact directory must be mounted deliberately.
- The feature is unavailable exactly where the product is easiest to deploy,
  which is an honest limitation rather than a bug.

## Alternatives considered

- **Full execution-environment management, as in large platforms.** Rejected:
  catalogue, registries and builds are the bulk of that feature, and they are
  what makes those platforms heavy.
- **Always run in a container.** Rejected: it would make a container runtime
  mandatory and contradict ADR-0003.
- **No isolation at all.** Rejected: it leaves the project with no answer to the
  most obvious security objection.
