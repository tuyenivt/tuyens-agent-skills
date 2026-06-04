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

Fixed structured deep-dive on **one named entity**. Composes with stack-specific `*-code-explain` atomics for framework-magic.

## When to Use

For callers + callees + data + tests + blast radius + concepts on a single known entity.

- "Walk me through `authenticate()`."
- "What does `OrderService` do, and how does it fit in?"
- "Explain `internal/payment/charge.go` end-to-end."

**Not for:**
- Free-form questions about the system -> `task-codemap-ask`.
- Multi-node flows ("how does the whole auth flow work") -> `task-codemap-guide` or `task-codemap-ask`.
- Debug, refactor -> respective `task-*` skills.

## Inputs

| Input | Notes |
| --- | --- |
| `$ARGUMENTS` | File path, qualified name, or node ID. Required. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

1. Confirm `.codemap/graph.json` exists. Missing -> fall back to `task-code-explain` (no graph dependency) and stop.
2. Apply the freshness rule from `codemap-query` (Freshness check); warn but proceed when stale.
3. Load graph.

Use skill: `codemap-schema` for shape. Use skill: `codemap-query` for traversal and the freshness rule.

### Step 3 - Resolve Target

Apply `codemap-query` resolution rules:
1. Exact ID.
2. `filePath`.
3. `name`.
4. Substring.

Multiple matches -> list and ask. Zero matches -> suggest closest 3 by Levenshtein and stop.

### Step 4 - Detect Stack & Compose

Use skill: `stack-detect`. If a stack-specific atomic exists, load it for framework-magic and gotchas:

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

The atomic enriches; it does not replace the graph-driven structure below.

### Step 5 - Collect Context from Graph

For the resolved node N:

| Section | Query |
| --- | --- |
| Identity | `N.id`, `type`, `filePath`, `lineRange`, `summary`, `tags`, `complexity`, `layer` |
| Containers | Walk `belongs_to` upward |
| Members (file/class) | Walk `belongs_to` downward |
| Callers (top 10) | Incoming `calls` by fan-in |
| Callees (top 10) | Outgoing `calls` by fan-out |
| Imports of N's file | Outgoing `imports` from `file:<N.filePath>` |
| Importers | Incoming `imports` |
| Data touchpoints | Outgoing `reads_from` / `writes_to` |
| Tests | Incoming `tested_by` |
| Related concepts | `concept` nodes within 2 hops |
| Blast radius | Reverse BFS depth 3 over `calls`/`imports`/`uses`; count by layer |

Use skill: `architecture-guardrail` to flag layer-violation participation. Use skill: `complexity-review` for function/class complexity.

### Step 6 - Read Source

Read N's `lineRange` (cap 200 lines). Read 1-2 close neighbors when they clarify intent. Cap total at 3 files.

### Step 7 - Render

Structured deep-dive with these sections (skip empty ones):

1. **Summary** - one paragraph: what N does, why it exists, where it fits.
2. **Identity** - node ID, file:line, layer, complexity.
3. **What it does** - line-referenced walkthrough.
4. **Inputs and outputs** - parameters, return, side effects.
5. **Callers** - top callers with `file:line` + one-line reason.
6. **Callees** - top callees with `file:line` + delegated purpose.
7. **Data touchpoints** - tables/schemas/resources read/written.
8. **Tests** - covering tests + coverage-gap assessment.
9. **Layer / boundary check** - via `architecture-guardrail`.
10. **Framework gotchas** - from the stack-specific atomic.
11. **Blast radius** - depth-3 reverse-BFS by layer.
12. **Related concepts** - connected `concept` nodes + one-line definitions.
13. **Recommendations** - flags only (god-method, missing tests, suspicious coupling). No refactor plan.

### Step 8 - Stale-Graph Footer

When applicable:

```
> Codemap built from commit abc1234. Run `/task-codemap` for current data.
```

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

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph loaded; freshness warning; fallback to `task-code-explain` when graph missing
- [ ] Step 3: target resolved; ambiguous matches surfaced
- [ ] Step 4: `stack-detect` ran; stack-specific atomic loaded when available
- [ ] Step 5: graph context collected per the section list
- [ ] Step 6: targeted reads to `lineRange`; total <= 3 files
- [ ] Step 7: all populated sections rendered; empty sections marked `none` not silently dropped
- [ ] Step 8: stale-graph footer when applicable
- [ ] No invented callers, callees, or tests

## Avoid

- Explaining without graph context - that's what differentiates this from `task-code-explain`.
- Reading whole files when `lineRange` is the exact span.
- Walking beyond depth 3 for blast radius - signal degrades fast.
- Producing a refactor plan - flag, don't redesign.
- Skipping the test-gap assessment - high-value output.
