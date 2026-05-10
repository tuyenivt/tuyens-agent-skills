---
name: agent-handoff-contract
description: Handoff envelope contract for orchestrated multi-agent SDD runs - filesystem bus under .specs/<slug>/handoffs/ for architect / dev / test / review.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, agents, handoff, contract]
user-invocable: false
---

# Agent Handoff Contract

> Composed by `task-spec-orchestrate`; consumed by `fix-loop-controller` and any per-stack agent that participates in an orchestrated run. Not for single-agent skills, ad-hoc runs, or in-conversation handoffs.

## Rules

- The envelope is the **only** durable record of an agent step. If it is not written, the step did not happen.
- Append-only by ordinal. Files are never overwritten or deleted.
- `<NN>-<step>-<agent>.md` filename convention - `ls` produces a readable timeline.
- The filesystem is the bus. No central state, no orchestration database. Downstream agents learn upstream state by reading the directory.
- An agent that cannot finish writes `blocked` or `needs-clarification` and stops. Never silently skip writing.

## Path Convention

`handoffs_dir` resolves via `Use skill: spec-artifact-paths` to `.specs/<slug>/handoffs/`. Filename:

```
<NN>-<step>-<agent>.md
```

`<NN>` is a stable two-digit ordinal in execution order. `<step>` is one of `architect | dev | test | review | fix`. `<agent>` is the producing agent (e.g., `spring-architect`).

Example timeline:

```
01-architect-spring-architect.md
02-dev-spring-tech-lead.md
03-test-java-test-engineer.md
04-review-spring-security-reviewer.md
05-fix-spring-tech-lead.md          # fix loop kicked in after 04 failed
06-test-java-test-engineer.md
```

## Envelope Schema

```markdown
---
step: architect | dev | test | review | fix
ordinal: <NN>                       # required
agent: <agent-name>                 # required
status: complete | blocked | needs-clarification | failed   # required
slug: <feature-slug>                # required
started_at: <YYYY-MM-DD HH:MM:SS>   # required
completed_at: <YYYY-MM-DD HH:MM:SS> # required
inputs: [<paths read>]              # required; empty allowed only if status=blocked before reading
outputs: [<paths written>]          # required; empty allowed only for read-only steps (e.g., clean review)
satisfies: [<task-id | AC-id | NFR>]   # required for dev/test/fix; optional for architect/review
blocking_questions: [...]           # required when status in {blocked, needs-clarification}; empty otherwise
proposed_amendments:                # required; never dropped silently
  spec: []
  plan: []
  tasks: []
next: architect | dev | test | review | fix | done   # required; `done` only on finish/escalate
notes_excerpt: <up to 200 chars>    # required; first line of body for ls-time scan
---

# <Step> - <Agent>

## Summary
<One paragraph: what was done, what was produced, what next agent reads first.>

## Decisions Made
- <decision: rationale>     # omit section if none

## Open Items
- <for next agent or user>  # omit section if none

## Verification
- <local checks: lint pass, tests run, reviewer verdict, ...>   # omit if none
```

## Status Semantics

| Status                | Meaning                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| `complete`            | Step finished. `next` points to the next phase.                                                  |
| `blocked`             | External action required (env, infra, missing dependency). User must act.                        |
| `needs-clarification` | A `blocking_questions` answer is needed before proceeding. User must act.                        |
| `failed`              | Step ran but its own verification rejected the output (e.g., tests ran and failed). Triggers fix loop. |

`failed` is for the fix loop; `blocked` is for the user. They are distinct on purpose.

## Edge Cases

- **Out-of-order ordinals**: highest ordinal is authoritative for current state, but flag the gap - something was deleted or renamed.
- **Duplicate ordinals**: contract violation. Stop and ask the user.
- **`failed` with `next: done`**: invalid combination. Surface as contract violation.
- **Empty `outputs` on `complete`**: legal only for read-only steps; the body must explain why.
- **Frontmatter parse error**: surface to user. Do not attempt repair.
- **Resumed run**: orchestrator reads existing envelopes, continues from the last `complete` step's `next`. A `blocked` or `needs-clarification` envelope blocks resumption.

## Avoid

- Editing or deleting an existing envelope.
- Skipping the envelope when a step "obviously succeeded" - breaks resumability.
- Putting decisions or open items in chat instead of the body.
- Free-form filenames - breaks `ls`-sorted timelines.
- Embedding large diffs in the body - reference paths in `outputs`.
- Treating `notes_excerpt` as optional - it is the only field humans read when scanning many envelopes.
