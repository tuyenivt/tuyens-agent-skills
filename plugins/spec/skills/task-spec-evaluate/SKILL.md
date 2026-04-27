---
name: task-spec-evaluate
description: Score an SDD feature's implementation against its spec. Runs project tests via `eval-test-runner`, maps acceptance criteria and NFRs to evidence via `eval-spec-coverage`, aggregates with review-agent verdicts via `eval-scorer`, and writes the result to `.specs/<slug>/evaluation.md` (append-only). Opt-in - shells out to run tests; only invoked explicitly or when `task-spec-orchestrate` runs with `--with-evaluation`.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, scoring, test-runner]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Evaluate

Score the produced implementation against the spec for a feature. Runs the project's tests, maps every acceptance criterion and NFR to its evidence, aggregates with review-agent verdicts, and emits a single status (`pass` / `needs-fix` / `fail`) plus a numeric score. Result is appended to `.specs/<slug>/evaluation.md` so the user can compare iterations.

This workflow shells out to run tests (`pytest`, `npm test`, `mvn test`, ...). It is opt-in and only runs when invoked explicitly or via `task-spec-orchestrate --with-evaluation`. Per merging-spec.md §13.5, this is the marketplace's first foray into "the system grades itself" and stays opt-in by design.

## When to Use

- After `task-spec-orchestrate` (or `task-spec-implement`) has produced code and tests for a feature
- When the user wants to know "does this implementation actually satisfy the spec?"
- When orchestration uses evaluation as the fix-loop signal (post-#18 wiring)
- To compare iterations - re-running this workflow appends a new dated section to `evaluation.md`; prior runs are preserved

**Not for:** Reviewing requirements quality (use `task-spec-checklist`), cross-artifact consistency (use `task-spec-analyze`), code review (use `task-code-review`), running tests in CI (this workflow is for ad-hoc evaluation, not pipeline integration).

## Inputs

| Input            | Required | Notes                                                                                            |
| ---------------- | -------- | ------------------------------------------------------------------------------------------------ |
| Feature slug     | Yes      | Workflow reads `.specs/<slug>/{spec,plan,tasks}.md` and (optionally) the handoff directory       |
| `--test-command` | No       | Override `eval-test-runner`'s detected command (e.g., for monorepo workspaces, custom runners)   |
| `--timeout`      | No       | Pass-through to `eval-test-runner` (default 300s, max 1800s)                                     |
| `--scope`        | No       | `full` (default) or `tests-only` - skip review-verdict aggregation when no orchestration was run |
| `--no-write`     | No       | Compute score and emit chat output without appending to `evaluation.md`                          |

**Insufficient input handling:** If `spec.md` is missing, abort and recommend `task-spec-specify`. If `tasks.md` is missing, the workflow CAN run (evaluation does not strictly require tasks), but emit a one-line `notes` entry that traceability via task `Satisfies:` is unavailable. If the project has no detectable test runner, `eval-test-runner` returns `status: no-runner-detected` - the workflow surfaces this and stops; do not proceed to scoring with `null` test data.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

Capture stack and `Stack Type` so `eval-test-runner` knows which test command to use.

### STEP 3 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Resolve `spec_path`, `plan_path`, `tasks_path`, `handoffs_dir`, and `evaluation_path` for the feature slug.

### STEP 4 - Gather Changed Files (if orchestration ran)

If `handoffs_dir` exists and contains envelopes, collect the union of `outputs:` lists from all `step: dev` and `step: fix` envelopes. This becomes `changed_files` passed to `eval-spec-coverage`.

If `handoffs_dir` is empty or missing (the user ran `task-spec-evaluate` standalone after manual implementation), `changed_files` is `null` and coverage will be searched repo-wide with a notes flag.

### STEP 5 - Run Tests

Use skill: eval-test-runner

Pass `--test-command` and `--timeout` through if provided. Capture the structured `test_run` output.

If `test_run.status` is `no-runner-detected` -> stop, surface the gap to the user with the recommendation to provide `--test-command`. Do not score with no test data.

If `test_run.status` is `error` -> continue to scoring, but the score will be forced to `fail` by `eval-scorer`'s hard-fail rule. The user gets a meaningful error report rather than a silent abort.

### STEP 6 - Map Spec Coverage

Use skill: eval-spec-coverage

Pass `spec_path`, `plan_path`, `tasks_path`, `test_run`, `changed_files`. Capture the structured `spec_coverage` output (per-AC verdicts, per-NFR verification, drift report, summary counts).

### STEP 7 - Collect Review Verdicts (when scope is `full`)

If `--scope` is `tests-only`, skip this step (`review_verdicts = null`).

Otherwise: list `handoffs_dir`, find all envelopes with `step: review`. The latest one drives scoring:

- Read its `status`, count blockers from the body, capture `proposed_amendments`.
- Construct the `review_verdicts` object passed to `eval-scorer`.

If no review envelope exists (orchestration never ran review, or `--skip-review` was used), pass `review_verdicts = null`. The scorer redistributes the review weight.

### STEP 8 - Score

Use skill: eval-scorer

Pass `test_run`, `spec_coverage`, `review_verdicts`. Capture the `score` block.

### STEP 9 - Write `evaluation.md` (unless `--no-write`)

Append a new dated section to `evaluation.md`. Existing content is preserved verbatim - this is an append-only audit trail.

```markdown
## Evaluation - <YYYY-MM-DD HH:MM:SS>

**Status:** pass | needs-fix | fail
**Overall score:** <int>/100
**Iteration:** <count of prior evaluations + 1 for this slug>

### Signals

| Sub-score | Value          | Weight                |
| --------- | -------------- | --------------------- |
| Tests     | <int>          | 30                    |
| Coverage  | <int>          | 50                    |
| Review    | <int or "n/a"> | 20 (or redistributed) |

### Acceptance Criteria

| ID  | Verdict   | Evidence                                          |
| --- | --------- | ------------------------------------------------- |
| AC1 | covered   | test:should_upload_avatar_when_user_authenticated |
| AC2 | uncovered | -                                                 |
| ... | ...       | ...                                               |

### NFRs

| Category | Verdict    | Evidence                  |
| -------- | ---------- | ------------------------- |
| latency  | unverified | (no load test in plan.md) |
| security | verified   | test:should_reject_unauth |

### Out-of-Scope Drift

- <none, or list of files/tests touching out-of-scope items>

### Hard-Fail Triggers

- <list, or "none">

### Blocking Issues

- <one line per issue, capped at 10>

### Recommendation

<single sentence from scorer>

### Source Data

- Test command: <command>
- Test counts: passed=X failed=Y skipped=Z errored=W (duration <N>s)
- Changed files considered: <count or "repo-wide">
- Review envelope: <filename or "n/a">
```

If `--no-write`, emit the same content to chat without writing.

### STEP 10 - Emit Final Summary

Print to chat:

- A one-line headline (`Status: <status>, score <N>/100, iteration <K>`)
- The Recommendation line from the scorer
- The path to `evaluation.md` (so the user can read the full report)
- If `pass`: nothing further. The user may ship.
- If `needs-fix`: the top 3 blocking issues and a suggestion to re-invoke `task-spec-orchestrate <slug>` (which will see the score and loop, post-#18).
- If `fail`: the hard-fail triggers and a suggestion to either fix the structural issue (drift, violated AC) or escalate.

## Output Format

The chat output is a brief summary; the durable artifact is `evaluation.md`. Both follow the structure shown in STEP 9. Total chat output should fit within ~30 lines so the user sees the verdict at a glance.

## Rules

- The workflow MUST run all three sub-skills in order - skipping coverage or scoring produces no usable verdict
- `evaluation.md` is append-only. Prior sections are never deleted, edited, or reordered. Each invocation adds a new dated section.
- The workflow does NOT modify `spec.md`, `plan.md`, `tasks.md`, source code, tests, or handoff envelopes. It is read-only against everything except `evaluation.md`.
- The scorer's hard-fail signals are surfaced verbatim - the workflow does not soften the status. A `fail` is reported as `fail` even if the user prefers good news.
- Test running is opt-in by virtue of this workflow being explicitly invoked. The workflow does not auto-run on file save or other triggers; it runs once per invocation.

## Self-Check

- [ ] STEP 1 loaded `behavioral-principles` before any other delegation
- [ ] STEP 2 detected stack; `eval-test-runner` could pick a test command
- [ ] STEP 3 resolved artifact paths and confirmed `spec.md` exists
- [ ] STEP 4 gathered `changed_files` from handoffs (or set to null with note)
- [ ] STEP 5 ran tests; `test_run.status` is captured (and `no-runner-detected` was handled by stopping)
- [ ] STEP 6 produced a verdict for every AC and every NFR in the spec
- [ ] STEP 7 collected review verdicts, or explicitly set them to null
- [ ] STEP 8 produced an aggregate score with hard-fail triggers populated
- [ ] STEP 9 appended a new dated section to `evaluation.md` (unless `--no-write`)
- [ ] No file outside `.specs/<slug>/evaluation.md` was modified

## Avoid

- Skipping STEP 5 when no test runner is detected and "scoring on coverage alone" - the score is meaningless without a test signal
- Editing prior sections of `evaluation.md` - the file is an audit trail; comparing iterations is the whole point
- Treating `proposed_amendments` from review or coverage as TODOs to apply here - amendments require user routing through `task-spec-clarify` / `task-spec-plan` / `task-spec-tasks`
- Auto-running this workflow on a timer or hook - it is opt-in
- Reporting `pass` when `ac_violated > 0` or `out_of_scope_drift > 0` - hard-fail rules override the headline number
- Substituting a different test runner to coax a passing result - the runner is whatever the project specifies; if it cannot run, that is the verdict

## Notes

- This workflow is the natural last step of `task-spec-orchestrate --with-evaluation` (#18 wires it as the loop signal). It is also useful standalone after manual implementation, where `changed_files` is null and the report focuses on test + coverage signals.
- The append-only `evaluation.md` makes iteration progress visible: a feature that goes from `score 62 / needs-fix` to `score 91 / pass` over three iterations has its history right in the file.
- Pairs with `task-spec-analyze` (consistency check, structural) and `task-spec-checklist` (requirements quality, pre-implementation). `task-spec-evaluate` is the post-implementation grade; the other two are pre-implementation gates.
