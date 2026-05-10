---
name: eval-scorer
description: Aggregate test, spec-coverage, and review verdicts into a weighted score plus pass / needs-fix / fail status for SDD evaluation.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, scoring, aggregation]
user-invocable: false
---

# Eval - Scorer

> Composed by `task-spec-evaluate` after `eval-test-runner` and `eval-spec-coverage`. Pure aggregation: no test runs, no coverage derivation. Routing decisions are `fix-loop-controller`'s job.

## Rules

- One integer 0-100 derived from fixed weights (Test 30 / Coverage 50 / Review 20).
- Hard-fail signals override the weighted score - any of `ac_violated > 0`, `out_of_scope_drift > 0`, or `test_run.status in {fail,timeout,error}` blocks `pass` regardless of score.
- Weights and bands are part of the contract; bump a version note when changed.

## Inputs

`test_run` (from `eval-test-runner`), `spec_coverage` (from `eval-spec-coverage`), `review_verdicts` (optional, parsed from `step: review` envelopes in `handoffs_dir`), `thresholds` (optional override - never widens defaults).

## Sub-Scores

```text
# Test (weight 30)
test_score = 100 * passed / max(passed + failed + errored, 1)
# `notes: "no tests collected"` from runner -> test_score = 0 (no evidence of behavior).

# Coverage (weight 50; ACs > NFRs because they encode user-visible behavior)
ac_score       = 100 * (covered_full + 0.7 * covered_by_code_only) / max(ac_total, 1)
nfr_score      = 100 * (nfr_verified + 0.5 * nfr_partially_verified) / max(nfr_total, 1)
coverage_score = 0.7 * ac_score + 0.3 * nfr_score

# Review (weight 20)
no envelope                 -> null (redistribute weight to test=37.5, coverage=62.5)
status=complete, 0 blockers -> 100
complete, only suggestions  -> 90
failed, N blockers          -> max(0, 80 - 15 * N)
blocked / needs-clarification -> null (escalate)

overall_score = round(0.30 * test_score + 0.50 * coverage_score + 0.20 * review_score)
```

## Status Bands

| Status      | Conditions                                                                                                                                   |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `pass`      | `overall_score >= 85` AND no hard-fail triggers AND `test_run.status == pass` AND no review blockers                                         |
| `needs-fix` | Score in `[60, 84]`, OR any hard-fail trigger, OR review has blockers, OR `nfr_failed > 0`                                                   |
| `fail`      | Score < 60, OR a hard-fail trigger persists at iteration cap                                                                                 |

Hard-fail triggers always force at least `needs-fix`; at the iteration cap they force `fail`. This is the only place these promotion rules are encoded.

## Output Format

```yaml
score:
  overall_score: <int 0-100>
  status: pass | needs-fix | fail
  weights_applied: { test: 30, coverage: 50, review: 20 }   # review may be "null - redistributed"
  sub_scores: { test_score, coverage_score, review_score }
  signals:
    ac_total, ac_covered, ac_violated
    nfr_total, nfr_verified, nfr_failed
    drift_count
    test_status: pass | fail | timeout | error | no-runner-detected
    review_blockers: <int or null>
  hard_fail_triggers: []                     # empty when none
  blocking_issues: []                        # one-line summaries, max 10
  recommendation: <one sentence>             # "loop and fix X" / "escalate" / "ship it"
```

## Edge Cases

- **`ac_total == 0`** (spec has no ACs): undefined. Status `fail`, `hard_fail_triggers: ["no acceptance criteria in spec.md"]`, recommend `task-spec-clarify`.
- **`nfr_total == 0`**: `nfr_score = 100` (vacuously satisfied). Add a `signals.notes` warning that the score is structurally optimistic.
- **Test run errored**: `test_score = 0`, runner error in `hard_fail_triggers`.
- **Review `complete` with non-empty `proposed_amendments`**: review_score 90; `recommendation` adds "amendments pending - resolve before claiming pass."

## Avoid

- Smoothing over hard-fail signals (no `pass` at score 100 if `ac_violated > 0`).
- Re-running tests or re-deriving coverage - aggregation only.
- Treating absent review as zero - it is `null`; weight is redistributed, not penalized.
- Emitting `status` without `hard_fail_triggers` populated.
