---
name: task-laravel-review
description: Laravel/PHP code review: mass assignment, Eloquent N+1, SQL injection, auth policies, fat controllers; spawns perf/security/observability subagents.
agent: php-tech-lead
metadata:
  category: backend
  tags: [php, laravel, eloquent, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Laravel Code Review

## Purpose

Laravel-aware staff-level code review umbrella covering correctness, architecture, AI-quality, and maintainability, with parallel perf/security/observability subagents. Stack-specific delegate of `task-code-review` for PHP/Laravel; preserves the core contract (depth, scope, low-risk short-circuit, output) and runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge Laravel PR review, post-AI-generation quality gate, branch risk assessment
- Architecture drift detection in layered Laravel codebases (controllers / form requests / services / actions / repositories / jobs)

**Not for:** pre-implementation design (`task-laravel-implement`); production incident triage (`/task-oncall-start`); single-error debugging (`task-laravel-debug`); new-system design review (`task-design-architecture`); single-scope reviews (delegate to `task-laravel-review-perf` / `-security` / `-observability`).

## Depth Levels

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot                             | Phases A + B summary only                                    |
| `standard` | Default - full Laravel staff-level review                                 | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, Principal sign-off        | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`. **Auto-promote to `deep`** when Phase A returns `Blast Radius: Wide|Critical` and the user did not pass `quick`; surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in Summary.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E (Laravel-flavored)                                              |
| + Perf          | Core + `task-laravel-review-perf` subagent                                 |
| + Sec           | Core + `task-laravel-review-security` subagent                             |
| + Obs           | Core + `task-laravel-review-observability` subagent                        |
| Full            | Core + Perf + Sec + Obs (3 parallel subagents)                             |

Default: **Core with auto-escalation**. Pass `core-only` to suppress. Two or more signal categories -> **Full**.

**Auto-escalation signals (Laravel):**

- **+Sec:** file uploads (`$request->file`, `Storage::put`), Sanctum/Passport/`auth:` middleware edits, Gate/Policy edits, `Model::create($request->all())`, `DB::raw($input)` / `whereRaw("...$input")`, `env()` in business code, jobs accepting webhook payloads, signed URLs, `Crypt::encrypt`, untrusted-input deserialization.
- **+Perf:** new Eloquent query / `with()` chain / Blade loop over relationship / `paginate*`, new endpoint with payload, loops calling DB or HTTP, new `Cache::remember`, `Http::pool` fan-out, new dispatched job.
- **+Obs:** new service or external client (`Http::withToken`, AWS/Stripe SDK), new Job/Listener/`Schedule::*`, edits to `bootstrap/app.php` / `config/logging.php` / `config/queue.php`, new `Log::*` channel / Telescope / Horizon config, worker lifecycle changes.
- **+Perf (migration):** migration on a hot table (alter/drop column/`change()`/index referenced by 5+ files or named in the PR title), `NOT NULL` on existing column without nullable->backfill->set-NOT-NULL, single-migration column rename/drop.

## Invocation

| Invocation                      | Meaning                                                                                                                                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-laravel-review`          | Review current branch vs its base - fails fast if on a trunk branch                                                                                                                    |
| `/task-laravel-review <branch>` | Review `<branch>` vs its base (3-dot diff)                                                                                                                                             |
| `/task-laravel-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants)  |

No checkout required (ref-qualified diffs). Pass `--base <branch>` when the PR was opened against a non-trunk base. Flags compose: `/task-laravel-review pr-50273 --base release/2026.05 +sec deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Governs every subsequent step. When invoked as a subagent of `task-code-review`, accept the parent's confirmation; do not re-load.

### Step 2 - Confirm Stack and Detect Eloquent / Queue / Auth Surface

Use skill: `stack-detect` to confirm PHP / Laravel (skip if a parent dispatcher pre-detected). If not Laravel, stop and tell the user to invoke `/task-code-review`.

Record: `PHP: <version>`, `Laravel: <version>`, `Auth: Sanctum (token) | Sanctum (SPA) | Passport | session`, `Queue: redis (Horizon) | database | sync` (sync in prod is `[Must]`), `Tests: Pest | PHPUnit`. Phase B-E checklists branch on these signals where the idiom differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or none for current branch); forward `--base <branch>` if passed. If it stops fail-fast (dirty tree, trunk branch, missing PR ref, denied head-vs-current), surface the message verbatim and stop. Never run state-changing git here.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Once approved, read once and reuse: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log --oneline <base_ref>..<head_ref>`. Skip this step when a parent subagent dispatcher passed the precondition handle plus pre-read diff/log.

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
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
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

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary based on mode:

- `mode = incremental`: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.`
- `mode = full`: `Scope expanded round <N>: +<list>.` (the incremental clause does not apply)

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

