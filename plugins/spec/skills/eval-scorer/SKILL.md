---
name: eval-scorer
description: Aggregate test, spec-coverage, and review signals into a weighted 0-100 score and pass / needs-fix / fail status for SDD evaluation.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, scoring, aggregation]
user-invocable: false
---

# Eval - Scorer

## When to Use

Composed by `task-spec-evaluate` after `eval-test-runner` and `eval-spec-coverage` have produced their structured outputs. Pure aggregation: never runs tests, never re-derives coverage, never decides whether to loop (that is `fix-loop-controller`'s job).

## Rules

- Fixed weights: Test 30, Coverage 50, Review 20. Coverage outweighs tests because acceptance criteria encode user-visible behavior; tests may be green yet miss ACs.
- Hard-fail signals override the weighted score: any of `ac_violated > 0`, `out_of_scope_drift > 0`, `nfr_failed > 0`, `test_run.status in {fail, timeout, error}`, or `review_blockers > 0` blocks `pass` regardless of score.
- Blocker count dominates review status: any `review_blockers > 0` is treated as a failed review regardless of envelope `status`.

## Inputs

| Bundle           | Fields used                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| `test_run`       | `status` (pass / fail / timeout / error / no-runner-detected), `passed`, `failed`, `errored`, `notes`      |
| `spec_coverage`  | `ac_total`, `covered_full`, `covered_by_code_only`, `ac_violated`, `nfr_total`, `nfr_verified`, `nfr_partially_verified`, `nfr_failed`, `drift_count` |
| `review_verdicts`| optional list from `handoffs/*-review-*.md`: `status`, `blockers[]`, `suggestions[]`, `proposed_amendments[]` |
| `thresholds`     | optional caller override; may tighten the pass band only, never widen it                                   |

`covered_by_code_only` = AC implemented and behaviorally exercised by tests, but not explicitly asserted against the AC text (partial credit 0.7).

## Patterns

### Sub-Scores

```text
# Test (weight 30)
test_score = 100 * passed / max(passed + failed + errored, 1)
# test_run.notes == "no tests collected" -> test_score = 0 (no evidence of behavior)

# Coverage (weight 50)
ac_score       = 100 * (covered_full + 0.7 * covered_by_code_only) / max(ac_total, 1)
nfr_score      = 100 * (nfr_verified + 0.5 * nfr_partially_verified) / max(nfr_total, 1)
coverage_score = 0.7 * ac_score + 0.3 * nfr_score

# Review (weight 20) - evaluated top-down, first match wins
review_blockers > 0                           -> max(0, 80 - 15 * blockers)
status in {blocked, needs-clarification}      -> null  (escalate)
no review envelope present                    -> null  (redistribute)
status == complete, only suggestions          -> 90
status == complete, clean                     -> 100

overall_score = round(0.30 * test_score + 0.50 * coverage_score + 0.20 * review_score)
```

### Weight Redistribution

When `review_score` is `null`, redistribute its 20 to the remaining components proportionally: `test 37.5, coverage 62.5`. When `test_run.status == no-runner-detected`, redistribute test's 30 the same way: `coverage 71.4, review 28.6` (and if review is also `null`, coverage absorbs everything at weight 100).

### Status Bands

| Status      | Conditions                                                                                       |
| ----------- | ------------------------------------------------------------------------------------------------ |
| `pass`      | `overall_score >= 85` AND zero hard-fail triggers AND `test_run.status == pass`                  |
| `needs-fix` | `60 <= overall_score < 85`, OR any hard-fail trigger present                                     |
| `fail`      | `overall_score < 60`                                                                             |

Hard-fail triggers force at least `needs-fix`. They never promote to `fail` here - `fix-loop-controller` owns iteration-cap escalation.

### Edge Cases

- `ac_total == 0`: spec has no ACs. Status `needs-fix`, append `"no acceptance criteria in spec.md"` to `hard_fail_triggers`, recommend `task-spec-clarify`.
- `nfr_total == 0`: `nfr_score = 100` (vacuously satisfied); add `signals.notes` flagging that the score is structurally optimistic.
- Review `status == complete` with non-empty `proposed_amendments`: keep computed `review_score`, append `"amendments pending"` to `recommendation`.

## Output Format

```yaml
score:
  overall_score: <int 0-100>
  status: pass | needs-fix | fail
  weights_applied: { test: <num>, coverage: <num>, review: <num | null> }
  sub_scores: { test_score: <num>, coverage_score: <num>, review_score: <num | null> }
  signals:
    ac_total: <int>
    ac_covered: <int>            # covered_full + covered_by_code_only
    ac_violated: <int>
    nfr_total: <int>
    nfr_verified: <int>
    nfr_failed: <int>
    drift_count: <int>
    test_status: pass | fail | timeout | error | no-runner-detected
    review_blockers: <int | null>
    notes: [<string>, ...]       # empty list when none
  hard_fail_triggers: [<string>, ...]   # empty list when none
  blocking_issues: [<string>, ...]      # one-line summaries, cap 10
  recommendation: <one sentence>        # e.g. "loop and fix auth blocker" / "escalate" / "ship it"
```

## Avoid

- Smoothing over hard-fail signals (no `pass` at any score if `ac_violated > 0` or blockers exist).
- Re-running tests or re-deriving coverage; the runner and coverage atomics own those.
- Treating an absent review envelope as zero; it is `null` and the weight is redistributed.
- Encoding iteration-cap promotion to `fail` here; that is `fix-loop-controller`'s decision.
