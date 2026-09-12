# Architecture Decision Records: index

Decisions live in `docs/adr/`, in [Nygard format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

Before changing the interface shape, the storage model, the safety rules or the
scope of what the controller does, read the relevant ADR. To deviate, add a new
ADR that supersedes the old one. Do not silently edit an accepted decision.

Most of these records exist to defend a boundary. This project is useful because
it is small, and each "no" below is load-bearing.

| #    | Title | Status | Date |
|------|-------|--------|------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted | 2026-09-12 |
| [0002](0002-mcp-first-rest-second.md) | MCP is the primary interface; REST is secondary | Accepted | 2026-09-12 |
| [0003](0003-no-external-infrastructure.md) | No external infrastructure, SQLite and asyncio | Accepted | 2026-09-12 |
| [0004](0004-dumb-executor.md) | The controller does not generate playbooks | Accepted | 2026-09-12 |
| [0005](0005-snapshot-playbook-and-inventory.md) | Snapshot the playbook and the inventory into every task | Accepted | 2026-09-12 |
| [0006](0006-provider-plugins.md) | Providers are thin plugins; credentials never reach the database | Accepted | 2026-09-12 |
| [0007](0007-write-safety-and-auth-gate.md) | Write safety, no automatic retries, and an authentication gate | Accepted | 2026-09-12 |
| [0008](0008-execution-environments.md) | Run in a given container image, but do not manage images | Accepted | 2026-09-12 |
| [0009](0009-toolchain-and-layout.md) | Poetry, src-layout, and one CI gate shared with developers | Accepted | 2026-09-12 |
| [0010](0010-http-restricted-to-loopback-until-auth.md) | HTTP stays on loopback until callers are verified | Superseded by 0012 | 2026-09-12 |
| [0011](0011-provider-file-access-is-confined.md) | A provider reads inventory files only from allowed directories | Accepted | 2026-09-12 |
| [0012](0012-static-bearer-token-for-http.md) | A static bearer token guards the HTTP endpoint | Accepted | 2026-09-12 |

Records 0002 to 0008 state decisions taken in the concept and the roadmap before
any of the target code existed; 0009 describes what the repository already does.
ADR-0007 is now fully realized: the confirm gate ships with the tools and
ADR-0012 verifies callers. ADR-0010 is kept as the record of what the server did
before verification existed.
