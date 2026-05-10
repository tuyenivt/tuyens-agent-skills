---
name: task-spec-orchestrate
description: Run multi-agent SDD pipeline (architect / dev / test / review with fix loop) over a feature; handoff envelopes on filesystem, resumable.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, multi-agent, pipeline]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Orchestrate

Drive a feature from a stable spec to reviewed, tested code by sequencing per-stack agents through architect -> dev -> test -> review, with a bounded fix loop. Every agent step writes an envelope per `agent-handoff-contract`; `fix-loop-controller` reads the directory after each step. The handoff directory is the only durable state - the workflow is fully resumable.

## When to Use

When `spec.md`, `plan.md`, and `tasks.md` exist and the user wants the full multi-agent pipeline (vs. one-task-at-a-time `task-spec-implement`), or when resuming an interrupted run. Not for: single-task execution, features without a spec, PR review, or build debugging.

## Inputs

| Input               | Notes                                                                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `<slug>`            | Required. Reads `.specs/<slug>/{spec,plan,tasks}.md`; writes to `.specs/<slug>/handoffs/`.                                                       |
| `--max-iterations`  | Fix-loop cap. Default 3, hard cap 5 (clamped).                                                                                                   |
| `--skip-review`     | Pipeline ends after `test` succeeds.                                                                                                             |
| `--no-fix-loop`     | Sets cap to 1; first `failed` envelope escalates.                                                                                                |
| `--start-from`      | `architect | dev | test | review`. Aborts if the named step's envelope does not yet exist - never skips ahead past unwritten history.            |
| `--with-evaluation` | After each `review` envelope, run `task-spec-evaluate` and use `score.status` as the **primary** fix-loop signal. Recommended when AC/NFR coverage matters more than reviewer opinion. |

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

List `handoffs_dir`, sort envelopes by ordinal:

- **Empty**: start at ordinal `01`, step `architect`.
- **Non-empty**: invoke `Use skill: fix-loop-controller`. Route on `decision`:
  - `proceed-done` -> STEP 9, exit.
  - `proceed-next` -> next step is `routed_step`; ordinal is `latest+1`.
  - `loop` -> next step is `dev`; include the `feedback` packet in STEP 6's prompt.
  - `pause-for-amendment` -> stop, surface `amendments`. Do not resume until the user routes them through `task-spec-clarify`/`plan`/`tasks` and a new envelope clears the block.
  - `escalate` / `error` -> stop, surface source envelope path.

### STEP 5 - Select Agents

Map `<step, stack>` to an agent under `plugins/<stack>/agents/`:

| Step      | Backend                                                                          | Frontend                                                                  |
| --------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| architect | `<stack>-architect`                                                              | `<stack>-tech-lead` (frontend has no separate architect)                  |
| dev       | `<stack>-tech-lead`                                                              | `<stack>-tech-lead`                                                       |
| test      | `<stack>-test-engineer` (or `java-test-engineer` for JVM)                        | `<stack>-test-engineer`                                                   |
| review    | `<stack>-security-reviewer` if auth/PII; `<stack>-performance-reviewer` if p95 latency NFRs; else `<stack>-reviewer` | `<stack>-reviewer`                                       |

`fullstack`: run two parallel pipelines with prefixes `be-` and `fe-` (e.g., `be-01-architect-spring-architect.md`). Controller is invoked separately per prefix. v1 emits two final summaries; joined review is deferred.

If a required agent does not exist for the detected stack, abort. Do not silently substitute.

### STEP 6 - Invoke Agent

Construct the prompt with:

1. Absolute paths to `spec.md`, `plan.md`, `tasks.md`, and the most recent prior envelope (if any).
2. The fix-loop `feedback` packet, when present.
3. The contract: the agent ends its run by writing `<NN>-<step>-<agent>.md` per `agent-handoff-contract`. The orchestrator does not write envelopes.

Step-specific notes (full responsibilities live in each agent's definition):
- `architect`: notes only, no code edits.
- `dev`: marks `tasks.md` `[~]` before starting, `[x]` on success. Code goes to normal source paths, not under `.specs/`.
- `test`: one test per AC; `failed` if any AC test fails.
- `review`: `failed` on blockers; `complete` if only suggestions/nitpicks.
- `fix`: invoked indirectly via `loop` (routed to `dev` with feedback); the dev agent writes a `step: fix` envelope when its inputs include a feedback packet.

Invoke via the Agent tool (`subagent_type` matches the agent name). Wait.

### STEP 7 - Verify Envelope

After the agent returns, list `handoffs_dir` and confirm the new envelope at the expected ordinal exists. Missing -> abort with contract-violation. Re-read its outputs from the envelope, not chat.

### STEP 7.5 - Evaluation Sidecar (when `--with-evaluation`)

Trigger when the just-written envelope has `step: review` and `status` in `{complete, failed}`.

Use skill: task-spec-evaluate

Capture the emitted `score` block and write it to `<handoffs_dir>/<NN>-review-score.yaml` (sidecar, not an envelope - does not increment the ordinal). The controller reads it next iteration.

If evaluation aborts (e.g., `no-runner-detected`), do NOT halt orchestration. Write a sidecar with `status: error` and `reason: <...>`, surface a warning in the final summary, continue. The controller falls back to envelope status when the sidecar is missing/errored.

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

Summary is derived from envelopes - never persisted.

## Self-Check

- [ ] Loaded `behavioral-principles` first
- [ ] Detected stack + `Stack Type`; agents selected match both
- [ ] Confirmed `spec.md`/`plan.md`/`tasks.md` exist
- [ ] STEP 4 used `fix-loop-controller` (no in-memory state)
- [ ] Every STEP 6 agent invocation was followed by STEP 7 envelope verification
- [ ] Orchestrator wrote no envelopes; edited no spec/plan/tasks
- [ ] Final summary derived strictly from envelope contents
- [ ] On escalation/amendment-pause, user has a clear resume path

## Avoid

- Inferring step success from chat output instead of the envelope.
- Tracking iteration count or current step in workflow memory.
- Calling `fix-loop-controller` more than once per loop iteration (a post-agent call reads pre-agent state and routes wrong).
- Persisting summary content into `.specs/<slug>/` (it is chat output).
- Auto-applying `proposed_amendments` (require human routing through clarify/plan/tasks).
- Continuing a fullstack pipeline when one half escalates (escalate the whole orchestration).
- Lifting the hard cap of 5 fix iterations under any flag.
