---
name: task-rust-review
description: Rust / Axum / sqlx / Tokio code review - unwrap, Mutex-across-await, task leaks, SQL injection; spawns perf/security/obs subagents.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles`. Cross-check every changed surface against `spec.md` / `plan.md`: each change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**; missing in-scope coverage is a gap. Never edit spec artifacts.

# Rust Code Review

Staff-level Rust / Axum / sqlx / Tokio review umbrella. Covers correctness, architecture, AI quality, maintainability. Coordinates perf / security / observability subagents in parallel.

## When to Use

- Pre-merge review on a Rust / Axum PR
- Post-AI-generation quality gate
- Architecture drift detection

**Not for:** pre-implementation design (`task-rust-implement`), production incident (`/task-oncall-start`), single-error debug (`task-rust-debug`), new-system architecture (`task-design-architecture`), single-scope reviews (delegate to perf/security/observability).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `quick` | Time-constrained snapshot | Phase A + B summary |
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical patterns + cross-PR context |

**Auto-promote to `deep`:** After Phase A, if Blast Radius is Wide/Critical and user did not pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E |
| + Perf | Core + `task-rust-review-perf` |
| + Security | Core + `task-rust-review-security` |
| + Observability | Core + `task-rust-review-observability` |
| Full | Core + all three in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals:**

- **+Security:** `axum::extract::Multipart`, JWT / auth changes (`jsonwebtoken`, auth `from_fn`), DTO changes (request structs deriving `Deserialize` + `Validate`), raw SQL via `sqlx::query(&format!(...))`, secrets in config, background tasks consuming user input, `serde_json::from_value::<Domain>(req.body)`, `unsafe` blocks, `FromRow` struct returned via `Json(...)`
- **+Perf:** new sqlx migration, new `query!` / `query_as!`, new `JOIN`, new pagination, loops calling DB / HTTP, new in-process cache (`moka` / `dashmap`) or Redis read paths, new `tokio::spawn` / `JoinSet`
- **+Observability:** new module / crate, new external client (`reqwest::Client`, `redis::Client`, `aws-sdk-*`), new background worker / Kafka producer or consumer, `tracing_subscriber` change, new `metrics::counter!`, lifecycle changes, missing `#[tracing::instrument]` on new handlers
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rust-review` | Current branch vs base; fails fast on trunk |
| `/task-rust-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-rust-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs fetch) |

Pass `--base <branch>` for non-trunk base. Scope and depth flags compose: `/task-rust-review pr-50273 --base release/2026.05 +security deep`.

**No checkout required.** Read via ref-qualified diffs; never modify the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as subagent.

### Step 2 - Stack, Runtime, Data Access, Messaging

Use skill: `stack-detect`. Accept pre-detected stack from parent. If not Rust, stop and recommend `/task-code-review`.

Detect: **Runtime** (Tokio assumed for Axum; flag `async-std` / `smol`), **Data Access** (sqlx primary; diesel secondary), **Messaging** (in-process Tokio queue, `lapin` AMQP, `rdkafka` Kafka, none). Record for branching.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as subagent and parent passed handle + pre-read artifacts.

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

### Step 3.5 - Decide Mode (re-review auto-detect)

Skip if the handle has no `prior_checkpoint` -> `mode = full`, `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `mode = full`, `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

Otherwise (valid prior checkpoint present):

**Step 3.5a - Auto-fetch the head branch.** Only when a valid prior checkpoint exists, refresh the local tracking ref so a script can re-run the same command without manually fetching:

```bash
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "<head_ref>@{u}" 2>/dev/null)
```

If `upstream` resolves to `<remote>/<branch>` form, split and run:

```bash
git fetch <remote> <branch>
```

