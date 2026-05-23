---
name: task-spec-evaluate
description: Score SDD feature vs spec - run tests, map AC/NFR to evidence, aggregate review verdicts to pass/needs-fix/fail; append evaluation.md.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, scoring, test-runner]
  type: workflow
user-invocable: true
---

# Spec - Evaluate

## When to Use

After `task-spec-orchestrate` or `task-spec-implement` produces code, to grade the implementation against `.specs/<slug>/spec.md` and append a dated section to `.specs/<slug>/evaluation.md`. Also used as the fix-loop signal under `task-spec-orchestrate --with-evaluation`. Not for requirements quality (`task-spec-checklist`), cross-artifact consistency (`task-spec-analyze`), or CI integration - this workflow shells out to test runners and is opt-in.

### Inputs

| Argument         | Notes                                                                |
| ---------------- | -------------------------------------------------------------------- |
| `<slug>`         | Required. Abort if `spec.md` missing.                                |
| `--test-command` | Override the detected command (maps to runner's `test_command`).     |
| `--timeout`      | Seconds; default 300, hard cap 1800 (maps to `timeout_seconds`).     |
| `--scope`        | `full` (default) or `tests-only` (skip review aggregation).          |
| `--no-write`     | Print result; do not append to `evaluation.md`.                      |

If no runner is detectable and `--test-command` was not supplied, stop with that recommendation - never score on null test data. If `tasks.md` is missing, continue and add a `notes` line about reduced task-side traceability.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

Capture `spec_path`, `plan_path`, `tasks_path`, `handoffs_dir`, `evaluation_path`. Abort if `spec_path` is absent.

### STEP 4 - Gather Changed Files

If `handoffs_dir` exists, union the `outputs:` list from every envelope where `step` is `dev` or `fix` (schema in `agent-handoff-contract`). Result is `changed_files`. If `handoffs_dir` is empty or missing, set `changed_files = null` (coverage searches repo-wide and notes the wider scope).

### STEP 5 - Run Tests

Use skill: eval-test-runner

Translate `--test-command` to `test_command` and `--timeout` to `timeout_seconds`. Capture `test_run`.

- `status: no-runner-detected` -> stop; recommend `--test-command`.
- `status: error | timeout | fail` -> continue; the scorer will hard-fail with a meaningful report.

### STEP 6 - Map Coverage

Use skill: eval-spec-coverage

Pass `spec_path`, `plan_path`, `tasks_path`, `test_run`, `changed_files`. Capture `spec_coverage`.

### STEP 7 - Collect Review Verdicts

If `--scope tests-only`, set `review_verdicts = null` and skip.

Otherwise, locate the highest-ordinal `step: review` envelope in `handoffs_dir`. Pass it through to the scorer as a one-element list preserving the envelope's `status`, `blockers`, `suggestions`, and `proposed_amendments` fields verbatim - the scorer derives the blocker count. If no review envelope exists, set `review_verdicts = null` (scorer redistributes weight).

### STEP 8 - Score

Use skill: eval-scorer

Pass `test_run`, `spec_coverage`, `review_verdicts`. Capture `score`. The scorer reads `spec_coverage.hard_fail` directly; do not recompute it.

### STEP 9 - Write evaluation.md

Skip if `--no-write`. Otherwise append a new section using the template below. Append-only: never edit prior sections. Compute `Iteration` by counting existing `## Evaluation -` headings in `evaluation.md` and adding 1 (start at 1 if the file does not exist).

### STEP 10 - Final Summary

Print one headline (`Status: <status>, score <N>/100, iteration <K>`), the scorer's `recommendation`, and the path to `evaluation.md`. Then:

- `pass`: stop.
- `needs-fix`: list `blocking_issues[:3]`; recommend `task-spec-orchestrate <slug> --with-evaluation`.
- `fail`: list `hard_fail_triggers`; recommend fixing the structural issue or escalating.

## Output Format

`evaluation.md` section template:

```markdown
## Evaluation - <YYYY-MM-DD HH:MM:SS>

**Status:** pass | needs-fix | fail
**Overall score:** <int>/100
**Iteration:** <K>

### Signals
| Sub-score | Value             | Weight applied        |
| --------- | ----------------- | --------------------- |
| Tests     | <int>             | <from weights_applied.test> |
| Coverage  | <int>             | <from weights_applied.coverage> |
| Review    | <int or "n/a">    | <from weights_applied.review or "redistributed"> |

### Acceptance Criteria
| ID  | Verdict   | Evidence                                          |
| --- | --------- | ------------------------------------------------- |
| AC1 | covered   | test:should_upload_avatar_when_user_authenticated |
| AC3 | uncovered | -                                                 |

### NFRs
| Category | Verdict    | Evidence                  |
| -------- | ---------- | ------------------------- |
| latency  | unverified | (no load test in plan.md) |

### Out-of-Scope Drift
- <none, or `spec_coverage.out_of_scope_drift` entries as `<item> -> <drift_ref>`>

### Hard-Fail Triggers
- <`score.hard_fail_triggers` entries, or "none">

### Blocking Issues
- <`score.blocking_issues` entries, max 10>

### Recommendation
<`score.recommendation`>

### Provenance
- Test command: <test_run.command>
- Test counts: passed=X failed=Y skipped=Z errored=W (duration <N>s)
- Changed files: <count, or "repo-wide">
- Review envelope: <filename, or "n/a">
```

Chat output mirrors this in compressed form.

## Self-Check

- [ ] Step 1: loaded `behavioral-principles` first.
- [ ] Step 2: stack detected; runner has a command to pick.
- [ ] Step 3: paths resolved; `spec.md` confirmed.
- [ ] Step 4: `changed_files` unioned from dev/fix envelopes, or set to `null` with a note.
- [ ] Step 5: tests ran; `no-runner-detected` halted the workflow.
- [ ] Step 6: every AC and every NFR has a verdict.
- [ ] Step 7: review envelope passed through verbatim, or `review_verdicts = null`.
- [ ] Step 8: scorer ran; `hard_fail_triggers` populated when applicable.
- [ ] Step 9: `evaluation.md` appended with correct iteration count (unless `--no-write`).
- [ ] Step 10: final summary printed with status-appropriate next action.

## Avoid

- Scoring when no runner was detected and no override was given.
- Editing or reordering prior `evaluation.md` sections.
- Applying `proposed_amendments` here (they route through clarify/plan/tasks).
- Reporting `pass` while `ac_violated > 0`, `nfr_failed > 0`, or `out_of_scope_drift > 0`.
- Substituting a different runner to coax a passing result.
- Auto-running on a timer or hook.
