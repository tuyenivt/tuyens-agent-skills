---
name: regression-contract-check
description: OpenAPI / JSON Schema body-shape assertions for outside-in regression. Validates response bodies against contract when flow.checks has "contract".
metadata:
  category: testing
  tags: [regression, contract, openapi, json-schema, validation]
user-invocable: false
---

# Regression Contract Check

Validates that response bodies still match the OpenAPI / JSON Schema contract the service declares. Caught at scenario time, not at production cutover.

## When to Use

- A flow has `checks: [..., contract]` in `flows.yaml` AND `regression-flow-extract` cited an `openapi:` evidence entry.
- The user passes `--check contract` explicitly to `task-regression-scenario`.

## Rules

1. **Opt-in per flow.** Default `flows.yaml` entries do NOT contract-check. The flow author adds `contract` to `checks:` to enable. Silent opt-in (e.g. auto-add when any `openapi:` evidence is present) is forbidden - schema-validation surprise breaks scenarios on minor server-side fields.
2. **Source = `openapi:` evidence path.** `regression-flow-extract` already cites the OpenAPI doc path under `evidence`. `regression-contract-check` reads that path. No re-discovery, no path inference.
3. **Schema cached under `.regression/fixtures/contracts/<service>/<sha>.json`.** Keyed on the OpenAPI doc's content hash, written at scenario emit time, committed. Runtime never re-reads the upstream OpenAPI doc - that would re-introduce sibling-repo runtime reads (forbidden by `task-regression` Step 2).
4. **Mismatch is a `real-bug` verdict, not a flake.** Contract drift is a contract violation; `regression-flakiness-triage` treats it as `real-bug`.
5. **Field-level diff in the failure message.** `expected required field 'orderId' missing in response`; `expected status 201 -> 200, type integer -> string`. Never just `validation failed`.

## Patterns

### Helper signature (consumed in scenarios)

```ts
import { matchesContract } from "../../fixtures/contracts";
// .regression/fixtures/contracts/index.ts is shipped by this skill.

expect(matchesContract(resp, "api/openapi.yaml#/paths/~1orders/post/responses/201"))
  .toEqual({ ok: true });
```

`matchesContract` reads the cached schema file under `fixtures/contracts/<service>/<sha>.json`, runs Ajv against the response body, and returns `{ ok: true } | { ok: false, errors: [<field-level>] }`. The helper does NOT throw - the scenario asserts on the structured result, so failure clusters share a top-3-frame signature.

### Scaffold emission

When `regression-scenario-author` sees `checks` containing `contract` on the flow, it appends one assertion block per hop with an `openapi:` evidence entry:

```ts
// CONTRACT (regression-contract-check)
const contractMatch = matchesContract(created, "api/openapi.yaml#/paths/~1orders/post/responses/201");
expect(contractMatch.ok, JSON.stringify(contractMatch)).toBe(true);
```

The `JSON.stringify(...)` second argument surfaces the field-level errors directly in the JUnit failure body so clustering keys correctly.

### Cache file shape

```json
{
  "openapi": "3.0.3",
  "info": { "title": "api", "version": "..." },
  "_meta": {
    "sourcePath": "../api/openapi.yaml",
    "sourceSha256": "abc123...",
    "extractedAt": "2026-06-04T00:00:00Z"
  },
  "components": { ... },
  "paths": { "/orders": { ... } }
}
```

The cache is committed. `task-regression-discover --refresh-flows` re-reads source OpenAPI and rewrites the cache; runtime never touches upstream paths.

### Schema drift handling

When the user adds `checks: [contract]` but no `openapi:` evidence exists, abort with `regression-contract-check: flow '<name>' has no openapi: evidence; rerun /task-regression-discover --refresh-flows or remove 'contract' from checks.` Do not silently degrade to no-op.

## Output Format

- `.regression/fixtures/contracts/<service>/<sha>.json` per OpenAPI source (committed).
- `.regression/fixtures/contracts/index.ts` (helper, committed). Signature: `matchesContract(resp, jsonPointer) -> { ok: boolean, errors?: Array<{ path, message }> }`.
- Scenario emission adds 2-4 lines per opt-in hop.

## Avoid

- Silent opt-in based on evidence presence.
- Reading upstream OpenAPI at runtime.
- Failing the build on contract drift without a clear field-level diff.
- Using JSON Schema directly without the `$ref` resolution OpenAPI requires.
- Vendoring a copy of Ajv in this skill - declare it as a peer dep of `.regression/package.json`.