No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. After a successful fetch, re-resolve `current_head_sha = git rev-parse <head_ref>`.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` and stop. Do not call `review-report-writer`. |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `mode = full`, `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten; full re-review.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round> - full re-review.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round> - full re-review.`           |
| None of the above                                                       | `mode = incremental`, `round = prior.round + 1`, `incremental_range = <prior_head_sha>...<current_head_sha>`.                       |

**Step 3.5c - Incremental: re-read the diff scoped to the new range.**

If `mode = incremental`, replace the diff read from Step 3 with:

- `git diff <prior_head_sha>...<current_head_sha>`
- `git diff --name-status <prior_head_sha>...<current_head_sha>`
- `git log --oneline <prior_head_sha>..<current_head_sha>`

The full-range diff from Step 3 is discarded; all Phase A-E analysis operates on the incremental range only.

**Step 3.5d - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.` The reconciliation table only covers findings whose scope was active in the prior round.

### Step 4 - Scope Auto-Escalation

Scan file list / diff for signals listed under **Scope**. Log each as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> Core
- One category -> add matching scope
- 2+ categories -> Full
- Explicit scope -> respect; still log signals

Surface decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk
- Use skill: `review-blast-radius` for failure propagation

Output risk level + blast radius before any findings.

**Low-risk short-circuit:** if Risk is Low, Blast Radius is Narrow, **and** change does not touch architecture-relevant files (auth middleware, JWT, router composition, shared traits, `main.rs` / `lib.rs` wiring, sqlx migrations), skip Phases C-D and produce streamlined output with Phase B only.

If Blast Radius is Wide/Critical and user did not pass `quick`, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

### Phase B - Rust Correctness and Safety

Apply atomic skills; each owns canonical patterns:

- Use skill: `rust-error-handling` - `thiserror` / `anyhow`, `?` / `.context(...)`, `#[from]`, `IntoResponse for AppError`, no `.unwrap()` / `.expect()` / `panic!` in production
- Use skill: `rust-async-patterns` - Tokio task lifecycle, `JoinHandle` / `JoinSet`, `CancellationToken`, `tokio::select!`, `spawn_blocking`, `tokio::time::timeout`, bounded channels
- Use skill: `rust-concurrency` - `Arc` / `Mutex` / `RwLock` choice, `Send + Sync`, no `std::sync::Mutex` across `.await`
- Use skill: `rust-db-access` - `query!` / `query_as!` (no `format!` interpolation), transaction boundaries, post-commit dispatch, per-iteration query N+1
- Use skill: `rust-web-patterns` - extractors with `Validate` derives, response DTO mapping, tower middleware order, body-size limits
- Use skill: `rust-messaging-patterns` if diff touches Kafka / AMQP / Tokio task queues
- Use skill: `rust-migration-safety` if diff touches `migrations/`. Use skill: `ops-backward-compatibility` for client / in-flight impact

**Additional checks (not owned by atomics):**

- **Test coverage finding (named, not buried).** PR adds logic without `#[cfg(test)]` / integration tests? `[Suggestion]`; escalate to `[High]` on critical path: auth (JWT, session middleware), authorization (ownership, role middleware), money / billing, multi-step transactions / state machines, background workers that mutate data, migrations changing column semantics
- **Authorization in-handler.** Every per-owner endpoint scopes queries by principal in handler / service (`WHERE id = $1 AND user_id = $2`); middleware presence alone is insufficient
- **Domain struct in `Json(...)`.** Flag `Json(<sqlx FromRow domain struct>)` regardless of current fields - adding a sensitive column later silently exposes it. Require an explicit `*Response` DTO at the boundary
- **`unsafe` discipline.** Every `unsafe` block carries a `// SAFETY:` comment justifying invariants. Bare `unsafe` is a Blocker
- **`cargo clippy --all-targets -- -D warnings` clean** expectation noted

### Phase C - Rust Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Rust-specific:**

