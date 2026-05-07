---
name: task-rust-refactor
description: Rust refactor planning for fat Axum handlers, anemic services, god modules, leaked Tokio tasks, missing CancellationToken, std::sync::Mutex held across .await, sqlx N+1, mass assignment via serde_json::from_value, single-implementation traits, Box<dyn Trait> defaults where generics fit, Arc<Mutex> overuse, package-level mutable state, and background-task idempotency. Produces a step-by-step sequence of independently-committable refactoring steps with a `cargo test + cargo clippy` coverage gate. Stack-specific override of task-code-refactor for Rust.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rust Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Rust target (Axum handler, service, repository, sqlx model, background-task processor, DTO). Identifies Rust-specific smells (fat handler, anemic services, god modules, `tokio::spawn` without owner / cancellation, `std::sync::Mutex` held across `.await`, sqlx N+1, mass assignment via `serde_json::from_value::<DomainModel>(req.body)`, package-level mutable state via `static` / `lazy_static!`, single-impl traits, `Box<dyn Trait>` where generics fit, `Arc<Mutex<T>>` where `Arc<T>` or `Arc<RwLock<T>>` fits better, `panic!` / `.unwrap()` in service code, background-tasks lacking idempotency, `unsafe` without SAFETY comment) and proposes independently-committable refactoring steps with `cargo test` + `cargo clippy --all-targets -- -D warnings` gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Rust.

## When to Use

- Rust code-smell identification and resolution
- Rust technical-debt reduction with a concrete plan
- Safe refactoring of a handler / service / repository / module / background-task processor
- Pre-merge "this PR grew the fat-handler / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-rust-implement`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes / panic investigations (use `task-rust-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                                  |
| --------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Target scope          | Yes         | File or module to refactor (e.g., `src/orders/handler.rs`, `src/orders/service.rs`, `src/worker/payment_processor.rs`)                                       |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `place_order` service from handler, swap `std::sync::Mutex` for `tokio::sync::Mutex`, split `OrdersService` god module) |
| Test coverage status  | Recommended | Whether `#[cfg(test)] mod tests` / `tests/` integration / testcontainers / job coverage exists for the target area; whether `cargo clippy` is clean         |
| Shared/public surface | Recommended | Whether the target is `pub` across module / crate / workspace boundaries                                                                                     |

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm Rust / Axum. If invoked as a subagent of a Rust-aware parent, accept the pre-confirmed stack. If the detected stack is not Rust, stop and tell the user to invoke `/task-code-refactor` instead.

