---
name: task-rust-implement
description: End-to-end Rust / Axum / sqlx feature implementation - generates migration, repository, service, handler layers with full test coverage.
agent: rust-engineer
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

# Implement Rust Feature

## When to Use

End-to-end Rust/Axum feature work: migration + model + repository + service + handler + tests in one pass.

Not for: single-file edits, bugfixes, frontend, library crates with no service around them.

## Rules

- Handlers orchestrate, services execute; no business logic in handlers. Extracting and validating a parameter is orchestration; deciding what a principal may see (admin vs owner scope) is business logic and lives in the service or middleware
- Constructor injection: `main` builds every dependency once and hands it to the router as `AppState`; no `static`, `OnceLock` or `lazy_static` for wiring
- Errors carry context at every layer: a `thiserror` enum per layer with `#[from]` / `#[source]`, so `?` converts and the chain survives; `anyhow` only in `main` and job bootstrap; no `.unwrap()` / `.expect()` on a request or job path
- Repository trait declared at the **consumer** - the service module. When model, store and service share one module tree, declare it beside the service rather than splitting crates; in a workspace where they are separate crates and the consumer depending on the implementation crate would close a dependency cycle (Cargo rejects cycles), the trait stays at the consumer and the shared type moves to a leaf crate, never the reverse. Extending an existing trait adds methods; existing signatures are not changed. A trait held as `Arc<dyn Store>` uses `#[async_trait]`, because native `async fn` in a trait is not dyn-compatible; with `#[automock]`, that attribute comes first. Where `rust-db-access` places the trait elsewhere, this rule wins, and the departure goes in Deviations
- Multi-model writes are transactional, and the **service** owns the boundary behind a `UnitOfWork` trait it declares: `begin(&self) -> Result<Box<dyn Tx>, StoreError>`, where `Tx` hands out the repositories bound to the open `sqlx::Transaction<'static, Postgres>` and `commit(self: Box<Self>)` ends it. A `Transaction` dropped without `commit` rolls back, so every `?` between `begin` and `commit` is a rollback. A fake `UnitOfWork` returns in-memory repositories, so the service unit-tests without a database; a `PgPool` cannot be mocked. When the project already holds `PgPool` in services and tests them under `#[sqlx::test]`, keep that and say so in Deviations. Never put the boundary in the repository - it has to span work the repository does not do
- Background jobs dispatched **after** `commit` returns `Ok`
- No side effects (audit logs, metrics, webhook dispatch) between `begin` and `commit` - they outlive a rollback. Buffer audit lines and flush them after commit. This governs effects that *leave* the database: an audit **row** written in the same transaction is correct, precisely because a rollback erases it too
- Design approved before code. Reading ahead is expected: consult STEP 6's atomics before the gate; the *approval* gate holds, not the reading order. When implementation proves an approved decision wrong, change it, and say so in Deviations rather than silently diverging or building the worse design
- A pre-existing defect is fixed only when the feature cannot compile or cannot run its own path without the fix (a build error, an error type with no `IntoResponse` on the route the feature adds); everything else is surfaced under `## Pre-existing Issues`, not repaired

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format. They are rule sets here: only this skill's Output Format is emitted, with one exception - `rust-testing-patterns`' `Count` format (`fns / cases`) governs the `## Tests` rows.

**Every sqlx and Axum name below is the common case, not the only one.** On Diesel (with `diesel-async`) or SeaORM, substitute the equivalent and say you did: `ON CONFLICT DO NOTHING` becomes `.on_conflict_do_nothing()`, `rows_affected()` becomes the `usize` that `execute` returns, and `sqlx-cli` migrations become `diesel migration` ones; "no persistence struct on the wire" holds on every data layer. On MySQL, `ON CONFLICT DO NOTHING` becomes `INSERT ... ON DUPLICATE KEY UPDATE id = id`, and insert-vs-duplicate is decided by re-reading on the unique key, not by `rows_affected()`. On another HTTP framework (actix-web), build each contract STEP 7 takes from `rust-web-patterns` in that framework's own API - extractors, the rejection that validation produces, `ResponseError` in place of `IntoResponse` - and name the substitution in Deviations.

