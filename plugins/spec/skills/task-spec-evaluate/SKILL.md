---
name: task-spec-evaluate
description: Score SDD implementation vs spec - runs tests, maps AC/NFR to evidence, aggregates review verdicts into pass/needs-fix/fail; writes evaluation.md.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, scoring, test-runner]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Evaluate

Score the implementation against the spec for one feature. Runs the project's tests, maps every AC and NFR to evidence, aggregates review verdicts, emits a status (`pass` / `needs-fix` / `fail`) plus a 0-100 score. Result is appended to `evaluation.md` (append-only, so iterations are comparable). Opt-in only - it shells out to test runners.

## When to Use

After `task-spec-orchestrate` (or `task-spec-implement`) produces code; or as the fix-loop signal under `task-spec-orchestrate --with-evaluation`. Re-running appends a new dated section. Not for: requirements quality (`task-spec-checklist`), cross-artifact consistency (`task-spec-analyze`), code review, or CI integration.

## Inputs

| Input            | Notes                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `<slug>`         | Required. Aborts if `spec.md` missing.                                                      |
| `--test-command` | Override `eval-test-runner`'s detected command.                                             |
| `--timeout`      | Default 300s, max 1800s.                                                                    |
| `--scope`        | `full` (default) or `tests-only` (skip review aggregation).                                 |
| `--no-write`     | Compute and print without appending to `evaluation.md`.                                     |

If `tasks.md` is missing the workflow runs but adds a `notes` line that task-side traceability is unavailable. If no runner is detectable, stop with the recommendation to pass `--test-command` - never score on null test data.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

### STEP 4 - Gather Changed Files

If `handoffs_dir` exists, union the `outputs:` fields of all `step: dev` and `step: fix` envelopes. Pass as `changed_files` to coverage. If empty/missing, pass `null` (coverage searches repo-wide and notes the broader scope).

### STEP 5 - Run Tests

Use skill: eval-test-runner

Pass through `--test-command` and `--timeout`. Capture `test_run`.

- `status: no-runner-detected` -> stop, surface, recommend `--test-command`.
- `status: error` -> continue; the scorer will hard-fail with a meaningful report rather than silent abort.

### STEP 6 - Map Coverage

Use skill: eval-spec-coverage

Pass `spec_path`, `plan_path`, `tasks_path`, `test_run`, `changed_files`. Capture `spec_coverage`.

### STEP 7 - Collect Review Verdicts (scope == full)

If `--scope tests-only`, set `review_verdicts = null` and skip.

Otherwise: find the latest `step: review` envelope in `handoffs_dir`. Capture `status`, body blocker count, `proposed_amendments`. If no review envelope exists, pass `null` (scorer redistributes weight).

### STEP 8 - Score

Use skill: eval-scorer

Pass `test_run`, `spec_coverage`, `review_verdicts`. Capture `score`.

### STEP 9 - Write evaluation.md (unless `--no-write`)

Append-only. Each invocation adds a new section using the template below.

### STEP 10 - Final Summary

One-line headline (`Status: <status>, score <N>/100, iteration <K>`), recommendation, path to `evaluation.md`. Then:
- `pass`: stop.
- `needs-fix`: top 3 blocking issues; recommend `task-spec-orchestrate <slug> --with-evaluation` (the orchestrator picks up the sidecar and loops).
- `fail`: list hard-fail triggers; recommend fixing the structural issue (drift, violated AC) or escalating.

## Output Format

`evaluation.md` section template:

```markdown
## Evaluation - <YYYY-MM-DD HH:MM:SS>

**Status:** pass | needs-fix | fail
**Overall score:** <int>/100
**Iteration:** <count>

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

### NFRs
| Category | Verdict    | Evidence                  |
| -------- | ---------- | ------------------------- |
| latency  | unverified | (no load test in plan.md) |

### Out-of-Scope Drift
- <none, or files/tests touching out-of-scope>

### Hard-Fail Triggers
- <list, or "none">

### Blocking Issues
- <one line per issue, max 10>

### Recommendation
<one sentence from scorer>

### Source Data
- Test command: <command>
- Test counts: passed=X failed=Y skipped=Z errored=W (duration <N>s)
- Changed files considered: <count or "repo-wide">
- Review envelope: <filename or "n/a">
```

Chat output mirrors this in compressed form (~30 lines).

## Self-Check

- [ ] Loaded `behavioral-principles` first
- [ ] Detected stack; runner could pick a command
- [ ] Resolved paths; confirmed `spec.md` exists
- [ ] Gathered `changed_files` (or set to null with note)
- [ ] Ran tests; handled `no-runner-detected` by stopping
- [ ] Produced a verdict for every AC and every NFR
- [ ] Collected review verdicts or set them to null
- [ ] Score includes `hard_fail_triggers`
- [ ] `evaluation.md` appended (unless `--no-write`)
- [ ] No files modified outside `.specs/<slug>/evaluation.md`

## Avoid

- Scoring on coverage alone when no runner is detected.
- Editing prior `evaluation.md` sections.
- Applying `proposed_amendments` here (they require routing through clarify/plan/tasks).
- Reporting `pass` when `ac_violated > 0` or `out_of_scope_drift > 0`.
- Substituting a different runner to coax a passing result.
- Auto-running on a timer or hook (this workflow is opt-in).
