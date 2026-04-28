---
name: task-spec-orchestrate
description: Run a coordinated multi-agent pipeline (architect -> dev -> test -> review with a fix loop) over an existing SDD feature. Reads `.specs/<slug>/{spec,plan,tasks}.md`, invokes per-stack agents in sequence, writes append-only handoff envelopes under `.specs/<slug>/handoffs/`, and uses `fix-loop-controller` to decide loop / escalate / proceed. Resumable via the handoff directory.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, multi-agent, pipeline]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Orchestrate

Drive a feature from a stable spec to reviewed, tested code by sequencing per-stack agents through architect -> dev -> test -> review, with a bounded fix loop when test or review fails. Every agent step writes an envelope following `agent-handoff-contract`; `fix-loop-controller` reads the envelopes after each step to decide what runs next. The handoff directory is the only durable state - the workflow is fully resumable.

## When to Use

- A feature has `spec.md`, `plan.md`, and `tasks.md` (run `task-spec-specify`/`plan`/`tasks` first if not)
- The user wants the full multi-agent pipeline rather than one-task-at-a-time delegation via `task-spec-implement`
- Resuming a previously interrupted orchestration (re-invoke with the same slug; the workflow reads existing envelopes and continues from the next ordinal)

**Not for:** Single-task execution (use `task-spec-implement` or stack-specific `task-*-new` directly), features without a spec (use `task-feature-implement`), code review of an existing PR (use `task-code-review`), debugging a broken build (use `task-debug`).

## Inputs

| Input               | Required | Notes                                                                                                                                                                                                                                          |
| ------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Feature slug        | Yes      | Workflow reads `.specs/<slug>/{spec,plan,tasks}.md` and writes to `.specs/<slug>/handoffs/`                                                                                                                                                    |
| `--max-iterations`  | No       | Fix-loop cap. Default `3`, hard cap `5` (clamped by `fix-loop-controller`)                                                                                                                                                                     |
| `--skip-review`     | No       | Skip the review step; pipeline ends after `test` succeeds                                                                                                                                                                                      |
| `--no-fix-loop`     | No       | Disable looping; any `failed` envelope routes straight to escalate                                                                                                                                                                             |
| `--start-from`      | No       | One of `architect`, `dev`, `test`, `review` - skip earlier steps if their envelopes already exist                                                                                                                                              |
| `--with-evaluation` | No       | After each `review` envelope, run `task-spec-evaluate` and use its `score.status` as the **primary** fix-loop signal (review verdict becomes secondary). Recommended for any pipeline where AC/NFR coverage matters more than reviewer opinion |

**Insufficient input handling:** If `spec.md` is missing, abort and recommend `task-spec-specify`. If `plan.md` is missing, abort and recommend `task-spec-plan`. If `tasks.md` is missing, abort and recommend `task-spec-tasks`. If `--start-from` names a step whose envelope does not yet exist, abort - the workflow does not skip ahead past unwritten history.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

Capture `Stack Type` (backend / frontend / fullstack) and the detected stack name. STEP 5's agent-selection table consumes both.

### STEP 3 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Resolve `spec_path`, `plan_path`, `tasks_path`, and `handoffs_dir` for the feature slug. Confirm the three artifact files exist; create `handoffs_dir` if missing.

### STEP 4 - Determine Resume Point

List `handoffs_dir`, parse all envelope frontmatter, sort by ordinal.

- **Empty directory:** start at ordinal `01` with the `architect` step.
- **Non-empty:** invoke `Use skill: fix-loop-controller` once with the current iteration cap. Use its `decision` to choose the next step:
  - `proceed-done` -> emit final summary (STEP 9), exit.
  - `proceed-next` -> next step is `routed_step`; next ordinal is `<latest>+1`.
  - `loop` -> next step is `dev`; include the `feedback` packet in STEP 6's prompt.
  - `pause-for-amendment` -> stop and surface `amendments` to the user. Do not resume until the user has accepted/rejected/edited the amendments via `task-spec-clarify` (for spec gaps) or `task-spec-plan`/`task-spec-tasks` (for plan/tasks gaps), and a new envelope clears the amendment block.
  - `escalate` / `error` -> stop and surface to the user with the source envelope path.

If `--start-from` is set and the named step's envelope is missing, abort per Insufficient Input handling.

### STEP 5 - Select Agents per Stack

Map `<step, Stack Type, stack>` to the agent that runs it. Agents already exist under `plugins/<stack>/agents/`.

