---
name: task-rust-refactor
description: Plan a Rust/Axum/sqlx refactor: fat handlers, tokio::spawn leaks, Mutex-across-await, sqlx N+1, single-impl traits. Phased, gated.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# Rust Refactor

Produce a step-by-step refactor plan for a Rust target (Axum handler, service, repository, sqlx model, background task, DTO). Each step is independently committable with `cargo test` + `cargo clippy --all-targets -- -D warnings` gates.

Stack-specific delegate of `task-code-refactor` for Rust.

## When to Use

- Rust code-smell identification with a concrete plan
- Safe refactor of a handler / service / repository / module / background-task processor
- Cleanup of a fat-handler / god-service PR before merge

**Not for:**

- Prioritizing across many candidates (use `task-debt-prioritize`)
- Feature changes (use `task-rust-implement`)
- Cross-module architecture moves (use `task-design-architecture`)
- Bug / panic investigation (use `task-rust-debug`)

## Inputs

| Input                 | Required    | Notes                                                                |
| --------------------- | ----------- | -------------------------------------------------------------------- |
| Target                | Yes         | File or module (e.g., `src/orders/handler.rs`)                       |
| Goal                  | Yes         | What the refactor should achieve                                     |
| Test coverage status  | Recommended | Tests covering the target; whether `cargo clippy` is clean           |
| Shared/public surface | Recommended | Whether the target is `pub` across module / crate / workspace        |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If the detected stack is not Rust, stop and route to `/task-code-refactor`. If invoked by a Rust-aware parent, accept the pre-confirmed stack.

Record `Data Access` (sqlx / diesel / mixed) and `Messaging` (Tokio queue / AMQP / Kafka / none) for the output.

### Step 3 - Read the Target

Read the actual files; do not classify from prose alone.

1. Target file top-to-bottom: function count, longest function, sync/async mix, transaction placement (`pool.begin()` ... `tx.commit()`), external collaborators (`reqwest`, queues, mailers), `.await` points
2. Matching tests (`#[cfg(test)] mod tests`, `tests/<feature>_test.rs`): cases by outcome (happy, validation, external failure, auth denial). Confirm `cargo clippy --all-targets -- -D warnings` runs clean
3. Immediate callers when obvious (handler → service, scheduler → service)

If only a goal was given without a target, ask before proceeding.

**Sibling smells.** Real targets sit in fat files. Other smells in the same file go under `Sibling Smells (Out of Scope)` with deferral rationale and recommended follow-up skill -- never silently included, never silently dropped.

**Severity inversion.** If a sibling smell is *higher severity* than the named target (working SQLi, `Command::new("sh")` RCE, auth bypass, `alg: none`), recommend pausing the refactor and routing through `task-rust-review-security` first. Flag this in `Sibling Smells (Out of Scope)`; the refactor PR should branch off the security fix, not main.

### Step 4 - Coverage Gate (mandatory)

Refactoring without coverage is a rewrite. Identify tests covering the target, then label:

| Status       | Definition                                                              | Action                                                                              |
| ------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** >= 2 boundary outcomes per public entry point       | Proceed                                                                             |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                          | Proceed; plan includes non-optional `Step 0` adding the missing boundaries          |
| `Inadequate` | No tests, or happy-path-only                                            | Refuse Steps 1+. Output gate verdict + recommend `task-rust-test`                   |

Happy-path-only is `Inadequate`, not `Thin` -- a single success case can't prove validation, authz, or error preservation.

**Lint gate.** `cargo clippy --all-targets -- -D warnings` must be clean or Step 0a folds the warnings in. Values: `clean` | `warnings present` | `not run (no baseline)`.

**Concurrency gate.** If the target uses `tokio::spawn`, `JoinSet`, `Arc<Mutex>`, `Arc<RwLock>`, or channels, tests must exercise concurrent paths (`#[tokio::test(flavor = "multi_thread")]`). If absent, downgrade status one tier.

