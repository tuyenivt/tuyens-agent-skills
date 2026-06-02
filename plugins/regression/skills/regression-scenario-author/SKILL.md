---
name: regression-scenario-author
description: Playwright scenario authoring template for outside-in regression. Emits api/browser/mixed .spec.ts plus from-story flows.yaml drafting with no-fabrication rules.
metadata:
  category: testing
  tags: [regression, playwright, scenarios, typescript, e2e]
user-invocable: false
---

# Regression Scenario Author

> Consumes a flow entry from `flows.yaml` (shape in `regression-flow-extract`) and the identifier-scoping contract from `regression-data-isolation`. Emits one `.spec.ts` under `.regression/scenarios/<kind>/<flow>.spec.ts`. In from-story mode also drafts the upstream `flows.yaml` entry.

## When to Use

- During `task-regression-scenario "<flow-name>"` (from-flow mode).
- During `task-regression-scenario --from <text-or-path>` (from-story mode) - drafts the `flows.yaml` entry from prose before scaffolding.
- When refreshing an existing scenario after the flow definition changes (the consuming workflow handles the diff).

## Rules

1. **One file per flow, basename = flow name.** A `const SCENARIO = "<flow-name>"` constant equals the filename basename and is passed to every `scopedId` / `scopedEmail` call. The identifier-scoping contract belongs to `regression-data-isolation`.
2. **Two tests per file: one `@smoke` golden, one `@negative`.** Both must execute. `test.fixme` / `test.skip` in the `@negative` slot bypass the regression guarantee this skill encodes. If the negative variant is genuinely unknown at authoring time, stop and ask before emitting - never silently emit a fixme.
3. **Idempotent setup.** All test-side identifiers go through `scopedId(SCENARIO, <kind>)` / `scopedEmail(SCENARIO)`. Re-running the same scenario in the same run must not collide.
4. **Bounded async waits only.** Use `pollUntil(predicate, { timeoutMs?: number, intervalMs?: number })` from `fixtures/poll` (defaults: 5000ms timeout, 200ms backoff). Override `timeoutMs` when the flow's `observableOutcome` states a tighter bound (`"within 3s"` -> `{ timeoutMs: 3000 }`). `setTimeout` / `page.waitForTimeout` / raw `sleep` in scenarios are forbidden. The helper's implementation is owned elsewhere - this skill only consumes its signature.
5. **Default retries 0.** Per-scenario `test.describe.configure({ retries: N })` is allowed only when the line immediately following the `configure(...)` call is a comment matching `^// flake (REG-\d+|TODO-[a-z0-9-]+); remove after fix$`. The literal token is what `regression-flakiness-triage` greps for.
6. **POM for browser flows.** Browser / mixed tests import page objects from `.regression/fixtures/pages/<name>`. No `page.locator(...)` in scenarios. POM files and their method surface are user-owned; this skill calls methods by intent name (`pom.goto()`, `pom.placeOrder()`, `pom.fillForm(data)`) and lets the user implement them. The scenario must compile against the POM the user wrote; if it does not, the lint / dry-run step of `task-regression-scenario` surfaces the mismatch.
7. **Fixtures by kind.**

   | `kind`    | Allowed Playwright fixtures | Default direction                                                                   |
   | --------- | --------------------------- | ----------------------------------------------------------------------------------- |
   | `api`     | `request` only              | -                                                                                   |
   | `browser` | `page` only                 | -                                                                                   |
   | `mixed`   | `request` and `page`        | API does setup, browser does the user-visible assertion. Inversion allowed (Rule 8). |

8. **Mixed-kind inversion when the entry is browser.** When the flow's `entryPoint.service` has `role: frontend` in `services.yaml`, the browser performs the action and the assertion observes via API and / or DB - regardless of whether API setup would have been technically possible. Document the inversion in a one-line header comment: `// kind: mixed; entry=browser; assertion=DB+UI`. Backend entry -> default direction (API setup, browser asserts) - no inversion comment needed. Mid-flow HTTP hop assertions inside a browser-driven `@smoke` use `page.waitForResponse(...)`; this is the only sanctioned pattern for asserting on an in-flight network call.
9. **Out-of-fixture transports observed via downstream state.** Kafka publishes, gRPC streams, raw WebSocket frames - assert on the resulting HTTP response or DB row through `pollUntil`. This skill never invents fixtures for transports Playwright does not own.
10. **From-story mode: no fabrication.** Service names, endpoint paths, and observable outcomes absent from the input become `<USER FILL: ...>` placeholders in `flows.yaml`. Plausible guesses are forbidden. The marker lives only in `flows.yaml`, never in the emitted `.spec.ts`.
11. **From-story mode: evidence is mandatory.** At least one `evidence:` entry citing the source. The list is a sequence of single-key mappings; conventional keys are `ticket` / `incident` / `commit` / `reporter` / `reported` / `repro` / `url`, but any kebab-case key is accepted. Empty list -> abort, no file changes.
12. **Refuse to scaffold over unresolved `<USER FILL>`.** Before emitting the `.spec.ts`, scan the resolved flow entry. Any `<USER FILL>` in `entryPoint`, `hops`, or `observableOutcome` -> stop and surface to the user; the consuming workflow exits non-zero. The from-story drafting step is the legitimate producer of these markers; the scenario authoring step is the gate that demands they be resolved.

