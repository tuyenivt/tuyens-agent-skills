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

Stack-specific delegate of `task-code-refactor` for Rust. Produce a phased, gated refactor plan for a target (handler, service, repository, sqlx model, background task, DTO). Each step is independently committable behind `cargo test` + `cargo clippy --all-targets -- -D warnings`.

## When to Use

- Plan a safe refactor of a Rust target with code smells
- Clean up a fat-handler / god-service before merge

**Not for:** feature changes (`task-rust-implement`), cross-module moves (`task-design-architecture`), bug/panic investigation (`task-rust-debug`).

If Target or Goal is missing, ask before proceeding.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Rust, route to `/task-code-refactor`. Record `Data Access` (sqlx / diesel / mixed) and `Messaging` (Tokio queue / AMQP / Kafka / none).

### Step 3 - Read the Target

Read files directly; do not classify from prose.

- Target file: function count, longest fn, sync/async mix, transaction placement (`pool.begin()` ... `tx.commit()`), external collaborators (`reqwest`, queues), `.await` points, and for any lock (`Mutex`/`RwLock`) whether its guard is held across an `.await` (drives the Step 7 Lock/await stance)
- Matching tests: outcomes covered (happy, validation, external failure, authz). Confirm clippy clean
- Immediate callers when obvious

**Sibling smells.** Real targets sit in fat files. List other smells under `Sibling Smells (Out of Scope)` with deferral rationale and follow-up skill - never silently included or dropped.

**Severity inversion.** If a sibling smell is higher severity than the named target (working SQLi, RCE, auth bypass, `alg: none`), pause the refactor and route through `task-rust-review-security`. Branch the eventual refactor PR off the security fix, not main. Stop after this step like a refused gate: emit Smells Identified, Sibling Smells (with the inversion verdict), and the Coverage Gate status if already computed; omit Blast Radius and Step Sequence. Do not emit a deferred plan - re-run this workflow once the security fix lands.

### Step 4 - Coverage Gate (mandatory)

Refactoring without coverage is a rewrite.

| Status       | Definition                                                          | Action                                                         |
| ------------ | ------------------------------------------------------------------- | -------------------------------------------------------------- |
| `Adequate`   | Happy path + >= 2 boundary outcomes per public entry point          | Proceed                                                        |
| `Thin`       | Happy path + exactly 1 boundary outcome                             | Proceed; Step 0 adds missing boundaries (non-optional)         |
| `Inadequate` | No tests, or happy-path only                                        | Refuse Steps 1+. Output gate verdict; recommend `task-rust-test` |

Happy-path-only is `Inadequate`, not `Thin` - one success case can't prove validation, authz, or error preservation.

**Lint gate.** `cargo clippy --all-targets -- -D warnings`: `clean` | `warnings present` (Step 0a folds them in) | `not run`.

**Concurrency gate.** If the target uses `tokio::spawn`, `JoinSet`, `Arc<Mutex>`, `Arc<RwLock>`, or channels, tests must exercise concurrent paths (`#[tokio::test(flavor = "multi_thread")]`). If absent, downgrade status one tier (`Adequate` -> `Thin`, `Thin` -> `Inadequate`, `Inadequate` stays `Inadequate`) and add the multi-thread row to the prerequisite table.

When `Thin` or `Inadequate`, render a prerequisite table: `entry point | outcome | recommended layer`. Outcomes must cover validation failure, authz denial, not-found/IDOR, external failure, and (when concurrency-gate fires) a multi-thread row. Layers: handler (`axum-test`/`oneshot`), service unit (`#[tokio::test]` + `mockall`), repository (testcontainers), background-task, multi-thread.

### Step 5 - Identify Smells

Delegate domain catalogs - do not inline rules from atomic skills:

- Async / runtime / `tokio::spawn` / `select!` / `spawn_blocking`: Use skill: `rust-async-patterns`
- Shared state / Mutex / RwLock / channels / `Send`+`Sync`: Use skill: `rust-concurrency`
- sqlx queries / N+1 / pool / transactions / pagination: Use skill: `rust-db-access`
- Axum router / extractors / DTOs / `ApiResponse` / pagination: Use skill: `rust-web-patterns`
- `thiserror`/`anyhow` / `?` / `panic!` / `Option` vs `Result`: Use skill: `rust-error-handling`
- JWT / mass assignment / secrets / `unsafe` audit: Use skill: `rust-security-patterns`
- Messaging / outbox / DLQ / idempotency: Use skill: `rust-messaging-patterns`
- Single-impl traits / `Box<dyn>` defaults / `Arc<Mutex>` on read-only / hot-loop clones: Use skill: `rust-overengineering-review`
- Cross-language signals: Use skill: `backend-coding-standards`

