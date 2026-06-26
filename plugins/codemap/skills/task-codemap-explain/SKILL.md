---
name: task-codemap-explain
description: Deep-dive on a file, function, or class using the codemap graph - neighbors, layer, callers, callees, blast radius, related concepts.
metadata:
  category: code
  tags: [codemap, explain, deep-dive, knowledge-graph]
  type: workflow
user-invocable: true
---

# Task: Codemap Explain

Fixed structured deep-dive on **one named entity**. Composes stack-specific `*-code-explain` atomics for framework gotchas. Falls back to `task-code-explain` when the graph is missing.

## When to Use

You want callers + callees + data + tests + blast radius + concepts for a single known entity.

- "Walk me through `authenticate()`."
- "What does `OrderService` do, and how does it fit in?"
- "Explain `internal/payment/charge.go` end-to-end."

**Not for:** free-form questions (`task-codemap-ask`); multi-node flows (`task-codemap-guide` / `task-codemap-ask`); debug/refactor (`task-*` skills).

## Inputs

| Input | Notes |
| --- | --- |
| `$ARGUMENTS` | File path, qualified name, or node ID. Required. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

Use skill: `codemap-schema` (shape). Use skill: `codemap-query` (resolution, traversal, freshness, source-reading caps).

1. Missing `.codemap/graph.json` -> fall back to `task-code-explain` (no graph dependency) and stop.
2. Run the `codemap-query` freshness check; warn but proceed when stale.
3. Load graph.

### Step 3 - Resolve Target

Apply `codemap-query` resolution rules. Multiple matches -> list and ask. Zero matches -> suggest closest 3 by Levenshtein; offer `task-code-explain` for source-only explanation if the path exists on disk.

### Step 4 - Detect Stack & Compose

Use skill: `stack-detect`. Load the stack's `*-code-explain` atomic when present - it enriches sections 10-11, never replaces graph structure.

| Stack | Atomic |
| --- | --- |
| Java / Spring | `spring-code-explain` |
| Kotlin / Spring | `kotlin-code-explain` |
| Python | `python-code-explain` |
| Ruby / Rails | `rails-code-explain` |
| Node.js / TypeScript | `node-code-explain` |
| Go / Gin | `go-code-explain` |
| Rust / Axum | `rust-code-explain` |
| .NET / ASP.NET | `dotnet-code-explain` |
| PHP / Laravel | `laravel-code-explain` |
| React | `react-code-explain` |
| Vue | `vue-code-explain` |
| Angular | `angular-code-explain` |