When status is `Thin` or `Inadequate`, render the prerequisite test list as: `entry-point | outcome | recommended layer`. Outcomes must include validation failure, authz denial, not-found/IDOR, external failure, and (when concurrency-gate fires) a concurrent-path row with `#[tokio::test(flavor = "multi_thread")]`. Layers: handler test (`axum-test`/`oneshot`), service unit test (`#[tokio::test]` + `mockall`), repository integration (testcontainers), background-task test, multi-thread test.

### Step 5 - Identify Smells

Use judgment -- these are signals, not rules. A 25-line fn with clear private helpers is fine; a 10-line fn doing three unrelated things is not.

**Handler / Route:**

| Smell                                          | Signal                                                                                                        | Risk   |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------ |
| Fat handler                                    | > 30 lines of orchestration (multiple service calls, conditional dispatch, response shaping)                  | High   |
| Logic in handler                               | Business rules / calculations beyond `Json<T>` + `Validate` derives                                           | High   |
| Direct sqlx in handler                         | `sqlx::query!` in handler, bypassing service/repo                                                             | Medium |
| `FromRow` struct returned from handler         | `Json(user)` leaks `password_hash`, soft-delete columns, internal fields                                      | High   |
| Manual validation duplicating derives          | Handler re-checks constraints already on `#[validate(...)]`                                                   | Low    |
| Ad-hoc `(StatusCode, "...")` errors            | Inline error mapping instead of `Result<_, AppError>` + `IntoResponse for AppError`                           | Medium |
| Missing `Validate` on DTO                      | `Deserialize` without `Validate` -- anything-goes input                                                       | High   |
| Mass assignment via `serde_json::from_value`   | Decoded straight into a domain model; client can set `user_id`, `role`                                        | High   |

**Service:**

| Smell                                              | Signal                                                                                                | Risk   |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------ |
| God service file                                   | `*_service.rs` > 500 lines mixing orchestration, persistence, mapping, scheduling                     | High   |
| Anemic domain                                      | Behavior in `*_helpers.rs::calculate_total(o: &Order)` belongs as `impl Order`                        | High   |
| Single-impl trait                                  | Trait + one impl, no `#[automock]`, no second implementer                                             | Medium |
| `&mut self` for I/O without need                   | Blocks shared concurrent access                                                                       | Medium |
| `panic!` / `.unwrap()` in service                  | Escapes `IntoResponse`; return `AppError` instead                                                     | High   |
| External I/O inside transaction                    | `reqwest` / queue publish between `pool.begin()` and `tx.commit()` -- holds connection, races commit  | High   |
| `Option` for failure-capable op                    | Caller can't distinguish validation vs not-found vs external; return `Result<T, AppError>`            | Medium |

**Persistence / sqlx:**

| Smell                                        | Signal                                                                                                 | Risk   |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------ |
| Fat repository                               | > 300 lines mixing mapping, computed properties, business ops                                          | High   |
| Repository returns `FromRow` upward          | Service/handler treats sqlx row as the domain type                                                     | Medium |
| Runtime query where `query!` fits            | `sqlx::query("...").bind(id)` for static SQL -- `query!` adds compile-time schema check                | Medium |
| sqlx N+1                                     | Per-iteration query in a loop                                                                          | High   |
| String-concat SQL                            | `format!` building dynamic SQL instead of parameterized `bind` or query builder                        | High   |
| `fetch_all` without pagination               | Full-table return                                                                                      | Medium |
| Long transaction holding connection          | External I/O between `pool.begin()` and `tx.commit()`                                                  | High   |
| `Pool::connect` per request                  | New pool per handler defeats pooling                                                                   | High   |

**Configuration / DI:**

| Smell                              | Signal                                                                                              | Risk   |
| ---------------------------------- | --------------------------------------------------------------------------------------------------- | ------ |
| Module-level mutable static        | `static MUT_CACHE: Lazy<RwLock<...>>` mutated by handlers; worse, `static mut`                      | High   |
| Module-level `Pool`                | `static POOL: OnceCell<PgPool>` accessed directly instead of `AppState` injection                   | High   |
| Sprinkled `std::env::var`          | Load once into a typed config struct (`figment` / `config` / `envy`)                                | Medium |
| Hardcoded defaults inline          | Belongs in typed config                                                                             | Medium |
| Trait at producer                  | Trait declared next to its impl; Rust idiom is trait at consumer                                    | Medium |
| `Box<dyn Trait>` where generics fit | `Box<dyn>` for a single callsite -- `<S: Trait>` is cheaper                                        | Medium |

