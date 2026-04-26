---
name: agent-handoff-contract
description: Define the structured handoff envelope every agent step writes to `.specs/<slug>/handoffs/<NN>-<step>-<agent>.md` during orchestrated multi-agent runs. Single-source contract so architect -> dev -> test -> review pipelines have a stable, inspectable bus on the filesystem (no central state machine). Read by `task-orchestrate` and `fix-loop-controller`.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, agents, handoff, contract]
user-invocable: false
---

# Agent Handoff Contract

> This atomic is composed by `task-orchestrate` and consumed by `fix-loop-controller` - do not invoke directly. Per-stack agents (architect, tech-lead, test-engineer, reviewer) write envelopes following this contract when they participate in an orchestrated run.

## When to Use

- Inside `task-orchestrate` after each agent step completes, to record what the agent did and what the next agent needs to know
- Inside `fix-loop-controller` to read prior handoffs and decide whether to loop back, escalate, or proceed
- Whenever a stack agent (e.g., `spring-architect`, `react-tech-lead`) participates in a multi-agent pipeline initiated from `task-orchestrate`

**Not for:** Single-agent skills invoked directly by the user, ad-hoc agent runs outside `task-orchestrate`, in-conversation handoffs (those are ephemeral and need no envelope).

## Rules

- The handoff envelope is the **only** durable record of an agent step. If it is not written, the step did not happen.
- Envelope writes are **append-only** by step number - a handoff file is never overwritten or deleted by another step
- Every envelope MUST include all required fields below; missing fields fail the contract
- File names MUST follow the `<NN>-<step>-<agent>.md` convention so `ls` produces a readable timeline
- The filesystem is the bus - no central state machine, no orchestration database. A downstream agent learns about upstream state only by reading the handoff directory
- Envelopes are **markdown with YAML frontmatter** - the frontmatter is machine-parsable, the body is the human-readable summary
- An agent that cannot finish its step writes an envelope with `status: blocked` or `status: needs-clarification` and stops the loop. It MUST NOT silently skip writing.

## Path Convention

Resolved via `Use skill: spec-artifact-paths` - the `handoffs_dir` for a feature is `.specs/<slug>/handoffs/`. File names within that directory:

```
<NN>-<step>-<agent>.md
```

- `<NN>` - two-digit step ordinal in execution order (`01`, `02`, ...). Stable across resumed runs.
- `<step>` - phase name from the orchestration pipeline: `architect`, `dev`, `test`, `review`, `fix`.
- `<agent>` - the agent that produced the envelope: `spring-architect`, `react-tech-lead`, `python-test-engineer`, etc.

Example:

```
.specs/user-profile-avatar-upload/handoffs/
  01-architect-spring-architect.md
  02-dev-spring-tech-lead.md
  03-test-java-test-engineer.md
  04-review-spring-security-reviewer.md
  05-fix-spring-tech-lead.md
  06-test-java-test-engineer.md
```

The `01-architect-...` envelope was written first; subsequent steps build on it. A `05-fix-...` after a failing `04-review-...` indicates the fix loop kicked in.

## Envelope Schema

```markdown
---
step: architect | dev | test | review | fix
ordinal: <NN>
agent: <agent-name>
status: complete | blocked | needs-clarification | failed
slug: <feature-slug>
started_at: <YYYY-MM-DD HH:MM:SS>
completed_at: <YYYY-MM-DD HH:MM:SS>
inputs:
  - <relative path to spec.md, plan.md, tasks.md, or prior handoff>
  - ...
outputs:
  - <relative path to file written or modified>
  - ...
satisfies:
  - <task ID from tasks.md, or AC ID from spec.md, or NFR category>
  - ...
blocking_questions:
  - <question text - empty list when status is complete>
proposed_amendments:
  spec: [] # list of strings: gaps in spec.md surfaced by this agent
  plan: [] # list of strings: gaps in plan.md
  tasks: [] # list of strings: gaps in tasks.md
next: architect | dev | test | review | fix | done
notes_excerpt: <up to 200 chars - first line of the body for quick scan>
---

# <Step Name> - <Agent Name>

## Summary

<One paragraph: what the agent did, what it produced, what the next agent should read first.>

## Decisions Made

- <Decision 1, with one-line rationale>
- <Decision 2, with one-line rationale>
- (Empty section omitted if none)

## Open Items

- <Anything the next agent needs to decide or the user needs to answer>
- (Empty section omitted if none)

## Verification

- <How this step's output was checked locally before handoff: lint pass, tests run, reviewer verdict, ...>
- (Empty section omitted if step had no local verification)
```

