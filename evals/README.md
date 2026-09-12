# evals

Measures whether a model can actually drive this server: does it pick the right
tool from the descriptions we wrote, and does it carry the arguments across.

The tool schemas are read from the real server at run time, so this cannot drift
from what an agent is offered. Nothing is executed: the model says what it would
call and the choice is scored.

## Why a weak local model

A 7B model running locally is free to re-run and unforgiving about vague
descriptions. If it picks correctly, a commercial agent will. And when it picks
wrong, the fault is usually the description rather than the model, which is the
whole reason to measure rather than to assume.

## Two harnesses

| | asks | executes |
|---|---|---|
| `scenario_runner.py` | which tool would you call? | nothing |
| `chain_runner.py` | finish this job | every call, for real |

## Running

Needs an Ollama endpoint. Point it at one with `--host`, or set `OLLAMA_HOST`.

```bash
poetry run python evals/scenario_runner.py --model qwen2.5-coder:7b
poetry run python evals/scenario_runner.py --only sibling      # one level
poetry run python evals/chain_runner.py --model qwen2.5-coder:14b
poetry run python evals/chain_runner.py --only confirm-gate
```

`scenario_runner` exits 1 below the pass-rate threshold, so it can gate a merge.

### What the chain harness is allowed to do

Each chain names the tools it may reach; anything else the model asks for is
blocked and recorded, so a model that decides to delete something cannot. Tools
listed as `bait` are described to the model and always blocked. Each chain runs
against a fresh temporary instance, the playbooks only touch the control node,
and names created along the way start with `eval-` and are removed afterwards.

The model is told about the tools the chain allows and no others, because a real
client sees the tools that are registered. Describing all thirteen and expecting
restraint would measure obedience, not tool choice.

## What the levels mean

| Level | Question |
|---|---|
| `select` | Is the obvious tool chosen at all? |
| `sibling` | Are two neighbouring tools told apart? Most real failures live here. |
| `argument` | Does an argument stated in the prompt reach the call? |
| `negative` | Is a tool correctly *not* called, and is a destructive one avoided? |

Prompts are in Russian and English, because that is how the requests arrive.

## Baseline, after ADR-0014

Both models: **30/33 (91%)**, on 33 scenarios.

| | qwen2.5-coder:7b | qwen2.5-coder:14b |
|---|---|---|
| select | 5/5 | 5/5 |
| sibling | 11/13 | 12/13 |
| argument | 8/8 | 8/8 |
| negative | 6/7 | 5/7 |

The previous baseline was 25/29 (86%) on both. Four scenarios were added with
the dry-run and syntax-check tools, and the improvement is not from the suite
getting easier — see below.

Neither model emits structured tool calls: both answer with correct JSON in the
message body and leave `tool_calls` empty. That is the model build under Ollama,
not our schemas, so it is reported separately and does not count as a failure.
Use `--require-structured` against a model with native tool support to hold it to
that as well.

### What the failures taught us

Three failures in the first run were our fault and were fixed by rewriting
descriptions, not by changing the suite:

- **`plugin_type: "ini"` invented out of thin air.** `add_provider` said "the
  types this installation has" without naming the built-in one, so the model
  guessed from the file extension. The description now names `static`, shows the
  two shapes of its config, and says an unknown type is refused.
- **"Restart it" became `cancel_task`.** Nothing said cancelling is not a
  restart, so the closest-looking tool won. `cancel_task` now says outright that
  there is no restart and that running again means `run_playbook`.
- **A request to check syntax reached for whatever was nearest.** `save_playbook`
  now says it is the only structural check available.

### The rename that the eval paid for

The syntax check shipped as `check_playbook`. On the first re-run, 7b scored
28/33 and got `what-would-change-ru` wrong: asked what a playbook *would change
on the hosts*, it called `check_playbook` instead of `run_playbook(check=true)`.

The descriptions already said which was which. What pulled it wrong was the
name: two tools, one called `check_playbook` and one taking `check=true`, and a
prompt containing "check". Renaming it to `syntax_check_playbook` took 7b to
30/33, with `select` and `argument` both clean. Nothing else changed.

Worth stating plainly: a tool name is part of the description, and two tools
whose names overlap compete no matter how carefully the docstrings distinguish
them.

### Known limits, unfixed on purpose

- **"Останови всё"** still reaches for `cancel_task` in both models, even though
  the description says cancelling acts on one id and there is no cancel-all. The
  verb triggers the tool. Worth revisiting if a `cancel_tasks` bulk tool ever
  exists; not worth contorting the description for.
- **"Save this and then run it"** makes both models call nothing at all. A
  two-step request is a multi-turn problem, which is what a chain harness
  measures, not a selection one.

A suite that always passes measures nothing, so these stay in as failures rather
than being deleted or relaxed.

## Chains, baseline after ADR-0014

`qwen2.5-coder:14b`: **2/5**.

| Chain | Result |
|---|---|
| `save-then-run` | ok, after one refusal it corrected itself |
| `find-and-diagnose` | ok, straight through |
| `provider-then-run` | fails: keeps sending both `inventory` and `provider` |
| `confirm-gate` | fails: never gets a run started, so never cancels one |
| `check-then-run` | fails: checks, then checks again, sending both `playbook` and `playbook_name` |

The new chain fails the same way the other two do, and one refusal was rewritten
because of it. The model was passing `playbook_name` alongside the text, which
means it read the argument as "the name for this playbook" rather than "a
playbook already stored here". The refusal now says exactly that, and points at
`save_playbook` for the thing the model seemed to want.

It did not help: 14b still loops. Recording that honestly, because the fix was
worth making anyway — the message is now true about what the mistake was — and
because a stronger model is the thing likely to benefit, not a reworded refusal
for this one.

### What the chains changed in the server

The first run scored 1/4 and every failure was ours. The model was not confused,
it was being told nothing it could act on:

- **A model repeated `save_playbook` six times** and the playbook was never
  stored. The refusal was a raw PyYAML message pointing at "line 1, column 1" of
  a document the model could not see. Playbooks now have a uniform indent
  stripped before parsing, and a refusal quotes the offending line and names the
  usual cause. The same chain now passes on the second attempt.
- **Arguments were refused for arriving in an equivalent shape.** An agent handed
  a playbook sends the parsed list of plays where text is declared; it sends
  `tags=""` for "no tags". Those are the same document and the same absence, so
  they are now accepted and normalized (`server/coercion.py`). A bare inventory
  where an object belongs is still refused, with an example of the object.
- **"Exactly one of" refusals did not say which argument to drop.** They do now.

### Known limits

Both remaining failures are the model rather than the descriptions: the refusals
name the argument to remove, and a 14B model still does not act on them within
the step budget. Worth re-running when a stronger local model is available; not
worth loosening the contract for. Accepting both `inventory` and `provider` with
a precedence rule would mean a run could quietly use a different inventory than
the caller believed, which is a worse failure than a refusal.