Collate findings into `Smells Identified` with `file:line`, risk, and the atomic skill that owns the rule.

Use judgment - signals, not rules. A 25-line fn with private helpers is fine; a 10-line fn doing three unrelated things is not.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. State `Narrow | Moderate | Wide | Critical`.

Rust signals: public handler API, crate/workspace boundary (`pub` in `lib.rs`), trait with broad impl surface, type on `AppState` (cascades to every `State<AppState>` consumer), `FromRow`/domain struct in many `query_as!` calls, DTO across endpoints, exported `pub` symbol in a published crate.

### Step 7 - Propose the Sequence

Every step is independently committable (`cargo build` + `cargo test` + clippy pass), behaviorally invariant (unless `coupled-fix`), reversible in one revert, tested.

**Primary recipe.** Pick one recipe matching the goal as the spine; fold supporting recipes as additive sub-steps where dependencies require. Never concatenate two plans. State `Primary recipe:` in the output - a named recipe (R-Tx/R-Mass/R-Static/R-Trait) or, for the unnamed ones below, a short verb-noun label (e.g. `extract service + repo`, `split god service`). If the spine exceeds ~8 steps, split into two PRs.

**Coupled-fix.** When the refactor genuinely requires behavior change (extracting a service needs middleware to supply the principal), label `coupled-fix` with its own test gate and rationale.

**Per-step stances** (recorded in Output Format):

- **Transaction stance** - inside caller's tx (`&mut tx`) | post-commit dispatch | not transactional. Never silently move I/O across a transaction boundary.
- **Lock/await stance** - no `.await` under lock (default) | `tokio::sync::Mutex` may span `.await` (justify) | unchanged. `std::sync::Mutex` across `.await` is always wrong.
- **Concurrency stance** - no change | introduces `tokio::spawn` (requires `CancellationToken` + multi-thread test) | removes spawn | mutex change.

**Decision-laden recipes** (the rest follow the atomic-skill patterns directly):

**R-Tx - Move side effects out of an open transaction.** Pick one option per refactor; don't stack.

- *Post-commit dispatch.* One fire-and-forget side effect; at-most-once on commit-to-dispatch crash acceptable. Capture inputs before `tx.commit()`; dispatch after `Ok`; log-and-continue on dispatch failure; test the commit-ok / dispatch-fail branch.
- *Transactional outbox.* At-least-once required, multiple side effects, or audit/replay matters. Migration: `outbox_messages(id, aggregate_*, event_type, payload JSONB, created_at, processed_at)` + partial index on `processed_at IS NULL`. Insert on the same `&mut *tx`. Relay worker polls `... WHERE processed_at IS NULL ORDER BY id LIMIT N FOR UPDATE SKIP LOCKED`. Downstream idempotent. Metrics: lag + oldest-age SLO.

**R-Mass - Eliminate `serde_json::from_value` mass assignment.** Define a DTO with explicit fields + `#[validate(...)]` - no `user_id`, `role`. Replace with `Json(req): Json<UpdateOrderRequest>` + `req.validate()?`; copy fields explicitly. Test that injected privileged keys are dropped.

**R-Static - Replace module-level mutable static with injection.** Move `static MUT_CACHE`/`static POOL` into a struct on `AppState`. Replace direct reads/writes with method calls. Assert cross-test isolation under `cargo test` parallel default. Replacing with thread-local or `OnceCell` to the same data is still a global - inject instead.

**R-Trait - Eliminate single-impl trait.** Skip if `#[automock]` mock exists, second impl exists, or trait is part of a published crate API. Otherwise use the concrete struct directly: `repo: Arc<PgOrderRepository>`; delete the trait. Move trait declarations to the consumer side when keeping them.

For other recipes (extract service, wrap `tokio::spawn` in `JoinSet`, swap `std::sync::Mutex` for `tokio::sync::Mutex` across `.await`, add `CancellationToken`, replace `Box<dyn>` with generics, split god service, idempotent worker, `spawn_blocking` for CPU): the steps follow directly from `rust-async-patterns`, `rust-concurrency`, `rust-overengineering-review`. Cite the atomic skill in the step body; do not re-derive.

## Output Format