### Required vs optional fields

| Field                                        | Required                                                                                        |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `step`, `ordinal`, `agent`, `status`, `slug` | Always required                                                                                 |
| `started_at`, `completed_at`                 | Always required                                                                                 |
| `inputs`, `outputs`                          | Required; empty list allowed only when `status` is `blocked` before the agent could read inputs |
| `satisfies`                                  | Required for `dev`, `test`, `fix` steps; optional for `architect` and `review`                  |
| `blocking_questions`                         | Required when `status` is `needs-clarification` or `blocked`; empty otherwise                   |
| `proposed_amendments`                        | Required (may be empty maps); never silently dropped                                            |
| `next`                                       | Required; `done` only when the pipeline is finished or escalated                                |
| `notes_excerpt`                              | Required; gives `ls`-time scannability without opening every file                               |

## Status Semantics

| Status                | Meaning                                                                                                                           |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `complete`            | Step finished cleanly. `next` points to the next pipeline phase.                                                                  |
| `blocked`             | Step cannot proceed without external action (missing dependency, broken environment, infra issue). Stops the orchestration loop.  |
| `needs-clarification` | Step cannot proceed without an answer to a `blocking_questions` item. The orchestrator surfaces these to the user.                |
| `failed`              | Step ran but produced output that fails its own local verification (e.g., test agent ran tests, tests failed). Triggers fix loop. |

`failed` and `blocked` are different on purpose: `failed` is a signal the fix loop can act on; `blocked` is a signal the user must act on.

## Reading the Handoff Directory

A consuming workflow (`task-orchestrate`, `fix-loop-controller`, or any agent that needs upstream context) reads the directory in order:

1. `ls` the `handoffs_dir`, sort by ordinal, parse frontmatter for each file
2. Build a timeline: `[ordinal -> { step, agent, status, next, satisfies, outputs }]`
3. Determine the current state from the **last** envelope:
   - `last.status == complete && last.next == done` -> pipeline finished
   - `last.status == complete && last.next != done` -> proceed to `last.next`
   - `last.status == failed` -> route to `fix-loop-controller`
   - `last.status == blocked` or `needs-clarification` -> stop, surface to user

Never trust just the last envelope's `next` field without verifying the `status` - a `complete` step might still have surfaced `proposed_amendments` that warrant a detour to `task-spec-clarify` before continuing.

## Output Format

This atomic does not produce chat output. Its "output" is the contract above. Consuming workflows write envelopes following this schema; consuming readers parse them.

## Handling Edge Cases

- **Out-of-order ordinals on disk:** treat the highest ordinal as authoritative for "current state", but flag the gap to the user (something deleted or renamed an envelope - investigate before proceeding).
- **Two envelopes with the same ordinal:** the contract has been violated. Stop and ask the user. Do not pick.
- **Envelope with `status: failed` and `next: done`:** invalid combination. Surface as a contract violation.
- **Empty `outputs` on `complete` step:** legal only for read-only steps (e.g., a review that found no issues and made no edits). The body must explain why outputs is empty.
- **Frontmatter parse error:** surface to the user immediately. Do not attempt to "repair" by re-deriving fields.
- **Resumed run after interruption:** the orchestrator reads existing envelopes, finds the last `complete` one, and continues from `next`. A `blocked` or `needs-clarification` envelope blocks resumption until the user acts.

## Avoid

- Editing or deleting an existing envelope - the contract is append-only by ordinal
- Skipping the envelope write when a step "obviously succeeded" - silent success breaks resumability
- Putting decisions or open items in chat instead of the body - if the next agent cannot read it from the file, it does not exist
- Using free-form file names instead of `<NN>-<step>-<agent>.md` - breaks `ls`-sorted timelines
- Embedding large diffs in the body - reference the file path under `outputs` instead; agents downstream can read the file directly
- Treating `notes_excerpt` as optional - it is the only field a human reads when scanning many envelopes

## Notes

- The file system **is** the orchestration bus. Adding a database, queue, or in-memory store would centralize what is intentionally distributed - any agent can join a run by reading the directory.
- Resumability is a property of the contract, not the orchestrator: any tool that follows this schema can pick up where another tool left off, including the user manually.
- The `proposed_amendments` field is the bridge between orchestrated execution and the SDD pipeline. When an agent surfaces a spec or plan gap, the user can route it through `task-spec-clarify` or `task-spec-plan` without losing the orchestration's place.