Unlisted/uninstalled stack (e.g., Elixir/Phoenix, or the stack plugin isn't installed) -> no atomic loads. Render section 10 from general framework knowledge, or `none` if there's nothing stack-specific to flag. Never omit the section silently.

### Step 5 - Collect Context from Graph

For the resolved node N, gather these slices via `codemap-query` patterns:

| Section | Query |
| --- | --- |
| Identity | `N.id`, `type`, `filePath`, `lineRange`, `summary`, `tags`, `complexity`, `layer` |
| Containers / Members | `belongs_to` up / down |
| Callers (top 10) | Incoming `calls`, ranked by edge weight then ascending node ID |
| Callees (top 10) | Outgoing `calls`, same ranking |
| File imports / importers | `imports` from / into `file:<N.filePath>` |
| Data touchpoints | Outgoing `reads_from` / `writes_to` (tables, schemas, configs, resources) |
| Tests | Incoming `tested_by` |
| Related concepts | `concept` nodes reachable within 2 undirected hops |
| Blast radius | `codemap-query` "Impact of change" pattern (reverse BFS depth 3 over `imports`/`calls`/`uses`/`routes_to`); count by layer |

When N is a **file** node, Callers/Callees aggregate over its member functions/classes. When N is **abstract** (`concept`, `service`, `table`) with no `filePath`/`lineRange`, skip What-it-does/Inputs-outputs/source-read and render from edges + `summary`.

Use skill: `architecture-guardrail` for layer-violation participation. Use skill: `complexity-review` for function/class complexity grading.

### Step 6 - Read Source

Apply `codemap-query` "Reading source from a node" rules. Cap total at 3 files (N + up to 2 close neighbors when they clarify intent).

### Step 7 - Render

Render the structured deep-dive (skip empty sections, but mark intentional skips with `none` rather than dropping silently):

1. **Summary** - one paragraph: what N does, why it exists, where it fits (orientation).
2. **Identity** - node ID, file:line, layer, complexity.
3. **What it does** - line-referenced walkthrough (mechanics, distinct from Summary).
4. **Inputs and outputs** - parameters, return, side effects.
5. **Callers** - top callers with `file:line` + one-line reason.
6. **Callees** - top callees with `file:line` + delegated purpose.
7. **Data touchpoints** - tables/schemas/resources read/written.
8. **Tests** - covering tests + coverage-gap assessment.
9. **Layer / boundary check** - from `architecture-guardrail`.
10. **Framework gotchas** - from the stack-specific atomic.
11. **Blast radius** - depth-3 reverse-BFS by layer.
12. **Related concepts** - connected `concept` nodes + one-line definitions.
13. **Recommendations** - flags only (god-method, missing tests, suspicious coupling). No refactor plan.

Append the freshness footer per Output Format.

## Output Format

```markdown
# Explain: `function:internal/auth/login.go:Authenticate`

> Codemap freshness: in sync with HEAD.

## Summary

`Authenticate` is the password-based login entry of the auth service. It validates credentials against `users`, issues a signed JWT via `jwt.Sign`, and appends an audit log entry. Lives at the `service` layer; called by `handler.auth.Login`.

## Identity

| Field | Value |
| --- | --- |
| ID | `function:internal/auth/login.go:Authenticate` |
| File | `internal/auth/login.go:42-87` |
| Layer | `service` |
| Complexity | `moderate` |
| Tags | `auth`, `jwt`, `audit` |

## What It Does

1. (42-50) Validates input shape; returns `ErrInvalidInput` if blank.
2. (51-64) Loads user via `repository.user.Find`; constant-time bcrypt compare.
3. (65-78) On success, calls `jwt.Sign` with user ID + 1h expiry.
4. (79-86) Appends to `audit_logs` via `repository.audit.Append`.
5. (87) Returns `(token, nil)` or wrapped error.

## Inputs and Outputs

| Parameter | Type | Notes |
| --- | --- | --- |
| `ctx` | `context.Context` | Carries trace ID |
| `username`, `password` | `string` | Constant-time-compared |

**Output:** `(token string, err error)`. **Side effects:** one row to `audit_logs`.

## Callers (top 3)

| Caller | Where | Why |
| --- | --- | --- |
| `function:internal/handler/auth.go:Login` | `internal/handler/auth.go:34-58` | HTTP entry |

## Callees (top 5)

| Callee | Where | What |
| --- | --- | --- |
| `function:internal/repository/user.go:Find` | `internal/repository/user.go:18-31` | Loads user row |
| `function:internal/auth/jwt.go:Sign` | `internal/auth/jwt.go:14-31` | Issues JWT |
| `function:internal/repository/audit.go:Append` | `internal/repository/audit.go:12-27` | Audit trail |

## Data Touchpoints

- Reads: `table:users`
- Writes: `table:audit_logs`

## Tests

- `function:internal/auth/login_test.go:TestAuthenticate_Success`
- `function:internal/auth/login_test.go:TestAuthenticate_BadPassword`

Gap: no test for `ErrInvalidInput` (lines 42-50).

## Layer / Boundary Check

Service-layer calling data-layer repositories - clean. No violations.

## Framework Gotchas (Go/Gin)

- Constant-time bcrypt compare - good.
- `audit.Append` is best-effort and doesn't roll back JWT issuance on failure - intentional?

## Blast Radius (depth-3 reverse BFS)

| Layer | Impacted |
| --- | --- |
| `api` | 1 (`handler.auth.Login`) |
| Total | 1 direct, ~6 transitive |

Low blast radius.

## Related Concepts

- `concept:JWT` - signed token format for session-less auth.
- `concept:Audit Log` - append-only auth-event trail.

## Recommendations

- Cover `ErrInvalidInput` (9 lines, no coverage).
- Consider transactional pairing for `audit.Append` + token issuance.
```

Stale variant of the freshness footer (use the canonical `codemap-query` format verbatim):

```
> Codemap built from commit abc1234 (12 commits behind HEAD, 9 days old). Run `/task-codemap` to sync.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph loaded; freshness warning; fallback to `task-code-explain` when graph missing
- [ ] Step 3: target resolved; ambiguous matches surfaced; zero-match fallback offered
- [ ] Step 4: `stack-detect` ran; stack-specific atomic loaded when available; section 10 from general knowledge or `none` when no atomic
- [ ] Step 5: graph context collected per the section list; file/abstract node kinds handled; blast radius via `codemap-query` impact pattern
- [ ] Step 6: targeted reads to `lineRange`; total <= 3 files
- [ ] Step 7: all populated sections rendered; empty sections marked `none`; freshness footer present
- [ ] No invented callers, callees, or tests

## Avoid

- Explaining without graph context - that's what differentiates this from `task-code-explain`.
- Reading whole files when `lineRange` is the exact span.
- Walking beyond depth 3 for blast radius - signal degrades fast.
- Producing a refactor plan - flag, don't redesign.