## Workflow

### STEP 1 - BEHAVIORAL PRINCIPLES

Use skill: `behavioral-principles`.

### STEP 2 - DETECT AND GATHER

Use skill: `stack-detect`. Confirm Rust, the HTTP framework, `Database`, and project layout; in a Cargo workspace the member crate the feature lives in decides, its `Cargo.toml` read in place of the detected primary stack. `Database` is `unknown` when only `sqlx` is declared: read its features (`postgres`, `mysql`, `sqlite`). The toolchain comes from `rust-toolchain.toml`, else `rust-version` and `edition`. When the code is not Rust, stop and say so: this workflow is Rust-only.

Ask before writing code, grouped so each cluster surfaces its own follow-ups. Skip clusters the feature does not touch (no External questions for a pure CRUD). A question the repo's own docs answer (a design doc, an answers file, `CLAUDE.md`) is answered - cite the source instead of asking.

**Domain**
1. Feature description and primary use case
2. Entities, fields, relationships, constraints
3. Status transitions and the invariants around them

**Persistence**
4. Schema shape (tables, indexes, FKs, soft-delete?)
5. Idempotency: client-supplied key or server-derived, and what carries it - an `Idempotency-Key` header, a body field, or a provider event id. A body field rides inside the DTO the mass-assignment guard filters; a header does not
6. Bulk or streamed input, whatever carries it - an upload (multipart, presigned URL, inline JSON), a broker record, a scheduled scan. Three answers: what carries the payload, what caps it (row count, byte size, attempt budget), and - when the work must be resumable - what the rows are re-read from on resume (the stored file, staged rows, an uncommitted offset)

**External**
7. Integrations (which providers, sync vs async, timeout budget)
8. Webhooks: signature scheme, raw-body requirement, replay window

**Concurrency**
9. Background jobs / async events (a Postgres job table, apalis, Kafka via `rdkafka`)
10. Concurrency requirements (fan-out, contention, ordering)

**Access**
11. AuthN / AuthZ (JWT claims used; per-owner vs admin paths). Skip for a feature with no caller-facing surface

Ask targeted questions for gaps. Do not guess.

**When a targeted question comes back unanswered**, do not stall and do not silently pick. Carry it into STEP 3 as a named open decision with a proposed default and its consequence, and let the approval gate settle it. An unanswered question that reaches code as an unmarked assumption is the failure this rule exists to prevent.

**Existing entity:** read it and extend. Record defects found in existing code while reading, for `## Pre-existing Issues`.

### STEP 3 - DESIGN (APPROVAL GATE)

Use skill: `rust-web-patterns` for API - skip it entirely when the feature has no HTTP surface. Use skill: `rust-db-access` for data layer.

Present file tree and decisions:

- Open decisions carried from STEP 2, each with its proposed default and the consequence of that default - list these first; the gate exists to settle them
- Endpoints (method, URI, every status returned, DTOs) - omit for a worker-only feature
- Schema (indexes, FKs, CHECK, idempotency unique)
- Service methods, transaction boundaries
- Error model (`thiserror` enums per layer, their variants)
- Idempotency strategy
- Webhook design (signature middleware, raw body, outside JWT)
- Background job dispatch points

When the design extends or deviates from the defaults in this skill (e.g., adds a new HTTP status to the error map, departs from the layered file tree, chooses a different layer order), call out the deviation explicitly with the reason so the approver sees the choice rather than discovering it in code review.

Wait for approval. Record the answers, the settled defaults, and the approval (who, or `self-approved per instruction`) for `## Decisions`.

### STEP 4 - DATABASE

