---
name: regression-scenario-author
description: Playwright scenario authoring template for outside-in regression. Emits api / browser / mixed .spec.ts with golden + negative paths, idempotent setup, data factories.
metadata:
  category: testing
  tags: [regression, playwright, scenarios, typescript, e2e]
user-invocable: false
---

# Regression Scenario Author

> Load `Use skill: regression-flow-extract` for the `flows.yaml` shape that feeds this skill, and `Use skill: regression-data-isolation` for the `run-id`-derived data factory contract.

Emits a single Playwright `.spec.ts` file under `.regression/scenarios/<kind>/<flow>.spec.ts` from a named flow. `kind` (`api` / `browser` / `mixed`) is taken from the flow entry; the template differs by kind.

## When to Use

- During `task-regression-scenario "<flow-name>"` after the flow is resolved from `flows.yaml`.
- When refreshing an existing scenario after the flow definition changes (diff-and-confirm, never silent rewrite).

## Rules

1. **One file per flow.** Filename matches `flows.yaml#name`. Location is `scenarios/<kind>/<flow>.spec.ts`.
2. **One golden-path scenario, one negative-path scenario - both required.** A flow without an explicit negative scenario is rejected by the self-check. Tag golden `@smoke`, tag negative `@negative`.
3. **Idempotent setup per scenario.** A scenario's setup uses a per-scenario data factory derived from `run-id` + scenario name (see `regression-data-isolation`). Re-running the same scenario in the same run must not collide.
4. **No raw sleeps.** Async side effects use a bounded poll (`expect.poll` or a `pollUntil` helper): max 5s total, 200ms backoff. Hard-coded `setTimeout` / `page.waitForTimeout` are forbidden.
5. **No retries by default.** Playwright `retries: 0` in config. A failure is a failure. Explicit per-test `test.describe.configure({ retries: N })` is allowed only with an inline comment naming the known flake.
6. **Page Object Model for browser flows.** Browser scenarios import page objects from `.regression/fixtures/pages/`; they do not call `page.locator(...)` directly.
7. **Pinned dependencies.** `package.json` pins `@playwright/test` to an exact version; `package-lock.json` is committed.
8. **Kind-correct fixtures.** `api` -> `request` only. `browser` -> `page` only. `mixed` -> both, with API doing setup and browser doing the user-visible assertion (never the reverse).

## Patterns

### Data factory derived from `run-id`

```ts
// .regression/fixtures/factory.ts
const runId = process.env.REGRESSION_RUN_ID!;
export const scopedId = (scenario: string, kind: string) =>
  `${kind}-${scenario}-${runId}`;          // e.g. tenant-checkout-happy-20260601T101530-a7f3c2
export const scopedEmail = (scenario: string) =>
  `user+${scopedId(scenario, "u")}@acme-test.local`;
```

Every scenario imports `scopedId` / `scopedEmail` and never hardcodes a tenant, user, or email - that is what makes two scenarios safe against the same DB.

### `kind: api` template

```ts
// scenarios/api/order-create.spec.ts
import { test, expect } from "@playwright/test";
import { scopedEmail, scopedId } from "../../fixtures/factory";
import { pollUntil } from "../../fixtures/poll";

const SCENARIO = "order-create";

test.describe("POST /orders", () => {
  test("@smoke creates an order and persists it", async ({ request }) => {
    const email = scopedEmail(SCENARIO);
    const tenant = scopedId(SCENARIO, "t");

    const created = await request.post("/orders", {
      data: { tenant, email, items: [{ sku: "ACME-1", qty: 1 }] },
    });
    expect(created.status()).toBe(201);
    const { id } = await created.json();

    // bounded read-after-write
    await pollUntil(async () => {
      const got = await request.get(`/orders/${id}`);
      return got.status() === 200 && (await got.json()).status === "confirmed";
    }, { timeoutMs: 5000, intervalMs: 200 });
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
// scenarios/browser/checkout.spec.ts
import { test, expect } from "@playwright/test";
import { CheckoutPage } from "../../fixtures/pages/checkout";
import { scopedEmail } from "../../fixtures/factory";

const SCENARIO = "checkout";

test.describe("Checkout UI", () => {
  test("@smoke completes a checkout end-to-end", async ({ page }) => {
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

API does the setup (faster, no UI flake surface), browser does the user-visible assertion.

```ts
// scenarios/mixed/order-confirmation.spec.ts
import { test, expect } from "@playwright/test";
import { OrdersPage } from "../../fixtures/pages/orders";
import { scopedEmail, scopedId } from "../../fixtures/factory";

const SCENARIO = "order-confirmation";

test.describe("Order confirmation page", () => {
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

  test("@negative shows 'not found' for an order in another tenant", async ({ request, page }) => {
    const otherTenant = scopedId(SCENARIO, "t-other");
    const orders = new OrdersPage(page);
    await orders.goto(`stranger-${otherTenant}`);
    await expect(orders.notFound).toBeVisible();
  });
});
```

### Read-after-write poll helper

```ts
// fixtures/poll.ts
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

### Bad / good

```ts
// BAD: shared email across scenarios -> tenant_id collision on parallel runs
const email = "tester@acme-test.local";

// GOOD: per-scenario, run-id-derived
const email = scopedEmail(SCENARIO);
```

```ts
// BAD: raw sleep hides timing issues
await page.waitForTimeout(3000);

// GOOD: bounded poll with explicit success condition
await pollUntil(async () => (await request.get(`/orders/${id}`)).ok());
```

```ts
// BAD: locator inside scenario
await page.locator("#place-order-btn").click();

// GOOD: page object
await new CheckoutPage(page).placeOrder();
```

```ts
// BAD: silent retry masking flake
test.describe.configure({ retries: 3 });

// GOOD: retries: 0, or a single retry with a TODO naming the root cause
// retries: 1 - flake tracked in REG-142; remove after fix
```

### Required `package.json` shape

```json
{
  "name": "regression",
  "private": true,
  "devDependencies": {
    "@playwright/test": "1.49.1",
    "pg": "8.13.1"
  },
  "scripts": {
    "test": "playwright test --reporter=junit,line"
  }
}
```

Exact version pin, not `^` or `~`. `package-lock.json` committed.

### Tag conventions

| Tag         | Meaning                                                                          |
| ----------- | -------------------------------------------------------------------------------- |
| `@smoke`    | Golden path. Selected by `npx playwright test --grep @smoke` for fast subsets.    |
| `@negative` | Explicit failure / validation / authz-denial scenario. Required once per flow.   |
| `@slow`     | Optional. Excluded from `@smoke` runs. Use sparingly.                            |

## Output Format

`.regression/scenarios/<kind>/<flow>.spec.ts` containing exactly two tests: one `@smoke` golden, one `@negative`. Imports `scopedId` / `scopedEmail` from `fixtures/factory.ts`, `pollUntil` from `fixtures/poll.ts`, and (for `browser` / `mixed`) page objects from `fixtures/pages/`. Header comment lists the source flow name and `kind`.

## Avoid

- **Scenarios without a `@negative` counterpart.** The self-check fails.
- **`page.waitForTimeout` / `setTimeout`-based waits.** Use `expect.poll` or `pollUntil`.
- **Inline locators in browser scenarios.** Page objects only.
- **Cross-scenario data sharing.** A scenario's state must be derivable from its own `SCENARIO` constant + `run-id`.
- **Default retries.** Retries mask real bugs; opt-in per-test with a written cause.
- **`request` inside a `browser` scenario or `page` inside an `api` scenario.** Pick the right kind, or use `mixed`.
- **Loose `@playwright/test` version (`^`, `~`).** Reproducibility requires exact pins.
