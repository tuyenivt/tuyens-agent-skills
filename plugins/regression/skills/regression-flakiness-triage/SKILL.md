---
name: regression-flakiness-triage
description: Classify regression test failures into real-bug / flake / infra / seed-drift. Surfaces flake-rate trend across last N runs. Triage only, no auto-retries.
metadata:
  category: testing
  tags: [regression, flakiness, triage, classification, reliability]
user-invocable: false
---

# Regression Flakiness Triage

> Triage, not a re-runner. Reads JUnit XML, container exit codes from the runner's `docker compose ps` snapshot, seed-file mtimes, and `.regression/runs/` history. Never re-executes a test. Verdicts feed `regression-report-format`.

## When to Use

- During `task-regression` after Playwright finishes, before `regression-report-format` writes `summary.md`.
- Once per run.

## Rules

1. **Exactly one bucket per failure.** `real-bug | flake | infra | seed-drift`.
2. **No automatic retries.** Playwright's own retry config is a user-set opt-in; this skill reports retry results, never invokes them.
3. **Signals are evidence; `real-bug` is the default.** The `real-bug` bucket has no positive signals - it is fall-through. The `signals` field for a real-bug verdict carries the reason it fell through (e.g. `"no infra/seed/flake signals matched"`) plus any positive real-bug indicators (HTTP 5xx, backend exception correlated with the failing request, deterministic reproduction across runs).
4. **Rotting-suite gate.** Default threshold `0.15` over `(flake / (flake + real-bug))` for the current run. Configurable in `.regression/config.json`. When tripped, the report's `## Verdict` prepends a `SUITE ROTTING` warning. Does not change exit code.
5. **Trend column, not trend verdict.** Per-flow flake rate across last `N` runs (default 10) is a column in the report; it does not change the current verdict.
6. **No codemap read.** Service paths come from `services.yaml#source.path`. The skill never opens `.codemap/`.

## Patterns

### Decision order (first match wins)

1. **`infra`** - the system was not up: container exit != 0 at run end, healthcheck never reached `healthy`, network error class (`ECONNREFUSED`, `EAI_AGAIN`, `ETIMEDOUT`) before any assertion, Docker daemon error in runner log.
2. **`seed-drift`** - the assertion targets a row that fresh seeds should have produced: the failing assertion's target identifier matches a literal in `.regression/seeds/**`, AND (any seed file mtime is newer than the last green run for this flow OR the seed apply phase logged a non-fatal warning for that file).
3. **`flake`** - non-deterministic execution: Playwright's own retry within the same run passed (config has retries > 0), OR the same `(scenario, error-class, top-frame)` tuple alternated pass/fail across the last `N` runs with no commit to the relevant scenario file or to any sibling service path (from `services.yaml#source.path`). Partial-tuple alternation (top-frame missing because the trace truncated) does not satisfy `flake`; fall through to `real-bug`.
4. **`real-bug`** - fall-through. Cite either the fall-through reason or any positive indicator listed in Rule 3.

### Cross-run history shape

`.regression/runs/<runId>/triage.json` (gitignored, one per run):

```json
{
  "runId": "20260601T143207-a1b2c3",
  "perFlow": {
    "order-checkout-happy": { "verdict": "flake", "errorClass": "TimeoutError", "topFrame": "order-checkout.spec.ts:42" },
    "user-signup": { "verdict": "pass" }
  }
}
```

Trend reads the last `N` of these. `flakeRate` in the per-flow output is `"<F>/<N>"` for flake verdicts and unset for others.

### Per-flow report column

```
| Flow | Verdict | Duration | Flake-rate (last 10) |
| --- | --- | --- | --- |
| order-checkout-happy | flake | 12.4s | 7/10 |
| user-signup | pass | 4.1s | - |
```

### Rotting-suite warning

When the ratio trips the threshold:

```
**SUITE ROTTING** - flake ratio 0.42 exceeds threshold 0.15.
{If infra > 0 OR seed-drift > 0:}  Fix infra and seeds before chasing assertion failures.
{Otherwise:}                       Investigate the alternating tests; assertions are probably correct.
```

Two messages: one when infra/seeds carry blame, one when the flake is pure assertion / timing churn.

## Output Format

JSON handed to `regression-report-format` and written to `.regression/runs/<runId>/triage.json`:

```json
{
  "perFlow": [
    {
      "flow": "order-checkout-happy",
      "verdict": "flake",
      "signals": ["alternates runs 7-9; no commits to api/ or scenarios/api/order-checkout.spec.ts"],
      "flakeRate": "7/10"
    },
    {
      "flow": "gateway-route",
      "verdict": "real-bug",
      "signals": ["no infra/seed/flake signals matched"]
    }
  ],
  "rottingSuite": { "tripped": true, "ratio": 0.42, "threshold": 0.15 }
}
```

`ratio` is rounded to 2 decimals.

## Avoid

- Auto-retrying failed tests.
- Marking a failure `flake` to keep the build green.
- Mixing verdicts per flow.
- Treating `infra` as `real-bug` (the system wasn't up).
- Reading codemap.
- Trend-changing a current verdict.
- Inferring `seed-drift` from `ON CONFLICT DO NOTHING` log lines on rows whose values do not appear in the failing assertion.