## Patterns

### Imports

```ts
import { test, expect } from "@playwright/test";
import { scopedId, scopedEmail } from "../../fixtures/factory";   // regression-data-isolation
import { pollUntil } from "../../fixtures/poll";                  // user-owned helper
```

For browser / mixed tests add the relevant page object; for DB-state assertions add `import { rowExists } from "../../fixtures/db"` (db helper owned by this skill's emitted scenarios - signature `rowExists(table: string, where: Record<string, unknown>): Promise<boolean>`; engine list comes from `regression-service-inventory#engine`).

### Canonical template (`kind: api`)

The api template is the reference; browser and mixed differ only by which fixtures they request and what they assert. The header comment, the `SCENARIO` constant, the `@smoke` / `@negative` split, and the `pollUntil` shape are identical.

```ts
// Flow: order-create
// Kind: api
const SCENARIO = "order-create";

test.describe("POST /orders", () => {
  test("@smoke creates an order and persists it", async ({ request }) => {
    const tenant = scopedId(SCENARIO, "t");
    const email  = scopedEmail(SCENARIO);

    const created = await request.post("/orders", {
      data: { tenant, email, items: [{ sku: "ACME-1", qty: 1 }] },
    });
    expect(created.status()).toBe(201);
    const { id } = await created.json();

    await pollUntil(async () => {
      const got = await request.get(`/orders/${id}`);
      return got.ok() && (await got.json()).status === "confirmed";
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

### Kind-specific differences

| `kind`        | Fixtures requested            | `@smoke` performs           | `@smoke` asserts                                 | Header comment                                  |
| ------------- | ----------------------------- | --------------------------- | ------------------------------------------------ | ----------------------------------------------- |
| `api`         | `{ request }`                 | HTTP call                   | response status + `pollUntil` on read-after-write | `// Flow: <n>\n// Kind: api`                    |
| `browser`     | `{ page }`                    | UI action via POM           | `await expect(pom.<locator>).toHaveText(...)`    | `// Flow: <n>\n// Kind: browser`                |
| `mixed`       | `{ request, page }`           | API setup, then UI assert   | UI element + optional `rowExists` on DB          | `// Flow: <n>\n// Kind: mixed`                  |
| `mixed` (inv) | `{ page, request }`           | UI action via POM           | `rowExists(...)` and/or UI confirmation          | `// Flow: <n>\n// Kind: mixed; entry=browser; assertion=DB+UI` |

A browser scenario substitutes the `request.post` block for `await pom.placeOrder()`; a mixed scenario keeps the api `@smoke` setup and adds a browser assertion before the `pollUntil`. Inversion (Rule 8) flips setup and assertion.

### From-story drafting (from-story mode only)

The skill drafts a `flows.yaml` entry from prose. Drafting mechanics:

- **Validate every referenced service against `services.yaml`.** Story names a service not in `services.yaml` -> surface as a gap and ask the user. Never auto-add to either file.
- **Endpoint paths and observable outcomes come from the story.** Anything the story does not state is a `<USER FILL: ...>` placeholder. The marker is preserved in committed `flows.yaml` and surfaces in the workflow's report block so it isn't forgotten.
- **Negative path is NOT stored in `flows.yaml`.** The `flows.yaml` entry describes the regression-target behavior (which becomes `@smoke`). The `@negative` lives only in the `.spec.ts`. When the story states a separate failure case (auth, validation, conflict), record it in the report block's "gaps" section so the consuming workflow asks the user. When the story does not state one, the same "gaps" entry says "negative path unspecified - the workflow will ask before scaffolding." Per Rule 2, the `.spec.ts` does not emit until the user provides the negative.
- **Evidence is required.** At least one entry citing ticket ID, incident date, reporter, or URL. Empty -> abort.
- **Flow-name derivation.** `--name` if provided, else kebab-case the story's first noun phrase plus the first cited evidence date (or today's date), e.g. `wallet-double-debit-inc-2026-04-12`, `invoice-export-empty-csv-qa-1041`, `resend-verification-email-2026-06-02`. Name collisions with existing entries -> abort; the user picks a different `--name`.
- **`kind` inference from prose.** Browser action verbs in the story (`click`, `navigate`, `submit`, `see`) and a frontend entry point -> `browser` or `mixed`. API action verbs (`POST`, `request`, `call`) with no UI verb -> `api`. Mixed signals (e.g. logged-in user but described in API terms) -> emit the `kind` line as `<USER FILL: api | browser | mixed>`. Per Rule 10, never pick a plausible default.

