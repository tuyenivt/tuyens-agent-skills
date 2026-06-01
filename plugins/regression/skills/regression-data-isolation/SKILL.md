---
name: regression-data-isolation
description: Per-run isolation for outside-in regression. Mints run-id, names compose project, owns ephemeral volumes, deterministic seed order, frozen clock, per-scenario tenant IDs.
metadata:
  category: testing
  tags: [regression, isolation, run-id, volumes, clock, tenant]
user-invocable: false
---

# Regression Data Isolation

The skill that prevents "passes locally, fails in CI" and "two scenarios collide on tenant_id." Owns the four isolation guarantees: ephemeral compose project, ephemeral volumes, deterministic order, frozen wall-clock. Plus per-scenario identifier scoping so concurrent scenarios against the same database do not poison each other.

## When to Use

- At the very start of `task-regression`, before `regression-runner` is invoked. This skill mints `REGRESSION_RUN_ID` and exports the env vars `regression-runner` consumes.
- Anywhere a scenario or fixture needs a unique tenant / user / email / order id derived from `run-id`.

## Rules

1. **`run-id` is minted once per run.** Format: `<UTC timestamp YYYYMMDDTHHMMSS>-<6 lowercase hex>`. Example: `20260601T101530-a7f3c2`. Exported as `REGRESSION_RUN_ID`; never regenerated mid-run.
2. **Compose project name is `regression-<runId>`.** Every `docker compose` invocation uses `-p regression-${REGRESSION_RUN_ID}`. No exceptions.
3. **All volumes are named and project-scoped.** No anonymous volumes. Wiped via `down -v --remove-orphans` at teardown. Never mounted from host paths into databases.
4. **Seeds apply in lexicographic order.** Numeric prefixes (`00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`) are mandatory. Sort is byte-wise ASCII, not locale-aware.
5. **Clock is frozen, not real.** `TZ=UTC` set on every container at compose level. Tests that depend on "now" import `now()` from `fixtures/clock.ts`, which returns a fixed `RUN_BASELINE` derived from `run-id` - never `new Date()` directly.
6. **Per-scenario identifier scoping.** Every tenant / user / email / order id in a scenario is derived from `scopedId(<scenario-name>, <kind>)`, which composes `run-id` + scenario name. Two scenarios in the same run get different IDs by construction.
7. **No identifier leaks across runs.** Any constant ID in a seed file (UUID literals) lives in the `seeds/` namespace; scenario-authored IDs live in the `run-id` namespace. They never overlap.

## Patterns

### `run-id` derivation

```ts
// .regression/scripts/mint-run-id.ts
import { randomBytes } from "crypto";
const ts = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "T");
// 2026-06-01T10:15:30.000Z -> 20260601T101530
const tsCompact = ts.substring(0, 15);
const rand = randomBytes(3).toString("hex");        // 6 hex chars
const runId = `${tsCompact}-${rand}`;
process.stdout.write(runId);
```

### `run-id` derivation table

| Context                          | Format                                | Example                                  |
| -------------------------------- | ------------------------------------- | ---------------------------------------- |
| `REGRESSION_RUN_ID` env          | `YYYYMMDDTHHMMSS-<6-hex>`             | `20260601T101530-a7f3c2`                 |
| Compose project name             | `regression-<runId>`                  | `regression-20260601T101530-a7f3c2`      |
| Report directory                 | `.regression/reports/<runId>/`        | `.regression/reports/20260601T101530-a7f3c2/` |
| Per-scenario tenant id           | `t-<scenario>-<runId>`                | `t-checkout-20260601T101530-a7f3c2`      |
| Per-scenario user id             | `u-<scenario>-<runId>`                | `u-checkout-20260601T101530-a7f3c2`      |
| Per-scenario email               | `user+u-<scenario>-<runId>@acme-test.local` | `user+u-checkout-20260601T101530-a7f3c2@acme-test.local` |
| `RUN_BASELINE` frozen clock      | `2026-01-01T00:00:00Z` + hash(runId) seconds | deterministic per run, stable within run |

### Frozen-clock contract

```ts
// .regression/fixtures/clock.ts
const runId = process.env.REGRESSION_RUN_ID!;
// hash runId to a 0..86399 second offset so each run picks a different (but stable) instant within 2026-01-01
const offsetSeconds = [...runId].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 0) % 86400;
const baseline = new Date("2026-01-01T00:00:00Z").getTime() + offsetSeconds * 1000;

export const RUN_BASELINE = new Date(baseline);
export const now = (): Date => new Date(baseline);   // every call returns the same instant within a run
```

Compose passes `TZ=UTC` to every service so the *container* clock is also UTC, eliminating off-by-9-hours bugs in Asia/Tokyo CI runners.

### Per-scenario identifier scoping (the most-important pattern)

