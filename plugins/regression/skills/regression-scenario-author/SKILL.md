---
name: regression-scenario-author
description: Playwright scenario authoring template for outside-in regression. Emits api / browser / mixed .spec.ts with golden + negative paths, idempotent setup, data factories.
metadata:
  category: testing
  tags: [regression, playwright, scenarios, typescript, e2e]
user-invocable: false
---

# Regression Scenario Author

> Consumes a flow entry from `flows.yaml` (see `regression-flow-extract` for the shape) and the data-factory contract from `regression-data-isolation`. Emits one `.spec.ts` under `.regression/scenarios/<kind>/<flow>.spec.ts`.

## When to Use

- During `task-regression-scenario "<flow-name>"`.
- When refreshing an existing scenario after the flow definition changes (the consuming workflow handles the diff).

## Rules

1. **One file per flow.** Filename basename equals the flow name; the `SCENARIO` constant equals the filename basename.
2. **Two tests per file: one `@smoke` golden, one `@negative`.** The `@negative` test exists in source - `test.fixme` / `test.skip` are not allowed for the `@negative` slot, because they bypass the regression guarantee the rule encodes. If the negative variant is genuinely unknown at authoring time, the workflow stops and asks the user to specify before emitting.
3. **Idempotent setup per scenario.** Use the factory from `fixtures/factory.ts` (owned by `regression-data-isolation`). Re-running the same scenario in the same run must not collide.
4. **Bounded async waits only.** `expect.poll` or `pollUntil` (max 5s, 200ms backoff). `setTimeout` / `page.waitForTimeout` / raw `sleep` are forbidden.
5. **Default retries 0.** Per-scenario `test.describe.configure({ retries: N })` is allowed only with a comment matching `/^// flake (REG-\d+|TODO-[a-z0-9-]+); remove after fix$/` - the literal token tells `regression-flakiness-triage` this is an intentional retry annotation.
6. **Page Object Model for browser flows.** Browser tests import page objects from `.regression/fixtures/pages/`; no `page.locator(...)` in test files. POMs are user-owned in `fixtures/pages/`; this skill emits scenarios that import them but does not generate POMs.
7. **Kind-correct fixtures.** `api` -> `request` only. `browser` -> `page` only. `mixed` -> both; API does setup, browser does the user-visible assertion. Exception: a browser-entry `mixed` flow whose API surface is unsuitable for setup (e.g. setup requires logging in through a UI redirect) may invert; the emitted file documents the inversion in a header comment.
8. **Out-of-fixture transports.** Kafka publishes, gRPC streams, raw WebSocket frames - observe via downstream HTTP / DB state. This skill does not invent fixtures for transports Playwright does not own.

## Patterns

### Imports for every emitted file

```ts
import { test, expect } from "@playwright/test";
import { scopedId, scopedEmail } from "../../fixtures/factory";    // regression-data-isolation owns
import { pollUntil } from "../../fixtures/poll";                    // see helper below
```

The `factory.ts` and `poll.ts` modules must exist under `.regression/fixtures/`. They are user-owned (created during discover) - this skill emits scenarios that import them.

### `pollUntil` (the helper this skill assumes exists)

```ts
// .regression/fixtures/poll.ts - user-owned, written during discover
export async function pollUntil(
  predicate: () => Promise<boolean>,
  { timeoutMs = 5000, intervalMs = 200 } = {},
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`pollUntil exceeded ${timeoutMs}ms`);
}
```

`setTimeout` inside the helper is allowed; in scenarios it is not.

### `kind: api` template

```ts
const SCENARIO = "order-create";    // equals filename basename

test.describe("POST /orders", () => {
  test("@smoke creates an order and persists it", async ({ request }) => {
    const email = scopedEmail(SCENARIO);
    const tenant = scopedId(SCENARIO, "t");

    const created = await request.post("/orders", {
      data: { tenant, email, items: [{ sku: "ACME-1", qty: 1 }] },
    });
    expect(created.status()).toBe(201);
    const { id } = await created.json();

    await pollUntil(async () => {
      const got = await request.get(`/orders/${id}`);
      return got.status() === 200 && (await got.json()).status === "confirmed";
    });
  });

  test("@negative rejects unknown SKU with 422", async ({ request }) => {
    const tenant = scopedId(SCENARIO, "t");
    const resp = await request.post("/orders", {
      data: { tenant, email: scopedEmail(SCENARIO), items: [{ sku: "DOES-NOT-EXIST", qty: 1 }] },
    });
    expect(resp.status()).toBe(422);
    expect((await resp.json()).error).toMatch(/unknown sku/i);
  });
});
```