**Concurrency / Async:**

| Smell                                    | Signal                                                                                                  | Risk   |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------ |
| `tokio::spawn` without owner             | No `JoinHandle` / `JoinSet`, no `CancellationToken`                                                     | High   |
| Unbounded spawn fan-out                  | `for x in xs { tokio::spawn(...) }` without `JoinSet` + `Semaphore`                                     | High   |
| `std::sync::Mutex` held across `.await`  | Blocks executor thread; deadlock pattern                                                                | High   |
| `Arc<Mutex<T>>` where `Arc<T>` suffices  | Immutable data wrapped in `Mutex` for no benefit                                                        | Medium |
| `Arc<Mutex<T>>` where `RwLock` fits      | Read-heavy state serializes readers unnecessarily                                                       | Medium |
| `mpsc::unbounded_channel`                | Memory leak under producer > consumer; use `mpsc::channel(N)`                                           | High   |
| Background dispatch inside transaction   | Worker may pick up before commit                                                                        | High   |
| Background task without idempotency      | Re-runs side effects on retry; no dedup/upsert                                                          | High   |
| Blocking I/O on runtime                  | `std::fs`, `std::thread::sleep`, `bcrypt::hash` in `async fn` without `spawn_blocking`                  | High   |
| Nested runtime                           | `Runtime::new().block_on(...)` inside `async fn` -- panics                                              | High   |

**`unsafe`:**

| Smell                          | Signal                                                                                  | Risk   |
| ------------------------------ | --------------------------------------------------------------------------------------- | ------ |
| `unsafe` without `// SAFETY:`  | Block has no comment naming the invariant                                               | High   |
| `unsafe` for speed without bench | "It's faster" with no benchmark                                                       | Medium |
| `static mut`                   | Use `Mutex` / `RwLock` / `OnceCell`                                                     | High   |

**Tests (when in scope):**

| Smell                                      | Signal                                                                                  | Risk   |
| ------------------------------------------ | --------------------------------------------------------------------------------------- | ------ |
| In-process repo mock instead of testcontainers | `MockRepo { state: Mutex<HashMap> }` over real Postgres                             | Medium |
| SQLite for a Postgres app                  | Tests pass on SQLite, fail on JSONB / partial index / `ON CONFLICT`                     | High   |
| Copy-paste test fns                        | Near-identical cases where `rstest` or a `Vec<Case>` loop would do                      | Low    |

**Cross-language signals:** Use skill: `backend-coding-standards`.
**Over-engineering signals (single-impl traits, premature factory):** Use skill: `complexity-review` -- these are simplifications, not new abstractions.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. State `Narrow | Moderate | Wide | Critical` before proposing steps.

Rust signals to weigh: public handler API, crate / workspace boundary (`pub` in `lib.rs`), trait with broad impl surface, type on `AppState` (changes cascade to every `State<AppState>` consumer), `FromRow` / domain struct used in many `query_as!` calls, DTO shared across endpoints, exported `pub` symbol in a published crate.

### Step 7 - Propose the Sequence

Each step must be: independently committable (`cargo build` + `cargo test` + `cargo clippy --all-targets -- -D warnings` pass), behaviorally invariant (unless labeled `coupled-fix`), reversible in one revert, tested.

**Primary recipe.** Pick one recipe matching the user's goal as the spine. Fold supporting recipes in as additive sub-steps where dependencies require. Never concatenate -- a 25-step plan mixing concerns is two plans. State `Primary recipe:` in the output. If the spine exceeds ~8 steps, split into two PRs.

**Coupled-fix.** When a refactor genuinely requires behavior change (extracting a service needs auth middleware to supply the principal), label `coupled-fix` with its own test gate and rationale.

**Per-step stances (recorded in Output Format).** Every step states:

