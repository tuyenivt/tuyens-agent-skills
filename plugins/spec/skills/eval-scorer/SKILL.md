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

Composed by `task-spec-evaluate` after `eval-test-runner` and `eval-spec-coverage`. Pure aggregation.

## Rules

- Fixed weights: Test 30, Coverage 50, Review 20. Coverage outweighs tests because ACs encode user-visible behavior; tests may be green yet miss ACs.
- Hard-fail = `spec_coverage.hard_fail_inputs` non-zero OR `test_run.status in {fail, timeout, error, no-tests-collected}` OR `review_blockers > 0`. Hard-fail blocks `pass` regardless of score.
- Hard-fail never promotes to `fail` here. `fix-loop-controller` owns iteration-cap escalation.
- Blocker count dominates review status: any `review_blockers > 0` is a failed review regardless of envelope `status`.

## Inputs

| Bundle           | Fields used                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| `test_run`       | `status`, `counts.{passed, failed, errored}`, `notes`                                                      |
| `spec_coverage`  | `acceptance_criteria[].verdict`, `nfrs[].verdict`, `summary.*`, `hard_fail_inputs`                         |
| `review_verdicts`| optional list from `handoffs/*-review-*.md`: `status`, `blockers[]`, `suggestions[]`, `proposed_amendments[]` |
| `thresholds`     | optional caller override; may tighten the pass band only, never widen it                                   |

Derive locally from per-AC/per-NFR verdicts:
- `covered_full = count(verdict == "covered")`
- `covered_by_code_only = count(verdict == "covered-by-code-only")`
- `nfr_verified_full = count(verdict == "verified")`
- `nfr_partially_verified = count(verdict == "partially-verified")`

`covered_by_code_only` is partial credit 0.7.

**Multiple review envelopes**: take the worst - max blocker count across envelopes; any non-`complete` status escalates.

## Sub-Scores

```text
# Test (weight 30)
test_score = 100 * passed / max(passed + failed + errored, 1)
# test_run.status == no-tests-collected -> test_score = 0

# Coverage (weight 50)
ac_score       = 100 * (covered_full + 0.7 * covered_by_code_only) / max(ac_total, 1)
nfr_score      = 100 * (nfr_verified_full + 0.5 * nfr_partially_verified) / max(nfr_total, 1)
coverage_score = 0.7 * ac_score + 0.3 * nfr_score

# Review (weight 20) - top-down, first match wins
review_blockers > 0                           -> max(0, 80 - 15 * blockers)
status in {blocked, needs-clarification}      -> null  (escalate)
no review envelope present                    -> null  (redistribute)
status == complete, only suggestions          -> 90
status == complete, clean                     -> 100

overall_score = round(0.30 * test_score + 0.50 * coverage_score + 0.20 * review_score)
```

### Weight Redistribution

- `review_score == null`: `test 37.5, coverage 62.5`.
- `test_run.status == no-runner-detected`: `coverage 71.4, review 28.6`. If review also null: `coverage 100`.

### Status Bands

| Status      | Conditions                                                                                       |
| ----------- | ------------------------------------------------------------------------------------------------ |
| `pass`      | `overall_score >= 85` AND no hard-fail AND `test_run.status == pass`                             |
| `needs-fix` | `60 <= overall_score < 85`, OR any hard-fail                                                     |
| `fail`      | `overall_score < 60`                                                                             |

Structural hard-fails (ac_violated, drift, nfr_failed) surface as `needs-fix` so `fix-loop-controller` can attempt remediation within the iteration cap; only iteration-cap exhaustion at the controller promotes to escalate/fail.

### Worked Example

`test 18/2/0; ac_total=4, covered_full=2, covered_by_code_only=1; nfr 2/2; drift=1; blockers=1`.
`test=90`, `ac=67.5`, `nfr=100`, `coverage=77.25`, `review=65`, `overall=round(27 + 38.625 + 13)=79`. Hard-fail triggers: drift (`out_of_scope_drift`), test fail, review_blockers. Status: `needs-fix`.

### Edge Cases

- `ac_total == 0`: status `needs-fix`, append `no-acceptance-criteria` to `hard_fail_triggers`, recommend `task-spec-clarify`.
- `nfr_total == 0`: `nfr_score = 100` (vacuously satisfied); flag in `signals.notes`.
- `review_verdicts` is empty list (not null): treat as null, redistribute weight.

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
    test_status: pass | fail | timeout | error | no-runner-detected | no-tests-collected
    review_blockers: <int | null>
    notes: [<string>, ...]
  hard_fail_triggers: [<string>, ...]   # spec_coverage.hard_fail_reasons verbatim, plus test_run.<status> and review_blockers:<n> when scorer-owned
  blocking_issues: [<string>, ...]      # one-line summaries, cap 10
  recommendation: <one sentence>        # e.g., "loop on <top blocker category>" / "escalate: <reason>" / "ship"
```

## Avoid

- Smoothing over hard-fail signals (no `pass` if any hard-fail trigger).
- Re-running tests or re-deriving coverage (upstream owns those).
- Treating an absent review envelope as zero; it is `null` and weight redistributes.
