---
name: regression-perf-check
description: Per-flow latency budget enforcement for outside-in regression. Rolling p95 over recent runs vs flows.yaml#latencyBudget.p95Ms, surfaces in report.
metadata:
  category: testing
  tags: [regression, performance, latency, budget, slo]
user-invocable: false
---

# Regression Perf Check

Catches latency regressions that pass functional assertions but blow past the user-facing SLO. Opt-in per flow.

## When to Use

- Flow has `latencyBudget: { p95Ms: <N> }` in `flows.yaml` AND `checks:` contains `perf`.
- The user passes `--check perf` to `task-regression-scenario`.

## Rules

1. **p95 is over the run, not over a single test execution.** The budget compares against the rolling p95 from `regression-report-format`'s `## Performance` section. A single slow run does not bust the budget; sustained slowness does.
2. **Always opt-in via `checks: [perf]`.** Presence of `latencyBudget:` alone is data, not a gate.
3. **OVER status does not change the exit code.** `task-regression` exit is `real-bug` only (Rule 5 of `regression-report-format`). OVER surfaces in `## Counts` as `BudgetViolations: N` for CI greps.
4. **Per-step budget syntax.** `latencyBudget: { p95Ms: <total>, steps: { <step-name>: <ms> } }` - total is required when `checks: [perf]`, per-step optional.
5. **Cold-cache warning.** First runs on a fresh runner skew high; the writer emits `_warm-up_` in Status while there are fewer than 4 prior runs for a given runner / image set (see Rolling window).

## Patterns

### Scenario emission (from `regression-scenario-author`)

```ts
// PERF (regression-perf-check)
const t0 = performance.now();
const created = await request.post("/orders", { data: { ... } });
const stepMs = performance.now() - t0;
test.info().attach("step-create-order-ms", { body: String(stepMs), contentType: "text/plain" });
```

The `test.info().attach(...)` writes per-step durations into JUnit `<system-out>` as `name=val` lines; `regression-report-format` parses them into the rolling p95 table. The scenario itself does NOT assert on `stepMs < budget` - the assertion lives in the report-time aggregation, not the runtime path, so transient slowness does not fail a real-bug verdict.

### `latencyBudget` shape

```yaml
- name: order-checkout-happy
  # ...
  checks: [perf]
  latencyBudget:
    p95Ms: 1500
    steps:
      create-order: 800
      poll-confirmed: 600
```

### When budget data is missing

`checks: [perf]` set but no `latencyBudget:` -> emission abort with `regression-perf-check: flow '<name>' opts into 'perf' but has no latencyBudget; add p95Ms or remove 'perf'.` Do not silently no-op.

### Rolling window

p95 reads the last 10 successful runs of the same flow from `.regression/runs/<runId>/triage.json`. Fewer than 4 prior runs -> Status `_warm-up_` (not OVER, not UNDER). This avoids false OVER on a noisy first runner.

## Output Format

- Per-step timing attachments in JUnit `<system-out>`.
- Consumed by `regression-report-format` to render `## Performance` table.
- `BudgetViolations` count in `## Counts`.

## Avoid

- Asserting `stepMs < budget` inside the scenario (a single transient slowness becomes a Fail).
- Treating an OVER status as a `real-bug` for exit code purposes.
- Setting per-step budgets without a total.
- Comparing against a baseline shorter than 4 runs (signal/noise).
- Reading prior runs across different runner classes (warm-up resets per runner).
