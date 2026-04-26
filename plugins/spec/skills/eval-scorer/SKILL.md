---
name: eval-scorer
description: Aggregate test-run output, spec-coverage verdicts, and review-agent verdicts from the handoff directory into a single weighted score plus pass/fail/needs-fix status. Composed by `task-spec-evaluate` and consumed by `fix-loop-controller` (after #18) as the primary loop signal.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, scoring, aggregation]
user-invocable: false
---

> This atomic is composed by `task-spec-evaluate` - do not invoke directly. It reads three signal sources (test runner, spec coverage, review verdicts) and emits one number plus a status.

## When to Use

- Inside `task-spec-evaluate` after `eval-test-runner` and `eval-spec-coverage` have completed
- When orchestration needs a single signal to gate the fix loop (post-#18 wiring)
- When the user asks for "the score" of an implementation against its spec

**Not for:** Producing the test result (use `eval-test-runner`), producing the coverage map (use `eval-spec-coverage`), reviewing skill quality (that's `skill-creator`'s eval domain).

## Rules

- Score is a single integer 0-100, derived from three sub-scores using fixed weights (below)
- Status is derived from explicit thresholds, not from the score alone - any single hard-fail signal forces `fail` regardless of overall number
- Hard-fail signals override the weighted score: `ac_violated > 0`, `out_of_scope_drift > 0`, or `test_run.status == fail/timeout/error` set status to `fail` even if the weighted score is high
- The atomic does not interpret what to DO with the score - that is `fix-loop-controller`'s job in #18
- Weights are explicit and stable; if changed, the change is a versioned amendment, not a silent tweak

## Inputs

| Input             | Source                                                                                                                   |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `test_run`        | `eval-test-runner` output                                                                                                |
| `spec_coverage`   | `eval-spec-coverage` output                                                                                              |
| `review_verdicts` | Optional - parsed from review handoff envelopes (status + blocker count from `step: review` envelopes in `handoffs_dir`) |
| `thresholds`      | Optional override of the pass/needs-fix bands                                                                            |

## Sub-Score Formulas

### Test pass rate (weight: 30)

```
test_score = 100 * passed / max(passed + failed + errored, 1)
```

If `test_run.status` is `pass` and counts show zero tests collected, `test_score = 0` (no evidence of behavior). The `notes: "no tests collected"` from the runner triggers this.

### Spec coverage (weight: 50 - the heaviest signal, since spec is source of truth)

```
ac_satisfied = ac_covered  (covered + covered-by-code-only)
ac_score = 100 * ac_satisfied / max(ac_total, 1)

# Penalty for partial coverage: each `covered-by-code-only` only counts as 0.7
ac_score = 100 * (covered_full + 0.7 * covered_by_code_only) / max(ac_total, 1)

nfr_score = 100 * (nfr_verified + 0.5 * nfr_partially_verified) / max(nfr_total, 1)

coverage_score = 0.7 * ac_score + 0.3 * nfr_score
```

ACs are weighted higher than NFRs because they encode user-visible behavior.

### Review verdict (weight: 20)

If review handoff envelopes exist in `handoffs_dir`:

```
review_score:
  no review envelope yet:                    null   (weight redistributed)
  latest review envelope status == complete and 0 blockers: 100
  latest review envelope status == complete and only suggestions/nitpicks: 90
  latest review envelope status == failed and N blockers:   max(0, 80 - 15 * N)
  latest review envelope status == blocked or needs-clarification: null (escalate)
```

If `review_score` is null because no review has run yet, redistribute its weight (20) proportionally across `test_score` and `coverage_score` (so they become weighted 37.5 and 62.5 respectively).

### Aggregate

```
overall_score = round(
  0.30 * test_score +
  0.50 * coverage_score +
  0.20 * review_score
)
```

(With redistribution if review is absent.)

## Status Bands

| Status      | Conditions                                                                                                                                   |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `pass`      | `overall_score >= 85` AND `ac_violated == 0` AND `out_of_scope_drift == 0` AND `test_run.status == pass` AND no review blockers              |
| `needs-fix` | `overall_score` in `[60, 84]` OR review has blockers OR `ac_violated == 0` but `nfr_failed > 0`. Indicates the fix loop should run again     |
| `fail`      | `overall_score < 60` OR `ac_violated > 0` OR `out_of_scope_drift > 0` OR `test_run.status` in `{fail, timeout, error}` AND iteration cap met |

Hard-fail signals (`ac_violated`, `out_of_scope_drift`, runner non-pass) ALWAYS force at least `needs-fix` regardless of overall_score; with iteration cap reached they force `fail`. The scorer is the **only** place these promotion rules are encoded.

## Output Format

```yaml
score:
  overall_score: <int 0-100>
  status: pass | needs-fix | fail
  weights_applied:
    test: 30
    coverage: 50
    review: 20    # or "null - redistributed" if no review envelope
  sub_scores:
    test_score: <int>
    coverage_score: <int>
    review_score: <int or null>
  signals:
    ac_total: <int>
    ac_covered: <int>
    ac_violated: <int>
    nfr_total: <int>
    nfr_verified: <int>
    nfr_failed: <int>
    drift_count: <int>
    test_status: <pass | fail | timeout | error | no-runner-detected>
    review_blockers: <int or null>
  hard_fail_triggers:
    - <list of triggers that forced status; empty when none>
  blocking_issues:
    - <one-line summary per issue, max 10>
  recommendation: <one sentence: "loop and fix X", "escalate to user", "ship it">
```

## Decision Surface for `fix-loop-controller` (post-#18)

After #18 lands, `fix-loop-controller` will read `score.status` instead of (or in addition to) the latest envelope's status:

| `score.status` | Controller behavior                                                                               |
| -------------- | ------------------------------------------------------------------------------------------------- |
| `pass`         | `proceed-done`                                                                                    |
| `needs-fix`    | `loop` (if iterations < cap) or `escalate` (if at cap), with `score.blocking_issues` as feedback  |
| `fail`         | `escalate` (do not loop on hard fails - the system disagrees with the spec at a structural level) |

The scorer itself does not perform this routing; it only emits the inputs.

## Handling Edge Cases

- **All inputs nominal but `ac_total == 0`:** the spec has no acceptance criteria. Score is undefined; emit `status: fail` with `hard_fail_triggers: ["no acceptance criteria in spec.md"]` and recommend running `task-spec-clarify`.
- **Test run errored:** `test_score` is 0; status forced to `fail` (or `needs-fix` if first iteration); `hard_fail_triggers` includes the runner error.
- **Coverage atomic produced no NFR section because plan.md has no NFRs:** `nfr_total == 0`, `nfr_score = 100` (vacuously satisfied). Note in `signals.notes` that the score is structurally optimistic.
- **Review verdict says `complete` with non-empty `proposed_amendments`:** review_score is 90 (treated as suggestion-tier), but `recommendation` includes "amendments pending - resolve before claiming pass."
- **Custom `thresholds` override:** caller may pass tighter bands (e.g., pass requires 90). The atomic accepts this; never widens defaults though.

## Avoid

- Smoothing over hard-fail signals - if `ac_violated > 0`, status cannot be `pass` even at score 100
- Inventing weights to make a number look better - the weights are part of the contract
- Re-running tests or re-deriving coverage - the scorer is purely aggregational
- Returning status without `hard_fail_triggers` populated - downstream consumers need to know WHY the band was forced
- Treating absent review as zero - it is `null`; weight is redistributed, not penalized

## Notes

- The single-number score is deliberately rough. Its role is to make the loop signal mechanical (`needs-fix` vs `pass`), not to be a meaningful quality grade. Detailed quality lives in `eval-spec-coverage` verdicts and review envelopes.
- Pairs with `eval-test-runner` and `eval-spec-coverage` upstream and `fix-loop-controller` downstream. Changes to the weights or bands ripple to those consumers - bump the contract version (in `notes`) when changing.
- Per merging-spec.md §13.3, this scoring model is intentionally simple. It will evolve with usage; future versions may add per-stack calibration or trend-over-iterations signals.
