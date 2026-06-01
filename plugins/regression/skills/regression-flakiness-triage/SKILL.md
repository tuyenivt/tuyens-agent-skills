---
name: regression-flakiness-triage
description: Classify regression test failures into real-bug / flake / infra / seed-drift. Surfaces flake-rate trend across last N runs. Triage only, no auto-retries.
metadata:
  category: testing
  tags: [regression, flakiness, triage, classification, reliability]
user-invocable: false
---

# Regression Flakiness Triage

> Triage, not a re-runner. This skill never re-executes a test. It reads JUnit XML, container exit codes, seed file mtimes, and `.regression/runs/` history to assign each failure to exactly one of four buckets. The verdicts feed `regression-report-format`.

## When to Use

- During `task-regression` after Playwright finishes, before `regression-report-format` writes the summary.
- Once per run. Output is consumed by the report skill, not by the user directly.

## Rules

1. **Exactly one bucket per failure.** `real-bug | flake | infra | seed-drift`. No "mostly a flake" - pick.
2. **No automatic retries.** Retries hide bugs. Playwright's own per-test retry config is a separate, explicit opt-in surfaced in the report; this skill does not invoke it.
3. **Signals over instinct.** Each classification cites at least one signal from the table below. No signals = `real-bug` (fail-closed).
4. **Rotting-suite gate.** If `flake / (flake + real-bug)` across the current run exceeds the threshold (default `0.15`), the report's `## Verdict` block prepends a `SUITE ROTTING` warning telling the user to fix infra/seeds before chasing assertions.
5. **Trend, not just snapshot.** Read the last N runs from `.regression/runs/` (default `N=10`) and emit the per-flow flake rate. A flow flaky in 7/10 runs is louder than one flaky once.

## Patterns

### Classification signal table

| Bucket        | Required signals (any one suffices)                                                                                                                                                                                                                                                                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `infra`       | Container exit code != 0 in `docker compose ps` snapshot taken at run end. Healthcheck never reached `healthy` within the configured retries. Network error class: `ECONNREFUSED`, `EAI_AGAIN`, `ETIMEDOUT` before any assertion ran. Docker daemon error in `runner` log.                                                                                                            |
| `seed-drift`  | The failing assertion targets a row/value present in `.regression/seeds/**`. AND any seed file's mtime is newer than the run's last green run timestamp for this flow. OR seed apply phase logged a non-fatal warning (e.g. `ON CONFLICT DO NOTHING` skipped an expected row because schema columns changed).                                                                       |
| `flake`       | Playwright retry within the same run passed (only when per-test retries are explicitly enabled in `playwright.config.ts`). OR the same `(scenario, error-class, top-frame)` tuple alternates pass/fail across the last N runs with no commit to the relevant scenario or service in between (mine git log via codemap-known service paths or `services.yaml#source`).                |
| `real-bug`    | Default when no other bucket's signals match. Also the explicit bucket for: assertion failures with deterministic reproduction, HTTP 5xx from the backend, exception in container logs correlated with the failing scenario's request, schema-mismatch errors from the backend itself.                                                                                              |

### Decision order

Evaluate in this order; first match wins:

1. `infra` - check container exit codes and healthcheck status first. If the system was not up, no test verdict is meaningful.
2. `seed-drift` - check seed mtimes and apply-phase warnings. A failed assertion against a missing fixture row is not a bug in the backend.
3. `flake` - check retry result and cross-run alternation. Requires evidence; never a guess.
4. `real-bug` - fall-through.

### Bad / good triage example

Bad - vague bucket assignment:

```
order-checkout-happy: flaky (sometimes fails)
```

Good - signal-cited assignment:

```
order-checkout-happy: flake
  signals:
    - alternates pass/fail across runs 7,8,9 (no commits to api/ or scenarios/api/order-checkout.spec.ts)
    - same top-frame: locator.click 'Place order' at 'order-checkout.spec.ts:42'
```

### Cross-run history shape

`.regression/runs/<runId>/index.json` (gitignored, one per run):

```json
{
  "runId": "2026-06-01T14-32-07-a1b2c3",
  "startedAt": "2026-06-01T14:32:07Z",
  "endedAt": "2026-06-01T14:35:54Z",
  "profile": "local-build",
  "perFlow": {
    "order-checkout-happy": { "verdict": "flake", "durationMs": 12400, "errorClass": "TimeoutError", "topFrame": "order-checkout.spec.ts:42" },
    "user-signup-email-verify": { "verdict": "pass", "durationMs": 4100 }
  }
}
```

The triage skill reads the last N (default 10) of these to compute per-flow flake rate.

### Per-flow flake-rate output

Surfaced in the report under `## Per-Flow` as an extra column or footnote:

```
| Flow                  | Verdict | Duration | Flake-rate (last 10) |
| --------------------- | ------- | -------- | -------------------- |
| order-checkout-happy  | flake   | 12.4s    | 7/10                 |
```

### Rotting-suite threshold

Default `0.15`. Configurable in `.regression/config.json`:

```json
{ "flakiness": { "rottingThreshold": 0.15, "historyWindow": 10 } }
```

When tripped, the report's `## Verdict` block leads with:

```
**SUITE ROTTING** - flake ratio 0.42 exceeds threshold 0.15. Fix infra and seeds before chasing assertion failures.
```

This does not change exit code. It changes the human's reading order.

## Output Format

A JSON blob handed to `regression-report-format`:

```json
{
  "perFlow": [
    {
      "flow": "order-checkout-happy",
      "verdict": "flake",
      "signals": ["alternates across runs 7-9", "top-frame stable"],
      "flakeRate": "7/10"
    }
  ],
  "rottingSuite": {
    "tripped": true,
    "ratio": 0.42,
    "threshold": 0.15
  }
}
```

Verdicts in this blob are 1:1 with what the report renders. The blob is also written to `.regression/runs/<runId>/triage.json` for trend computation on the next run.

## Avoid

- **Auto-retrying failed tests.** This skill never invokes Playwright; it classifies what already ran.
- **Guessing buckets.** No signal = `real-bug`. Don't mark something `flake` to keep the build green.
- **Mixing verdicts per flow.** One bucket. The signals can be multiple; the bucket is one.
- **Ignoring trend.** A flow flaky in 7/10 runs is a load-bearing warning, not a footnote.
- **Reading codemap.** Cross-run history lives in `.regression/runs/`; service paths come from `services.yaml`. No codemap read at runtime.
- **Treating `infra` as `real-bug`.** A container that never came up cannot have produced a real-bug assertion failure.
