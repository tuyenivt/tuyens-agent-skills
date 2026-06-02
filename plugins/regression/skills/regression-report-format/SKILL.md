---
name: regression-report-format
description: JUnit XML normalization + Markdown verdict report for outside-in regression. Produces summary.md with per-flow verdicts, failure clusters, CI-grep-friendly sections.
metadata:
  category: testing
  tags: [regression, report, junit, markdown, ci]
user-invocable: false
---

# Regression Report Format

> Consumes Playwright JUnit XML, the triage blob from `regression-flakiness-triage`, and the lifecycle metadata block from `regression-runner` (`runId`, `composeProject`, `profile`, image digests, `playwrightVersion`, `node`). Emits `.regression/reports/<runId>/summary.md`.

## When to Use

- During `task-regression` after Playwright finishes and triage has classified each failure.
- Once per run. Each run gets a new `<runId>` directory.

## Rules

1. **Fixed section headers in this order:** `## Verdict`, `## Counts`, `## Per-Flow`, `## Failure Clusters`, `## Run Metadata`. Exact strings. CI greps them.
2. **One verdict per flow.** From triage. Per-flow casing is `Pass | Fail | Flake | Infra | Seed-drift` (Title-case). The `## Verdict` block label is the UPPER-case mapping: real-bug count -> `**FAIL**`; zero real bugs with any flake/infra/seed-drift -> `**PASS-WITH-NOISE**`; zero real bugs and zero noise -> `**PASS**`.
3. **`Fail` (table) = `**FAIL**` (block).** Same concept, two casings - intentional, this rule names them so CI matchers can target either.
4. **Cluster identical failures** by `(error-class, top-3-stack-frames)`. Report the cluster body once with affected scenarios listed. Truncate body to first 20 lines + `... (N more lines, see <trace-link>)`. Clustering applies only to `Fail` and `Flake` failures - `Infra` and `Seed-drift` failures bypass clustering (the error class is the verdict).
5. **Exit-code rule.** Process exit non-zero iff any flow's verdict is `Fail`. Flake / Infra / Seed-drift never block the pipeline. The exit code is the contract; the verdict label is for humans.
6. **Link, do not embed traces.**
7. **Zero-failures section handling.** `## Failure Clusters` always exists; its body is `_None._` when no failures.

## Patterns

### Verdict semantics

| Verdict | Meaning | Non-zero exit? |
| --- | --- | --- |
| `Pass` | Green on first attempt | No |
| `Fail` | Real-bug from triage | Yes |
| `Flake` | Passed on retry, no code change | No |
| `Infra` | Container exit / healthcheck / network before assertions | No |
| `Seed-drift` | Assertion failed on a row a fresh seed should have produced | No |

### Failure-cluster grouping

```
# BAD: one entry per failing scenario
- order-checkout-happy: TimeoutError: locator.click 'Place order' (45s)
- order-checkout-refund: TimeoutError: locator.click 'Place order' (45s)

# GOOD: one cluster with affected list
### Cluster 1 (2 scenarios) - TimeoutError on `locator.click 'Place order'`
Affected: order-checkout-happy, order-checkout-refund
First trace: traces/order-checkout-happy.zip
```

### `summary.md` template

```markdown
# Regression Run <runId>

## Verdict

**FAIL** - 1 real-bug failure. 2 flakes, 0 infra, 0 seed-drift surfaced separately.

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

| Flow | Verdict | Duration | Trace |
| --- | --- | --- | --- |
| order-checkout-happy | Fail | 12.4s | traces/order-checkout-happy.zip |

## Failure Clusters

### Cluster 1 (1 scenario) - AssertionError: expected 201, got 500
Affected: order-checkout-happy
First trace: traces/order-checkout-happy.zip
Error head:
```
AssertionError: expected 201, got 500
  at scenarios/api/order-checkout.spec.ts:42:18
  at scenarios/api/order-checkout.spec.ts:38:5
... (14 more lines, see traces/order-checkout-happy.zip)
```

## Run Metadata

- runId: 20260601T143207-a1b2c3
- composeProject: regression-20260601T143207-a1b2c3
- profile: local-build
- duration: 3m 47s
- imageDigests:
  - api: ghcr.io/acme/api@sha256:<full-digest>
  - web: ghcr.io/acme/web@sha256:<full-digest>
  - db: postgres@sha256:<full-digest>
- playwrightVersion: 1.49.0
- node: v20.10.0
```

### Verdict block examples (one per label)

```
**FAIL** - {N} real-bug failure{s}. {flakes} flakes, {infra} infra, {seed-drift} seed-drift surfaced separately.
**PASS-WITH-NOISE** - 0 real bugs. {flakes} flakes, {infra} infra, {seed-drift} seed-drift surfaced - read the report.
**PASS** - All {N} scenarios green.
```

Pluralization follows the count (`1 real-bug failure` / `2 real-bug failures`).

### CI-grep contract

- `grep '^## Verdict$' summary.md` finds the verdict block header. The label is on the **next non-empty line**, prefixed with `**FAIL**` / `**PASS**` / `**PASS-WITH-NOISE**` (one of three; mutually exclusive).
- `## Counts` lists `- <Label>: <number>` lines with stable labels: `Total`, `Passed`, `Failed`, `Flake`, `Infra`, `Seed-drift`, `Skipped`, `Duration`.

### Image digests

Always full sha256 (`sha256:` followed by 64 hex chars). Never truncated - CI compares for reproducibility.

### JUnit normalization

- One `<testcase>` -> one `## Per-Flow` row.
- `<failure>` body -> clustering input (Fail / Flake only).
- `<skipped>` -> Skipped count; no `## Per-Flow` row.
- `time` -> Duration column (`Xs` / `X.Xs` precision).

### When the lifecycle metadata block is missing

If `regression-runner` did not supply image digests / runId / etc. (legacy invocation or partial input), write `unknown` for each missing field rather than omitting the bullet - the CI contract requires the line to exist.

## Output Format

`.regression/reports/<runId>/summary.md` + sibling artifacts:

```
.regression/reports/<runId>/
  summary.md
  junit.xml
  traces/<scenario>.zip
  videos/<scenario>.webm
  screenshots/<scenario>.png
```

## Avoid

- Embedding full stack traces.
- Reporting the same error N times instead of clustering.
- Mixing verdicts.
- Non-zero exit on flake / infra / seed-drift.
- Free-form section names.
- Appending to an existing run's summary.
- Truncating image digests.
