---
name: regression-flow-extract
description: Discovery-time flow suggester for outside-in regression. Reads symlinked codemap graphs, OpenAPI specs, and git history to propose cross-service flows for flows.yaml.
metadata:
  category: testing
  tags: [regression, flows, discovery, codemap, openapi]
user-invocable: false
---

# Regression Flow Extract

> **Authoring-time only.** Output is human-reviewed and frozen into `.regression/flows.yaml`. Runtime never re-reads these inputs.

Produces ranked cross-service flow suggestions for the user to confirm before they land in `flows.yaml`. The plugin treats this as a *suggester* - never overwrites committed flows, never runs during `task-regression`.

## When to Use

- During `task-regression-discover` after `services.yaml` is committed.
- When the user asks for fresh suggestions ("propose new flows since last topology change").

## Rules

1. **Read-only.** Touch no sibling repo state. Codemap symlinks under `.regression/.cache/codemap/` are user-managed.
2. **Rank, do not pick.** Emit 3-10 ranked candidates with rationale. The user accepts/rejects each.
3. **Diff against `flows.yaml`.** Never silently overwrite. Show additions and changes; let the user confirm per-entry.
4. **Cite inputs.** Each candidate names the evidence source (codemap edge, OpenAPI path, git commit).
5. **Stop at boundaries.** A flow is a cross-service path from an externally-triggerable entry point to an observable outcome (DB row, status code, UI change). Single-service flows are out of scope - those are unit/integration tests.

## Patterns

### Input priority

1. **Symlinked codemap graphs** under `.regression/.cache/codemap/<service>/graph.json`. Load all available; merge by node ID. Use `codemap-schema` for shape and `codemap-query` for traversal.
2. **OpenAPI specs** discovered under each sibling-path service (`openapi.yaml` / `openapi.json` / `swagger.json` in common locations).
3. **Recent git history** across sibling-path services - last 30 commits per service, mining commit messages and changed files for new/changed endpoints.

Lower-priority sources fill gaps when higher ones are absent. Never assume one source is exhaustive.

### Flow shape

Each candidate has:

```yaml
- name: order-checkout-happy
  kind: mixed                    # api | browser | mixed
  entryPoint: { service: web, action: "navigate /checkout, click 'Place order'" }
  hops:
    - { from: web, to: api, call: "POST /orders" }
    - { from: api, to: db, call: "INSERT INTO orders" }
    - { from: api, to: api, call: "POST /payments (internal)" }   # within same service
  observableOutcome:
    - "HTTP 201 returned to web"
    - "row in orders with status='confirmed'"
    - "UI shows 'Thank you' screen"
  evidence:
    - "codemap edge web/src/checkout.tsx -> api POST /orders"
    - "openapi: api/openapi.yaml POST /orders"
    - "git: api 2026-05-14 'add payments handoff'"
  rationale: "Cross-service write path, high blast-radius, no existing scenario."
```

### Ranking signals

Rank descending by:

1. **Blast radius** - more services touched = higher rank.
2. **Recency of change** - flows touching files changed in the last 14 days = +1 tier.
3. **DB write involvement** - any `Endpoint -> Table` write edge = +1 tier.
4. **Auth/payments/identity surfaces** - keywords in endpoint paths (`/login`, `/pay`, `/checkout`, `/admin`) = +1 tier.
5. **Existing coverage** - if a scenario in `scenarios/` already covers the flow, drop to bottom or omit.

### Flow `kind` inference

- All hops are API-only and no UI entry point -> `kind: api`.
- Entry point is browser-driven, all assertions are UI-observable -> `kind: browser`.
- Browser entry + API setup, or browser entry + DB observable -> `kind: mixed`.

### Fallback when no inputs are available

If no codemap, no OpenAPI, no recent git: emit a *single* placeholder candidate per backend - "`POST /<inferred>` -> `<backend>` -> `<db>` write" - flagged with `rationale: "Skeleton only; backend OpenAPI not found"`. The user fills in details. Do not invent endpoint names from imagination.

## Output Format

A ranked candidate list, written to `.regression/.cache/flow-suggestions.json` (gitignored), surfaced to the user as a numbered list with accept/reject prompts. Accepted candidates are appended to `flows.yaml` with the same shape above.

## Avoid

- **Silently rewriting `flows.yaml`.** Always diff and confirm.
- **Inventing endpoints.** A flow with no evidence source is not a candidate.
- **Single-service flows.** Hand them back to `task-<stack>-test`.
- **Reading codemap at runtime.** This skill is invoked only by `task-regression-discover`, never by `task-regression`.
- **Assuming codemap is present.** It is optional. Degrade gracefully to OpenAPI + git, then to skeleton fallback.