- **Layering:** `handler` -> `service` -> `repository` -> `model`. Handlers extract / validate / delegate / respond; services hold rules (no Axum extractors, no sqlx types); repositories return domain types; `main.rs` (or `app::build()`) wires constructors via `AppState`
- **Traits at the consumer.** `OrderRepository` lives in the consuming module (typically `service`), not next to its `PgOrderRepository` impl. Trait + single impl in the same module with no second implementer and no mock is a single-impl-trait smell (Phase D)
- **`AppState` + typed config.** Single `#[derive(Clone)]` `AppState` extracted via `State<AppState>`; fields wrapped in `Arc` where needed. Typed config struct (`figment` / `config` / `envy`) loaded once at startup; no `lazy_static!` / `OnceCell` globals or `std::env::var("X")` scattered across files
- **Module boundaries:** feature-module layout (`src/orders/{handler,service,repository,model}.rs`) preferred over layer-module; cross-feature imports through public service traits. `pub` items not in the public API surface stay `pub(crate)` or unmarked
- **Multi-tenant isolation** enforced at repository layer (every query filters `tenant_id`), not at routes alone
- **Router + `IntoResponse`:** `Router::new().nest("/orders", orders_router())` per domain; auth via `.route_layer(middleware::from_fn(auth))` at sub-router level. One `impl IntoResponse for AppError` maps domain errors to status codes - per-handler `(StatusCode::INTERNAL_SERVER_ERROR, "...")` leaks internals
- **Anemic domain (deep depth only):** rules accumulating in `*_service.rs` while domain structs stay as bare data containers - flag for `task-rust-refactor`. Don't raise on a single PR

**Multi-service PRs:** API contract compatibility (OpenAPI diff via `utoipa`, Pact); deployment order documented; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering, simplification
- Use skill: `rust-overengineering-review` for: validator-crate rules duplicating sqlx / DB / type system, unreachable `match` arms, `Result` where `E` is never constructed, `.unwrap_or_default()` on non-`Option`, single-impl trait at the impl, `Box<dyn Trait>` on hot single-callsite, `Arc<Mutex<T>>` on never-mutated data, hot-loop `.clone()`, speculative `cfg(feature)`

**Additional AI smells:**

- Redundant mapping layers (`Row -> InternalDto -> ServiceDto -> ResponseDto`)
- Test verbosity (setup > 30 lines for one assertion; full deep-equal when a few field assertions would do)
- `Box<dyn Error>` / `anyhow::Error` in domain types - if callers need to match, use a `thiserror` enum

### Phase E - Maintainability

Use skill: `backend-coding-standards` for cross-language naming. Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth in `task-rust-review-observability`).

**Rust-specific:**

- Naming: `snake_case` modules with no stutter (`user::UserService` -> `user::Service`); `UpperCamelCase` types; `SCREAMING_SNAKE_CASE` constants. Public types start doc comments with the type name
- Magic numbers / strings extracted to `const`
- Hardcoded URLs / credentials in env / typed config
- Function length: > 30 lines reviewed for extraction; > 60 lines flagged unless clearly orchestrating
- Duplicated query logic: same `WHERE` predicate in 3+ places extracted to a repository method
- Surface `println!` / `eprintln!` in production paths; log lines without correlation IDs; wrong levels
- Doc comments on `pub` items; fallible functions document `# Errors`; non-obvious panics document `# Panics`; public modules have `//!` docs

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread.

**Subagent prompt contract:**

- Resolved review target (`base_ref`, `head_ref`) + pre-read diff and commit log (no re-running git)
- Depth level
- Pre-confirmed stack (Rust / Axum) + runtime + data-access + messaging
- Return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into single Output Format. Do not append raw reports.

- Deduplicate cross-cutting findings (one entry citing all scopes)
- Highest severity wins (`Blocker` > `High` > `Suggestion` > `Question`). Map subagent scales: `Critical` -> `Blocker`, `High` -> `High`, `Medium` / `Low` -> `Suggestion`
- Preserve `file:line` citations from the originating subagent
- Order by severity, not scope
- Note missing scopes as `Scope incomplete: <scope>`
- Merge Next Steps with `[Implement]` / `[Delegate]` tags; re-sort by severity

### Step 6.5 - Reconcile Prior Findings (incremental mode only)

