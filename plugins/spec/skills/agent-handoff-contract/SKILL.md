---
name: agent-handoff-contract
description: Handoff envelope contract for orchestrated SDD runs - filesystem bus under .specs/<slug>/handoffs/ for architect/dev/test/review/fix steps.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, agents, handoff, contract]
user-invocable: false
---

# Agent Handoff Contract

> Composed by `task-spec-orchestrate`; consumed by `fix-loop-controller` and per-stack agents in orchestrated runs.

## When to Use

Every agent step in `task-spec-orchestrate` writes exactly one envelope before exiting.

## Rules

- The envelope is the only durable record; the filesystem is the bus. No envelope = step did not happen.
- Files are append-only by ordinal: never overwrite, never delete, never edit.
- Filename `<NN>-<step>-<agent>.md` so `ls` sorts to a readable timeline.
- An agent that cannot finish writes `blocked`, `needs-clarification`, or `failed` and stops.
- Exactly one agent writes per ordinal. The orchestrator serializes step starts and passes the ordinal. The directory-scan fallback (`max(NN) + 1`) applies only when the orchestrator hands off without one; the agent records the choice in Verification.
- When re-executing after `status: failed` in a fix loop, write `step: fix` (not the original step). The original step's name is preserved in the prior envelope's filename. Only `step: fix` envelopes count toward `fix_iterations`.
- All timestamps are ISO-8601 UTC with `Z` suffix.

## Path Convention

`handoffs_dir` resolves via `spec-artifact-paths` to `.specs/<slug>/handoffs/`. Files:

- Envelopes: `<NN>-<step>-<agent>.md`
- Evaluation sidecars (orchestrate only): `<NN>-review-score.yaml` at the same ordinal as the review envelope; does not advance ordinal.

`<NN>` is two digits. `<step>` is one of `architect | dev | test | review | fix`. `<agent>` is the producing agent name (e.g., `java-tech-lead`).

Example timeline:

```
01-architect-spring-architect.md
02-dev-java-tech-lead.md
03-test-java-test-engineer.md          # status: failed
04-fix-java-tech-lead.md               # step: fix after 03 failed
05-test-java-test-engineer.md
06-review-java-performance-engineer.md
06-review-score.yaml                   # evaluation sidecar; same ordinal as 06
```

## Envelope Schema

```markdown
---
step: architect | dev | test | review | fix
ordinal: <NN>
agent: <agent-name>
status: complete | blocked | needs-clarification | failed
slug: <feature-slug>
started_at: <ISO-8601 UTC>
completed_at: <ISO-8601 UTC>
inputs: [<paths read>]
outputs: [<paths written>]                # on `failed`, list partially-written paths
satisfies: [<typed-id>]                   # e.g., task:T5, ac:1.2, nfr:perf-1 (no zero-padding; match spec text)
blocking_questions: [<question>]          # required when status in {blocked, needs-clarification}
review:                                   # review step only; omit on other steps
  blockers:    [<one-line blocking finding>]    # must-fix; drives review_blockers downstream
  suggestions: [<one-line non-blocking finding>]
proposed_amendments:                      # omit the key entirely when none
  spec:  [{target: <section>, change: <diff>, reason: <why>}]
  plan:  [...]
  tasks: [...]
next: architect | dev | test | review | fix | done | pause
notes_excerpt: <up to 200 chars; single sentence>
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

| Field                 | Required for          | Notes                                                                    |
| --------------------- | --------------------- | ------------------------------------------------------------------------ |
| `satisfies`           | dev, test, fix        | Typed IDs (`task:`, `ac:`, `nfr:`); match spec text exactly (no padding) |
| `inputs`              | all                   | Empty only if `status=blocked` before reading                            |
| `outputs`             | all                   | On `failed`, list partial paths. Empty `complete` legal only on read-only steps (body explains) |
| `proposed_amendments` | when any are proposed | Omit the key entirely when none; never empty-stub                        |
| `blocking_questions`  | blocked, needs-clar.  | At least one question; omit on other statuses                            |
| `review`              | review step           | `blockers` are must-fix findings (drive `review_blockers`); `suggestions` are non-blocking. Omit on non-review steps |
| `next`                | all                   | See Status x Next                                                        |
| `notes_excerpt`       | all                   | Scan-time tag; do not duplicate the Summary opening                      |

### Status x Next

| Status                | Valid `next`                            | Orchestrator behavior         |
| --------------------- | --------------------------------------- | ----------------------------- |
| `complete`            | architect, dev, test, review, fix, done | Proceed to `next`             |
| `failed`              | fix                                     | Enter fix loop                |
| `blocked`             | pause                                   | Halt; surface to user         |
| `needs-clarification` | pause                                   | Halt; surface questions       |

Any other combination is a contract violation - stop and ask the user.

## Edge Cases

- **Failed dev -> fix**: `02-dev-...md` with `status: failed, next: fix`. Next envelope is `03-fix-<same-agent>.md` with `step: fix`. A successful fix routes to test via `next: test`.
- **Out-of-order ordinals**: highest ordinal is authoritative; flag the gap.
- **Duplicate ordinals**: contract violation. Stop and ask the user.
- **Frontmatter parse error**: surface to user. Do not attempt repair.
- **Resumed run**: orchestrator finds the highest-ordinal envelope. If `complete`, continue from its `next`. If `blocked`/`needs-clarification`/`failed`, resolve, then a new agent writes a fresh ordinal with the routed step; `inputs` should include the prior envelope path so the resolution trail is auditable.

## Avoid

- Editing or deleting an existing envelope.
- Skipping the envelope when a step "obviously succeeded" - breaks resumability.
- Free-form filenames - breaks `ls`-sorted timelines.
- Embedding large diffs in the body - reference paths in `outputs`.
- Empty-stub `proposed_amendments: {spec: [], plan: [], tasks: []}` - omit the key.