```markdown
## Rust Refactor Plan

**Target:** [file:line]
**Goal:** [what this refactor achieves]
**Primary recipe:** [recipe name]
**Stack:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Lint state:** clean | warnings present (Step 0a) | not run (no baseline)
**Concurrency-test coverage:** clean | not exercised cross-thread | n/a

[Adequate: one sentence on boundary cases. Thin: list missing boundaries; Step 0 covers them. Inadequate: state required coverage; recommend `task-rust-test`. Stop here - omit Blast Radius and Step Sequence. You may still produce **Smells Identified**, **Sibling Smells**, and the prerequisite table as preview-only.]

**Prerequisite tests** (when Thin or Inadequate):

| Entry point     | Outcome                  | Recommended layer                                |
| --------------- | ------------------------ | ------------------------------------------------ |
| `POST /orders`  | unknown-field rejected   | handler test (`axum-test`)                       |
| `place_order`   | concurrent path drains   | `#[tokio::test(flavor = "multi_thread")]`        |

## Smells Identified

| Smell   | Location  | Risk | Owner (atomic skill)         | Notes |
| ------- | --------- | ---- | ---------------------------- | ----- |
| [Smell] | file:line | High | rust-async-patterns          | [one-line why] |

## Sibling Smells (Out of Scope)

_Other smells in the target file; hand-off, not action. Omit if none._

| Smell   | Location  | Why deferred | Recommended follow-up                |
| ------- | --------- | ------------ | ------------------------------------ |
| [Smell] | file:line | [reason]     | `task-rust-review-security` / other |

[If a sibling smell outranks the named target: "Severity inversion: pause this refactor; route through `task-rust-review-security` first; branch the refactor PR off the security fix, not main." Then stop - omit Blast Radius and Step Sequence below; do not emit a deferred plan.]

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_
- **Change:** add missing boundary tests from the Prerequisite Tests table
- **Risk:** Low (tests only)
- **Test gate:** new tests pass; `cargo clippy` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if clippy clean)_
- **Change:** clear existing clippy warnings on the target crate
- **Risk:** Low
- **Test gate:** `cargo clippy --all-targets -- -D warnings` clean; `cargo test` green
- **Rollback:** revert lint fixes

### Step 1 - [Verb + noun]
- **Change:** [what is added / extracted / moved]
- **Risk:** Low | Medium | High
- **Step kind:** refactor | coupled-fix
- **Test gate:** [tests; clippy clean]
- **Transaction stance:** [inside caller's tx | post-commit dispatch | not transactional]
- **Lock/await stance:** [no `.await` under lock | `tokio::sync::Mutex` may span (justify) | unchanged]
- **Concurrency stance:** [no change | introduces spawn (CancellationToken + multi-thread test) | removes spawn | mutex change]
- **Rollback:** [one git revert]

### Step 2 - [Verb + noun]
[Same structure. `coupled-fix` requires rationale for the coupling.]

## Out of Scope

[Adjacent improvements explicitly NOT in this plan.]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed Rust/Axum; data access + messaging recorded
- [ ] Step 3 - target + tests read directly (incl. lock-across-`.await`); sibling smells listed or section omitted; severity inversion flagged and, if present, stops before Blast Radius/Step Sequence
- [ ] Step 4 - Coverage Gate verdict with sharp boundaries; `Inadequate` refuses Steps 1+; happy-path-only -> `Inadequate`; concurrency-gate downgrade applied; lint state recorded; prerequisite table when Thin/Inadequate
- [ ] Step 5 - smells classified by delegating to atomic skills (async, concurrency, db, web, error, security, messaging, overengineering); each finding cites its owning skill
- [ ] Step 6 - blast radius stated
- [ ] Step 7 - `Primary recipe:` named; spine <= ~8 steps or split into PRs; every step states Transaction / Lock-await / Concurrency stance; behavior changes labeled `coupled-fix`; ordered low-risk first; goal reached at end with no bundled cleanup

## Avoid

- Producing Steps 1+ when Coverage Gate is `Inadequate`
- Introducing concurrency without cross-thread test coverage
- Bundling behavior changes with refactor steps (use `coupled-fix`, or split the PR)
- "While we're here" cleanup; renames during a refactor
- Removing a trait without a real second use case or `mockall` mock
- Moving HTTP / dispatch across a `pool.begin()`/`tx.commit()` boundary without naming the transaction stance
- `std::sync::Mutex` held across `.await` - always wrong
- `tokio::spawn` without `JoinHandle`/`JoinSet` ownership or (for long-lived) `CancellationToken`
- Refactoring a `pub` symbol in a published crate without a back-compat plan
- Replacing `Box<dyn Trait>` with generics at the trait declaration when only one callsite needed it - convert at the callsite
- Re-encoding rules already owned by `rust-async-patterns`, `rust-concurrency`, `rust-overengineering-review`, etc. - delegate via `Use skill:`