- **Transaction stance** -- callee inside caller's tx (`&mut tx`) | post-commit dispatch (capture inputs, dispatch after `tx.commit()`) | not transactional. Never silently move I/O across a transaction boundary.
- **Lock/await stance** -- no `.await` while a guard is held (default) | `tokio::sync::Mutex` may span `.await` (justify) | unchanged. `std::sync::Mutex` across `.await` is always wrong.
- **Concurrency stance** -- no change | introduces `tokio::spawn` (requires `CancellationToken` + multi-thread test) | removes spawn | mutex change.

**Common recipes:**

**R1 - Extract service from fat handler.**
1. Add `<feature>/service.rs` with one intention-revealing method `pub async fn place(&self, ctx) -> Result<_, AppError>`; copy logic. Handler still does the original work
2. Add tests covering one case per outcome (success, validation, external failure)
3. Handler calls service via `State<AppState>`; preserves response shape; handler tests pass
4. Remove duplicated logic from handler; tests still pass
5. Add handler-level test asserting service failure maps via `AppError` → `IntoResponse`

**R2 - Eliminate `tokio::spawn` leak.**
1. Wrap in `JoinSet`; for fan-out, gate with `Semaphore::new(N)`
2. Add `tokio::select! { _ = token.cancelled() => return Ok(()), ... }` to inner loops
3. `while let Some(res) = set.join_next().await { res??; }` to surface panics
4. `cargo clippy` + `cargo test`; add `#[tokio::test(flavor = "multi_thread")]` if absent

**R3 - Eliminate `std::sync::Mutex` across `.await`.**
1. If lock need not span the await, scope it:
   ```rust
   let value = { let g = mutex.lock().unwrap(); g.clone() };
   let result = io_call(value).await?;
   ```
2. If it must span, swap to `tokio::sync::Mutex` (yields cooperatively). Name this in the lock/await stance
3. `cargo clippy` + `cargo test`

**R4 - Add `CancellationToken` to a long-lived task.**
1. Add `tokio_util::sync::CancellationToken` on the worker; clone into each spawn
2. Wrap inner loop in `tokio::select! { _ = token.cancelled() => return Ok(()), msg = rx.recv() => ... }`
3. Shutdown path: `token.cancel()` then `set.shutdown().await` or `handle.await`
4. Test the drain-on-cancel path within a bounded timeout

**R5 - Eliminate single-impl trait.**
1. Confirm no `#[automock]`, no mocks, no second impl, no API obligation
2. Use the concrete struct directly: `repo: Arc<PgOrderRepository>`; delete the trait
3. `cargo test` -- caller code is shorter
4. **Skip if** the trait is part of a published crate API, or has a real second impl / `mockall` mock used in tests

**R6 - Move trait from producer to consumer.**
1. Move the trait declaration from `repository/` into the consuming `service/` module
2. Update imports; producer exposes only its concrete struct
3. `cargo test` -- now follows "accept interfaces at the consumer"

**R7 - Replace `Box<dyn Trait>` with generic.**
1. `fn handle(svc: Box<dyn OrderService>)` → `fn handle<S: OrderService>(svc: S)`
2. **Skip if** heterogeneous storage is needed (`Vec<Box<dyn ...>>`)
3. Benchmark on hot paths

**R8 - Split god service.**
1. Identify orthogonal concerns (place / cancel / refund / report)
2. Extract one concern per commit into a focused file; god service delegates temporarily
3. Update callers via `AppState`; remove delegation; repeat
4. Delete the empty god service

**R9 - Move side effects out of an open transaction.**

Pick one option per refactor; don't stack.

*Option A - Post-commit dispatch.* Use when one fire-and-forget side effect and at-most-once on crash is acceptable.

1. Capture dispatch inputs in locals before `tx.commit()`
2. Move dispatch after `tx.commit()` returns `Ok`; log-and-continue on dispatch failure
3. Test the commit-ok / dispatch-fail branch
4. State explicitly: "post-commit dispatch; tolerates at-most-once on commit-to-dispatch crash"

