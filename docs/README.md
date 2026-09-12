# Documentation

*Русская версия: [docs/ru/README.md](ru/README.md)*

| | |
|---|---|
| [Concept](concept.md) | What the project is for: the problem, the consumers, the trade-offs it accepts |
| [Architecture](architecture.md) | What the code does now, layer by layer |
| [Configuration](configuration.md) | Every setting, and the two that matter |
| [Decision log](adr/INDEX.md) | Why the boundaries are where they are, and what was rejected |
| [Packaging](../packaging/README.md) | Container image and Debian package |
| [Evals](../evals/README.md) | Measuring whether a model can actually drive this |
| [Integration](../integration/README.md) | Connecting a client, and a ready-made skill |
| [Roadmap](ru/roadmap.md) | What is done and what is next *(in Russian)* |

Contributors, human or otherwise, start at [AGENTS.md](../AGENTS.md).

## Reading order

For understanding the project: concept, then the decision log, then
architecture. The concept explains the shape, the decisions explain why the
shape has those edges, and the architecture is what came out.

For changing it: AGENTS.md, then the ADR covering the area you are touching.

## What is not here

The prototype's reference documentation (a REST API, a CLI, an LLM module and a
safety validator) described code that has been removed, so it was deleted rather
than left to mislead. The same applies to the old architecture document: it
described Celery workers and a PostgreSQL schema that no longer exist.

There is no API reference for the tools, on purpose. A tool's docstring is its
contract and is what a client shows an agent; a second copy in Markdown would
drift from it within a week. `poetry run task eval` prints the current list, or
ask a connected client to list the tools.