### `kind: browser` template

```ts
import { CheckoutPage } from "../../fixtures/pages/checkout";

const SCENARIO = "checkout";

test.describe("Checkout UI", () => {
  test("@smoke completes checkout end-to-end", async ({ page }) => {
    const checkout = new CheckoutPage(page);
    await checkout.goto();
    await checkout.fillEmail(scopedEmail(SCENARIO));
    await checkout.placeOrder();
    await expect(checkout.confirmation).toHaveText(/thank you/i);
  });

  test("@negative shows validation error for empty cart", async ({ page }) => {
    const checkout = new CheckoutPage(page);
    await checkout.goto();
    await checkout.placeOrder();
    await expect(checkout.error).toHaveText(/cart is empty/i);
  });
});
```

### `kind: mixed` template

API setup, browser assertion (the default direction).

```ts
import { OrdersPage } from "../../fixtures/pages/orders";

const SCENARIO = "order-confirmation";

test.describe("Order confirmation", () => {
  test("@smoke shows a confirmed order created via API", async ({ request, page }) => {
    const tenant = scopedId(SCENARIO, "t");
    const created = await request.post("/orders", {
      data: { tenant, email: scopedEmail(SCENARIO), items: [{ sku: "ACME-1", qty: 1 }] },
    });
    expect(created.status()).toBe(201);
    const { id } = await created.json();

    const orders = new OrdersPage(page);
    await orders.goto(id);
    await expect(orders.status).toHaveText("confirmed");
  });

  test("@negative shows 'not found' for an order in another tenant", async ({ page }) => {
    const otherTenant = scopedId(SCENARIO, "t-other");
    const orders = new OrdersPage(page);
    await orders.goto(`stranger-${otherTenant}`);
    await expect(orders.notFound).toBeVisible();
  });
});
```

### DB-state assertion (when `observableOutcome` is a row)

API and mixed templates may assert DB state directly using `pg` / `mysql2` / `mongodb` clients connecting through the compose network from the test runner. The skill emits the scenario; the connection helper lives in `.regression/fixtures/db.ts`. Example for `api`:

```ts
import { rowExists } from "../../fixtures/db";

await pollUntil(() => rowExists("orders", { id, status: "confirmed" }));
```

### Tag conventions

| Tag | Meaning |
| --- | --- |
| `@smoke` | Golden path. Selected by `--grep @smoke`. |
| `@negative` | Validation / authz / conflict. Required once per flow. |

`@slow` and similar project tags are out of this skill's scope.

### Bad / good

```ts
// BAD: shared email across scenarios -> collision under parallelism
const email = "tester@acme-test.local";
// GOOD
const email = scopedEmail(SCENARIO);
```

```ts
// BAD: raw sleep
await page.waitForTimeout(3000);
// GOOD: bounded poll with explicit success condition
await pollUntil(async () => (await request.get(`/orders/${id}`)).ok());
```

```ts
// BAD: locator in test
await page.locator("#place-order-btn").click();
// GOOD: page object
await new CheckoutPage(page).placeOrder();
```

```ts
// BAD: silent retries
test.describe.configure({ retries: 3 });

// GOOD: documented per Rule 5
test.describe.configure({ retries: 1 });
// flake REG-142; remove after fix
```

## Output Format

`.regression/scenarios/<kind>/<flow>.spec.ts`. Header comment lists `Flow:`, `Kind:`, and any kind-inversion note. Imports `scopedId` / `scopedEmail` from `fixtures/factory`, `pollUntil` from `fixtures/poll`, page objects from `fixtures/pages/` for `browser` / `mixed`, DB helpers from `fixtures/db` when asserting on rows.

`package.json` / `package-lock.json` are owned by the discover workflow, not this skill. This skill never modifies them.

## Avoid

- Scenarios without an executable `@negative`. `test.fixme` does not satisfy.
- `page.waitForTimeout` / `setTimeout` in tests.
- Inline locators in browser tests.
- Cross-scenario data sharing.
- Default retries.
- Invented fixtures for Kafka / gRPC streaming / raw WebSocket.
- Loose `@playwright/test` version (`^` / `~`) - exact pins only (enforced by the discover-written `package.json`).