*Option B - Transactional outbox.* Use when at-least-once is required, multiple side effects must be coordinated, or audit/replay matters.

1. Migration: `outbox_messages(id, aggregate_type, aggregate_id, event_type, payload JSONB, created_at, processed_at)`; partial index on `processed_at IS NULL`
2. Inside the original transaction: `INSERT INTO outbox_messages` on the same `&mut *tx` (not external dispatch)
3. Relay worker polls `... WHERE processed_at IS NULL ORDER BY id LIMIT N FOR UPDATE SKIP LOCKED`, dispatches, sets `processed_at`
4. Downstream handlers idempotent (dedup on outbox id or business key)
5. Metrics: outbox lag (`unprocessed_count`, `oldest_age_seconds`) with SLO alert

**R10 - Make background task idempotent.**
1. Test asserting one side effect when the same business key is processed twice
2. Dedup table or `INSERT ... ON CONFLICT (key) DO NOTHING`
3. Configure max-retries / DLQ so poison messages don't loop

**R11 - Eliminate `serde_json::from_value` mass assignment.**
1. Define a DTO with explicit fields + `#[validate(...)]` -- no `user_id`, `role`, `is_admin`
2. Replace decode with `Json(req): Json<UpdateOrderRequest>` + `req.validate()?`; copy fields explicitly
3. Test that injected privileged keys are dropped

**R12 - Replace module-level mutable static with injection.**
1. Move `static MUT_CACHE` / `static POOL` into a struct on `AppState`
2. Replace direct reads/writes with method calls on the injected instance
3. Callers receive via `State<AppState>` extractor or constructor
4. Assert cross-test isolation under `cargo test` parallel default

**R13 - Wrap blocking work in `spawn_blocking`.**
1. `tokio::task::spawn_blocking(move || blocking_call(args)).await??`
2. For pure CPU (`bcrypt`, `argon2`), this is the canonical fix; for file I/O prefer `tokio::fs` where supported
3. Benchmark request latency under concurrency
4. Comment why `spawn_blocking` is used so it isn't "simplified" back

### Step 8 - Validate Plan Against Goal

- [ ] Goal achieved at end of sequence
- [ ] Each step reviewable in < 30 min
- [ ] `cargo test` + `cargo clippy --all-targets -- -D warnings` between every step
- [ ] Low-risk first (additions, extractions) before high-risk (deletions, signature changes)
- [ ] Rollback is one revert per step
- [ ] No "while we're here" cleanup bundled

## Output Format

```markdown
## Rust Refactor Plan

**Target:** [file:line]
**Goal:** [what this refactor achieves]
**Primary recipe:** [R# from Step 7 -- the spine]
**Stack:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Lint state:** clean | warnings present (Step 0a) | not run (no baseline)
**Concurrency-test coverage:** clean | not exercised cross-thread | n/a

[Adequate: one sentence on boundary cases that exist.]
[Thin: list missing boundary tests; Step 0 covers them.]
[Inadequate: state required coverage; recommend `task-rust-test` first. Stop here -- omit Blast Radius, Step Sequence, Verification. You may still produce **Smells Identified**, **Sibling Smells**, and the prerequisite table below as preview-only.]

**Prerequisite tests** (when Thin or Inadequate):

| Entry point     | Outcome                  | Recommended layer                                |
| --------------- | ------------------------ | ------------------------------------------------ |
| `POST /orders`  | unknown-field rejected   | handler test (`axum-test`)                       |
| `place_order`   | concurrent path drains   | `#[tokio::test(flavor = "multi_thread")]`        |

## Smells Identified

| Smell        | Location  | Risk | Notes |
| ------------ | --------- | ---- | ----- |
| [Smell]      | file:line | High | [one-line why] |

## Sibling Smells (Out of Scope)

_Other smells in the target file; listed for hand-off, not action. Omit if none._

| Smell   | Location  | Why deferred                                  | Recommended follow-up                    |
| ------- | --------- | --------------------------------------------- | ---------------------------------------- |
| [Smell] | file:line | separate target / separate severity / etc.   | `task-rust-review-security` / other     |