Detect data access (sqlx / diesel / mixed) and messaging (Tokio queue / AMQP / Kafka / none). Record `Data Access`, `Messaging` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target file top-to-bottom; note function count, longest function, sync-vs-async signature mix (`fn` vs `async fn`, `Result<T, AppError>` returns), transaction placement (`pool.begin()...tx.commit()`), every external collaborator (`reqwest::Client`, message dispatch, mailers, `.await` points)
2. Read the matching test file(s) (`#[cfg(test)] mod tests` blocks, `tests/<feature>_test.rs` files); count cases by outcome (happy path, validation failure, external failure, auth denial). Confirm `cargo clippy --all-targets -- -D warnings` runs clean (or note it doesn't)
3. If callers are obvious (handler calling the service, scheduled task calling the service), read the immediate caller too - removing or reshaping a `pub fn` without seeing call sites is how silent breakage happens

If the user named only the goal without a target file / module, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat modules. If the file containing the target also contains other smells (e.g., the user names `create_order` but the same handler file has IDOR in `get_order` and a `Command::new("sh").arg("-c").arg(user_input)` in `bulk_import`), do **not** action them in this plan and do **not** ignore them silently. List them under a `Sibling Smells (Out of Scope)` heading in the output, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-rust-review-security`), and recommend follow-up invocations.

**Severity-inversion rule.** When any sibling smell is *higher severity* than the named primary target (e.g., the user asks to extract a fat handler, but the same file contains a working SQL injection, an `Command::new("sh").arg("-c")` RCE, an authentication bypass, or `Validation::default()` accepting `alg: none`), recommend pausing the refactor and routing the security finding first. State this prominently in the `Sibling Smells (Out of Scope)` table's `Recommended follow-up` column with phrasing like `Fix before refactor: invoke task-rust-review-security on this file; refactor PR should branch off the security fix, not main`. The refactor skill produces a plan; it does not silently let an in-scope severe finding land via a refactor PR that doesn't address it.

**Severity-inversion banner.** When the inversion rule fires, **also render a one-paragraph banner at the top of the Coverage Gate section** (above the status verdict) so the inversion is impossible to skim past. Suggested form: `> **Severity inversion detected.** This file contains <N> sibling smells of higher severity than the named target (<list>). Recommended next action: pause this refactor; route through task-rust-review-security first; branch the eventual refactor PR off the security fix. See Sibling Smells (Out of Scope) below for details.`. The banner is required when inversion fires regardless of whether the Coverage Gate verdict is `Adequate` / `Thin` / `Inadequate` - the gate verdict and the inversion are orthogonal concerns.

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (`#[cfg(test)] mod tests`, integration tests under `tests/`, testcontainers tests, background-task processor tests), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                   | What the workflow does                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., validation failure, auth denial, external failure, not-found) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                               | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                        | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-rust-test` first               |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves validation, authorization, or error behavior - you would be flying blind.

**Lint-gate check.** `cargo clippy --all-targets -- -D warnings` must be clean for the target crate, OR the refactor plan must include cleaning it as Step 0a. Refactoring on top of unaddressed clippy warnings risks masking new lint hits behind existing ones. Lint state values: `clean` (no warnings), `warnings present` (Step 0a covers them), or `not run (no baseline)` (greenfield / net-new project where clippy hasn't been wired into CI yet - the plan's first step folds clippy into the coverage prerequisite work so the refactor isn't the first thing to find lint debt).

**Concurrency-gate check.** If the target module spawns `tokio::spawn` / `JoinSet`, holds `Arc<Mutex>` / `Arc<RwLock>`, or uses channels, also confirm tests exercise the concurrent paths (`#[tokio::test(flavor = "multi_thread")]` for cross-thread cases). If absent, treat coverage status as one tier worse (Adequate → Thin, Thin → Inadequate) - refactoring concurrent code without concurrent test coverage is unsafe.

**Output of this step:** explicit coverage status using one of the three labels above. Do not proceed past Step 4 if status is `Inadequate`.

### Step 4 - Identify Rust Smells

Inspect the target for these Rust-specific smells. Use judgment - these are signals, not hard rules.

**Handler / Route smells:**

| Smell                                   | Signal                                                                                                                                                                                              | Risk   |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Handler                             | Handler > 30 lines of orchestration (multiple service calls, conditional dispatch, response shaping, business rules)                                                                                | High   |
| Logic in Handler                        | Business rules, validation beyond `Json<T>` extractor + `Validate` derives, calculation, or domain decisions inside the handler                                                                     | High   |
| Direct sqlx Query in Handler            | Handlers call `sqlx::query!(...)` directly, bypassing the service / repository layer                                                                                                                | Medium |
| `FromRow` Struct Returned from Handler  | Handler returns `Json(user)` where `user: User` is a sqlx `FromRow` struct (mass-assignment + leak risk: leaks `password_hash`, soft-delete columns, internal fields)                               | High   |
| Manual Validation Duplicating Derives   | Handler body re-checks `req.name.len() > 0` constraints already on the `#[validate(...)]` field tag                                                                                                 | Low    |
| Per-handler `(StatusCode::INTERNAL_SERVER_ERROR, "...")` Errors | Inline error mapping scattered across handlers instead of `Result<_, AppError>` + `IntoResponse for AppError` central mapping                                          | Medium |
| Missing `Validate` derive on DTO        | DTO declared with `Deserialize` but no `Validate` - anything-goes input                                                                                                                              | High   |
| Mass Assignment via `serde_json::from_value` | `serde_json::from_value::<Order>(req.body)?` decoded directly into a domain model - client can override server-set fields like `user_id`, `role`                                              | High   |

**Service smells:**

| Smell                              | Signal                                                                                                                                                                          | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Service File                   | `*_service.rs` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                                                                             | High   |
| Anemic Domain                      | Structs are pure data containers; business rules live in `*_helpers.rs` with names like `calculate_total(order: &Order)` and could belong as methods in an `impl Order` block   | High   |
| Single-Implementation Trait        | `OrderRepository` trait + single `PgOrderRepository` impl with no mock generated (no `#[automock]`) and no second implementation - the trait adds nothing                       | Medium |
| Missing `&self` async fn signature | Method does I/O / blocks but takes `&mut self` without need - prevents shared concurrent access                                                                                 | Medium |
| `panic!` / `.unwrap()` in Service Code | `.unwrap()` for "should never happen" cases - return a wrapped `AppError` instead; panics escape the error model and bypass `IntoResponse`                                  | High   |
| External I/O Inside Transaction    | `reqwest::Client::get(url).send().await` or message publish inside `let mut tx = pool.begin().await?; ...; tx.commit().await?` (defers commit, holds DB locks long, races worker pickup before commit) | High   |
| Returning `Option` From Failure-Capable Operation | Service returns `Option<T>`; caller cannot distinguish failure cases (validation vs not-found vs external) - return `Result<T, AppError>` with thiserror variants | Medium |
| Floating `tokio::spawn`            | `tokio::spawn(async move { ... })` in a service body without ownership (no `JoinHandle`, no `JoinSet`) and without a cancellation path (no `CancellationToken`) - leak           | High   |

**Persistence / sqlx smells:**

| Smell                                        | Signal                                                                                                                                                                                                          | Risk   |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Repository                               | Repository struct with > 300 lines of methods; mixes mapping, computed properties, business operations, validation                                                                                              | High   |
| Repository Returns `FromRow` Struct Upward   | Service / handler imports the sqlx `FromRow` struct directly and uses it as the domain type - couples upper layers to sqlx                                                                                      | Medium |
| sqlx Runtime Query Where `query!` Would Fit  | `sqlx::query("SELECT ... WHERE id = $1").bind(id)` for static SQL - `query!`/`query_as!` would compile-time-check the schema                                                                                   | Medium |
| sqlx N+1 via Per-Iteration Query             | `for parent in parents { sqlx::query!("... WHERE parent_id = $1", parent.id)... }` - N round-trips                                                                                                              | High   |
| `sqlx::query(&format!(...))` String Concat   | Dynamic SQL built via string concatenation instead of parameterized `sqlx::query("... WHERE col = $1").bind(val)` or query builder                                                                              | High   |
| `fetch_all` Without Pagination               | Returns full table without `LIMIT` / `OFFSET` or keyset pagination                                                                                                                                              | Medium |
| Long-Running Transaction Holding Connection  | `let mut tx = pool.begin().await?;` followed by external I/O before `tx.commit().await?` - holds a pool connection for the network roundtrip                                                                    | High   |
| `Pool::connect` Per Request                  | New pool per handler defeats pooling - pool lives on `AppState`, cheap to clone                                                                                                                                  | High   |

**Configuration / DI smells:**

| Smell                        | Signal                                                                                                                                                              | Risk   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Module-level Mutable Statics | `static MUT_CACHE: Lazy<RwLock<HashMap<...>>>` mutated by request handlers; or worse, `static mut`                                                                  | High   |
| Module-level `Pool` Var      | `static POOL: OnceCell<PgPool>` accessed directly by repositories instead of `AppState` constructor injection                                                       | High   |
| `std::env::var("X")` Sprinkled | `std::env::var` scattered across modules; should be loaded once into a typed config struct at startup (`figment` / `config` / `envy`)                             | Medium |
| Hardcoded Defaults Inline    | Default values inline in code rather than a typed config struct                                                                                                     | Medium |
| Single-Impl Trait            | Trait defined for a single concrete type with no `#[automock]` / no test mock and no second implementation                                                          | Medium |
| Trait At Producer (Java idiom) | Trait defined in the module that implements it; Rust idiom is trait at the consumer (mirrors Go's "accept interfaces, return structs")                            | Medium |
| `Box<dyn Trait>` Where Generics Fit | `fn handle(svc: Box<dyn OrderService>)` for a single callsite - `fn handle<S: OrderService>(svc: S)` (static dispatch) is cheaper and more idiomatic for hot or single-callsite paths | Medium |

**Concurrency / Async smells:**

| Smell                                      | Signal                                                                                                                                                  | Risk   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `tokio::spawn` Without Owner               | `tokio::spawn(async move { ... })` in a long-running service without a `JoinHandle` held / awaited or `JoinSet` membership                              | High   |
| `tokio::spawn` Without Cancellation Path   | Long-lived spawned task with `loop { ... }` and no `tokio::select! { _ = token.cancelled() => ... }` arm - leak / no graceful drain                     | High   |
| Unbounded `tokio::spawn` Fan-out           | `for url in urls { tokio::spawn(...) }` over a big list without `JoinSet` + semaphore / spawn limit - exhausts pool / file descriptors at scale         | High   |
| `std::sync::Mutex` Held Across `.await`    | `let g = std_mutex.lock().unwrap(); some_async().await; drop(g)` - blocks the executor thread, deadlock risk                                            | High   |
| `Arc<Mutex<T>>` Where `Arc<T>` Suffices    | Immutable shared data wrapped in `Mutex` for no reason - the lock adds contention with no protection benefit                                            | Medium |
| `Arc<Mutex<T>>` Where `Arc<RwLock<T>>` Fits | Read-heavy concurrent state held under `Mutex` instead of `RwLock` - serializes readers unnecessarily                                                  | Medium |
| Unbounded `mpsc::unbounded_channel`        | Memory leak under producer-faster-than-consumer; use `mpsc::channel(N)` and decide drop / await policy                                                  | High   |
| Channel Receive Without Cancellation Pair  | `let msg = rx.recv().await;` in a long-lived loop without `tokio::select!` cancellation arm - cannot drain on shutdown                                  | High   |
| Background-Task Dispatch Inside Transaction | Task enqueued inside `pool.begin()...commit()` - worker may pick it up before commit                                                                   | High   |
| Background-Task Without Idempotency        | Task that re-runs side effects when delivered twice (no dedup, no upsert, no state check)                                                               | High   |
| Blocking I/O on Runtime                    | `std::fs::read_to_string`, `std::thread::sleep`, `bcrypt::hash` (CPU-heavy) on an `async fn` without `spawn_blocking`                                   | High   |
| Nested Tokio Runtime                       | `Runtime::new().block_on(...)` inside an `async fn` already running on a runtime - panics                                                               | High   |

**`unsafe` smells:**

| Smell                       | Signal                                                                                              | Risk   |
| --------------------------- | --------------------------------------------------------------------------------------------------- | ------ |
| `unsafe` Without SAFETY     | `unsafe { ... }` block with no `// SAFETY:` comment naming what the caller must uphold              | High   |
| `unsafe` for Speed Without Bench | `unsafe` used because "it's faster" without a benchmark proving the win                       | Medium |
| `static mut`                | Module-level mutable state via `static mut` - inherently `unsafe`; use `Mutex` / `RwLock` / `OnceCell` | High   |

**Test smells (when refactoring brings tests into scope):**

| Smell                                       | Signal                                                                            | Risk   |
| ------------------------------------------- | --------------------------------------------------------------------------------- | ------ |
| Repository Mocked With In-Process State     | `MockRepo { state: Mutex<HashMap> }` instead of using a testcontainers integration test                                                                              | Medium |
| SQLite in Repository Tests for Postgres App | Tests pass on SQLite but fail in prod on JSONB / partial index / `ON CONFLICT`; sqlx compile-time-checked queries are validated against PostgreSQL specifically       | High   |
| In-Process Job Mocking Reality              | Mock processor hides at-least-once / retry / DLQ semantics                        | Medium |
| Copy-Paste Test Functions                   | Multiple near-identical test fns where a `Vec<Case>` loop or `rstest` would do    | Low    |
| `Box<dyn Any>` In Test Mocks                | Type-cast escape hatch used to bypass a real type bug                             | Medium |

**General OO smells (apply with Rust judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl traits, abstract base structs for two embedders, premature factory / strategy, redundant mapping layers) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply Rust judgment - a 25-line service fn orchestrating clearly named private fns is fine; a 10-line fn doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected by the refactor.

Rust-specific blast-radius signals:

- [ ] **Public API surface**: target is a handler used by external clients - refactor risks API contract change
- [ ] **Crate / workspace boundary**: target is in a published crate or a workspace member consumed by other binaries (`pub` in `lib.rs`)
- [ ] **Trait with broad implementor surface**: refactoring a trait connected to many impls / consumers cascades
- [ ] **Service injected widely**: target is constructed in `src/main.rs` and stored on `AppState` - signature changes cascade to every handler that uses `State<AppState>`
- [ ] **`FromRow` / domain struct used in many queries**: refactoring a struct affects every repository / `query_as!` call
- [ ] **DTO reused across endpoints**: DTO field rename / removal cascades into every dependent endpoint and its tests
- [ ] **Exported `pub` symbol**: refactoring a `pub` type / fn means every importer breaks

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single module, multiple callers) / **Wide** (cross-module, public handler API, broad trait) / **Critical** (published crate, struct used by 5+ consumers).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles with `cargo build` cleanly and the test suite passes after each step (`cargo test` and `cargo clippy --all-targets -- -D warnings`)
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`, see below)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing test suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target (e.g., a fat handler that also has `serde_json::from_value::<Order>(req.body)`, leaks a Tokio task, and stashes a `FromRow` struct in a module-level cache), do **not** concatenate the recipes - that produces a 25-step plan mixing concerns. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly in the output via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs rather than one mega-plan.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a service that derives `user_id` from JWT claims _requires_ the principal to be available, so adding auth middleware to the route is a structural prerequisite). Label the step `coupled-fix` in the Output Format with its own test gate and rationale.

**Transaction-boundary watch.** When extracting orchestration that runs inside `let mut tx = pool.begin().await?; ... tx.commit().await?;`, the extracted unit may inherit the transaction context if it takes `&mut Transaction` or runs inside the closure. If the extracted code makes HTTP calls, publishes to a queue, or writes files, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's transaction (`&mut tx` parameter)" or "callee uses post-commit dispatch (capture inputs, dispatch after `tx.commit().await?` returns)." Never silently move I/O across a transaction boundary.

**`.await`-in-critical-section watch.** When restructuring code that takes `std::sync::Mutex` or `tokio::sync::Mutex` guards, state explicitly whether any `.await` happens while a guard is held. `std::sync::Mutex` across `.await` is always wrong (deadlocks the executor); `tokio::sync::Mutex` across `.await` is allowed but should be minimized. Refactors that introduce async work inside a previously-sync critical section need their lock strategy named.

**Cancellation-stance watch.** Adding `tokio::spawn` / `JoinSet` introduces concurrency. State whether `CancellationToken` is added for graceful shutdown - if not, the new task leaks at process termination. State whether tests cover the concurrent path (`#[tokio::test(flavor = "multi_thread")]`) - if not, the new race surface is unguarded.

**Common Rust refactor recipes:**

**Recipe: Extract service from fat handler**

1. Add `src/<feature>/service.rs` (or new file alongside) with a single intention-revealing method `pub async fn place(&self, ctx: PlaceOrderInput) -> Result<PlaceOrderResult, AppError>`; copy logic from handler; handler still does the original work
2. Add `#[cfg(test)] mod tests` (or `tests/<feature>_service_test.rs`) with table-driven tests covering one case per outcome (success, validation failure, external failure)
3. Update handler to call the service via `State<AppState>` extractor; preserve response shape; ensure handler tests pass unchanged
4. Remove the original logic from the handler; verify handler tests pass
5. Add a handler-level test asserting service failure surfaces as the expected error response (likely via `AppError` → `IntoResponse` central mapping)

**Recipe: Eliminate `tokio::spawn` leak**

1. Identify the leaked task - bare `tokio::spawn(async move { ... })` in a request handler / service, no `JoinHandle` retained, no `CancellationToken`
2. Wrap in `JoinSet`: `let mut set = JoinSet::new(); set.spawn(async move { ... });` and keep the set on the owning struct; for unbounded fan-out, control via a `Semaphore::new(N)` acquired before each spawn
3. Add `tokio::select! { _ = token.cancelled() => return Ok(()), ... = work => ... }` arms to any blocking `select!` or `recv` inside the task
4. `while let Some(res) = set.join_next().await { res??; }` (or equivalent) at the end of the orchestrator to surface panics and errors instead of dropping them
5. Run `cargo clippy --all-targets -- -D warnings` and `cargo test`; confirm clean. If `#[tokio::test(flavor = "multi_thread")]` was not used for this module, add it
6. Validate task count under load (or via `tokio-console`) shows no growth over time

**Recipe: Eliminate `std::sync::Mutex` held across `.await`**

1. Identify the offending guard: `let g = mutex.lock().unwrap(); some_async().await; drop(g)` - blocks the executor thread, classic deadlock pattern
2. Decide: does the lock need to span the await? If no (typical case), drop the guard before the await:
   ```rust
   let value = {
       let g = mutex.lock().unwrap();
       g.clone()
   }; // guard drops here
   let result = io_call(value).await?;
   {
       let mut g = mutex.lock().unwrap();
       g.apply_result(result);
   }
   ```
3. If yes (must hold across await), swap to `tokio::sync::Mutex`: `let g = tokio_mutex.lock().await;` - this yields cooperatively instead of blocking the executor. State explicitly that the lock now spans an await
4. Run `cargo clippy --all-targets -- -D warnings` and `cargo test`; confirm clean
5. Add a benchmark asserting throughput improves (`criterion`) when contention was the original problem

**Recipe: Add `CancellationToken` to a long-lived task**

1. Add `tokio_util::sync::CancellationToken` to the worker struct; pass a clone to each spawned task
2. Wrap the inner loop in `tokio::select! { _ = token.cancelled() => return Ok(()), msg = rx.recv() => { let Some(msg) = msg else { return Ok(()) }; process(msg).await?; } }`
3. On graceful shutdown (in `main.rs` or the supervisor), call `token.cancel()` and `set.shutdown().await` (for `JoinSet`) or `handle.await` (for individual `JoinHandle`)
4. Run `cargo clippy --all-targets -- -D warnings` and `cargo test`; confirm clean
5. Add a test asserting the task drains cleanly on `token.cancel()` within a bounded timeout

**Recipe: Eliminate single-implementation trait**

1. Confirm the trait has no `#[automock]` / no test mocks, no second implementation, no construction-time abstraction need
2. Inline: the consuming code uses the concrete struct directly - `pub struct OrderService { repo: Arc<PgOrderRepository> }` instead of `pub struct OrderService<R: OrderRepository> { repo: R }`. Delete the trait
3. Run `cargo clippy --all-targets -- -D warnings` and `cargo test`; confirm pass. Caller code is shorter and clearer
4. **Skip if** the trait is part of a published crate API or has a real second implementation (or a `mockall`-generated mock used in tests) - the smell is fake

**Recipe: Move trait from producer to consumer**

1. Identify the trait defined in the implementing module (Java style: `repository/order_repository_trait.rs` declaring `pub trait OrderRepository {...}` next to the implementation)
2. Move the trait declaration into the consuming module (typically `service`): `service/order.rs` declares the trait alongside the service that consumes it
3. Update imports; the producer (`repository`) no longer references the trait - it just exposes its concrete struct via `pub fn new(...) -> Self`
4. Run `cargo clippy --all-targets -- -D warnings` and `cargo test`; confirm pass
5. The Rust idiom is now followed - traits declared at the consumer (mirrors "accept interfaces, return structs")

**Recipe: Replace `Box<dyn Trait>` with generic parameter (where one callsite / hot path)**

1. Identify the `Box<dyn Trait>` use: `pub fn handle(svc: Box<dyn OrderService>) -> ...`
2. Convert to generic parameter: `pub fn handle<S: OrderService>(svc: S) -> ...` (or `impl OrderService` for argument-position-only)
3. If the trait is object-safe and the heterogeneous storage need is real (e.g., `Vec<Box<dyn Handler>>`), keep `Box<dyn Trait>` and skip the change
4. Run `cargo clippy --all-targets -- -D warnings` and `cargo test`; confirm pass; benchmark if it was on a hot path

**Recipe: Split god service into focused services**

1. Identify the orthogonal concerns inside the service file (e.g., `orders/service.rs` doing place + cancel + refund + reporting → split into `place.rs`, `cancel.rs`, `refund.rs`, `report.rs` with focused service structs or focused methods on a smaller `OrderService`)
2. Extract one concern at a time into a new file with explicit constructors; original god service delegates to it temporarily
3. Update callers to use the new focused service directly via `AppState`; remove delegation from god service
4. Repeat until god service is empty; delete it. Each extraction commits independently
5. Verify all tests still pass

**Recipe: Make background-task idempotent**

1. Add a task test asserting the side effect happens exactly once when the same payload is processed twice (different request IDs, same business key)
2. Add an idempotency guard inside the handler: dedup table keyed by a business key; upsert via `INSERT ... ON CONFLICT (key) DO NOTHING` (sqlx); or version check
3. Verify retries on transient failures still complete the work
4. Configure max-retries / DLQ explicit on the task type so poison messages do not loop forever
5. Use a client-side dedup key on enqueue when the same input must collapse to one task

**Recipe: Eliminate mass assignment via `serde_json::from_value`**

1. Identify the unsafe decode: `serde_json::from_value::<Order>(req.body)?`, `serde_json::from_slice::<Order>(body)?` directly into a domain model
2. Define a request DTO with explicit fields and `#[validate(...)]` derives:
   ```rust
   #[derive(Deserialize, Validate)]
   pub struct UpdateOrderRequest {
       #[validate(length(max = 500))]
       pub notes: String,
   }
   ```
   No `user_id`, `role`, `is_admin`, etc.
3. Replace the decode with `Json(req): Json<UpdateOrderRequest>` extractor + `req.validate()?`, then explicit field copy: `order.notes = req.notes;`
4. Add a test attempting to inject `user_id` / `role` keys; assert they are stripped
5. Audit other unsafe decodes in the codebase

**Recipe: Replace module-level mutable static with constructor-injected state**

1. Identify the mutable state (`static MUT_CACHE: Lazy<RwLock<HashMap<...>>>`, `static POOL: OnceCell<PgPool>`, `static mut HANDLERS: ...`)
2. Move into a struct with a constructor: `pub struct Cache { inner: Arc<RwLock<HashMap<K, V>>> }`; `pub fn new() -> Self { ... }`; stored on `AppState`
3. Replace module-level reads/writes with method calls on the injected instance
4. Update callers to receive the new dependency explicitly via `State<AppState>` extractor (handlers) or constructor argument (services), typically wired in `src/main.rs`
5. Run `cargo clippy --all-targets -- -D warnings` and `cargo test`; confirm pass; assert cross-test isolation (no leaking state between tests when running with `cargo test` parallel by default)

**Recipe: Wrap blocking work in `spawn_blocking`**

1. Identify the blocking call inside an `async fn`: `bcrypt::hash(pw, cost)`, `std::fs::read_to_string(path)`, sync `argon2`
2. Wrap in `tokio::task::spawn_blocking(move || { blocking_call(args) }).await??`
3. For pure CPU work (`bcrypt`, `argon2`), this is the canonical fix; for file I/O prefer `tokio::fs` if the operation is supported
4. Run `cargo test` and benchmark request latency under concurrency - the executor no longer stalls
5. Add a comment naming why `spawn_blocking` is used (so future readers don't "simplify" it back to a direct call)

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end); `cargo clippy --all-targets -- -D warnings` and `cargo test` for every commit
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, trait removals)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Rust Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Rust refactor recipes" - this is the spine]
**Stack:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Lint state:** `cargo clippy --all-targets -- -D warnings` clean | warnings present (Step 0a covers them) | not run (no baseline)
**Concurrency-test coverage:** clean | not exercised cross-thread | n/a (no concurrency in target)

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-rust-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce the **Smells Identified**, **Sibling Smells (Out of Scope)**, and the **Coverage prerequisite list** (the `entry-point | outcome | recommended layer` table described below) as a *preview* so the implementer has a target list when filling the coverage gap; mark them clearly as preview-only. The prerequisite table is the most actionable output in this mode - render it inside the Coverage Gate section, not as a separate top-level heading.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure (4xx), authorization denial (401/403), not-found / IDOR, external-collaborator failure, and (when the target spawns / locks across `.await`) **concurrent path** with `#[tokio::test(flavor = "multi_thread")]` as the recommended layer. The concurrency row is required whenever the concurrency-gate-check applied above (target uses `tokio::spawn` / `JoinSet` / `Arc<Mutex>` / `Arc<RwLock>` / channels) - it makes the concurrency-gate-check directly actionable in the prerequisite table instead of leaving it implicit. Layer options: handler test (`axum-test` / `oneshot`), service unit test (`#[tokio::test]` + `mockall`), repository integration test (testcontainers), background-task test, multi-thread test (`#[tokio::test(flavor = "multi_thread")]`). Example: `POST /orders | unknown-field rejected | handler test`. This makes the prerequisite directly actionable rather than a vague "add boundary tests."

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/module that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                              |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-rust-review-security` / `task-rust-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green; `cargo clippy --all-targets -- -D warnings` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if clippy was already clean)_