Use skill: `rust-migration-safety`. Reversible pairs from `sqlx migrate add -r <name>` (`<version>_<name>.up.sql` / `.down.sql`), versioned above the highest version on both base and branch. `sqlx migrate run` applies every version it has not recorded, in version order, so a branch migration versioned below one main already applied still runs - after it on a deployed database, before it on a fresh one; when its DDL depends on main's, re-version it above main's highest before merge. sqlx stores a checksum per applied version and refuses to run when an applied file changed, so an environment that applied the branch's version is reverted off it (`sqlx migrate revert`) before the file is edited. sqlx wraps each migration in a transaction; `CREATE INDEX CONCURRENTLY` needs `-- no-transaction` as the file's first line. Index FKs and frequent-filter columns. CHECK for status fields. Unique index for idempotency keys.

### STEP 5 - DATA LAYER

Use skill: `rust-db-access`. Newtype IDs (`struct RefundId(Uuid)`, `#[sqlx(transparent)]`) and status enums derive `sqlx::Type`, the enum backed by STEP 4's CHECK; the query macros need a column override to use them (`id AS "id: RefundId"`). Repository trait at the consumer; sqlx impl with `query_as!` (compile-time checked against `DATABASE_URL`, or the committed `.sqlx/` data from `cargo sqlx prepare` under `SQLX_OFFLINE=true`), methods taking `&mut PgConnection` so one impl serves the pool and an open transaction. Configure the pool once at startup (`PgPoolOptions` with `max_connections` and `acquire_timeout`). List reads use keyset pagination, which overrides any offset default in `rust-db-access` and `rust-web-patterns` - an offset list kept for an existing endpoint goes in Deviations; the cursor is an opaque encoding of the `ORDER BY` columns, and the repository re-applies the principal scope so a tampered cursor cannot cross owners.

### STEP 6 - SERVICE

Use skill: `rust-error-handling`. Use skill: `rust-security-patterns` for AuthZ scoping (IDOR), webhook signature verification, secret handling, and SSRF guards when external URLs are user-controlled. Constructor injection. Context at every `?`. `UnitOfWork` for multi-step writes.

State transitions: validate in the service via an exhaustive `match` on `(from, to)`, so a new status fails to compile until every transition is decided.

Concurrency: Use skill: `rust-async-patterns` for spawned tasks, timeouts, cancellation and `spawn_blocking`; Use skill: `rust-concurrency` for shared state, channels and `Send` / `Sync` bounds. Contention over a **database row** is a different problem with a different answer - two workers claiming the same job, two requests transitioning the same entity. Pick by whether the write needs the prior state:

- **Blind transition** (no read required): conditional `UPDATE ... WHERE id = $1 AND status = $2`, and `rows_affected() == 0` means "someone else has it" - a normal outcome, return early.
- **Read-then-write** (the new state depends on the old, as any classifier does): `SELECT ... FOR UPDATE` inside the transaction, then the guarded `UPDATE` under the held lock. Here `rows_affected() == 0` is **unreachable** - the lock guarantees the row cannot move - so treat it as a broken invariant and return an error rather than swallowing it as contention. A queue-level dedup key dedups the enqueue, not the execution, and is never the guard on its own.

Background jobs: Use skill: `rust-messaging-patterns`. Dispatch after `commit` returns `Ok`.

External APIs: bound every call (`tokio::time::timeout`, or `reqwest::ClientBuilder::timeout`); classify at the gateway into `GatewayError::{Declined, Retryable, Rejected, Indeterminate}`; declare a trait for testability.

External mutations (charge, refund, provision): never between `begin` and `commit`. Commit an intent state (e.g. `executing`) first, then make the call - via a post-commit job when retries/backoff are needed, inline when the caller waits on the result. Hyper drops the handler future when the client disconnects, cancelling it at whatever `.await` it is parked on, so an inline call plus the write that records its outcome runs inside `tokio::spawn` and the handler awaits the `JoinHandle`. The outcome re-enters as a state transition (webhook, poll, or job completion moves `executing` -> `succeeded`/`failed`); a crash between commit and call is then visible and recoverable instead of silent. An indeterminate outcome (timeout after send) is not an error at the HTTP layer: the service returns the committed `executing` row and the handler renders 202 with it, so `Indeterminate` never reaches `IntoResponse`; the error mapping produces no status below 400.