Skip if `mode = full`. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `incremental_diff`: from Step 3.5c
- `name_status`: from Step 3.5c

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode` (from Step 3.5), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = rust-axum`

Write before ending; print confirmation.

## Feedback Labels

| Label | Meaning | Required |
|-------|---------|----------|
| [Blocker] | Must fix before merge - correctness / risk | Yes |
| [High] | Should fix - significant impact | Strong |
| [Suggestion] | Would improve - non-blocking | No |
| [Question] | Need clarity from author | Clarify |

No `[Nitpick]` or `[Praise]`.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted: `auto-promoted from standard; Blast Radius: <level>`)_
**Round:** <N>                                _(include from round 2 onward)_
**Mode:** incremental (since <prior_head_sha_short>) | full _(include from round 2 onward)_
**Diff Range:** <range_short> (<N> commits, <M> files) _(incremental rounds only)_

## Prior Round Reconciliation _(incremental rounds only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Blocker] file:line

- Issue: [name the Rust idiom: `.unwrap()` in production, `std::sync::Mutex` across `.await`, fire-and-forget `tokio::spawn`, sqlx `format!` interpolation, missing extractor validation, `IntoResponse` leaking `sqlx::Error`, domain struct in `Json(...)`, dispatch inside transaction, `unsafe` without SAFETY]
- Impact: [user-visible or operational]
- System Risk: [why system-level, not just local bug]
- Fix: [concrete Rust change with code]

### [High] file:line
- Issue, Impact, Fix

### [Suggestion] file:line
- Improvement

### [Question] file:line
- Question: [what is ambiguous]
- Why it matters: [what the right next step depends on]

_Use [Question] for genuine ambiguity, not as softer Blocker._

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line._
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by severity alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Implement]** [High] old_file.rs:88 - N+1 in list_all (open since round 1)
3. **[Delegate]** [High] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Blocker heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Rust conventions (Rust API Guidelines, Rust Book, `cargo clippy`)
- Actionable feedback with Rust code
- `cargo fmt` applies; don't nitpick style
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: stack confirmed Rust / Axum; runtime, data-access, messaging recorded
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff and commit log read once and reused; for `pr-ref` mode the fetch was surfaced; when `head_matches_current` was false, approval obtained; current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Step 4: scope auto-escalation evaluated; promotion (or `core-only`) recorded with firing signals
- [ ] Phase A: risk + blast radius stated before any finding; depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills applied (`rust-error-handling`, `rust-async-patterns`, `rust-concurrency`, `rust-db-access`, `rust-web-patterns`, plus `rust-messaging-patterns` / `rust-migration-safety` when relevant); test coverage, authorization, `Json(<domain>)`, `unsafe` discipline checked
- [ ] Phase C: layering, trait-at-consumer, `AppState` + typed config, multi-tenant, router + `IntoResponse` applied
- [ ] Phase D: `complexity-review` + `rust-overengineering-review` applied; AI smells covered (redundant mapping, test verbosity, `anyhow::Error` in domain types)
- [ ] Phase E: naming, magic numbers, function length, structured logging, doc comments on `pub` items
- [ ] Missing tests raised as a named finding (not buried)
- [ ] Every Blocker states system risk
- [ ] Every finding has label + `file:line` + actionable Rust fix
- [ ] If `--spec`: every finding traces to AC/NFR/task or flagged out-of-scope blocker
- [ ] Step 5: extra scopes ran in parallel with pre-resolved handle + stack detection
- [ ] Step 6: subagent findings merged into one severity-ordered list; raw reports not appended; failed/missing scope noted as `Scope incomplete: <scope>`; Next Steps tagged `[Implement]` / `[Delegate]` and ordered by severity
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Step 7: review report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Suggestions or Architecture/Maintainability notes - only `## High-Impact Findings` rows.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Generic backend conventions when a Rust idiom exists ("define trait in consuming module", not "use DI")
- Nitpicking style where `cargo fmt` applies
- Vague feedback ("this could be better"); blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability depth here when the dedicated Rust subagent owns it
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
