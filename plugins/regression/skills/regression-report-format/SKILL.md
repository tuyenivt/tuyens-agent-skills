---
name: regression-report-format
description: JUnit XML normalization + Markdown verdict report for outside-in regression. Produces summary.md with per-flow verdicts, failure clusters, CI-grep-friendly sections.
metadata:
  category: testing
  tags: [regression, report, junit, markdown, ci]
user-invocable: false
---

# Regression Report Format

> Consumes JUnit XML from `npx playwright test --reporter=junit` plus verdict labels from `regression-flakiness-triage`. Emits `.regression/reports/<runId>/summary.md` with fixed section headers so CI can grep without parsing YAML.

## When to Use

- During `task-regression` after Playwright finishes and `regression-flakiness-triage` has classified each failure.
- Once per run. The summary is not append-only; each run gets a new `<runId>` directory.

## Rules

1. **Fixed section headers.** `## Verdict`, `## Counts`, `## Per-Flow`, `## Failure Clusters`, `## Run Metadata`. Headers are exact strings, in this order. CI greps them.
2. **One verdict per flow.** Exactly one of `Pass | Fail | Flake | Infra | Seed-drift`. Pulled from `regression-flakiness-triage` for failures; `Pass` if all retries green.
3. **Cluster identical failures.** Group by `(error-class, top-3-stack-frames)`. Report the cluster once at the top with the count and a list of affected scenarios. Do not duplicate the error body per scenario.
4. **Exit-code rule.** Exit non-zero **only if any flow's verdict is `Fail` (real-bug)**. `Flake`, `Infra`, `Seed-drift` exit zero but are surfaced loudly in `## Verdict`.
5. **Link, do not embed.** Traces, videos, screenshots are referenced by relative path under `reports/<runId>/`. The Markdown stays small enough to paste into a PR.
6. **Truncate long error messages.** Cluster body shows first 20 lines + `... (N more lines, see <trace-link>)`.

## Patterns

### Verdict semantics

| Verdict      | Meaning                                                            | Contributes to non-zero exit |
| ------------ | ------------------------------------------------------------------ | ---------------------------- |
| `Pass`       | All assertions green on first attempt                              | No                           |
| `Fail`       | Real-bug classification from `regression-flakiness-triage`         | Yes                          |
| `Flake`      | Passed on retry without code change                                | No                           |
| `Infra`      | Container exit / healthcheck / network failure before assertions   | No                           |
| `Seed-drift` | Assertion failed on a row a fresh seed should have produced        | No                           |

### Failure-cluster grouping

Bad - one entry per failing scenario:

```
- order-checkout-happy: TimeoutError: locator.click 'Place order' (45s)
- order-checkout-refund: TimeoutError: locator.click 'Place order' (45s)
- order-checkout-coupon: TimeoutError: locator.click 'Place order' (45s)
```

Good - one cluster, affected scenarios listed:

```
### Cluster 1 (3 scenarios) - TimeoutError on `locator.click 'Place order'`
Affected: order-checkout-happy, order-checkout-refund, order-checkout-coupon
First trace: traces/order-checkout-happy.zip
```

### Per-flow table

```
| Flow                          | Verdict     | Duration | Trace                                    |
| ----------------------------- | ----------- | -------- | ---------------------------------------- |
| order-checkout-happy          | Fail        | 12.4s    | traces/order-checkout-happy.zip          |
| user-signup-email-verify      | Pass        | 4.1s     | -                                        |
| admin-refund-flow             | Flake       | 8.7s     | traces/admin-refund-flow.zip             |
```

### Exact `summary.md` template

```markdown
# Regression Run <runId>

## Verdict

**FAIL** - 1 real-bug failure. 2 flakes, 0 infra, 0 seed-drift surfaced separately.

(Or: **PASS** / **PASS-WITH-NOISE** when no real bugs but flake/infra/seed-drift > 0.)

## Counts

- Total: 24
- Passed: 21
- Failed: 1
- Flake: 2
- Infra: 0
- Seed-drift: 0
- Skipped: 0
- Duration: 3m 47s

## Per-Flow

| Flow                          | Verdict     | Duration | Trace                                    |
| ----------------------------- | ----------- | -------- | ---------------------------------------- |
| order-checkout-happy          | Fail        | 12.4s    | traces/order-checkout-happy.zip          |
| ...                           | ...         | ...      | ...                                      |

## Failure Clusters

### Cluster 1 (1 scenario) - AssertionError: expected status 201, got 500
Affected: order-checkout-happy
First trace: traces/order-checkout-happy.zip
Error head:
```
AssertionError: expected status 201, got 500
  at scenarios/api/order-checkout.spec.ts:42:18
  at scenarios/api/order-checkout.spec.ts:38:5
... (14 more lines, see traces/order-checkout-happy.zip)
```

## Run Metadata

- runId: 2026-06-01T14-32-07-a1b2c3
- composeProject: regression-2026-06-01T14-32-07-a1b2c3
- profile: local-build
- duration: 3m 47s
- imageDigests:
  - api: ghcr.io/acme/api@sha256:abc...
  - web: ghcr.io/acme/web@sha256:def...
  - db: postgres@sha256:fed...
- playwrightVersion: 1.49.0
- node: v20.10.0
```

### CI-grep contract

CI can rely on:

- `grep -E '^## Verdict$' summary.md` finds the top verdict block.
- The line after `## Verdict` starts with `**FAIL**`, `**PASS**`, or `**PASS-WITH-NOISE**`.
- `## Counts` block has one `- <Label>: <number>` per line, labels are stable identifiers (`Total`, `Passed`, `Failed`, `Flake`, `Infra`, `Seed-drift`, `Skipped`).

### JUnit XML normalization

Playwright's JUnit reporter emits one `<testsuite>` per `.spec.ts`. Normalize:

- One `<testcase>` -> one flow row.
- `<failure>` body -> cluster grouping input.
- `<skipped>` -> Skipped count, no row in `## Per-Flow`.
- `time` attr -> Duration column.

## Output Format

`.regression/reports/<runId>/summary.md` (gitignored), plus sibling artifacts:

```
.regression/reports/<runId>/
  summary.md
  junit.xml                # raw Playwright output
  traces/<scenario>.zip
  videos/<scenario>.webm
  screenshots/<scenario>.png
```

The summary is the contract; everything else is linked from it.

## Avoid

- **Embedding full stack traces.** Link the trace zip; keep the report PR-pastable.
- **Reporting the same error N times.** Cluster first, then list affected scenarios.
- **Mixing verdicts.** A scenario is `Fail` *or* `Flake` *or* `Infra` *or* `Seed-drift`, never two.
- **Non-zero exit on flake/infra/seed-drift.** Only `Fail` blocks the pipeline; the other three are loud but green.
- **Free-form section names.** CI greps the fixed headers. Renaming breaks the contract.
- **Appending to an existing run's summary.** Each run gets a new `<runId>` directory.
