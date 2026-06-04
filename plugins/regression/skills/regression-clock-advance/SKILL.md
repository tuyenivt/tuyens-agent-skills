---
name: regression-clock-advance
description: App-side clock advance for outside-in regression - libfaketime, restart-with-env, or admin endpoint. For cron / scheduled-job flow tests.
metadata:
  category: testing
  tags: [regression, clock, time-travel, cron, scheduled-jobs]
user-invocable: false
---

# Regression Clock Advance

`regression-data-isolation` freezes the test side and the container TZ; it does NOT freeze application-internal `now()`. Cron / scheduled-job / token-expiry regressions need the app to think time has passed. Three mechanisms, opt-in per flow.

## When to Use

- Flow has `clock: { advanceMs: <N>, mechanism: <one-of> }` in `flows.yaml`.
- The user passes `--clock <ms>` to `task-regression-scenario`.

**Not for:** flows that only need the deterministic-baseline behavior `regression-data-isolation` already provides.

## Rules

1. **Three mechanisms; the user picks per flow.** No global default. Each has different blast radius.

   | mechanism | How | Blast radius | Service-side cost |
   | --- | --- | --- | --- |
   | `libfaketime` | Image variant with `LD_PRELOAD=libfaketime.so.1`, `FAKETIME=<offset>` | Whole container | Image change; not all base images compatible |
   | `restart-env` | `docker compose up -d --no-deps <svc>` after setting `APP_CLOCK_OFFSET_MS=<N>` | Whole container, requires code support | App must read `APP_CLOCK_OFFSET_MS` from env |
   | `admin-endpoint` | `POST /__test/advance-clock` with `{advanceMs}` body | Per-request, in-process only | App must expose the endpoint (test-build only) |

2. **The mechanism must be declared in `services.yaml`,** not invented in the scenario.

   ```yaml
   services:
     - name: api
       clockAdvance:
         mechanism: admin-endpoint
         endpoint: POST /__test/advance-clock
   ```

3. **Clock advance is a per-scenario action, not a per-run setting.** The `regression-data-isolation` `RUN_BASELINE` stays stable; the advance is layered on top.
4. **Reset on scenario teardown.** Every clock-advance scenario emits an `afterEach` that resets the clock (`POST /__test/advance-clock {advanceMs: 0}` for admin-endpoint; container restart for the other two). Without this, scenario ordering becomes load-bearing - which violates the per-run baseline stability `regression-data-isolation` Rule 5 guarantees.
5. **`admin-endpoint` requires a test-build guard.** The endpoint must 404 under prod build flags. The skill emits a one-time pre-flight: hit the endpoint on the first scenario use; if response is `200`, proceed; if anywhere outside test-build, abort with `regression-clock-advance: __test/advance-clock returned <status> - not a test build.`

## Patterns

### `clock:` field shape

```yaml
- name: subscription-expires-after-30-days
  kind: api
  clock:
    advanceMs: 2592000000   # 30 days
    mechanism: admin-endpoint
```

### Helper signatures

```ts
import { advanceClock, resetClock } from "../../fixtures/clock-advance";

test.afterEach(async () => { await resetClock("api"); });

test("@smoke subscription expires after 30 days", async ({ request }) => {
  const subId = scopedId(SCENARIO, "sub");
  await request.post("/subscriptions", { data: { id: subId, plan: "monthly" } });
  await advanceClock("api", 2592000000);   // 30 days
  await pollUntil(async () => {
    const got = await request.get(`/subscriptions/${subId}`);
    return got.ok() && (await got.json()).status === "expired";
  });
});
```

The helpers dispatch by `services.yaml#services[].clockAdvance.mechanism`. User does not pick at call time.

### `libfaketime` image variant

```yaml
api:
  build:
    context: ../api
    dockerfile: Dockerfile.test       # adds libfaketime; user-owned
  environment:
    LD_PRELOAD: /usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1
    FAKETIME: ${API_FAKETIME_OFFSET:-+0}
```

The discover-time inventory writer surfaces "Dockerfile.test must exist and install `libfaketime`" as a follow-up - this skill does not write into sibling repos.

### Restart-env mechanism caveat

`restart-env` requires the app to read `APP_CLOCK_OFFSET_MS` at boot and apply it on every `now()` call. The skill checks for the presence of that env var in `services.yaml`; absent -> emit warning, do not auto-add.

### Why not `mock-time` at the test side

Playwright `page.clock` exists but only affects the browser tab. API and DB queries still see the host clock. For backend cron regressions, the only sound option is to move the app's clock - hence three mechanisms above.

## Output Format

- `.regression/fixtures/clock-advance/index.ts` (helpers, committed).
- Scenario emission adds `afterEach` reset + `advanceClock` calls.
- `regression-compose-build` consumes `services.yaml#services[].clockAdvance.mechanism: libfaketime` to add env vars.

## Avoid

- Faking time on the test side alone (Playwright `page.clock`) for backend cron tests.
- Forgetting the `afterEach` reset - scenario ordering becomes load-bearing.
- Using `admin-endpoint` in prod builds - the endpoint must be guarded.
- Mixing mechanisms across scenarios in the same suite (pick one per service).
- Hardcoding `advanceMs` in the scenario - it belongs in `flows.yaml#clock`.