### Step 4 - Evaluate Scope Auto-Escalation

Scan files/diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then: zero signals or `core-only` -> Core; one signal category -> add the matching extra scope; two or more -> **Full**; explicit user scope -> respect it but still record signals. Surface in Summary `Scope:`; if escalated, append `auto-escalated from Core; signals: <list>`.

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

### Phase A - PR Risk Snapshot (run first)

Use skill: `review-pr-risk` for cross-cutting risk signals; use skill: `review-blast-radius` for failure-propagation scope. Output risk level and blast radius before any findings.

**Low-risk short-circuit:** Risk `Low` + Blast Radius `Narrow` + no touch to architecture-relevant files (auth middleware, Sanctum/Passport config, `bootstrap/app.php`, `config/{auth,queue,database}.php`, model `$fillable`/`$casts`, Policies, `database/migrations/`) -> skip Phases C-D, output Phase B findings only.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is `Wide|Critical` and the user did not pass `quick`, promote depth to `deep` and surface in Summary **before** launching Phases B-E so deep-only behaviors (historical patterns, cross-PR context, anemic-domain assessment) are in scope.

### Phase B - Laravel Correctness and Safety

Logical correctness, error handling, state-integrity edge cases, backward compatibility, transaction boundaries, queue dispatch safety.

**Test coverage finding:** Changed logic without Pest/PHPUnit coverage -> `[Recommend]`; escalate to `[Must]` on critical paths (Sanctum/auth middleware, Policies/Gates/ownership, money or billing, multi-step `DB::transaction`, queue jobs with side effects, migrations changing column semantics). Raise as a named Findings entry, not in Key Takeaways.

**Wrong-store test finding:** Feature tests on SQLite while prod uses MySQL/PostgreSQL -> `[Recommend]`. SQLite FK/`JSON`/fulltext/concurrency semantics differ.

**Correctness checklist** (canonical patterns in the cited atomic skills):

- [ ] **Mass assignment**: no `$guarded = []`; `Model::create($request->validated())` not `$request->all()`; server-set fields (`user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`) assigned explicitly outside fillable
- [ ] **Form Request validation** (not inline `$request->validate`); `authorize()` not defaulted to `true` on user-data endpoints
- [ ] **Auth + rate limits** on protected routes (`auth:sanctum`/`auth`/`auth:api`; `throttle:auth`/`throttle:api` on auth + write-heavy routes)
- [ ] **Authorization on every protected action**: Policy/Gate/`can:` middleware OR ownership-scoping (`$user->orders()->findOrFail($id)`); bare `Order::find($id)` on owned data is IDOR
- [ ] **Route model binding scoping**: nested per-owner resources use `->scopeBindings()` or in-controller scoping
- [ ] **No raw SQL interpolation** (`whereRaw`/`DB::raw`/`orderByRaw`/`selectRaw`/`havingRaw` with user input); user-supplied `orderBy` allowlisted via `Rule::in([...])`
- [ ] **N+1**: eager-load via `with(...)` in controllers/Blade/Resources; `Model::shouldBeStrict()` in non-prod
- [ ] **`Model::all()` on growable tables** -> require `chunkById`/`lazy`/`cursor`/pagination
- [ ] **Single `DB::transaction()` boundary** per multi-write use case
- [ ] **Queue dispatch after commit** (`->afterCommit()` or `public bool $afterCommit = true;`); jobs take scalar IDs not models; `$tries`/`$backoff`/`$timeout`/`failed()` set on every queueable job
- [ ] **No `env()` outside `config/*.php`**; no closures in config arrays; no hardcoded secrets (`Hash::make`/`Hash::check` for passwords)
- [ ] **No raw Eloquent model returned from controller**; API Resources with explicit `toArray()` and `whenLoaded`/`when`
- [ ] **HTTP idempotency** on state-mutating writes (`Idempotency-Key` + server-side dedupe)
- [ ] **Response-shape field stripping**: compare Resource `toArray()` vs ORM columns; flag `internal_notes`, `password_hash`, `mfa_secret`, `audit_log`, `tenant_internal_*`, `is_admin` exposure
- [ ] **Webhook controllers**: signature verified (`hash_equals` / SDK), responds 200 fast, dispatches async, dedupes on provider event ID; CSRF `validateCsrfTokens(except: [...])` only for webhooks
- [ ] **Concurrency**: no mutable static class properties (leaks across PHP-FPM and crashes under Octane); race-prone updates use DB locking inside transaction (`lockForUpdate`) or atomic guarded SQL (`->where('stock', '>=', $qty)->decrement(...)`); `Cache::lock` for cross-replica critical sections

