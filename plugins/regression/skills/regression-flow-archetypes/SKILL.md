---
name: regression-flow-archetypes
description: Prebuilt regression patterns - OAuth callback, signed upload, feature-flag matrix, idempotency, rate-limit, cache invalidation, tenant isolation.
metadata:
  category: testing
  tags: [regression, archetypes, patterns, oauth, idempotency, multi-tenant]
user-invocable: false
---

# Regression Flow Archetypes

Library of opinionated scenario templates for recurring flow shapes. `regression-scenario-author` reads `flow.archetype` to pick a template; the user writes 5 lines of flow YAML instead of 80 lines of scenario code.

## When to Use

- A flow entry sets `archetype: <name>` (one of the names below).
- The user passes `--archetype <name>` to `task-regression-scenario`.

## Rules

1. **Archetypes are scaffolds, not enforcement.** The generated scenario is editable; the archetype lives in the emit step only.
2. **Each archetype owns its own required-fields list.** `oauth-callback` requires `archetype.idp` and `archetype.scopes`; missing required fields aborts emission with a specific message.
3. **`@negative` is archetype-specific.** Idempotency-key retry's negative is "different body, same key -> 409". Rate-limit's negative is "N requests under the limit pass". No archetype emits a fake / generic `@negative`.
4. **POMs are user-owned.** Browser archetypes reference POM method names (`pom.placeOrder()`) the user must implement; the lint step surfaces missing methods.

## Patterns

### Archetype index

| Name | Shape | Required `archetype:` fields |
| --- | --- | --- |
| `oauth-callback` | API setup mock IdP -> browser navigates to login -> callback -> assert session cookie + DB row | `idp`, `scopes`, `redirectUri` |
| `signed-upload` | POST /signed-url -> PUT to signed URL -> assert object exists + DB row references it | `bucket`, `objectKeyPattern` |
| `feature-flag-matrix` | Two flag states -> same flow yields two observable outcomes | `flagKey`, `variants` (list of `{name, value, expect}`) |
| `idempotency-key-retry` | POST + same key -> second call returns same result, no side-effect duplication | `endpoint`, `idempotencyHeader` |
| `rate-limit-429` | N+1 requests under the limit pass, N+2 returns 429 with `Retry-After` | `endpoint`, `limit`, `windowSec` |
| `cache-invalidation` | GET -> mutate -> GET again -> assert new value within bound | `getEndpoint`, `mutateEndpoint`, `boundMs` |
| `tenant-isolation-cross-read` | Tenant A creates resource -> Tenant B reads -> 404/403 | `endpoint`, `tenantHeader` |

### `archetype:` field shape

```yaml
# Map form (canonical when the archetype has required params)
- name: checkout-with-flag-off
  kind: api
  archetype:
    name: feature-flag-matrix
    flagKey: new-checkout-v2
    variants:
      - { name: "off", value: false, expect: "old checkout response shape" }
      - { name: "on",  value: true,  expect: "new checkout response shape" }

# Scalar form (shorthand, reserved for a param-free archetype)
- name: ping-roundtrip
  kind: api
  archetype: <param-free-archetype-name>
```

The `archetype:` value is either a scalar (the archetype name) or a map with a required `name:` field plus archetype-specific params. Never both at the same level - YAML disallows duplicate keys. The map form is canonical. All seven cataloged archetypes have required fields, so each uses the map form; the scalar form exists for a future param-free archetype and never names one outside the catalog.

### Example emission - `idempotency-key-retry`

Flow:

```yaml
- name: payment-retry-double-debit-inc-2026-04-12
  kind: api
  archetype:
    name: idempotency-key-retry
    endpoint: POST /payments
    idempotencyHeader: Idempotency-Key
```

Emits:

```ts
const SCENARIO = "payment-retry-double-debit-inc-2026-04-12";

test.describe("idempotency-key-retry POST /payments", () => {
  test("@smoke same key returns same result, no double side-effect", async ({ request }) => {
    const key = scopedId(SCENARIO, "ik");
    const body = { amount: 1000, currency: "USD", merchant: scopedId(SCENARIO, "m") };
    const first  = await request.post("/payments", { headers: { "Idempotency-Key": key }, data: body });
    const second = await request.post("/payments", { headers: { "Idempotency-Key": key }, data: body });
    expect(first.status()).toBe(201);
    expect(second.status()).toBe(200);
    expect(await second.json()).toEqual(await first.json());
    // assert exactly one DB side-effect
    expect(await rowExists("payments", { idempotency_key: key })).toBe(true);
  });

  test("@negative different body, same key returns 409", async ({ request }) => {
    const key = scopedId(SCENARIO, "ik2");
    await request.post("/payments", { headers: { "Idempotency-Key": key }, data: { amount: 1000, currency: "USD" } });
    const conflict = await request.post("/payments", { headers: { "Idempotency-Key": key }, data: { amount: 9999, currency: "USD" } });
    expect(conflict.status()).toBe(409);
  });
});
```

The archetype's `@negative` is canonical: "different body, same key -> 409". The user can override by supplying their own `@negative` description in `task-regression-scenario --negative`.

### Missing required-fields handling

```yaml
- name: foo
  archetype: oauth-callback
  # missing idp / scopes / redirectUri
```

-> `regression-flow-archetypes: oauth-callback requires idp, scopes, redirectUri; flow 'foo' is missing idp, scopes, redirectUri.` Abort.

## Output Format

- Scenario file with archetype-specific `@smoke` and `@negative` tests.
- The emitted file's header includes `// Archetype: <name>` after `// Flow:` and `// Kind:` for traceability.

## Avoid

- Generic `@negative` when the archetype has a canonical one - if a user override is empty, emit the canonical.
- Mutating the flow entry to fill in archetype-required fields. The scenario author surfaces the gap; the user resolves it in `flows.yaml`.
- Adding stack-specific assertions (Spring vs Express response codes) - archetypes are stack-agnostic.
- Inventing archetypes silently - the seven above are the catalog. New ones get added by editing this skill.
