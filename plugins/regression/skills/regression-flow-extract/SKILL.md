---
name: regression-flow-extract
description: Discovery-time flow suggester for outside-in regression. Reads symlinked codemap graphs, OpenAPI specs, and git history to propose cross-service flows for flows.yaml.
metadata:
  category: testing
  tags: [regression, flows, discovery, codemap, openapi]
user-invocable: false
---

# Regression Flow Extract

> Authoring-time only. Output is human-reviewed and frozen into `.regression/flows.yaml`. Runtime never re-reads these inputs.

Produces ranked cross-service flow suggestions for the user to confirm before they land in `flows.yaml`.

## When to Use

- During `task-regression-discover` after `services.yaml` is committed.
- When the user asks for fresh suggestions after sibling-repo pulls.

## Rules

1. **Read-only across sibling repos.** Symlinks under `.regression/.cache/codemap/` are user-managed.
2. **Rank, do not pick.** Emit candidates ranked, with rationale. User accepts / rejects each.
3. **Diff against `flows.yaml`.** Never silently overwrite. Show additions; name-conflict candidates handled by the workflow (`task-regression-discover` Step 4).
4. **Cite inputs per candidate.** Each entry's `evidence:` lists every signal (codemap edge, OpenAPI path, git commit). A skeleton candidate uses `evidence: skeleton`.
5. **Cross-service only.** A flow runs from an externally-triggerable entry point through at least two services to an observable outcome. Single-service flows belong to `task-<stack>-test`; this skill discards them from candidate output.
6. **Candidate count.** Aim for 3-10 ranked candidates when any evidence tier is present. When all tiers are absent, emit exactly one `evidence: skeleton` candidate per backend - this overrides the 3-10 floor.

## Patterns

### Input priority (fall through silently when a tier is absent)

1. Symlinked codemap graphs under `.regression/.cache/codemap/<service>/graph.json`. Merge by node ID. Node types and edge types come from `codemap-schema` (the `codemap` plugin's atomic); traversal verbs come from `codemap-query`. Both are optional reads - skip if absent.
2. OpenAPI specs in declared service paths (`openapi.yaml` / `openapi.json` / `swagger.json`).
3. Git history across `sibling-path` services - last 30 commits per service.

### Candidate shape

```yaml
- name: order-checkout-happy
  kind: mixed                    # api | browser | mixed
  entryPoint: { service: web, action: "navigate /checkout, click 'Place order'" }
  hops:
    - { from: web, to: api, call: "POST /orders" }
    - { from: api, to: db, call: "INSERT INTO orders" }
    - { from: api, to: payment-service, call: "POST /payments" }
  observableOutcome:
    - "HTTP 201 returned to web"
    - "row in orders with status='confirmed'"
    - "UI shows 'Thank you' screen"
  evidence:
    - codemap: "web/src/checkout.tsx -> api POST /orders"
    - openapi: "api/openapi.yaml POST /orders"
    - git: "api 2026-05-14 'add payments handoff'"
  rationale: "Cross-service write path, high blast-radius, no existing scenario."
```

Cross-service means at least two `from`/`to` services across the hops. Intra-service hops are allowed *only* as supporting context; a flow whose hops all stay in one service is discarded per Rule 5.

### Ranking

Compute a score, then sort descending. Ties broken alphabetically by name.

```
score = 10 * (#distinct services touched in hops)
      + 3  if (any hop's source file changed in last 14 days)
      + 3  if (any hop is a DB write)
      + 3  if (entryPoint path contains /login|/pay|/checkout|/admin|/auth)
      - 100 if (an existing scenarios/**/*.spec.ts is named identically to this candidate)
```

Negative score means the candidate is hidden by default; surface only on `--show-covered`. The window mismatch (14 days for ranking vs 30 commits for mining) is intentional: mining is wider so we have enough signal; ranking is tighter so the boost reflects recent risk.

### Flow `kind` inference

| Entry | All-API hops | UI-only observable | DB observable | -> kind |
| --- | --- | --- | --- | --- |
| API | yes | n/a | optional | `api` |
| Browser | n/a | yes | no | `browser` |
| Browser | n/a | optional | yes | `mixed` |
| Browser | API setup hops | yes | optional | `mixed` |

### Fallback when no inputs

For each `services.yaml#services[].role == backend`, emit one candidate:

```yaml
- name: skeleton-<backend>-write
  kind: api
  entryPoint: { service: <backend>, action: "<USER FILL: an externally-triggerable write>" }
  hops: []                       # USER FILL
  observableOutcome: []          # USER FILL
  evidence: skeleton             # singular literal; not a list
  rationale: "No evidence sources present; user fills hops and outcome."
```

Do not invent endpoint names. The user owns every field marked `USER FILL`.

### User-confirm prompt format

Numbered list per candidate. For each: name, kind, score, evidence count, rationale. User responds with one of `accept` / `reject` / `defer`. Defer keeps the candidate visible on the next run.

## Output Format

`.regression/.cache/flow-suggestions.json` (gitignored). Accepted candidates are appended to `.regression/flows.yaml` with the shape above (YAML for readability; JSON only in the suggestions cache for tool consumption).

## Avoid

- Silently rewriting `flows.yaml`.
- Inventing endpoint names.
- Single-service flows. Hand back to `task-<stack>-test`.
- Reading codemap at runtime.
- Assuming codemap is present. Degrade through tiers.
- Boosting reads when a write boost already fires (no double-counting).
