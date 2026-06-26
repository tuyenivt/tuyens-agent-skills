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

After `task-spec-orchestrate` or `task-spec-implement` produces code, to grade implementation against `.specs/<slug>/spec.md`. Also used as the fix-loop signal under `task-spec-orchestrate --with-evaluation`.

### Inputs

| Argument         | Notes                                                                |
| ---------------- | -------------------------------------------------------------------- |
| `<slug>`         | Required.                                                            |
| `--test-command` | Override the detected command.                                       |
| `--timeout`      | Seconds; default 300, hard cap 1800.                                 |
| `--scope`        | `full` (default) or `tests-only` (skip review aggregation).          |
| `--no-write`     | Print result; do not append to `evaluation.md`.                      |

If no runner is detectable and `--test-command` was not supplied, stop. If `tasks.md` is missing, continue and add a `notes` line about reduced task-side traceability.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

Capture `spec_path`, `plan_path`, `tasks_path`, `handoffs_dir`, `evaluation_path`. Abort if `spec_path` is absent.

### STEP 4 - Gather Changed Files

If `handoffs_dir` exists, union the `outputs:` list from every envelope where `step in {dev, fix} AND status == complete`, in ordinal order. Result is `changed_files`. If `handoffs_dir` is empty or missing, set `changed_files = null` (coverage searches repo-wide).

### STEP 5 - Run Tests

Use skill: eval-test-runner

Translate `--test-command` to `test_command` and `--timeout` to `timeout_seconds`. Capture `test_run`. `status: no-runner-detected` -> stop. Any other status -> continue (scorer hard-fails when appropriate).

### STEP 6 - Map Coverage

Use skill: eval-spec-coverage

Pass `spec_path`, `plan_path`, `tasks_path`, `test_run`, `changed_files`. Capture `spec_coverage`.

### STEP 7 - Collect Review Verdict

Under `--scope tests-only`, set `review_verdicts = null` and skip. Otherwise set `review_verdicts = [latest review envelope]` if present, else `null`. Pass the envelope's `status`, `review.blockers`, `review.suggestions`, `proposed_amendments` verbatim (envelope fields per `agent-handoff-contract`).

### STEP 8 - Score

Use skill: eval-scorer

Pass `test_run`, `spec_coverage`, `review_verdicts`. Capture `score`.

### STEP 9 - Write evaluation.md

Skip if `--no-write`. Otherwise append using the template below. `Iteration` = count of lines matching `^## Evaluation - ` in `evaluation.md` plus 1 (start at 1 if file does not exist).

### STEP 10 - Final Summary

Print one headline (`Status: <status>, score <N>/100, iteration <K>`), the scorer's `recommendation`, and the path. Then:

- `pass`: stop.
- `needs-fix`: list `blocking_issues[:3]`; recommend `task-spec-orchestrate <slug> --with-evaluation`.
- `fail`: list `hard_fail_triggers`; recommend fixing or escalating.

## Output Format

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
| AC2 | covered   | test:should_accept_png_file                       |
| AC3 | uncovered | -                                                 |

### NFRs
| Category | Verdict    | Evidence | Notes                       |
| -------- | ---------- | -------- | --------------------------- |
| latency  | unverified | -        | no load test in plan.md     |

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

## Self-Check

- [ ] STEP 1-3: behavioral-principles, stack-detect, paths loaded; `spec.md` confirmed
- [ ] STEP 4: `changed_files` unioned from complete dev/fix envelopes in ordinal order, or `null` with note
- [ ] STEP 5: tests ran; `no-runner-detected` halted
- [ ] STEP 6: every AC and every NFR has a verdict
- [ ] STEP 7: latest review envelope passed verbatim, or `review_verdicts = null`
- [ ] STEP 8: scorer ran
- [ ] STEP 9: appended with iteration = `^## Evaluation - ` count + 1 (unless `--no-write`)
- [ ] STEP 10: summary printed with status-appropriate next action

## Avoid

- Scoring when no runner was detected and no override was given.
- Editing or reordering prior `evaluation.md` sections.
- Applying `proposed_amendments` here (route through clarify/plan/tasks).
- Substituting a different runner to coax a passing result.
- Auto-running on a timer or hook.
