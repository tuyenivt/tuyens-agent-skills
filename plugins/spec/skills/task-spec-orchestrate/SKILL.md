---
name: task-spec-orchestrate
description: Run multi-agent SDD pipeline (architect / dev / test / review with fix loop) over a feature; handoff envelopes on filesystem, resumable.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, multi-agent, pipeline]
  type: workflow
user-invocable: true
---

# Spec - Orchestrate

## When to Use

When `spec.md`, `plan.md`, and `tasks.md` exist and the user wants the full multi-agent pipeline (vs. one-task-at-a-time `task-spec-implement`), or when resuming an interrupted run. Not for: single-task execution, features without a spec, PR review, or build debugging.

## Inputs

| Input               | Notes                                                                                  |
| ------------------- | -------------------------------------------------------------------------------------- |
| `<slug>`            | Required. Reads `.specs/<slug>/{spec,plan,tasks}.md`; writes to `.specs/<slug>/handoffs/`. |
| `--max-iterations`  | Fix-loop cap. Default 3, clamped to `[1, 5]`.                                          |
| `--skip-review`     | Pipeline ends after `test` succeeds.                                                   |
| `--start-from`      | `architect | dev | test | review`. Validated in STEP 4.                               |
| `--with-evaluation` | After each `review` envelope, run `task-spec-evaluate`; the score sidecar drives the fix-loop signal. |

If `spec.md`/`plan.md`/`tasks.md` is missing, abort and recommend the upstream workflow.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

Capture stack name and `Stack Type` (backend / frontend / fullstack).

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

Confirm the three artifacts exist; create `handoffs_dir` if missing.

### STEP 4 - Determine Resume Point

Use skill: fix-loop-controller

Route on the controller's `decision` per its Output Format. Empty `handoffs_dir` skips the call: start at ordinal `01`, step `architect`. If `--start-from` is set and no envelope exists for an earlier step, abort - never skip ahead past unwritten history.

### STEP 5 - Select Agent

Look up `<step>` under `plugins/<stack>/agents/`:

| Step      | Agent name                       |
| --------- | -------------------------------- |
| architect | `<stack>-architect`              |
| dev       | `<stack>-tech-lead`              |
| test      | `<stack>-test-engineer`          |
| review    | `<stack>-reviewer` (default)     |

**Reviewer variant precedence** (first match wins): `security-reviewer` if the spec touches auth, PII, or secrets; else `performance-reviewer` if any NFR sets a p95/throughput target; else `reviewer`.

If the required agent does not exist for the detected stack, abort. Do not silently substitute.

**Fullstack:** abort and recommend two single-stack runs (one per surface). v1 does not orchestrate parallel be/fe pipelines.

### STEP 6 - Invoke Agent

Assemble the prompt with:

1. Absolute paths to `spec.md`, `plan.md`, `tasks.md`, and the most recent prior envelope (if any).
2. The fix-loop `feedback` packet, when present.
3. Pointer: agent ends its run by writing `<NN>-<step>-<agent>.md` per `agent-handoff-contract`. The orchestrator does not write envelopes.

Invoke via the Agent tool (`subagent_type` matches the agent name). Wait.

### STEP 7 - Verify Envelope

List `handoffs_dir`; confirm the new envelope at the expected ordinal exists. Missing -> abort with contract-violation. Re-read outputs from the envelope, not chat.

### STEP 7.5 - Evaluation Sidecar (when `--with-evaluation`)

When the just-written envelope has `step: review` and `status` in `{complete, failed}`, run `Use skill: task-spec-evaluate` and write its `score` block to `<handoffs_dir>/<NN>-review-score.yaml` (same ordinal as the review envelope; sidecar, not an envelope - does not advance ordinal). On evaluation failure, write the same filename with `status: error` and `reason: <...>` so the controller's sidecar-parse path engages and falls back to envelope status.

### STEP 8 - Loop

Return to STEP 4. Loop terminates on `proceed-done`, `escalate`, `pause-for-amendment`, or `error`.

### STEP 9 - Final Summary

Read every envelope in order; emit Output Format below. Do not modify any envelope or `tasks.md`.

## Output Format

```markdown
## Orchestration Summary

**Slug:** <feature-slug>
**Stack:** <detected stack> / <Stack Type>
**Pipeline status:** complete | escalated | paused-for-amendment | error
**Iterations used:** <fix-loop count> / <cap>

### Timeline

| Ordinal | Step      | Agent                    | Status   | Outputs (count) |
| ------- | --------- | ------------------------ | -------- | --------------- |
| 01      | architect | spring-architect         | complete | 0 (notes only)  |
| 02      | dev       | spring-tech-lead         | complete | 7               |

### Tasks Completed
- T01 - <name>
- T02 - <name>

### Surfaced Amendments
<aggregated `proposed_amendments` from envelopes; omit section if empty>

### Escalation
<source envelope, blocking questions, recommended action; only when status == escalated>

### Resume Instructions
<how to resume; only when status != complete>
```

## Self-Check

- [ ] STEP 1 loaded `behavioral-principles`; STEP 2 captured stack + `Stack Type`
- [ ] STEP 3 confirmed `spec.md`/`plan.md`/`tasks.md` exist
- [ ] STEP 4 routed via `fix-loop-controller` (no in-memory iteration state)
- [ ] STEP 5 agent exists for the detected stack; reviewer variant precedence applied
- [ ] Every STEP 6 invocation was followed by STEP 7 envelope verification (and STEP 7.5 when `--with-evaluation`)
- [ ] STEP 9 summary derived strictly from envelope contents; orchestrator wrote no envelopes

## Avoid

- Inferring step success from chat output instead of the envelope.
- Persisting summary content into `.specs/<slug>/` (it is chat output).
- Auto-applying `proposed_amendments` (require human routing through clarify/plan/tasks).
- Silently substituting an agent when the stack-specific one is missing.
