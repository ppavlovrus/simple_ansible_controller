# ADR-0015: REST is shaped by resources, and the method is the statement of intent

## Status

Accepted (2026-09-13)

## Context

ADR-0002 said REST would exist for humans and scripts, as a thin layer over the
same core. MCP was built first and the REST layer was never written, so the
promise sat in the record for a while with nothing behind it.

Writing it now raises questions the earlier record deliberately left open. What
shape does it take: the tool names over POST, or resources? Where do the rules
live, now that two callers need them? What happens to `confirm=true`, which
exists because an agent acting on an ambiguous instruction should have to state
its intent twice (ADR-0007)? And how does a refusal, which MCP delivers as a
sentence, become a status code?

Getting these wrong in the obvious direction produces either a second RPC
interface that no curl user wants, or two copies of every rule that slowly stop
agreeing with each other.

## Decision

**One port, one token.** `/api/v1` is served alongside `/mcp` by the same
process, guarded by the same bearer token, with `/healthz` exempt as before
(ADR-0012). A second port would mean a second thing to expose, secure and
document, for no gain.

**Resources, not tool names.** Runs, playbooks, providers and syntax checks are
things; the methods do the verbs. `POST /api/v1/runs` answers 202 with a
`Location`, because a run is created and then followed. Cancelling is
`POST /runs/{id}/cancel` rather than `DELETE`, because a cancelled run is not
removed: its history, logs and snapshots stay. Storing is `PUT
/playbooks/{name}`, because the name is in the path and saving again replaces
what was there, which is what PUT means.

**Neither surface holds a rule.** Both call `ansible_mcp/operations`, which
decides what is refused, what is capped and what comes back. The tools keep what
is MCP's own -- the descriptions an agent chooses by, the argument shapes it
sends, the confirmation gate -- and the routes keep what is HTTP's.

**The method is the statement of intent, so there is no `confirm`.** ADR-0007's
gate answers a specific failure: an agent turns "tidy this up" into a call, and
a second deliberate step is what stands between an ambiguous instruction and a
deletion. A person typing `curl -X DELETE`, or a script someone wrote on
purpose, has already made that statement. Carrying `confirm=true` over would add
a parameter every caller pastes in without reading, which is worse than not
having one: it teaches that confirmation is noise.

**A small error vocabulary, one body.** 400 for a request that is wrong,
including a body the schema rejects; 404 for something named that is not here;
401 for a missing or wrong token; 500 for a defect in this service. The body is
always `{"error": "<one sentence>"}`, the same shape the token check already
answered with. Bodies refuse unknown fields, because a silently ignored
misspelling is how a run ends up doing something other than what was asked.

**The schema is served; the pages are not.** `/api/v1/openapi.json` describes
the surface. Swagger UI and ReDoc are disabled: they fetch their JavaScript from
a CDN, and this service is meant to run where there may be no route to one. A
blank page is a worse answer than a schema and a README.

**Answers are the operation's own JSON**, not a response model that filters it.
A declared response model would silently drop any field added below it, which is
drift that nobody sees until a caller asks where a field went.

## Consequences

+ The controller is scriptable with curl and readable with jq, with one token
  and one port.
+ A rule cannot differ between the two surfaces, because there is only one copy
  of it. A refusal is worded identically whether it arrives as a tool error or
  as a 400.
+ The schema documents the surface for whoever generates a client.
- The same operation now has two names: `run_playbook` and `POST /api/v1/runs`.
  Documentation has to carry both, and the audit log records the tool name for
  either, so a REST call appears under the MCP name.
- The audit says what was done, not which door it came through, since one token
  means there is nobody to attribute a call to anyway (ADR-0012).
- REST inherits MCP's tolerance of equivalent argument shapes (ADR-0013): a
  playbook may arrive as YAML text or as the parsed list of plays, because the
  coercion lives in the operation. That is more permissive than a REST API
  usually is, and it is the price of one copy of the rules.
- Serving REST means an ASGI application in front of the MCP one, so the MCP
  lifespan is now run by the outer app. That is invisible to an in-process test
  and is covered by starting a real server.

## Alternatives considered

- **Mirror the tool names over POST** (`POST /api/v1/run_playbook` with the tool
  arguments). Rejected: it is RPC over HTTP with none of MCP's advantages, and
  the curl user it exists for gets neither idiomatic HTTP nor a schema worth
  generating a client from. The consistency it buys is the kind a shared
  operations layer already provides.
- **REST calling the core directly, with its own validation.** Rejected: two
  copies of "exactly one of playbook or playbook_name" is one copy too many. The
  first divergence would be silent and would be found by a user.
- **Keeping `confirm=true` on destructive routes.** Rejected, as above: it is a
  second statement of an intent the method already makes, and a parameter every
  script hardcodes stops being a confirmation.
- **DELETE for cancelling a run.** Rejected: it reads as "remove this run", and
  the history is exactly what is kept.
- **A separate port for REST.** Rejected: it doubles what has to be exposed and
  secured, and ADR-0003's one-process deployment is the reason anyone would pick
  this over a platform.
- **Answering 422 for a malformed body**, as FastAPI does by default. Rejected:
  it is a second way of saying "your request was wrong" in a shape nothing else
  on this surface uses.
