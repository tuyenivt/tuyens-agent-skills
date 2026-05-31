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

Deep-dive a single graph node using its neighborhood as context. Composes with `task-code-explain` for framework-magic when a stack-specific atomic exists.

## When to Use

For a fixed structured deep-dive on one **named entity** - callers, callees, data touchpoints, tests, blast radius, related concepts, all surfaced by default.

- "Walk me through `authenticate()`."
- "What does `OrderService` do, and how does it fit in?"
- "Explain `internal/payment/charge.go` end-to-end."

**Not for:**
- Free-form questions about the system where the relevant entity is not known yet ("which handlers touch this table?"). Use `task-codemap-ask`.
- "How does the whole auth flow work" - that's a multi-node story; use `task-codemap-guide` or `task-codemap-ask`.
- "Why does this code have a bug" - that's `task-code-debug`.
- "How should I refactor this" - that's `task-code-refactor`.

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| `$ARGUMENTS` | Yes | A file path, qualified name, or node ID. Examples: `src/auth/login.ts`, `authenticate`, `function:src/auth/login.ts:authenticate`. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

1. Confirm `.codemap/graph.json` exists. If missing, fall back to `task-code-explain` (which doesn't need a graph) and stop.
2. Check freshness; warn if stale.
3. Load graph.

Use skill: `codemap-schema` for shape.
Use skill: `codemap-query` for traversal.

### Step 3 - Resolve Target

Apply the resolution rules from `codemap-query`:

1. Exact ID match.
2. File-path match.
3. Name match.
4. Substring match.

Multiple matches -> list and ask user to pick. Zero matches -> suggest closest 3 by Levenshtein and stop.

### Step 4 - Detect Stack & Compose

Use skill: `stack-detect`. If a stack-specific code-explain atomic exists for the detected stack, load it for framework-magic and gotchas (Spring AOP, Rails callbacks, React hooks, etc.):

| Detected stack | Load atomic |
| --- | --- |
| Java / Spring Boot | `spring-code-explain` |
| Kotlin / Spring Boot | `kotlin-code-explain` |
| Python | `python-code-explain` |
| Ruby / Rails | `rails-code-explain` |
| Node.js / TypeScript | `node-code-explain` |
| Go / Gin | `go-code-explain` |
| Rust / Axum | `rust-code-explain` |
| .NET / ASP.NET Core | `dotnet-code-explain` |
| PHP / Laravel | `laravel-code-explain` |
| React | `react-code-explain` |
| Vue | `vue-code-explain` |
| Angular | `angular-code-explain` |

The atomic enriches the explanation with framework-specific behavior; it does not replace this workflow's graph-driven structure.

### Step 5 - Collect Context from Graph

For the resolved node N:

| Section | Query |
| --- | --- |
| Identity | `N.id`, `N.type`, `N.filePath`, `N.lineRange`, `N.summary`, `N.tags`, `N.complexity`, `N.layer` |
| Containers | Walk `belongs_to` upward from N to its file and module |
| Members (if file/class) | Walk `belongs_to` downward to functions/methods |
| Callers (top 10 by fan-in) | Incoming `calls` edges |
| Callees (top 10 by fan-out) | Outgoing `calls` edges |
| Imports of N's file | Outgoing `imports` from `file:<N.filePath>` |
| Importers of N's file | Incoming `imports` to `file:<N.filePath>` |
| Data touchpoints | Outgoing `reads_from` / `writes_to` from N |
| Tests | Incoming `tested_by` to N |
| Related concepts | `concept`-type nodes connected within 2 hops |
| Blast radius | Reverse BFS depth 3 over `calls`/`imports`/`uses`; count by layer |

Use skill: `architecture-guardrail` to flag if N participates in a layer-violation edge.
Use skill: `complexity-review` to assess complexity if N is a function or class.

### Step 6 - Read Source

Read N's source at `N.lineRange` (cap 200 lines). Read 1-2 close neighbors when they clarify intent (e.g., the called helper, the parent class definition). Cap total source reads at 3 files.

### Step 7 - Render

Produce a structured deep-dive with these sections (skip those that have no content):

1. **Summary** - one paragraph: what N does, why it exists, where it lives in the architecture.
2. **Identity** - node ID, file:line, layer, complexity.
3. **What it does** - step-by-step walkthrough of the source, referencing line numbers.
4. **Inputs and outputs** - parameters, return type, side effects (reads/writes/network/files).
5. **Callers** - top N callers with file:line and a one-line reason each is calling.
6. **Callees** - top N callees with file:line and what each is delegated to do.
7. **Data touchpoints** - tables/schemas/resources read from or written to.
8. **Tests** - test files covering N, with assessment of coverage gaps (no tests? only happy-path? mocked-heavy?).
9. **Layer / boundary check** - via `architecture-guardrail` - is N participating in any violations?
10. **Framework gotchas** - injected by the stack-specific atomic from Step 4.
11. **Blast radius** - depth-3 reverse-BFS count by layer; identify the riskiest downstream consumers.
12. **Related concepts** - graph-connected concept nodes with one-line definitions.
13. **Recommendations** - if anything stood out (god-method, missing tests, suspicious coupling), call it out. No refactor plan - just the flag.

### Step 8 - Stale-Graph Footer

Same as `task-codemap-ask` Step 6.

## Output Format

```markdown
# Explain: `function:internal/auth/login.go:Authenticate`

> Codemap freshness: in sync with HEAD.

## Summary

`Authenticate` is the password-based login entry of the auth service. It validates credentials against `users`, issues a signed JWT via `jwt.Sign`, and appends an audit log entry. Lives at the `service` layer; called by the HTTP handler `handler.auth.Login`.

## Identity

| Field | Value |
| --- | --- |
| ID | `function:internal/auth/login.go:Authenticate` |
| File | `internal/auth/login.go:42-87` |
| Layer | `service` |
| Complexity | `moderate` |
| Tags | `auth`, `jwt`, `audit` |

## What It Does

1. (lines 42-50) Validates the username/password input shape, returns `ErrInvalidInput` if blank.
2. (lines 51-64) Looks up the user via `repository.user.Find`; constant-time bcrypt compare.
3. (lines 65-78) On success, calls `jwt.Sign` with the user ID and a 1h expiry claim.
4. (lines 79-86) Appends to `audit_logs` via `repository.audit.Append`.
5. (line 87) Returns `(token, nil)` or wrapped error.

## Inputs and Outputs

| Parameter | Type | Notes |
| --- | --- | --- |
| `ctx` | `context.Context` | Request-scoped; carries trace ID |
| `username`, `password` | `string` | Plaintext password; constant-time-compared |

| Output | Type |
| --- | --- |
| `token` | `string` (JWT) |
| `err` | `error` (`ErrInvalidInput`, `ErrUnauthorized`, wrapped DB errors) |

**Side effects:** writes one row to `audit_logs`.

## Callers (top 3 by fan-in)

| Caller | Where | Why |
| --- | --- | --- |
| `function:internal/handler/auth.go:Login` | `internal/handler/auth.go:34-58` | HTTP entry point |

## Callees (top 5)

| Callee | Where | What |
| --- | --- | --- |
| `function:internal/repository/user.go:Find` | `internal/repository/user.go:18-31` | Loads the user row |
| `function:internal/auth/jwt.go:Sign` | `internal/auth/jwt.go:14-31` | Issues the JWT |
| `function:internal/repository/audit.go:Append` | `internal/repository/audit.go:12-27` | Audit trail |

## Data Touchpoints

- Reads: `table:users`
- Writes: `table:audit_logs`

## Tests

- `function:internal/auth/login_test.go:TestAuthenticate_Success`
- `function:internal/auth/login_test.go:TestAuthenticate_BadPassword`

Gap: no test for `ErrInvalidInput` branch (lines 42-50).

## Layer / Boundary Check

- Service-layer function calling data-layer repositories (clean).
- No layer violations flagged.

## Framework Gotchas (Go/Gin)

- Bcrypt compare uses constant-time op - good for password handling.
- `audit.Append` is best-effort and does not roll back the JWT issuance on failure - intentional?

## Blast Radius (depth 3 reverse-BFS)

| Layer | Impacted nodes |
| --- | --- |
| `api` | 1 (`handler.auth.Login`) |
| Total | 1 direct, ~6 transitive |

Low blast radius - only one upstream caller chain.

## Related Concepts

- `concept:JWT` - signed token format used for session-less auth.
- `concept:Audit Log` - append-only trail of auth events.

## Recommendations

- Cover the `ErrInvalidInput` branch with a test - it's 9 lines of behavior with no coverage.
- Consider whether `audit.Append` should be transactional with the token issuance.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph loaded; freshness warning if stale; fallback to `task-code-explain` when graph missing
- [ ] Step 3: target resolved; ambiguous matches surfaced for user choice
- [ ] Step 4: `stack-detect` ran; stack-specific code-explain atomic loaded when available
- [ ] Step 5: graph context collected (identity, containers, callers, callees, imports, data, tests, blast)
- [ ] Step 6: source read targeted to `lineRange`; total reads <= 3 files
- [ ] Step 7: report rendered with all populated sections; skipped sections noted as `none` rather than silent
- [ ] Step 8: stale-graph footer when applicable
- [ ] No invented callers, callees, or test files

## Avoid

- Explaining without graph context. The graph is what differentiates this from `task-code-explain`.
- Reading the whole file when `lineRange` gives the exact span.
- Walking the graph beyond depth 3 for blast radius. The signal degrades fast and the report bloats.
- Producing a refactor plan - call out flags, do not redesign.
- Skipping the test-gap assessment - it's one of the highest-value outputs.