Use skill: `laravel-eloquent-patterns` for canonical Eloquent correctness.
Use skill: `laravel-api-patterns` for Form Request / API Resource / controller / webhook patterns.
Use skill: `laravel-queue-patterns` when the diff touches queues.
Use skill: `laravel-service-patterns` for service/action layering and event-driven patterns.

**Migration PRs (only when `database/migrations/` changed):**

- [ ] Every `up()` has a matching `down()` (missing `down()` is `[Must]` on multi-instance deploys)
- [ ] Two-phase deploys for column rename/drop (add -> backfill -> cut over -> remove); single-migration drops break rolling deploys
- [ ] `NOT NULL` on existing columns: nullable -> backfill -> set-NOT-NULL on tables > 100K rows; flag `->change()` on tables > 1M rows for `pt-online-schema-change`
- [ ] Indexes on large tables use `ALGORITHM=INPLACE, LOCK=NONE`
- [ ] FKs use `->constrained()` with explicit `onDelete`/`onUpdate`
- [ ] DDL and data migrations in separate files; backfills via `chunkById(1000, ...)`
- Use skill: `ops-backward-compatibility` for client/session/in-flight-request impact
- Use skill: `laravel-migration-safety` for canonical safe-migration patterns

### Phase C - Laravel Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations, new coupling, circular-dependency risk, bypassed abstractions, boundary erosion.

- [ ] **Thin controllers**: validate -> delegate -> respond; actions > 30 lines orchestrating business logic belong in a service/action
- [ ] **Services/Actions for business logic** in `app/Services/*Service.php` or `app/Actions/*Action.php`; not duplicated across controllers/jobs/console
- [ ] **No business logic in Eloquent models** beyond scopes/relationships/casts/accessors/mutators; > 500 lines or cross-aggregate methods = god-model
- [ ] **DTOs for non-trivial cross-layer transport**: `readonly` DTOs over `$request->validated()` arrays through deep stacks
- [ ] **Repository pattern only when justified**: one-implementation repository over Eloquent is over-abstraction
- [ ] **Container bindings centralized** in service providers; inline `app()->bind(...)` in business code is a smell
- [ ] **Events for cross-domain side effects**; expensive listeners implement `ShouldQueue`
- [ ] **Multi-tenant isolation** via global scopes (`addGlobalScope(new TenantScope)`) AND query layer; `withoutGlobalScope(...)` needs a justifying comment
- [ ] **Middleware order in `bootstrap/app.php`**: auth before rate limiting; CSRF before route binding on web
- [ ] **One resource controller per aggregate root**
- [ ] **Central exception handling via `withExceptions(...)`** (Laravel 11+); scattered `try/catch/return response()->json(..., 500)` is inconsistent and leaks internals

**Multi-service PRs (2+ services):** check API contract compatibility (OpenAPI diff via `l5-swagger`/`scramble`, Pact, etc.); document deployment order or confirm independence; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` for verbosity, over-engineering, simplification opportunities.
Use skill: `laravel-overengineering-review` for redundancy and premature-abstraction findings (each cites its constraint source).

Additional Laravel AI smells:

- [ ] **Redundant mapping layers** (`Eloquent -> InternalDto -> ServiceDto -> ApiResource` when one would suffice)
- [ ] **Test verbosity**: factory setup > 30 lines for a single assertion; full-payload `assertJson` when key fields would do
- [ ] **Queue for synchronous work** pushed through `Bus::dispatch` for "decoupling"
- [ ] **Comment cruft**: PHPDoc restating method names (`/** Returns the user. */` on `getUser()`)
- [ ] **`@phpstan-ignore` without a `// reason: ...` comment**

### Phase E - Laravel Maintainability and Clarity

- [ ] **Naming (PSR-12 + Laravel)**: `PascalCase` namespaces/classes, `camelCase` methods/vars, `UPPER_SNAKE_CASE` constants; suffixes `Controller`/`Request`/`Job`/`Policy`; events past-tense, listeners present-tense
- [ ] **Magic numbers/strings** extracted to `const` or `config()`; backed enums for status/role/type, cast via `'status' => OrderStatus::class`
- [ ] **Method length**: > 30 lines reviewed for extraction; > 60 flagged unless orchestrating intention-revealing private methods
- [ ] **Duplicated query logic**: same `where(...)` chain in 3+ places extracted to a local scope (`scopeActive`) or query class
- [ ] **`declare(strict_types=1)`** at file top
- [ ] **PHP 8.2+ idioms**: `readonly` DTOs, constructor property promotion, first-class callables, enums for state machines
- [ ] **Logging hygiene** (`[Recommend]`): no `dd()`/`dump()` in prod paths; no PII in `Log::*`. Observability subagent owns depth.
- [ ] **`composer normalize` / Pint / PHPStan** clean in CI