[If a sibling smell is higher severity than the named target, state prominently: "Severity inversion: pause this refactor; route through `task-rust-review-security` first; branch the eventual refactor PR off the security fix, not main."]

## Blast Radius

[Narrow | Moderate | Wide | Critical] -- [rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_
- **Change:** add missing boundary tests from the Prerequisite Tests table
- **Risk:** Low (tests only)
- **Test gate:** new tests pass; suite green; `cargo clippy` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if clippy clean)_
- **Change:** clear existing clippy warnings on the target crate
- **Risk:** Low (no behavior change)
- **Test gate:** `cargo clippy --all-targets -- -D warnings` clean; `cargo test` green
- **Rollback:** revert lint fixes

### Step 1 - [Verb + noun]
- **Change:** [what is added / extracted / moved]
- **Risk:** Low | Medium | High
- **Step kind:** refactor | coupled-fix
- **Test gate:** [tests; `cargo clippy --all-targets -- -D warnings` clean]
- **Transaction stance:** [inside caller's tx | post-commit dispatch | not transactional]
- **Lock/await stance:** [no `.await` under lock | `tokio::sync::Mutex` may span (justify) | unchanged]
- **Concurrency stance:** [no change | introduces `tokio::spawn` (CancellationToken + multi-thread test) | removes spawn | mutex change]
- **Rollback:** [one git revert]

### Step 2 - [Verb + noun]
[Same structure. `coupled-fix` requires rationale for the coupling.]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] `cargo test` + `cargo clippy --all-targets -- -D warnings` between every step
- [ ] No bundled unrelated cleanup
- [ ] One revert per step
- [ ] No I/O silently moved across a transaction boundary
- [ ] No `std::sync::Mutex` across `.await`; `tokio::sync::Mutex` spanning `.await` is named
- [ ] No new `tokio::spawn` without owner + (for long-lived) `CancellationToken`
- [ ] No new concurrency without cross-thread test coverage

## Out of Scope

[Adjacent improvements explicitly NOT in this plan.]
```

## Self-Check

- [ ] Step 1 -- `behavioral-principles` loaded
- [ ] Step 2 -- stack confirmed Rust/Axum (or accepted from parent); data access + messaging recorded
- [ ] Step 3 -- target file(s) + tests read directly; sibling smells listed or section omitted; severity inversion flagged if applicable
- [ ] Step 4 -- Coverage Gate verdict using sharp boundaries; `Inadequate` refuses Steps 1+; happy-path-only -> `Inadequate`; concurrency-gate downgrade applied; lint state recorded; prerequisite table rendered when Thin/Inadequate
- [ ] Step 5 -- smells classified using Step 5 catalog (handler, service, persistence, config/DI, concurrency, `unsafe`, tests)
- [ ] Step 6 -- blast radius stated
- [ ] Step 7 -- `Primary recipe:` named; supporting recipes folded as sub-steps; spine <= ~8 steps or split into PRs; every step states Transaction / Lock-await / Concurrency stance; behavior changes labeled `coupled-fix`; ordered low-risk first
- [ ] Step 8 -- goal mapped to end state; no bundled cleanup

## Avoid

- Producing Steps 1+ when Coverage Gate is `Inadequate`
- Introducing concurrency without cross-thread test coverage
- Bundling behavior changes with refactor steps (use `coupled-fix` with rationale, or split the PR)
- "While we're here" unrelated cleanup; renames during a refactor
- Removing a trait without a real second use case or `mockall` mock
- Replacing module-level mutable static with thread-local / `OnceCell` to the same data -- still a global; inject instead
- Moving HTTP / dispatch across a `pool.begin()` / `tx.commit()` boundary without naming the transaction stance
- Any `std::sync::Mutex` held across `.await` -- always wrong
- `tokio::spawn` without `JoinHandle`/`JoinSet` ownership or (for long-lived) `CancellationToken`
- Refactoring a `pub` symbol in a published crate without a back-compat plan
- Replacing `Box<dyn Trait>` with generics at the trait declaration when only one callsite needed it -- convert at the callsite