| Step      | Backend stack agent (examples)                                                                                                                                                                                 | Frontend stack agent (examples)                                                                                                      |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| architect | `spring-architect`, `dotnet-architect`, `python-architect`, `kotlin-architect`, `node-architect`, `go-architect`, `rust-architect`, `laravel-architect`, `rails-architect`                                     | `react-tech-lead`, `vue-tech-lead`, `angular-tech-lead` (frontend stacks have no separate architect; the tech-lead plays both roles) |
| dev       | `<stack>-tech-lead` (e.g., `spring-tech-lead`, `python-tech-lead`)                                                                                                                                             | `<stack>-tech-lead` (e.g., `react-tech-lead`)                                                                                        |
| test      | `<stack>-test-engineer` (e.g., `java-test-engineer`, `python-test-engineer`)                                                                                                                                   | `<stack>-test-engineer` (e.g., `react-test-engineer`)                                                                                |
| review    | `<stack>-security-reviewer` or `<stack>-performance-reviewer` (selected by spec NFR profile - security if auth/PII present; performance if NFR has p95 latency targets; default `<stack>-reviewer` if neither) | `<stack>-reviewer`                                                                                                                   |

If `Stack Type: fullstack`, the orchestrator runs **two parallel pipelines** (one backend, one frontend) sharing the same `spec.md` but with separate handoff ordinals - prefix backend envelopes with `be-` and frontend with `fe-` (e.g., `be-01-architect-spring-architect.md`). Joining at review is deferred; v1 emits two separate final summaries.

If the detected stack has no agent for a given step, abort and surface the gap - do not silently substitute.

### STEP 6 - Invoke the Routed Step's Agent

Construct the agent prompt:

1. **Required reading:** absolute paths to `spec.md`, `plan.md`, `tasks.md`, and the most recent prior envelope (if any).
2. **Step-specific instructions:**
   - `architect`: read spec + plan; produce a brief module/component breakdown that the dev step will follow. Outputs are notes only - no code edits.
   - `dev`: read spec + plan + tasks + (if `loop`) the feedback packet from STEP 4. Implement the next `[ ]` task or address fix-loop feedback. Mark task `[~]` before starting and `[x]` on success in `tasks.md`. Code edits go in normal source paths, NOT under `.specs/`.
   - `test`: read spec acceptance criteria + plan NFR mapping. Generate / update tests (one per AC), run them, capture pass/fail. Status `failed` if any AC-mapped test fails; `complete` only when all run green.
   - `review`: read the diff produced by `dev` + `test`. Apply stack-appropriate review (security / performance / code-review per STEP 5 selection). Status `failed` if blockers; `complete` if only suggestions/nitpicks.
   - `fix`: only invoked indirectly via `loop` decisions, which route to `dev` with feedback. There is no standalone `fix` agent - the dev agent writes a `step: fix` envelope when its inputs include a feedback packet.
3. **Envelope-write instruction:** every agent MUST end its run by writing `<NN>-<step>-<agent>.md` under `handoffs_dir` per `agent-handoff-contract`. The orchestrator does not write envelopes for agents.

Invoke the agent (Agent tool, subagent_type matching the agent name). Wait for completion.

### STEP 7 - Verify Envelope Was Written

After the agent returns, list `handoffs_dir` and confirm a new envelope at the expected ordinal exists. If missing -> abort with a contract-violation error; do not infer success from agent chat output. Re-read the agent's stated outputs in the envelope before continuing.

### STEP 7.5 - Run Evaluation (when `--with-evaluation`)

Trigger conditions: `--with-evaluation` is set AND the envelope just written has `step: review` AND `status` is `complete` or `failed`. Otherwise, skip this step.

Use skill: task-spec-evaluate

Pass the slug. The workflow runs `eval-test-runner` -> `eval-spec-coverage` -> `eval-scorer` and appends a section to `evaluation.md`. Capture the resulting `score` block (the YAML emitted by `eval-scorer`).

Write the score back to the handoff directory as a sidecar file (NOT a numbered envelope) at `<handoffs_dir>/<NN>-review-score.yaml` where `<NN>` matches the ordinal of the review envelope just verified. The sidecar is read by `fix-loop-controller` in the next iteration; it is not itself an envelope and does not increment the ordinal.

If `task-spec-evaluate` aborts (e.g., `no-runner-detected`), do NOT halt orchestration. Surface the gap as a one-line warning in the eventual final summary, write a sidecar with `status: error` and `reason: <abort reason>`, and continue. The fix-loop controller treats a missing/errored sidecar by falling back to the review envelope's `status`.

