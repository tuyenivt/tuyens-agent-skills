---
name: regression-fixture-factory
description: Test-data factory pattern beyond scopedId / scopedEmail - typed builders for orders, tenants, subscriptions. Pure builders, idempotent within run.
metadata:
  category: testing
  tags: [regression, fixtures, factory, test-data, builders]
user-invocable: false
---

# Regression Fixture Factory

`scopedId` + `scopedEmail` from `regression-data-isolation` cover identifier scoping. Real flows need typed builders: an order with status, an amount, a tenant; a tenant with a plan; a subscription with billing period. This skill documents the factory contract so factories under `.regression/fixtures/factories/` stay consistent.

## When to Use

- A scenario needs a richer test object than `scopedId` produces.
- The same multi-field entity appears in 3+ scenarios.

**Not for:** one-off ad-hoc objects in a single scenario. Inline literals are fine.

## Rules

1. **Factory functions are typed builders, not direct inserters.** `scopedOrder({ status, amount })` returns an object; persistence is the caller's choice (POST to API, INSERT via DB helper, or use as a JSON body).
2. **Every required field defaults from the scenario context.** Tenant defaults to `scopedId(SCENARIO, "t")`. User email defaults to `scopedEmail(SCENARIO)`. Status defaults to a documented "neutral" value. Only the fields the test actually cares about appear in the call.
3. **Factories are idempotent within a run.** Calling `scopedOrder()` twice with the same SCENARIO returns the same id. To force a distinct one, pass a `discriminator`: `scopedOrder({ discriminator: "second" })`.
4. **Cleanup is a separate concern.** Factories never auto-register cleanup. `regression-data-isolation` Rule 8's post-teardown check + ephemeral DB volumes handles per-run cleanup. Factories are pure builders.
5. **Output schema must match the producing service's contract.** `scopedOrder()`'s shape must validate against `POST /orders`'s request body schema. The factory imports the contract cache from `regression-contract-check` when the service has one.

## Patterns

### Factory layout

```
.regression/fixtures/factories/
  index.ts                # re-exports
  order.ts                # scopedOrder({...})
  tenant.ts               # scopedTenant({...})
  subscription.ts         # scopedSubscription({...})
```

### Canonical factory

```ts
// fixtures/factories/order.ts
import { scopedId, scopedEmail } from "../factory";   // primitives from regression-data-isolation

export interface OrderInput {
  status?: "pending" | "confirmed" | "shipped" | "cancelled";
  amount?: number;
  currency?: string;
  items?: Array<{ sku: string; qty: number }>;
  discriminator?: string;
}

export interface Order {
  id: string;
  tenantId: string;
  userEmail: string;
  status: "pending" | "confirmed" | "shipped" | "cancelled";
  amount: number;
  currency: string;
  items: Array<{ sku: string; qty: number }>;
}

export const scopedOrder = (scenario: string, input: OrderInput = {}): Order => {
  const kind = `o${input.discriminator ?? ""}`;
  return {
    id: scopedId(scenario, kind),
    tenantId: scopedId(scenario, "t"),
    userEmail: scopedEmail(scenario),
    status: input.status ?? "pending",
    amount: input.amount ?? 1000,
    currency: input.currency ?? "USD",
    items: input.items ?? [{ sku: "ACME-1", qty: 1 }],
  };
};
```

### Usage in a scenario

```ts
const order = scopedOrder(SCENARIO, { status: "confirmed", amount: 2500 });
const resp = await request.post("/orders", { data: order });
expect(resp.status()).toBe(201);
```

### Cross-factory composition

```ts
// fixtures/factories/subscription.ts
import { scopedId } from "../factory";
import { RUN_BASELINE } from "../clock";       // regression-data-isolation
import { scopedTenant } from "./tenant";

export const scopedSubscription = (scenario: string, input: { plan?: string } = {}) => ({
  id: scopedId(scenario, "sub"),
  tenant: scopedTenant(scenario),    // typed Tenant
  plan: input.plan ?? "monthly",
  startsAt: RUN_BASELINE,
});
```

### Anti-pattern: factory that POSTs

```ts
// BAD - factory does I/O
export const createOrder = async (scenario, input) => {
  const order = { id: scopedId(scenario, "o"), ... };
  await fetch("/orders", { method: "POST", body: JSON.stringify(order) });
  return order;
};

// GOOD - factory builds, caller persists
const order = scopedOrder(SCENARIO, {...});
const resp = await request.post("/orders", { data: order });
```

The caller controls auth, the request fixture, error handling. The factory is unit-testable in isolation.

### Contract-conformance assertion

When `regression-contract-check` has a cached schema for the factory's target endpoint, the factory's tests assert the output validates:

```ts
// fixtures/factories/order.test.ts
import { matchesContract } from "../contracts";
test("scopedOrder output matches POST /orders request schema", () => {
  const out = scopedOrder("test", {});
  expect(matchesContract(out, "api/openapi.yaml#/paths/~1orders/post/requestBody").ok).toBe(true);
});
```

## Output Format

- `.regression/fixtures/factories/<entity>.ts` per entity (committed).
- `.regression/fixtures/factories/index.ts` re-exports (committed).
- Factory tests under `.regression/fixtures/factories/<entity>.test.ts` (committed) - run as part of the same Playwright invocation.

## Avoid

- Factories that do I/O (POST, DB INSERT). They build; callers persist.
- Auto-registering cleanup - per-run isolation handles it.
- Factories that read env without going through `scopedId` / `scopedEmail`.
- Encoding business rules in factories (validation, defaults that mirror the app's defaults exactly). The factory is a *test*-data builder; matching the app's defaults too closely hides bugs where the app's default changes.
- One mega-factory file. One file per entity.
