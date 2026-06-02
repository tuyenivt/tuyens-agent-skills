---
name: regression-data-isolation
description: Per-run isolation for outside-in regression. Mints run-id, names compose project, owns ephemeral volumes, deterministic seed order, frozen clock, per-scenario tenant IDs.
metadata:
  category: testing
  tags: [regression, isolation, run-id, volumes, clock, tenant]
user-invocable: false
---

# Regression Data Isolation

Prevents "passes locally, fails in CI" and "two scenarios collide on tenant_id." Owns four guarantees plus per-scenario identifier scoping.

## When to Use

- At the very start of `task-regression`, before `regression-runner`. Mints `REGRESSION_RUN_ID` and writes the audit record.
- Anywhere a scenario / fixture needs a unique tenant / user / email / order id derived from `run-id`.

## Rules

1. **`run-id` is minted once per run.** Format: `<UTC YYYYMMDDTHHMMSS>-<6 lowercase hex>`. Example: `20260601T101530-a7f3c2`. Exported as `REGRESSION_RUN_ID` and written to `.regression/runs/<runId>.json` (`{ runId, startedAt, profile }`). Never regenerated mid-run; on collision (same-second + 6-hex match) the minter retries.
2. **Compose project name is `regression-<runId>`.** Every `docker compose -p` uses it.
3. **All volumes named and project-scoped.** No anonymous volumes. No host bind-mounts into databases. Wiped via `down -v --remove-orphans`.
4. **Seeds apply in byte-wise lexicographic order.** `LC_ALL=C` when shell-sorted. Numeric prefixes (`00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`) mandatory.
5. **Clock frozen, not real.** `TZ=UTC` on every container at compose level. Test-side code reads `now()` from `fixtures/clock.ts` which returns `RUN_BASELINE` (deterministic per run, stable within run). Never `new Date()` / `Date.now()` directly in scenarios. The skill does not freeze the application's clock - it freezes the test side and the container TZ; tests assert on observable state, not application-internal wall-clock reasoning.
6. **Per-scenario identifier scoping.** Every tenant / user / email / order id derives from `scopedId(<scenario>, <kind>)` which composes `run-id` + scenario name. The `kind` argument is open (any short token); the seven examples below (`t`, `u`, `o`, ...) are convention, not enum.
7. **No identifier overlap with seeds.** Seed files use literal UUIDs in the `seeds/` namespace; scenario-authored IDs live in the `run-id` namespace.
8. **Post-teardown verification.** Run the checklist below before declaring the run done. A failure means the next run starts poisoned.

## Patterns

### Derivation

| Context | Format | Example |
| --- | --- | --- |
| `REGRESSION_RUN_ID` | `YYYYMMDDTHHMMSS-<6-hex>` | `20260601T101530-a7f3c2` |
| Compose project | `regression-<runId>` | `regression-20260601T101530-a7f3c2` |
| Report dir | `.regression/reports/<runId>/` | |
| Per-scenario tenant | `t-<scenario>-<runId>` | `t-checkout-happy-20260601T101530-a7f3c2` |
| Per-scenario email | `user+u-<scenario>-<runId>@acme-test.local` | |
| `RUN_BASELINE` | `2026-01-01T00:00:00Z` + hash(runId) seconds | deterministic per run |

### Minting (Node, the only Node-required surface; non-Node projects still run this from `.regression/` per plugin README)

```ts
// .regression/scripts/mint-run-id.ts
import { randomBytes } from "crypto";
import { writeFileSync, mkdirSync } from "fs";

const ts = new Date().toISOString().replace(/[-:]/g, "").substring(0, 15);  // 20260601T101530
const rand = randomBytes(3).toString("hex");                                 // 6 hex chars
const runId = `${ts}-${rand}`;
const profile = process.env.REGRESSION_PROFILE ?? "local-build";

mkdirSync(".regression/runs", { recursive: true });
writeFileSync(`.regression/runs/${runId}.json`,
  JSON.stringify({ runId, startedAt: new Date().toISOString(), profile }));

process.stdout.write(runId);
```

### Frozen-clock contract

```ts
// .regression/fixtures/clock.ts
const runId = process.env.REGRESSION_RUN_ID!;
const offset = [...runId].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 0) % 86400;
const baseline = new Date("2026-01-01T00:00:00Z").getTime() + offset * 1000;
export const RUN_BASELINE = new Date(baseline);
export const now = (): Date => new Date(baseline);
```

Compose passes `TZ=UTC` to every service so the container clock is also UTC.

### Per-scenario scoping (the central pattern)

Two scenarios in parallel against the same Postgres both try to create tenant `acme-corp`. Second `INSERT` fails on unique key. Fix: scope per scenario.

```ts
// fixtures/factory.ts
const runId = process.env.REGRESSION_RUN_ID!;
export const scopedId = (scenario: string, kind: string) =>
  `${kind}-${scenario}-${runId}`;
export const scopedEmail = (scenario: string) =>
  `user+${scopedId(scenario, "u")}@acme-test.local`;
```

```ts
// BAD: collides under parallelism
const tenant = "acme-corp";

// GOOD: cannot collide with any other scenario or any other run
const tenant = scopedId("checkout-happy", "t");
```

### Post-teardown verification

Run after `regression-runner` exits, before declaring the run done:

- `docker ps --filter "label=com.docker.compose.project=regression-<runId>"` -> 0 containers.
- `docker volume ls --filter "label=com.docker.compose.project=regression-<runId>"` -> 0 volumes.
- `docker network ls --filter "label=com.docker.compose.project=regression-<runId>"` -> 0 networks.
- `.regression/reports/<runId>/junit.xml` exists.
- `.regression/reports/<runId>/traces/` contains only failed-scenario traces (Playwright `retain-on-failure`).
- External (non-ephemeral) datastores have zero rows containing `<runId>`. Registry of in-scope external stores lives in `services.yaml` (any service marked `persistence: external` is the audit target; default scope is none).

If any check fails, do **not** start the next run. Investigate the leak.

## Output Format

| Output | Consumed by |
| --- | --- |
| `REGRESSION_RUN_ID` env | runner, scenario factories, report-format |
| `PROJECT=regression-<runId>` env | every `docker compose` call |
| `TZ=UTC` env | every container |
| `.regression/runs/<runId>.json` | audit; flake-triage reads prior runs |

## Avoid

- Regenerating `run-id` inside scenarios. Mint once.
- Anonymous volumes. `down -v` cannot reliably clean them.
- `new Date()` / `Date.now()` in scenarios.
- Hard-coded tenant / user / email.
- Reusing the compose project name across runs.
- Skipping the post-teardown checklist.
