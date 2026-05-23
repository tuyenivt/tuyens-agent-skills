---
name: agent-handoff-contract
description: Handoff envelope contract for orchestrated SDD runs - filesystem bus under .specs/<slug>/handoffs/ for architect/dev/test/review/fix steps.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, agents, handoff, contract]
user-invocable: false
---

# Agent Handoff Contract

> Composed by `task-spec-orchestrate`; consumed by `fix-loop-controller` and per-stack agents in orchestrated runs. Not for single-agent skills or in-conversation handoffs.

## When to Use

Every agent step in `task-spec-orchestrate` writes exactly one envelope before exiting. Skip only outside orchestration.

## Rules

- The envelope is the **only** durable record of a step. Not written = did not happen.
- Files are append-only by ordinal: never overwrite, never delete, never edit.
- Filename `<NN>-<step>-<agent>.md` so `ls` sorts to a readable timeline.
- The filesystem is the bus. Downstream agents learn upstream state by reading the directory; no central state.
- An agent that cannot finish writes `blocked`, `needs-clarification`, or `failed` and stops. Never silently skip writing.
- Ordinal is assigned by the orchestrator (`task-spec-orchestrate`) and passed to the agent. Agents do not compute it. If unset, the agent reads the directory, picks `max(NN) + 1`, and records that choice in the body's Verification section.
- All timestamps are ISO-8601 UTC with `Z` suffix: `2026-05-23T10:14:22Z`.

## Path Convention

`handoffs_dir` resolves via `Use skill: spec-artifact-paths` to `.specs/<slug>/handoffs/`. Filename:

```
<NN>-<step>-<agent>.md
```

`<NN>` = two-digit ordinal in execution order. `<step>` = one of `architect | dev | test | review | fix`. `<agent>` = producing agent name (e.g., `spring-tech-lead`).

Example timeline:

```
01-architect-spring-architect.md
02-dev-spring-tech-lead.md
03-test-java-test-engineer.md
04-review-spring-security-reviewer.md
05-fix-spring-tech-lead.md          # fix loop after 04 failed
06-test-java-test-engineer.md
```

## Envelope Schema

```markdown
---
step: architect | dev | test | review | fix
ordinal: <NN>
agent: <agent-name>
status: complete | blocked | needs-clarification | failed
slug: <feature-slug>
started_at: <ISO-8601 UTC, e.g., 2026-05-23T10:14:22Z>
completed_at: <ISO-8601 UTC>
inputs: [<paths read>]
outputs: [<paths written>]
satisfies: [<typed-id>]             # e.g., task:T1, ac:1.2, nfr:perf-1
blocking_questions: [<question>]    # required when status in {blocked, needs-clarification}
proposed_amendments:                # omit the key entirely when none
  spec:  [{target: <section>, change: <diff>, reason: <why>}]
  plan:  [...]
  tasks: [...]
next: architect | dev | test | review | fix | done | pause
notes_excerpt: <up to 200 chars; single sentence visible in ls/grep>
---

# <Step> - <Agent>

## Summary
<One paragraph: what was done, what was produced, what the next agent reads first.>

## Decisions Made
- <decision: rationale>     # omit section if none

## Open Items
- <for next agent or user>  # omit section if none

## Verification
- <local checks: lint pass, tests run, reviewer verdict, ordinal source ...>  # omit if none
```

### Field Semantics

| Field                 | Required for            | Notes                                                                 |
| --------------------- | ----------------------- | --------------------------------------------------------------------- |
| `satisfies`           | dev, test, fix          | Typed IDs (`task:`, `ac:`, `nfr:`); architect/review may include      |
| `inputs`              | all                     | Empty only if `status=blocked` before reading                         |
| `outputs`             | all                     | Empty only on read-only steps (e.g., clean review); body explains why |
| `proposed_amendments` | when any are proposed   | Omit the key entirely when none; never empty-stub                     |
| `blocking_questions`  | blocked, needs-clar.    | At least one question; omit on other statuses                         |
| `next`                | all                     | See Status x Next matrix below                                        |
| `notes_excerpt`       | all                     | Single sentence; the only field humans read when scanning             |

### Status x Next

| Status                | Valid `next`                            | Orchestrator behavior         |
| --------------------- | --------------------------------------- | ----------------------------- |
| `complete`            | architect, dev, test, review, fix, done | Proceed to `next`             |
| `failed`              | fix                                     | Enter fix loop                |
| `blocked`             | pause                                   | Halt; surface to user         |
| `needs-clarification` | pause                                   | Halt; surface questions       |

Any other status/next combination is a contract violation - stop and ask the user.

## Edge Cases

- **Out-of-order ordinals**: highest ordinal is authoritative; flag the gap as something was deleted or renamed.
- **Duplicate ordinals**: contract violation. Stop and ask the user.
- **Empty `outputs` on `complete`**: legal only for read-only steps; body must explain why.
- **Frontmatter parse error**: surface to user. Do not attempt repair.
- **Resumed run**: orchestrator finds the highest-ordinal envelope; if it is `complete`, continue from its `next`; if `blocked` / `needs-clarification` / `failed`, resolve before resuming.

## Avoid

- Editing or deleting an existing envelope.
- Skipping the envelope when a step "obviously succeeded" - breaks resumability.
- Putting decisions or open items in chat instead of the body.
- Free-form filenames - breaks `ls`-sorted timelines.
- Embedding large diffs in the body - reference paths in `outputs`.
- Empty-stub `proposed_amendments: {spec: [], plan: [], tasks: []}` - omit the key instead.
- Letting `notes_excerpt` duplicate the Summary opening - it is a scan-time tag, not a preview.