Two scenarios run in parallel against the same Postgres. Both try to create tenant `acme-corp`. The second `INSERT` fails with a unique-key violation -> the slower scenario goes red intermittently. Fix: scope every identifier per scenario.

```ts
// fixtures/factory.ts
const runId = process.env.REGRESSION_RUN_ID!;
export const scopedId = (scenario: string, kind: "t" | "u" | "o") =>
  `${kind}-${scenario}-${runId}`;
export const scopedEmail = (scenario: string) =>
  `user+${scopedId(scenario, "u")}@acme-test.local`;
```

```ts
// BAD: hard-coded; collides under parallelism
const tenant = "acme-corp";

// GOOD: scoped; cannot collide with any other scenario or any other run
const tenant = scopedId("checkout-happy", "t");
```

### Why each guarantee matters

| Guarantee                          | Failure mode it prevents                                                            |
| ---------------------------------- | ----------------------------------------------------------------------------------- |
| `run-id` minted once               | Two scripts derive different IDs mid-run -> teardown misses half the resources.     |
| Compose project `regression-<runId>` | Parallel CI jobs share `regression` and stomp each other's containers/networks.   |
| Ephemeral named volumes + `down -v` | Yesterday's seed rows leak into today's run; tests pass for the wrong reasons.     |
| Lexicographic seed order           | macOS vs Linux directory order differs -> tests order-dependent in CI but not local. |
| `TZ=UTC` everywhere                | `created_at` assertions pass in UTC dev box, fail at midnight JST in CI.            |
| Frozen `now()`                     | Test asserts "expires in < 1 hour" - passes at 11:59, fails at 12:00.               |
| Per-scenario `scopedId`            | Concurrent scenarios collide on `tenant_id` PK; one goes red, one green, randomly.  |

### What to verify after teardown

Checklist - run after `regression-runner` exits, before declaring the run done.

- [ ] `docker ps --filter "label=com.docker.compose.project=regression-<runId>"` returns zero containers.
- [ ] `docker volume ls --filter "label=com.docker.compose.project=regression-<runId>"` returns zero volumes.
- [ ] `docker network ls --filter "label=com.docker.compose.project=regression-<runId>"` returns zero networks.
- [ ] `.regression/reports/<runId>/junit.xml` exists.
- [ ] `.regression/reports/<runId>/` contains traces only for failed scenarios (Playwright `retain-on-failure`).
- [ ] No stray rows containing `<runId>` in any external (non-ephemeral) datastore - if any exist, the suite touched something it should not have.

If any check fails: do **not** start the next run. Investigate the leak first; a leaking teardown poisons every subsequent run.

### Anti-patterns made concrete

```ts
// BAD: real wall clock; flaky at month boundaries, DST transitions, CI time skew
const expiresSoon = new Date(Date.now() + 60_000);

// GOOD: deterministic relative to the run baseline
import { now } from "../../fixtures/clock";
const expiresSoon = new Date(now().getTime() + 60_000);
```

```yaml
# BAD: anonymous volume - down -v cannot reliably clean it
services:
  db:
    image: postgres@sha256:...
    volumes:
      - /var/lib/postgresql/data        # anonymous

# GOOD: named volume, project-scoped
volumes:
  db-data: {}
services:
  db:
    volumes:
      - db-data:/var/lib/postgresql/data
```

```bash
# BAD: fixed project name - parallel CI jobs collide
docker compose -p regression up -d --wait

# GOOD: per-run project name
docker compose -p "regression-${REGRESSION_RUN_ID}" up -d --wait
```

## Output Format

This skill exports environment variables and emits one file:

| Output                                  | Consumed by                                              |
| --------------------------------------- | -------------------------------------------------------- |
| `REGRESSION_RUN_ID` env                 | `regression-runner`, `regression-scenario-author` factories, `regression-report-format` |
| `PROJECT=regression-<runId>` env        | Every `docker compose` call in `regression-runner`       |
| `TZ=UTC` env (passed through to compose)| Every container, ensuring uniform clock                  |
| `.regression/runs/<runId>.json`         | One-line record: `{ runId, startedAt, profile }` for audit |

## Avoid

- **Regenerating `run-id` inside scenarios.** Mint once; read from env everywhere else.
- **Anonymous volumes.** `down -v` cannot reliably clean them; the next run inherits stale data.
- **`new Date()` / `Date.now()` in scenarios.** Use `now()` from `fixtures/clock.ts`.
- **Hard-coded tenant / user / email.** Always `scopedId` / `scopedEmail`.
- **Reusing the compose project name across runs.** Parallel CI matrices break instantly.
- **Locale-aware sort for seeds.** Byte-wise sort only; `LC_ALL=C` if shell-sorted.
- **Skipping the post-teardown checklist.** A silent volume leak only surfaces three runs later as "phantom rows."