- **Change:** address the existing clippy warnings on the target crate so the refactor's clippy gate has a clean baseline
- **Risk:** Low (no behavior change; lint-only fixes)
- **Test gate:** `cargo clippy --all-targets -- -D warnings` clean; `cargo test` still green
- **Rollback:** revert the lint fixes

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - unit / handler / testcontainers integration / background-task; `cargo clippy --all-targets -- -D warnings` clean]
- **Transaction stance:** [callee runs inside caller's transaction (`&mut tx`) | callee uses post-commit dispatch | not transactional]
- **Lock / await stance:** [no `.await` while holding a lock | `tokio::sync::Mutex` may span `.await` (justified) | unchanged]
- **Concurrency stance:** [no concurrency change | introduces `tokio::spawn` (CancellationToken + multi-thread test required) | removes spawned task | mutex change]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it. Always state why the coupling is structural, not cosmetic.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `cargo build` clean and `cargo test` (with `cargo clippy --all-targets -- -D warnings`) passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No `std::sync::Mutex` held across `.await` introduced; `tokio::sync::Mutex` use across `.await` is named explicitly
- [ ] No new `tokio::spawn` without `JoinHandle` / `JoinSet` ownership and (for long-lived tasks) `CancellationToken`
- [ ] No new concurrency without cross-thread test coverage in CI

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as Rust / Axum (or accepted from parent dispatcher); data-access mix and messaging recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin`; concurrency-test check applied for concurrent modules; clippy state recorded (Step 3)
- [ ] Rust-specific smells identified using Step 4 catalog (handler/route, service, persistence, configuration/DI, concurrency/async, `unsafe`) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate`. Step 0a included if clippy is not clean (Output Format)
- [ ] Transaction stance stated per step (no I/O silently moved across transaction boundary) (Step 6)
- [ ] Lock / await stance stated per step (no silent `std::sync::Mutex` across `.await`; `tokio::sync::Mutex` use across `.await` justified) (Step 6)
- [ ] Concurrency stance stated per step (`CancellationToken` + multi-thread test required when concurrency added) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, trait removals, signature changes) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `cargo build` clean and `cargo test` passes between every step
- [ ] `cargo clippy --all-targets -- -D warnings` clean for any step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Proposing a refactor that introduces concurrency to a module that lacks cross-thread test coverage - the new race surface is unguarded
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing a trait without a real second use case - wait for the second use case before generalizing
- Replacing `sqlx` with `diesel` (or vice versa) on a code path with no measured benefit (premature change)
- Replacing module-level mutable state with thread-local storage / `OnceCell` carrying a pointer to the same data - that is the same global with extra steps; use constructor injection instead
- Moving HTTP calls or task dispatches from a non-transactional context to inside a `pool.begin()...commit()` (or vice versa) without explicitly stating the transaction stance
- Introducing `std::sync::Mutex` across an `.await` - always wrong (deadlocks the executor); use `tokio::sync::Mutex` or restructure to drop the guard before the await
- Refactoring an exported `pub` symbol in a published crate without a backward-compatibility plan - that is a public API
- Adding `tokio::spawn` to "make it concurrent" without `JoinHandle` / `JoinSet` ownership and `CancellationToken` for long-lived tasks - that is a leak waiting to happen
- Replacing `Box<dyn Trait>` with generics on the trait declaration site (changes the trait API for every consumer) when only one callsite needed it - convert at the callsite