#### Bad / good - faithful drafting

Story:

> INC-2026-04-12: a user retried a `POST /payments` with the same idempotency key and the wallet was debited twice. The fix landed in payment-service 2026-04-14.

```yaml
# BAD - fabricates the wallet endpoint, invents a generic HTTP outcome
- name: payment-retry-double-debit
  kind: api
  entryPoint: { service: payment-gateway, action: "POST /payments retried" }
  hops:
    - { from: payment-gateway, to: payment-service, call: "POST /charge" }
    - { from: payment-service, to: wallet-service, call: "POST /wallets/debit" }  # invented path
  observableOutcome:
    - "HTTP 200 returned"                                                          # generic, not from story
    - "wallet balance updated"                                                     # vague
  evidence: []                                                                     # would abort (Rule 11)
```

```yaml
# GOOD - cites the incident, leaves <USER FILL> for unknowns, asserts the exact bug
- name: payment-retry-double-debit-inc-2026-04-12
  kind: api
  entryPoint: { service: payment-gateway, action: "POST /payments with retried client idempotency key" }
  hops:
    - { from: payment-gateway, to: payment-service, call: "POST /payments" }
    - { from: payment-service, to: wallet-service, call: "<USER FILL: debit endpoint path>" }
  observableOutcome:
    - "wallet balance debited exactly once across two POST /payments calls sharing the same idempotency key"
    - "<USER FILL: response shape on the second call - 200 with the original charge, or 409, etc.>"
  evidence:
    - incident: "INC-2026-04-12 wallet double-debit on client retry"
    - commit: "payment-service 2026-04-14 fix landed"
  rationale: "Regression guard against the double-debit incident; idempotency-key path not exercised by any current scenario."
```

### Documented retry annotation

Rule 5 permits per-scenario retries only with the exact comment shape `regression-flakiness-triage` greps for:

```ts
test.describe.configure({ retries: 1 });
// flake REG-142; remove after fix
```

### DB-state assertion

For `observableOutcome` entries that name a row:

```ts
await pollUntil(() => rowExists("orders", { id, status: "confirmed" }));
```

The supported engines are whatever `regression-service-inventory#engine` permits; the helper's connection string comes from compose env at runtime.

### Tag conventions

| Tag         | Meaning                                                                                                            |
| ----------- | ------------------------------------------------------------------------------------------------------------------ |
| `@smoke`    | Golden path. Exactly one per file. Selected by `/task-regression --grep @smoke`.                                   |
| `@negative` | Validation / authz / conflict. Exactly one required per file (Rule 2). Multiple negatives go in separate flows.    |

Other project tags (`@slow`, `@flaky`, `@nightly`) are out of this skill's scope.

## Output Format

`.regression/scenarios/<kind>/<flow>.spec.ts` only. Two-line header comment with `Flow:` and `Kind:` (plus the inversion note when Rule 8 fires). Imports listed under Patterns -> Imports. The skill never modifies `package.json` / `package-lock.json` / `playwright.config.ts` - those are owned by `task-regression-discover`.

In from-story mode the skill also appends to `.regression/flows.yaml` after the user's `accept` (the workflow owns the prompt; this skill owns the draft shape). The `.spec.ts` is emitted only after Rule 12 passes against the resolved entry.

## Avoid

- `test.fixme` / `test.skip` for the `@negative` slot (Rule 2).
- `setTimeout` / `page.waitForTimeout` / raw sleeps (Rule 4).
- Locator calls in scenarios; everything goes through POMs (Rule 6).
- Cross-scenario data sharing (Rule 3).
- Default-on retries without the Rule-5 grep marker.
- Invented fixtures for Kafka / gRPC streaming / raw WebSocket (Rule 9).
- Loose `@playwright/test` version pins (exact pins enforced by the discover-written `package.json`).
- From-story fabrication - plausible endpoint paths or assertions the story did not state belong as `<USER FILL>` in `flows.yaml`, never silent invention (Rule 10).
- `<USER FILL>` in the emitted `.spec.ts` - Rule 12 refuses to scaffold over unresolved markers.
- Empty `evidence:` in from-story drafts (Rule 11).