### STEP 7 - HTTP LAYER

Use skill: `rust-web-patterns`. Use skill: `rust-security-patterns` for the request DTO (no privilege-bearing fields, `#[serde(deny_unknown_fields)]`), default-deny routing (the auth layer on the protected router, `route_layer` so unmatched paths stay 404), and JWT validation (`jsonwebtoken`'s `Validation::new` pinned to one algorithm, `iss` / `aud` / `exp` checked); the principal reaches handlers through request extensions or a `FromRequestParts` extractor. Axum 0.8 routes write `/{id}`, not `/:id`. `Path` / `Query` extractors first, the body extractor (`Json`, `Bytes`, `Multipart`) last; `validator` derives checked before the service is called; `Multipart` under `DefaultBodyLimit::max`, its type from sniffed bytes and its stored name server-generated. Axum's `Json` rejects a body that fails to deserialize (an unknown field included) with 422 unless the project maps rejections; map it to 400 to match the table. Response envelope, pagination - an envelope the project already uses wins over `rust-web-patterns`' own, named in Deviations. Map domain errors in one `IntoResponse for AppError`, which writes only the rows at 400 and above; `rust-web-patterns`' idempotency layer writes the replay (at the stored original status, a stored 4xx included) and both duplicate-request 409s, adding `Retry-After` to the in-flight 409; every other row below 400 is written by the handler in the success envelope:

| Domain outcome | HTTP |
|--------------|------|
| Created | 201 |
| Accepted for async processing; external outcome indeterminate (intent row committed) | 202 |
| Duplicate request, original result returned | the stored original status (201 for a replayed create) |
| Duplicate request, original still in flight; same key with a different body | 409 (+ `Retry-After` while in flight) |
| Validation | 400 |
| Unauthenticated (absent, invalid, or expired credential) | 401 |
| Authenticated but wrong role | 403 |
| Not found; resource owned by another principal (the owner-scoped lookup finds nothing) | 404 |
| Conflict | 409 |
| Gone (expired single-use link token, deleted resource) | 410 |
| Payload too large (body over `DefaultBodyLimit`, row-count cap exceeded) | 413 |
| Invalid transition | 422 |
| Provider declined the operation (`GatewayError::Declined`) | 402 |
| External unavailable before send, or rate-limited (`GatewayError::Retryable`) | 503 |
| Provider rejected the request with a decoded non-5xx error other than a decline or a rate limit (`GatewayError::Rejected`: invalid account, invalid parameters); an undecoded error or a 5xx after a mutation was sent is `Indeterminate` and renders 202 per STEP 6 | 502 |
| Already-processed webhook event | 200 (return success so provider stops retrying) |

401 and 403 are different answers: 401 means "we do not know who you are", 403 means "we do and you may not". 404 for another principal's resource is the default because the owner-scoped query finds nothing; a 403 after an unscoped load confirms the resource exists (an existence oracle) and repeats a handler-level ownership check after the fact.

201 and 202 split on whether the thing the client asked for exists once you answer: a request that writes its row synchronously and only defers the work *on* that row is 201, while one with nothing yet to show is 202. A retry landing while the original is still working has no result to replay - 409 with `Retry-After` tells the client to retry shortly, not to abandon.

**Centralized rendering, per-domain classification.** `AppError` owns the envelope and the status write; each domain module implements `From<DomainError> for AppError`, choosing the status for its own variants, so `?` in a handler converts and the web module never names a domain's variants. Where `rust-error-handling` shows one `match` over every domain's variants, this wins.

Duplicate webhook events return 200: Stripe and similar providers retry on any non-2xx, so a duplicate-detection 409 produces a retry storm (GitHub does not redeliver automatically, but a 4xx still shows as a failed delivery). Treat duplicate as a no-op success.

Webhooks: the handler takes `body: Bytes` and verifies the signature over those bytes (`hmac`'s `verify_slice`, constant-time) before deserializing; route lives on a router merged without the JWT layer.

### STEP 8 - TESTS

Use skill: `rust-testing-patterns`. `#[tokio::test]` with `mockall` mocks or hand-written fakes for services; `#[sqlx::test]` or a testcontainers PostgreSQL for repositories; `tower::ServiceExt::oneshot` on the production `Router` when there is an HTTP surface.

Cover happy path, validation, not-found, conflict, timeout. On a worker those read as: a well-formed record, a malformed payload, a referenced entity that does not exist, a concurrent or duplicate delivery, and a cancelled or timed-out per-record future. State machines: every valid + invalid transition. Webhooks: valid / invalid / missing signature. Idempotency: duplicates return the same result and the side effect happens once. Ownership: another principal's resource is 404. Codec and helper functions count under `Unit`; `proptest` properties count there too.

### STEP 9 - VALIDATE

Run `cargo build --all-targets`, `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check`, `cargo test` (or `cargo nextest run` plus `cargo test --doc`, since nextest skips doctests), and `cargo sqlx prepare --check -- --all-targets` when the crate uses the query macros. Database-backed tests need a reachable Postgres (`DATABASE_URL`, or Docker for testcontainers). Fix failures before reporting done; a database-backed run that could not execute is labelled unverified in `## Validation`.

**When the toolchain is absent** (`cargo --version` fails), the step cannot pass and must not be reported as passing; when only the database is missing and the query macros have no `.sqlx/` data, nothing that uses them compiles - label those crates unverified in `## Validation` rather than reporting the build green. With no toolchain, do a static substitute - trait signatures against every impl, mock and fake, `From` impls behind every `?` that crosses an error type, `Send` bounds on futures that hold a guard or `Rc` across `.await` (Axum rejects such a handler), unused imports - then label the delivery `unverified: not compiled` in the Output Format and name the commands that would settle it. Macro-expanded queries, database-backed tests, and anything behind a cargo feature stay unverified regardless; say which. A static check that fails is a defect, not a note - fix it before reporting done, exactly as a failing build would be.

## Edge Cases

- No persistence: skip STEPs 4-5
- Webhook-only: skip CRUD; signature verification + dedicated handler
- State transitions: service validation + DB CHECK
- Idempotency: unique key + upsert-on-conflict + service guard. When the idempotent operation is an **UPDATE**, there is no inserted row to carry the key - add a dedupe carrier (an `inbox` / `processed_events` table keyed on the event id, inserted in the same transaction as the effect) or the redelivery re-runs and, on a state machine, writes a spurious invalid-transition failure
- Bulk: batch writes + input size limit; one transaction when all-or-nothing, one per chunk when a partial import must be resumable. Resumability needs three things this rule does not name: a durable source the rows are re-read from (the stored payload, staged rows, or a re-fetchable object), a cursor advanced in the same transaction as the chunk, and a claim so two workers cannot resume the same job
- Worker-only (no HTTP): skip STEP 7 and STEP 3's `rust-web-patterns` load; omit Endpoints from the design and from the output; test the job handler instead of `oneshot`, and read the output's `Handler` count row as the handler-level tests of whatever the entry point is (a job processor, a consumer)

## Output Format

While the STEP 3 gate is open the deliverable is the design presentation alone, open decisions first; the sections below are emitted once the design is approved and the code written.

```markdown
## Files Generated
[grouped by layer; mark each created or modified]

## Decisions
[Each STEP 2 question with its answer and source, each open decision with the default that settled it, and the approval record (`approved by <who>` or `self-approved per instruction`). Assumptions about existing code (`models::Refund` already exists) belong here too.]

## Endpoints
| Method | Path | Request | Response | Statuses |

_Omit this whole section for a worker-only feature._

## Tests
[Any row with nothing to count reads `n/a - <reason>`; counts follow `rust-testing-patterns`' `fns / cases`]
- Unit: {fns / cases}
- Handler: {fns / cases} [HTTP handlers; with no HTTP surface, every job / consumer entry point]
- Jobs: {fns / cases} [job/consumer handlers; omit the row unless the feature has both an HTTP surface and background work]
- Integration: {fns / cases}

## Migration
[file names + what they create]

## Deviations
[Every choice that departs from this skill's defaults or from the approved design - the error-map row added, the layout change, the layer order, a decision reversed during implementation - each with its reason. `None` when there are none. The list surfaced at the STEP 3 gate, written down.]

## Pre-existing Issues
[Defects in existing code that this change did not introduce, each marked surfaced-only or fixed-with-reason per the Rules. `None` when there are none.]

## Validation
`cargo build --all-targets` / `cargo clippy --all-targets -- -D warnings` / `cargo fmt --check` / `cargo test` (or `cargo nextest run` + `cargo test --doc`) / `cargo sqlx prepare --check` - per command `passed` or `unverified: <reason>` (database-backed tests without Postgres, query macros without `.sqlx/` data), or for the whole delivery `unverified: not compiled` with the reason and what was checked instead.
```

## Self-Check

Mark a line N/A with its reason when the feature has no matching surface - no HTTP layer, no persistence, no webhook - or when a default needed no adaptation because the project already runs the library it names.

- [ ] Step 1: behavioral-principles loaded
- [ ] STEP 2: Rust confirmed (else stopped), framework, `Database` and toolchain detected; requirements gathered, repo-answered questions cited; unanswered questions carried to the gate as named open decisions; existing-code defects recorded
- [ ] STEP 3: design approved before code; deviations called out at the gate **and** written into `## Deviations`; decisions and approval written into `## Decisions`
- [ ] STEP 4: reversible migrations versioned above the highest on base and branch; no applied file edited; `-- no-transaction` on concurrent index builds; FKs and filters indexed; CHECK on status; unique index on idempotency keys
- [ ] STEP 5: repository trait at the consumer, methods on `&mut PgConnection`; every sqlx-named default adapted to the detected data layer, with the substitution stated; list reads keyset-paginated, or an offset list kept for an existing endpoint named in `## Deviations`
- [ ] STEP 6: `thiserror` per layer, no `.unwrap()` on request paths; constructor injection; `UnitOfWork` boundary in the service; jobs dispatched after commit; no side effects before commit; transitions matched exhaustively; external mutations behind a committed intent state and shielded from cancellation
- [ ] STEP 7: status table applied, `Json` rejections mapped to 400; per-domain `From` impls; request DTO free of privilege-bearing fields; webhook raw body, signature, outside JWT, duplicate-as-200; on another HTTP framework, the substitution named in `## Deviations`
- [ ] STEP 8: tests cover happy path, validation, not-found, conflict, timeout, every valid and invalid transition, valid / invalid / missing webhook signature, a duplicate proving the side effect ran once, and another principal's resource
- [ ] STEP 9: build, clippy, fmt, tests and the sqlx offline check pass - or, when the database-backed run could not execute, it is labelled unverified in `## Validation` - or, with no toolchain, the static substitute ran and the delivery is labelled `unverified: not compiled`

## Avoid

- Editing a migration file an environment has already applied
- Generating code before design approval
- `Json` extractor on webhook endpoints
- Returning 4xx for a duplicate webhook event (a retrying provider keeps redelivering it)
- Blocking the Tokio runtime with sync I/O or CPU-bound hashing outside `spawn_blocking`
- Fixing a pre-existing defect the feature can compile and run without