Use skill: `backend-coding-standards` for cross-language naming/structure.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (subagent owns depth).

### Step 5 - Delegate Extra Scopes in Parallel (if scope includes)

Skip if Core only. Otherwise spawn each extra-scope subagent **in parallel** with the main Core thread: `+Perf` -> `task-laravel-review-perf`; `+Sec` -> `task-laravel-review-security`; `+Obs` -> `task-laravel-review-observability`; **Full** -> all three concurrently.

Each subagent prompt must include: resolved `base_ref`/`head_ref` + pre-read diff/log (skips `review-precondition-check` and `git diff`); depth level + pre-confirmed stack/ORM/auth/queue signals (skips `stack-detect`); spec slug if `--spec` was passed; instruction to return findings in the subagent's own Output Format.

**Failure isolation.** If a subagent fails or times out, continue with the rest; note the missing scope in the synthesized output.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** Same issue across scopes (e.g., per-iteration `Order::find($id)` flagged by both Phase B and Perf) -> one entry citing all scopes.
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`. Map subagent scales: `Critical` -> `Must`, `High` -> `Recommend`, `Medium`/`Low` -> drop from the merged list (only `Must`, `Recommend`, `Question` are emitted).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by intent, not scope.** One merged list.
- **Note missing scopes** -> add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps** into one prioritized list; preserve `[Implement]`/`[Delegate]` tags; deduplicate; re-sort by intent.

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
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = php-laravel`

Write the assembled output to the report file before ending; print the confirmation line.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |
| [Question]   | Author must answer; reviewer decides if a fix follows.                   |

No `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** PHP <version> / Laravel <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Queue:** redis (Horizon) | database | sync
**Tests:** Pest | PHPUnit
**Scope:** Core | +Sec | +Perf | +Obs | Full _(if auto-escalated: `auto-escalated from Core; signals: <list>`)_
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

### [Must] file:line
- Issue: [name the Laravel idiom]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Laravel change with code example]

### [Recommend] file:line
- Issue:
- Impact:
- Fix:

### [Question] file:line
- Question:
- Why it matters:

## Architecture Notes

_Cross-cutting commentary; reference Findings by file:line, do not duplicate._

## Maintainability Notes

- Over-engineering detected / Simplification opportunities

## Key Takeaways

- 2-4 bullets on systemic impact and what to address before merge.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Prioritized list tagged `[Implement]` or `[Delegate]`, ordered Must > Recommend > Question. Omit if no actionable findings.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] OldFile.php:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]
```

**Omit empty sections.**

## Rules

- Review the whole change as system impact, not file-by-file
- Lead with risk assessment before line-level findings
- Apply Laravel conventions (PSR-12, Laravel docs, Pint preset), not generic backend
- Provide actionable feedback with PHP / Laravel code examples
- Default to Core scope; auto-escalate on signals; honor `core-only`
- Delegate perf/security/observability depth to the appropriate Laravel subagent

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: stack confirmed; auth strategy, queue driver, test framework recorded
- [ ] Step 3: `review-precondition-check` ran; diff and commit log read once and reused; current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Step 4: scope auto-escalation evaluated; promotion or `core-only` recorded in Summary with firing signals
- [ ] Step 4.5: depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Phase A: risk level and blast radius stated before any line-level findings
- [ ] Phase B: Laravel correctness checklist applied; migration safety delegated to `laravel-migration-safety` when migrations changed
- [ ] Phase C: architecture checks applied (thin controllers, services/actions, no model in responses, repository only when justified, multi-tenant isolation, middleware order)
- [ ] Phase D: `complexity-review` + `laravel-overengineering-review` applied
- [ ] Phase E: maintainability checks applied
- [ ] Missing tests raised as a named Finding (not buried in Key Takeaways)
- [ ] Every Must cites system risk; every finding has label, `file:line`, actionable Laravel fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] Step 5: non-Core subagents ran in parallel with pre-resolved diff/log + stack signals
- [ ] Step 6: findings merged with deduplication and strongest-intent-wins; raw subagent reports not appended; failed scopes noted as `Scope incomplete: <scope>`
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Step 7: report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Generic backend phrasing when a Laravel idiom exists ("wrap in a Form Request", not "validate input")
- Vague feedback without a concrete Laravel fix
- Running extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports instead of merging into one intent-ordered Findings list
