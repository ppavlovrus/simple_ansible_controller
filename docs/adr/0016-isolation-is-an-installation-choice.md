# ADR-0016: Isolation is an installation choice, and a run cannot opt out of it

## Status

Accepted (2026-09-13). Extends [ADR-0008](0008-execution-environments.md), which
decided the feature and left open how it is switched on.

## Context

ADR-0008 says a task may name a container image and the run happens inside it.
That settles what the feature is and deliberately says nothing about who turns it
on, what launches the container, or what happens to the sandbox the service
already runs in. The code was never written, so those questions stayed open.

They decide whether the feature protects anything at all. The reason to want it
is the plainest weakness of this design: whoever holds the API key can run a
playbook with `hosts: localhost` and execute code on the controller host
(ADR-0004, and the README says so in as many words). An isolation mode that the
caller can decline is not an answer to that -- it is a setting that looks like
one.

Two more things shape the answer. Rootless podman needs user namespaces and the
setuid mapping helpers, both of which the packaged systemd unit currently
forbids; and running a container through docker means putting the service user
in the `docker` group, which is root on the controller and removes exactly what
was being bought.

## Decision

**The operator enables isolation; a run chooses an image, never the mode.** The
switch lives with the rest of the configuration, in the environment file the
package already ships. When it is on, every run is isolated -- a run that names
no image gets the configured default. `execution_environment` on a task selects
among images; it cannot be set to "none".

**Rootless podman is the supported runtime.** Docker can be named, and the
documentation says what it costs: membership of the `docker` group is root on the
controller host, so the isolation it provides is bounded by trust it has already
given away.

**The strict unit stays the default.** Enabling isolation installs a systemd
drop-in that relaxes precisely what rootless podman needs; an installation that
does not enable it keeps the hardening it has today. The `/etc/subuid` and
`/etc/subgid` entries for the service user are the package's job, and are what
makes this an installation choice rather than a runtime one.

**A missing runtime is refused at startup**, exiting 2 with a line naming what to
install, the way a missing `ANSIBLE_MCP_API_KEY` already is (ADR-0012). Finding
out at the first run, from inside a failed playbook, is not acceptable for
something an operator turned on deliberately.

**There are two supported shapes of the package**: without isolation, which needs
no container runtime, and with it, which needs podman. They are documented as two
installation paths once the code exists, and not before. The container image
keeps its own isolation from the host and does not gain this mode, for the reason
ADR-0008 gives: reaching a container runtime from inside a container means the
runtime socket, which is root on the host.

## Consequences

+ The mode protects something, because the caller cannot step out of it. An agent
  holding the token can still run any playbook; it runs it in a sandbox.
+ An installation that does not want a container runtime is unaffected, and keeps
  the systemd hardening it has now.
+ Reproducibility arrives with it: `ansible-core` and the collections come from
  the image rather than from whatever the host happens to have (ADR-0005 covers
  the playbook and the inventory; this covers the rest).
- Two shapes of the package to document, test and support.
- Enabling isolation trades part of the systemd sandbox for the container one.
  That trade is defensible but it is a trade, and it has to be measured on a
  native Linux host rather than argued about -- macOS hides exactly this class of
  difference.
- `localhost` starts meaning "inside the container". A playbook that legitimately
  writes something on the controller changes behaviour, and a playbook needing a
  collection the image does not carry fails in a new way.
- The image remains the operator's responsibility, pulled beforehand. Nothing
  here builds, stores or fetches images (ADR-0008).

## Alternatives considered

- **Per-run opt-in only**, which is what ADR-0008's wording implies on its own.
  Rejected: a caller that can leave the argument out can leave the sandbox, and
  the feature then protects against accidents rather than against the thing it
  exists for.
- **Per-run opt-out, restricted to some callers.** Rejected: telling callers
  apart is identity, and this service has none by design (ADR-0003, ADR-0012).
- **Isolation always on.** Rejected: it makes a container runtime a hard
  dependency and contradicts ADR-0003, which is the reason this project is
  deployable in one command.
- **Docker as the supported runtime.** Rejected as the default: the group
  membership it requires is the privilege the mode is trying to avoid handing
  out. It stays available for operators who have already made that choice.
- **Relaxing the base unit for everybody.** Rejected: it would weaken every
  installation, including the majority that will never enable the mode, in
  exchange for a protection they do not get.
- **A debconf prompt at install time.** Rejected: nothing else in this project is
  configured interactively, and the environment file is the one place an operator
  edits (ADR-0009's spirit). What genuinely belongs to installation -- subuid
  ranges and the unit drop-in -- is postinst work, not a question.
