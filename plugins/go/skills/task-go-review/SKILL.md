---
name: task-go-review
description: Go / Gin / GORM / sqlx code review: goroutine leaks, context propagation, N+1, auth, validation; spawns perf/security/observability subagents.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Go Code Review

## Purpose

Go-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Go-specific correctness, architecture, AI-quality, and maintainability checks (unchecked `error` returns, goroutine leaks via missing `context.Context` cancellation, fat Gin handlers, GORM N+1, raw SQL string concatenation, missing `ShouldBindJSON` + validator tags, missing JWT middleware on protected routes, `sync.Mutex` held across I/O, `panic` in service code, missing `defer rows.Close()`, returning ORM models from handlers). Coordinates Go-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Go. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a Go/Gin PR before merge
- Post-AI-generation quality gate on a Go change set
- Architecture drift detection in a Go codebase
- Pre-merge risk assessment on a Go branch

**Not for:**

- Pre-implementation feature design (use `task-go-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error / panic debugging (use `task-go-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-go-review-perf`, `task-go-review-security`, or `task-go-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Go staff-level review                                      | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                              |
| --------------- | ---------------------------------------------------------------------- |
| Core            | Phases A-E only (Go-flavored)                                          |
| + Perf          | Core + parallel subagent: `task-go-review-perf`                        |
| + Security      | Core + parallel subagent: `task-go-review-security`                    |
| + Observability | Core + parallel subagent: `task-go-review-observability`               |
| Full            | Core + Performance + Security + Observability (3 parallel Go subagents)|

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (Go-tuned):**

- File uploads (`c.FormFile`, `multipart.FileHeader`), JWT middleware / auth changes, struct tag binding changes (`ShouldBindJSON` DTOs), raw SQL via `db.Exec(fmt.Sprintf(...))` / `db.Raw(...)` with interpolation, secrets in env / config, Asynq / Kafka consumers reading user-supplied input, `mapstructure.Decode(req.Body, target)` patterns → auto-add **+Security**
- New golang-migrate file, new GORM query (`Find`, `First`, `Preload`), new `Joins`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `ristretto` / Redis read paths, new goroutines / `errgroup` fan-out → auto-add **+Perf**
- New service / package, new external client (`http.Client`, `resty`, `pgxpool`), new Asynq / Kafka producer / consumer, change to logging config (`slog` setup, log handler), new `prometheus.NewCounter` registration, new `pprof` endpoint, lifecycle changes (graceful shutdown, signal handling) → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                 | Meaning                                                                                                                                                                               |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-go-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-go-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-go-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-go-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-go-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-go-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step (think before acting, surgical changes, surface confusion, push back when the user is likely wrong). When invoked as a subagent of `task-code-review`, accept the parent's confirmation that this skill is already loaded; do not re-load.

### Step 2 - Confirm Stack and Detect Data-Access Mix

Use skill: `stack-detect` to confirm Go / Gin. If invoked as a delegate of `task-code-review` (parent already detected Go), accept the pre-detected stack and skip re-detection. If the detected stack is not Go, stop and tell the user to invoke `/task-code-review` instead.

Detect data access: GORM (`gorm.io/gorm` import), sqlx (`github.com/jmoiron/sqlx` import), raw `database/sql`, or mixed. Detect messaging: Asynq (`hibiken/asynq`) vs franz-go Kafka (`twmb/franz-go`) vs none. Record `Data Access: GORM | sqlx | mixed | database/sql`, `Messaging: Asynq | Kafka | none`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. Make this explicit because the default of "skip if user did not pass `+security` etc." silently misses the cases where the change itself signals the need.

For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals so the Summary documents why the chosen scope was correct

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`. If the user passed a scope and signals contradicted it, surface a one-line note so reviewers see what was deliberately deferred.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth middleware, JWT validation, router groups, shared interfaces, `cmd/api/main.go`, golang-migrate files), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 4.5 - Re-evaluate Depth After Phase A

If `Blast Radius` (from Phase A) is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors (historical pattern matching, cross-PR context, anemic-domain assessment) are in scope for the rest of the review.

### Phase B - Go Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness - through a Go lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding `*_test.go` coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication (JWT validation, session middleware), authorization (ownership checks, role middleware), money or billing flows, data-integrity writes (multi-table transactions, state machines), Asynq / Kafka consumers that mutate data, migrations that change column semantics. Do not bury this finding in Key Takeaways - a separate, named entry in Findings.

**Go-specific correctness checks (all data-access mixes):**

- [ ] **Error discipline**: every `error` return checked (no `_ = fn()` / naked `fn()`); wrapping uses `%w` not `%v` / `%s`; sentinels matched via `errors.Is` / `errors.As`, never `err.Error() == "..."`. Depth in `go-error-handling`
- [ ] **No `panic` in service / handler code**: panics belong in `main.go` for unrecoverable startup only. Gin recovery middleware catches but does not absolve - they indicate a missing error path
- [ ] **`context.Context` first param + propagation**: every I/O / blocking function takes `ctx`; downstream calls receive it (`db.WithContext(ctx)`, sqlx `*Context` variants); no `context.Background()` / `context.TODO()` mid-call as placeholder
- [ ] **Goroutine ownership + cancellation**: every `go fn()` has an owner (`errgroup.Group`, `sync.WaitGroup`, Go 1.25+ `WaitGroup.Go`, worker pool with shutdown); blocking receives paired with `<-ctx.Done()` arm. `sync.Mutex` not held across I/O. Depth in `go-concurrency` and the perf workflow
- [ ] **`defer rows.Close()`** immediately after `db.Query` / `db.QueryContext` succeeds - missing leaks a connection back to the pool
- [ ] **`ShouldBindJSON` + validator tags**: `ShouldBindJSON` (not `BindJSON`) so the handler controls error response; every bound DTO declares `validate:"..."` tags via `go-playground/validator`
- [ ] **Authorization + IDOR**: every endpoint touching user data has JWT middleware at the router-group level AND ownership scoping (`db.Where("id = ? AND user_id = ?", id, claims.UserID)`) - `auth.Required()` alone proves authentication, not object access. Depth in `task-go-review-security`
- [ ] **No raw SQL string interpolation**: `db.Exec(fmt.Sprintf(..., userInput))` / `db.Raw(fmt.Sprintf(...))` is SQL injection - use `?` placeholders or `:name` named params. Depth in `task-go-review-security`
- [ ] **GORM `Preload` / `Joins` for associations + `db.WithContext(ctx)`**: lazy `order.Items` after `Find` is N+1 or panics; queries that omit `WithContext` continue after request cancel. Depth in `go-data-access` and the perf workflow
- [ ] **No ORM model returned from handlers + Response-DTO field hygiene**: handlers map to `internal/dto/` before `c.JSON`. Compare the response DTO's `json:` field list against the model's persisted columns and flag any of `PasswordHash` / `MFASecret` / `RecoveryCodes` / `APIKey` / `WebhookSecret` / `InternalNotes` / `AuditLog` / `IsAdmin` / `Role` / `DeletedAt` / `LastLoginIP` on the model but exposed on the wire. Mirror smell: response-DTO field that doesn't exist on the model (typo / rename drift). Raw `c.JSON(200, *model.User{...})` with no DTO at all is `[High]` regardless of current fields - adding `MFASecret` to the model later silently exposes it
- [ ] **Transactions + post-commit dispatch**: writes spanning multiple tables wrapped in `db.Transaction(func(tx *gorm.DB) error {...})` (GORM auto-rollback on error return) or `sqlx.Tx` with `defer tx.Rollback()` after `Begin`; `client.Enqueue(...)` (Asynq) / `producer.Produce(...)` (Kafka) / outbound HTTP / mailers happen **after** the transaction returns nil, never inside the closure (worker may pick up before commit). Depth in `go-messaging-patterns` and the perf workflow
- [ ] **HTTP `Idempotency-Key` on retry-prone POSTs**: `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` (when upstream retries on 5xx) accept an `Idempotency-Key` header and dedupe via a `request_idempotency` table (`(tenant_id, idempotency_key)` → cached `(status, body)`). **Distinct** from `asynq.TaskID(businessKey)` (worker-side dedup) - the HTTP key protects the client→server boundary; without it, a client retry before the server response arrives creates a second DB row + enqueue regardless of worker-side dedup
- [ ] **Go quirks at boundaries**: `net.JoinHostPort` not `fmt.Sprintf("%s:%d", ...)` (breaks IPv6); `time.Now().UTC()` for stored timestamps; structured logging via `slog`, never `fmt.Println` / `log.Printf` (evades correlation IDs, redaction)
- [ ] **Migration PRs (any change in `migrations/`)**: see the Migration PRs subsection below

**Migration PRs (any change under `migrations/`):**

- [ ] Two-phase deploys for column rename / drop (add new → backfill → cut over → remove old)
- [ ] `NOT NULL` on existing columns: PostgreSQL 11+ avoids a full table rewrite when `ADD COLUMN ... NOT NULL DEFAULT <constant>` is added (the default is stored in pg_attribute, not back-filled). For older Postgres versions, for non-constant defaults (`now()`, function calls), or for adding `NOT NULL` to an *existing* nullable column on a hot table, require the two-step (add nullable → backfill → set NOT NULL via separate migration). Do not flag `ADD COLUMN ... NOT NULL DEFAULT 'literal'` on PG11+ as unsafe by default - it is safe; the row count and PG version determine the verdict
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); `golang-migrate` files contain the raw SQL so this is explicit
- [ ] **`SET lock_timeout`** before DDL on large tables to fail fast
- [ ] Foreign keys added with validation deferred (or as a separate validate step)
- [ ] Data migrations isolated from DDL migrations; long-running data backfills not in the same migration as the schema change; backfills via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] Every `up` migration has a matching `down` migration; `down` is tested or documented as one-way
- [ ] No `db.AutoMigrate` (GORM) in production code paths - migrations go through `golang-migrate` so the schema state is reproducible
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `go-migration-safety` for canonical safe-migration patterns

**Concurrency safety:**

- [ ] No mutable package-level state (`var cache = map[string]T{}` mutated by request handlers); if state is required, encapsulate in a struct with a mutex and an explicit lifecycle, or use `sync.Map` for concurrent access patterns where the surface is small
- [ ] Race-prone updates (counters, balance changes, state transitions) use database-level locking (`SELECT ... FOR UPDATE` via `db.Clauses(clause.Locking{Strength: "UPDATE"}).First(...)` in GORM, or optimistic version field) - not in-process mutexes, which only protect a single replica
- [ ] HTTP clients (`http.Client`, `resty.Client`) shared at package level - per-request `&http.Client{}` breaks connection reuse, defeats `Transport.MaxIdleConns`, and triggers excess TCP / TLS overhead
- [ ] `go test -race ./...` clean - data races at test time are confirmed concurrency bugs in production. CI must run with `-race`

Use skill: `go-data-access` for canonical GORM and sqlx correctness patterns.
Use skill: `go-error-handling` for error wrapping, sentinel errors, and `errors.As` patterns.
Use skill: `go-concurrency` for goroutine lifecycle, context, channel, mutex, and errgroup design.
Use skill: `go-gin-patterns` for Gin routing, binding, middleware, and response patterns.
Use skill: `go-messaging-patterns` for Asynq / Kafka / worker pool patterns when the diff touches messaging.

### Phase C - Go Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Go-specific architecture checks:**

- [ ] **Layering**: `handler` → `service` → `repository` → `model`. Handlers parse / validate / delegate / respond - no business logic. Services hold business rules - no `gin.Context`, no GORM, no HTTP types. Repositories return domain types (model structs or DTOs internal to the data layer), not GORM models leaked upward when the upper layer should not depend on GORM. `cmd/api/main.go` wires constructors
- [ ] **Interfaces defined at the consumer**: `OrderRepository` interface lives in the `service` package (the consumer); the `gormOrderRepository` implementation lives in `repository`. This is the Go idiom - "accept interfaces, return structs". The reverse (interface in `repository`, implementation in `repository`) creates an unused abstraction
- [ ] **Constructor injection, no `init()` / globals**: `NewOrderService(repo OrderRepository, mailer Mailer) *OrderService` - dependencies passed at construction time. `init()` functions wiring shared state, package-level variables for clients (`var DB *gorm.DB`) cause test isolation failures and hidden coupling
- [ ] **Internal vs public API split**: `internal/` packages are import-restricted by the compiler - use it for everything that should not be a public surface. Top-level packages are the public API of the module
- [ ] **No circular imports**: Go forbids them outright; refactor via shared package or interface relocation. Use `go list -deps` to inspect
- [ ] **Anemic domain antipattern (deep depth only)**: when reviewing in `deep` mode and historical pattern matching shows business rules accumulating in service files while model structs stay as pure data containers (no methods), flag for refactor via `task-go-refactor`. Do **not** raise on a single PR's evidence alone - one PR adding a service method is not "anemic accumulation."
- [ ] **Settings discipline**: typed config struct loaded once at startup via `viper` / `envconfig` / `cleanenv`; no `os.Getenv("X")` sprinkled across files - centralize so missing-at-startup fails fast. The config struct passes to constructors that need it
- [ ] **Package boundaries**: feature-package layout (`internal/orders/{handler,service,repository,model}.go`) preferred over layer-package layout (`internal/handlers/`, `internal/services/`); cross-feature imports go through public service interfaces, not direct repository imports
- [ ] **Multi-tenant isolation**: tenant scoping enforced at the repository layer (every query filters by `tenant_id` via a GORM scope or sqlx WHERE clause inserted by a wrapper), not at the controller / route layer alone
- [ ] **Gin middleware order**: `recovery → logging → request-id → CORS → auth → rate-limit → handler`. Recovery must be first to catch panics in subsequent middleware; auth after logging so unauthenticated requests are still logged; rate-limit before the handler runs
- [ ] **Router groups per domain**: `/api/v1` parent group; per-resource subgroups (`/orders`, `/users`); auth middleware applied at group level (`orders := v1.Group("/orders", auth.Required())`), not per-route - per-route is easy to forget
- [ ] **GORM scopes / hooks for cross-cutting concerns**: soft-delete (`gorm.Model.DeletedAt`), audit timestamps (`CreatedAt` / `UpdatedAt` auto-managed), tenant scoping. Hooks (`BeforeCreate`, `AfterUpdate`) used for genuinely cross-cutting concerns (audit, search-index sync) - not as a hidden control-flow mechanism dispatching emails / Asynq tasks. Move business logic to explicit service calls
- [ ] **Error-handling middleware**: `c.Error(err)` pushes errors to a Gin error-handling middleware that maps domain errors → HTTP status codes (`errors.Is(err, ErrNotFound)` → 404, `ErrUnauthorized` → 401). Per-handler `c.JSON(500, gin.H{"error": err.Error()})` scattered across files leaks internal details and is inconsistent

**Multi-service PRs (when change spans 2+ services or this Go app + a separate service):**

- API contract compatibility checked (OpenAPI diff via `swaggo/swag`, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.
Use skill: `go-overengineering-review` for: `binding:` / service-layer validation duplicating GORM / DB constraints, defensive nil checks after non-nil constructors, `if err != nil { return nil }` silent swallows, single-impl interfaces declared at the implementation side / `BaseRepository` embedded by two children / speculative config / `Result[T]` aliases for `(T, error)`, naked `go fn()` wrapping sequential calls. Each finding cites the redundancy source.

**Additional Go AI smells not covered by the above:**

- [ ] **Redundant mapping layers**: `Model → InternalDTO → ServiceDTO → ResponseDTO` when one mapping would suffice; chained `mapstructure.Decode` calls
- [ ] **Test verbosity**: setup helpers > 30 lines for a single assertion; `gomock` chains that could be a unit test on a smaller surface; full deep-equal `assert.Equal(t, response, full struct...)` when a few key field assertions would suffice
- [ ] **DTO noise**: identical DTOs reimplemented per endpoint; field-level `json:"name,omitempty"` boilerplate when the field is genuinely optional
- [ ] **Comment cruft**: comments restating function names; `// end of function foo` markers; godoc on private helpers that just repeat the signature; auto-generated TODOs left in
- [ ] **`interface{}` / `any` proliferation**: legitimate uses are rare in non-test code; `any` to bypass a real type bug is a finding. Generics (Go 1.18+) replace most legitimate `interface{}` uses

### Phase E - Go Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Go-specific maintainability checks:**

- [ ] **Naming conventions**: package names lowercase, short, no stutter (`user.UserService` → `user.Service`); exported types have doc comments starting with the type name (`// Order represents...`); private helpers documented if non-obvious; no `Util` / `Manager` / `Helper` packages accumulating unrelated functions
- [ ] **Magic numbers / strings**: extracted to package-level constants; `const (DefaultTimeout = 5 * time.Second)` over raw `5000000000` mid-expression
- [ ] **Hardcoded URLs / credentials**: in env vars / config struct, not inline in code
- [ ] **Function length**: functions > 30 lines reviewed for extraction; functions > 60 lines flagged unless they are a clearly orchestrating service function calling intention-revealing private helpers
- [ ] **Duplicated query logic**: same `WHERE` predicate in 3+ places extracted to a repository method or a GORM scope (`db.Scopes(ActiveOrders)`)
- [ ] **Logging hygiene**: surface obvious offenders as Core findings at `[Suggestion]` - `fmt.Println(...)` in production code path, `log.Printf(...)` instead of `slog`, log lines without correlation IDs, wrong log levels. The observability subagent owns depth (sampling, structured-field schemas, OTel correlation IDs, log redaction); do not duplicate that audit here. If observability is not in scope this run, still surface the obvious offenders so they are not lost.
- [ ] **`gofmt` / `goimports` clean**: no manual formatting deviations; `golangci-lint` / `staticcheck` clean (or noted exceptions documented)
- [ ] **Godoc completeness on exported APIs**: every exported type, function, and const has a `// Name does ...` comment. `swaggo/swag` annotations (`@Summary`, `@Param`, `@Success`) on Gin handlers when the project uses Swagger-generated docs

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-go-review-observability` subagent owns the depth review).

### Step 5 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                |
| -------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-go-review-perf`                                                                         |
| Core + Security      | 1 subagent running `task-go-review-security`                                                                     |
| Core + Observability | 1 subagent running `task-go-review-observability`                                                                |
| Full                 | 3 subagents running `task-go-review-perf`, `task-go-review-security`, `task-go-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 3 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Go / Gin) and detected data-access mix (GORM / sqlx / database/sql / mixed) so the subagent skips its own `stack-detect` and data-access branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a GORM query with a missing `Preload` inside a request loop can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Go idiom: unchecked `error` return, goroutine launched without cancellation, missing `defer rows.Close()`, GORM N+1 via per-iteration query, raw SQL `fmt.Sprintf` interpolation, missing JWT middleware, ORM model returned from handler, `sync.Mutex` held across HTTP call, Asynq enqueue inside transaction, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Go change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

### [Question] file:line

- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on - author intent, business rule, deployment topology, etc.]

_Use [Question] when the change is genuinely ambiguous and the right action depends on author intent. Do NOT use it as a softer Blocker._

## Architecture Notes

_Summary commentary on systemic patterns. **Do not restate individual findings here.** If a pattern is severe enough to be a finding, keep it in Findings and reference it by file:line from these notes. Use this section for cross-cutting observations the per-file findings cannot carry on their own._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes - summary commentary, not duplicated findings._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Add `defer rows.Close()` immediately after `db.QueryContext` succeeds in OrderRepository.ListByUser"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Go conventions (Effective Go, Code Review Comments wiki), not generic backend conventions
- Provide actionable feedback with Go code examples
- Never comment on trivial formatting or style where no project standard exists - assume `gofmt` / `goimports` apply
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Go subagent rather than duplicating the check here

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 (or accepted from parent dispatcher)
- [ ] Stack confirmed as Go / Gin (or accepted from parent dispatcher); data-access mix and messaging library detected and recorded
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If user passed `--base`, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated (Step 4); promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; promotion recorded in Summary
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B - every `error` return checked; wrapping uses `%w`; sentinels matched via `errors.Is`
- [ ] Phase B - context propagation (`ctx context.Context` first param, `db.WithContext(ctx)` on queries) checked
- [ ] Phase B - goroutine ownership / cancellation / `defer rows.Close()` checked
- [ ] Phase B - `ShouldBindJSON` + validator tags checked for changed DTOs
- [ ] Phase B - authentication AND authorization both checked (ownership scoping, not just JWT middleware presence)
- [ ] Phase B - GORM N+1 (`Preload` / `Joins`) and raw SQL injection (`fmt.Sprintf` in queries) checked
- [ ] Phase B - ORM-model-in-handler leak (no model returned from `c.JSON`) checked
- [ ] Phase B - transaction boundaries + post-commit Asynq / Kafka dispatch checked
- [ ] Phase B - migration safety (concurrent index, lock_timeout, expand-contract, keyset backfill, no `db.AutoMigrate` in prod) checked when migrations changed
- [ ] Phase C Go architecture checks applied: layering, interface-at-consumer, constructor injection, internal vs public, settings discipline, GORM hook discipline, multi-tenant
- [ ] Phase D applied via `complexity-review` and `go-overengineering-review` (binding tags / service guards vs GORM/DB, defensive nil after non-nil constructors, silent error swallows, single-impl interface at implementation / `BaseRepository` / speculative config / `Result[T]` over `(T, error)`, naked `go fn()` wrapping sequential calls); Go-specific AI smells covered: redundant mapping layers, test verbosity, DTO noise, `interface{}` / `any` proliferation
- [ ] Phase E Go maintainability checks applied: naming, magic numbers, function length, structured logging vs `fmt.Println`
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Go fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Go-specific subagents (`task-go-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus data-access detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Go idiom exists (say "define the interface in the consuming package", not "use dependency inversion")
- Nitpicking style where `gofmt` / `goimports` already apply
- Providing vague feedback without a concrete Go fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Go subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `panic` in service code for "this should never happen" cases - return a wrapped error instead; panics escape the error model and bypass observability
- Recommending `db.AutoMigrate` for production schema changes - migrations belong in `golang-migrate` files so the schema is reproducible and reviewable
- Recommending `db.Raw(fmt.Sprintf(...))` for "dynamic" queries - parameterize via `?` placeholders or named args, or use the query builder