### STEP 8 - Loop

Return to STEP 4 to determine the next decision. The loop terminates when `fix-loop-controller` emits `proceed-done`, `escalate`, `pause-for-amendment`, or `error`.

### STEP 9 - Final Summary

Once `proceed-done` is reached (or the pipeline halts on escalation):

- Read every envelope in order.
- Emit the Output Format below.
- Do NOT modify any envelope or `tasks.md` from this step.

## Output Format

```markdown
## Orchestration Summary

**Slug:** <feature-slug>
**Stack:** <detected stack> / <Stack Type>
**Pipeline status:** complete | escalated | paused-for-amendment | error
**Iterations used:** <fix-loop count> / <iteration cap>

### Timeline

| Ordinal | Step      | Agent                    | Status   | Outputs (count) |
| ------- | --------- | ------------------------ | -------- | --------------- |
| 01      | architect | spring-architect         | complete | 0 (notes only)  |
| 02      | dev       | spring-tech-lead         | complete | 7               |
| 03      | test      | java-test-engineer       | complete | 4               |
| 04      | review    | spring-security-reviewer | complete | 0               |

### Tasks Completed

- T01 (Foundation) - <task name>
- T02 (Data) - <task name>
- ...

### Surfaced Amendments

<spec / plan / tasks amendments collected from all envelopes' `proposed_amendments`. Empty section omitted.>

### Escalation

<Only when status is `escalated`: the source envelope, blocking questions, and recommended next action. Empty section omitted otherwise.>

### Resume Instructions

<If status != `complete`: how the user resumes - typically "after addressing <X>, re-invoke `/task-spec-orchestrate <slug>`". Empty section omitted on `complete`.>
```

The summary is **derived** from envelopes - never persisted. Re-invoking the workflow regenerates it.

## Rules

- The orchestrator never writes handoff envelopes itself - only agents do. Confirming an envelope exists after each step is non-negotiable.
- The orchestrator never edits `spec.md`, `plan.md`, or `tasks.md`. The dev agent updates `tasks.md` task statuses; spec/plan amendments are surfaced as `proposed_amendments` and routed through `task-spec-clarify` / `task-spec-plan` / `task-spec-tasks`.
- Iteration count is read from disk via `fix-loop-controller`, never tracked in workflow memory - this is what makes the workflow resumable across sessions.
- `--no-fix-loop` does NOT bypass `fix-loop-controller`; it sets the iteration cap to 1, so the first `failed` envelope escalates instead of looping.
- A `pause-for-amendment` decision is sticky: re-invoking the workflow with un-addressed amendments returns the same decision. The user must act before the pipeline resumes.
- Fullstack pipelines run with separate ordinal prefixes (`be-`, `fe-`); the controller is invoked separately for each prefix.

## Self-Check

- [ ] STEP 1 loaded `behavioral-principles` before any other delegation
- [ ] STEP 2 detected stack and `Stack Type`; agent selection in STEP 5 matched both
- [ ] STEP 3 resolved artifact paths and confirmed `spec.md` / `plan.md` / `tasks.md` exist
- [ ] STEP 4 used `fix-loop-controller` to derive the next step from the handoff directory - no in-memory state
- [ ] Every agent invocation in STEP 6 was followed by STEP 7 envelope verification before continuing
- [ ] No envelope was written, modified, or deleted by the orchestrator (only by agents)
- [ ] No edits made to `spec.md`, `plan.md`, or `tasks.md` from this workflow (dev agent updates task statuses; amendments are surfaced not applied)
- [ ] Final summary derived strictly from envelope contents
- [ ] On escalation or amendment-pause, the user has a clear resume path

## Avoid

- Inferring step success from agent chat output instead of the envelope - silent success breaks resumability
- Tracking iteration count, current step, or feedback in workflow memory - the filesystem is the source of truth
- Calling `fix-loop-controller` more than once per loop iteration - it is stateless and idempotent, but a second call after invoking an agent reads pre-agent state and routes wrong
- Writing summary content into `.specs/<slug>/` - the summary is chat output, not a persisted artifact
- Auto-applying `proposed_amendments` - amendments require a human decision and routing through the appropriate `task-spec-*` workflow
- Continuing a fullstack pipeline when one half escalates - escalate the whole orchestration; partial completion is harder to reason about than a clean halt
- Lifting the hard cap of 5 fix iterations under any flag - the cap is a contract safety
