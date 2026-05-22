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
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Laravel staff-level review                                 | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`. **Auto-promote to `deep`** when Phase A returns `Blast Radius: Wide|Critical` and the user did not pass `quick`; surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in Summary.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E only (Laravel-flavored)                                         |
| + Perf          | Core + parallel subagent: `task-laravel-review-perf`                       |
| + Security      | Core + parallel subagent: `task-laravel-review-security`                   |
| + Observability | Core + parallel subagent: `task-laravel-review-observability`              |
| Full            | Core + Perf + Security + Observability (3 parallel Laravel subagents)      |

Default: **Core with auto-escalation**. Pass `core-only` to suppress. Two or more signal categories -> **Full**.

**Auto-escalation signals (Laravel):**

- **+Security:** file uploads (`$request->file`, `Storage::put`), Sanctum/Passport/`auth:` middleware edits, Gate/Policy edits, `Model::create($request->all())`, `DB::raw($input)` / `whereRaw("...$input")`, `env()` in business code, jobs accepting webhook payloads, signed URLs, `Crypt::encrypt`, untrusted-input deserialization.
- **+Perf:** new Eloquent query / `with()` chain / Blade loop over relationship / `paginate*`, new endpoint with payload, loops calling DB or HTTP, new `Cache::remember`, `Http::pool` fan-out, new dispatched job.
- **+Observability:** new service or external client (`Http::withToken`, AWS/Stripe SDK), new Job/Listener/`Schedule::*`, edits to `bootstrap/app.php` / `config/logging.php` / `config/queue.php`, new `Log::*` channel / Telescope / Horizon config, worker lifecycle changes.
- **+Perf (migration):** migration on a hot table (alter/drop column/`change()`/index referenced by 5+ files or named in the PR title), `NOT NULL` on existing column without nullable->backfill->set-NOT-NULL, single-migration column rename/drop.

## Invocation

| Invocation                      | Meaning                                                                                                                                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-laravel-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                            |
| `/task-laravel-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                      |
| `/task-laravel-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants)  |

No checkout required (ref-qualified diffs). Pass `--base <branch>` when the PR was opened against a non-trunk base. Flags compose: `/task-laravel-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Governs every subsequent step. When invoked as a subagent of `task-code-review`, accept the parent's confirmation; do not re-load.

### Step 2 - Confirm Stack and Detect Eloquent / Queue / Auth Surface

Use skill: `stack-detect` to confirm PHP / Laravel (skip if a parent dispatcher pre-detected). If not Laravel, stop and tell the user to invoke `/task-code-review`.

Record: `PHP: <version>`, `Laravel: <version>`, `Auth: Sanctum (token) | Sanctum (SPA) | Passport | session`, `Queue: redis (Horizon) | database | sync` (sync in prod is a Blocker), `Tests: Pest | PHPUnit`. Phase B-E checklists branch on these signals where the idiom differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or none for current branch); forward `--base <branch>` if passed. If it stops fail-fast (dirty tree, trunk branch, missing PR ref, denied head-vs-current), surface the message verbatim and stop. Never run state-changing git here.

Once approved, read once and reuse: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log --oneline <base_ref>..<head_ref>`. Skip this step when a parent subagent dispatcher passed the precondition handle plus pre-read diff/log.

### Step 4 - Evaluate Scope Auto-Escalation

Scan files/diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then: zero signals or `core-only` -> Core; one signal category -> add the matching extra scope; two or more -> **Full**; explicit user scope -> respect it but still record signals. Surface in Summary `Scope:`; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot (run first)

Use skill: `review-pr-risk` for cross-cutting risk signals; use skill: `review-blast-radius` for failure-propagation scope. Output risk level and blast radius before any findings.

**Low-risk short-circuit:** Risk `Low` + Blast Radius `Narrow` + no touch to architecture-relevant files (auth middleware, Sanctum/Passport config, `bootstrap/app.php`, `config/{auth,queue,database}.php`, model `$fillable`/`$casts`, Policies, `database/migrations/`) -> skip Phases C-D, output Phase B findings only.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is `Wide|Critical` and the user did not pass `quick`, promote depth to `deep` and surface in Summary **before** launching Phases B-E so deep-only behaviors (historical patterns, cross-PR context, anemic-domain assessment) are in scope.

### Phase B - Laravel Correctness and Safety

Logical correctness, error handling, state-integrity edge cases, backward compatibility, transaction boundaries, queue dispatch safety.

**Test coverage finding:** Changed logic without Pest/PHPUnit coverage -> at minimum `[Suggestion]`; escalate to `[High]` on critical paths (Sanctum/auth middleware, Policies/Gates/ownership, money or billing, multi-step `DB::transaction`, queue jobs with side effects, migrations changing column semantics). Raise as a named Findings entry, not in Key Takeaways.

**Wrong-store test finding:** Feature tests on SQLite while prod uses MySQL/PostgreSQL -> `[High]`. SQLite FK/`JSON`/fulltext/concurrency semantics differ; false confidence is worse than a known gap.

**Correctness checklist** (canonical patterns in the cited atomic skills):

- [ ] **Mass assignment**: no `$guarded = []`; `Model::create($request->validated())` not `$request->all()`; server-set fields (`user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`) assigned explicitly outside fillable
- [ ] **Form Request validation** (not inline `$request->validate`); `authorize()` not defaulted to `true` on user-data endpoints
- [ ] **Auth + rate limits** on protected routes (`auth:sanctum`/`auth`/`auth:api`; `throttle:auth`/`throttle:api` on auth + write-heavy routes)
- [ ] **Authorization on every protected action**: Policy/Gate/`can:` middleware OR ownership-scoping (`$user->orders()->findOrFail($id)`); bare `Order::find($id)` on owned data is IDOR
- [ ] **Route model binding scoping**: nested per-owner resources use `->scopeBindings()` or in-controller scoping
- [ ] **No raw SQL interpolation** (`whereRaw`/`DB::raw`/`orderByRaw`/`selectRaw`/`havingRaw` with user input); user-supplied `orderBy` allowlisted via `Rule::in([...])`
- [ ] **N+1**: eager-load via `with(...)` in controllers/Blade/Resources; `Model::preventLazyLoading()` in non-prod
- [ ] **`Model::all()` on growable tables** -> require `chunkById`/`lazy`/`cursor`/pagination
- [ ] **Single `DB::transaction()` boundary** per multi-write use case
- [ ] **Queue dispatch after commit** (`->afterCommit()` or `public bool $afterCommit = true;`); jobs take scalar IDs not models; `$tries`/`$backoff`/`$timeout`/`failed()` set on every queueable job
- [ ] **No `env()` outside `config/*.php`** (returns null after `config:cache`); no closures in config arrays
- [ ] **No raw Eloquent model returned from controller**; API Resources with explicit `toArray()` and `whenLoaded`/`when`
- [ ] **HTTP idempotency** on state-mutating writes (`Idempotency-Key` + server-side dedupe; distinct from queue-job idempotency)
- [ ] **Response-shape field stripping**: compare Resource `toArray()` vs ORM columns; flag `internal_notes`, `password_hash`, `mfa_secret`, `audit_log`, `tenant_internal_*`, `is_admin` exposure
- [ ] **CSRF default-on** for web/SPA; `validateCsrfTokens(except: [...])` only for webhooks with signature verification
- [ ] **No hardcoded secrets**; `Hash::make`/`Hash::check` for passwords; `Auth::attempt(...)` for login

Use skill: `laravel-eloquent-patterns` for canonical Eloquent correctness.
Use skill: `laravel-api-patterns` for Form Request / API Resource / controller patterns.
Use skill: `laravel-queue-patterns` when the diff touches queues.
Use skill: `laravel-service-patterns` for service/action layering and event-driven patterns.

**Migration PRs (any change under `database/migrations/`):**

- [ ] Every `up()` has a matching `down()` (missing `down()` is `[Blocker]` on multi-instance deploys)
- [ ] Two-phase deploys for column rename/drop (add -> backfill -> cut over -> remove); single-migration drops break rolling deploys
- [ ] `NOT NULL` on existing columns: nullable -> backfill -> set-NOT-NULL on tables > 100K rows; flag `->change()` on tables > 1M rows for `pt-online-schema-change`
- [ ] Indexes on large tables use `ALGORITHM=INPLACE, LOCK=NONE` (MySQL 5.6+) where Schema Builder default doesn't apply
- [ ] FKs use `->constrained()` with explicit `onDelete`/`onUpdate`; avoid `set null` unless column is nullable
- [ ] DDL and data migrations in separate files; backfills via `chunkById(1000, ...)`, never `WHERE col IS NULL LIMIT N`
- [ ] Multi-replica deploys run `php artisan migrate` once (deployer exec or init container with leader election)
- Use skill: `ops-backward-compatibility` for client/session/in-flight-request impact
- Use skill: `laravel-migration-safety` for canonical safe-migration patterns

**Concurrency / queue safety:**

- [ ] No mutable static class properties for shared state - use `Cache::*` or `Cache::lock('key')->block(5, fn() => ...)`; statics leak across PHP-FPM requests and crash under Octane
- [ ] Race-prone updates (counters, balance, inventory, seats) use DB locking inside a transaction (`Order::lockForUpdate()->find($id)`) or atomic guarded SQL (`->where('stock', '>=', $qty)->decrement('stock', $qty)`); in-process semaphores only cover one replica
- [ ] `Cache::lock` for cross-replica critical sections with a short timeout, never indefinite
- [ ] Queue connection is **not** `sync` in production
- [ ] Octane/Swoole/RoadRunner: flag new `app()->singleton(...)` closures capturing request data
- [ ] PHPStan/Larastan level 5+ + Pint clean in CI

### Phase C - Laravel Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations, new coupling, circular-dependency risk, bypassed abstractions, boundary erosion.

- [ ] **Thin controllers**: validate -> delegate -> respond; actions > 30 lines orchestrating business logic, multiple models, or multi-step transactions belong in a service/action
- [ ] **Services/Actions for business logic** in `app/Services/*Service.php` or `app/Actions/*Action.php`; not duplicated across controllers/jobs/console
- [ ] **No business logic in Eloquent models** beyond scopes/relationships/casts/accessors/mutators; > 500 lines or cross-aggregate methods = god-model
- [ ] **DTOs for non-trivial cross-layer transport**: `readonly` DTOs (PHP 8.2+) over `$request->validated()` arrays through deep stacks
- [ ] **Repository pattern only when justified**: one-implementation repository over Eloquent is over-abstraction
- [ ] **Container bindings centralized** in service providers; inline `app()->bind(...)` in business code is a smell
- [ ] **Events for cross-domain side effects** (notifications/audit/search-index); expensive listeners implement `ShouldQueue`
- [ ] **Multi-tenant isolation** via global scopes (`addGlobalScope(new TenantScope)`) AND query layer; `withoutGlobalScope(...)` needs a justifying comment
- [ ] **Service Provider registration** in `bootstrap/providers.php` (Laravel 11+) or `config/app.php`; defer rare bindings; flag eager providers resolving heavy services at boot
- [ ] **Middleware order in `bootstrap/app.php`**: explicit `prepend`/`append`/`replaceWith`; auth before rate limiting; CSRF before route binding on web
- [ ] **One resource controller per aggregate root**
- [ ] **Central exception handling via `withExceptions(...)`** (Laravel 11+): domain exceptions mapped centrally; scattered `try/catch/return response()->json(..., 500)` is inconsistent and leaks internals

**Multi-service PRs (2+ services):** check API contract compatibility (OpenAPI diff via `l5-swagger`/`scramble`, Pact, etc.); document deployment order or confirm independence; use skill: `ops-backward-compatibility` for any changed inter-service contract.

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

- [ ] **Naming (PSR-12 + Laravel)**: `PascalCase` namespaces/classes, `camelCase` methods/vars, `UPPER_SNAKE_CASE` constants; suffixes `Controller`/`Request`/`Job`/`Policy`; events past-tense, listeners present-tense; migrations descriptive snake_case
- [ ] **Magic numbers/strings** extracted to `const` or `config()`; backed enums for status/role/type, cast via `'status' => OrderStatus::class` in `casts()`
- [ ] **Hardcoded URLs/credentials** in `config/services.php` via `config('...')` (no `env()` outside config; covered in Phase B)
- [ ] **Method length**: > 30 lines reviewed for extraction; > 60 flagged unless orchestrating intention-revealing private methods
- [ ] **Duplicated query logic**: same `where(...)` chain in 3+ places extracted to a local scope (`scopeActive`) or query class
- [ ] **`declare(strict_types=1)`** at file top (Pint preset / PHPStan rule)
- [ ] **PHP 8.2+ idioms**: `readonly` DTOs, constructor property promotion, first-class callables, enums for state machines
- [ ] **Logging hygiene** (`[Suggestion]`): no `dd()`/`dump()`/`var_dump()` in prod paths; no PII in `Log::*`; log lines carry context arrays. Observability subagent owns depth.
- [ ] **`composer normalize` / Pint / PHPStan** clean in CI

Use skill: `backend-coding-standards` for cross-language naming/structure.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (subagent owns depth).

### Step 5 - Delegate Extra Scopes in Parallel (if scope includes)

Skip if Core only. Otherwise spawn each extra-scope subagent **in parallel** with the main Core thread: `+Perf` -> `task-laravel-review-perf`; `+Security` -> `task-laravel-review-security`; `+Observability` -> `task-laravel-review-observability`; **Full** -> all three concurrently.

Each subagent prompt must include: resolved `base_ref`/`head_ref` + pre-read diff/log (skips `review-precondition-check` and `git diff`); depth level + pre-confirmed stack/ORM/auth/queue signals (skips `stack-detect`); spec slug if `--spec` was passed; instruction to return findings in the subagent's own Output Format.

**Failure isolation.** If a subagent fails or times out, continue with the rest; note the missing scope in the synthesized output.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** Same issue across scopes (e.g., per-iteration `Order::find($id)` flagged by both Phase B and Perf) -> one entry citing all scopes.
- **Severity wins.** Highest across scopes: `Blocker` > `High` > `Suggestion` > `Question`. Map subagent scales: `Critical` -> `Blocker`, `High` -> `High`, `Medium`/`Low` -> `Suggestion`. Do not introduce `Critical`/`Medium`/`Low`.
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not scope.** One merged list.
- **Note missing scopes** -> add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps** into one prioritized list; preserve `[Implement]`/`[Delegate]` tags; deduplicate; re-sort by severity.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write the assembled output to the report file before ending; print the confirmation line.

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
**Stack Detected:** PHP <version> / Laravel <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Queue:** redis (Horizon) | database | sync
**Tests:** Pest | PHPUnit
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line
- Issue: [name the Laravel idiom: `$guarded = []`, `Model::create($request->all())`, N+1 in Blade, `whereRaw($input)`, missing `$this->authorize`, job in transaction without `afterCommit`, job constructor takes Eloquent model, raw model returned, `env()` outside config, `sync` queue in prod, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Laravel change with code example]

### [High] / [Suggestion] / [Question] file:line
Same shape (Issue/Impact/Fix; or Improvement; or Question/Why-it-matters). Use [Question] only when genuinely ambiguous - not a softer Blocker.

## Architecture Notes

_Cross-cutting commentary; reference Findings by file:line, do not duplicate._

- Boundary impact / Coupling change / Drift detected

## Maintainability Notes

- Over-engineering detected / Simplification opportunities

## Key Takeaways

- 2-4 bullets on systemic impact and what to address before merge.

## Next Steps

Prioritized list tagged `[Implement]` or `[Delegate]`, ordered Blocker > High > Suggestion. Omit if no actionable findings.
1. **[Implement]** [Blocker] file:line - action
2. **[Delegate]** [High] [scope: cross-service] - action
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

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
- [ ] Step 3: `review-precondition-check` ran; diff and commit log read once and reused
- [ ] Step 4: scope auto-escalation evaluated; promotion or `core-only` recorded in Summary with firing signals
- [ ] Step 4.5: depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Phase A: risk level and blast radius stated before any line-level findings
- [ ] Phase B: Laravel correctness checklist applied (mass assignment, Form Request, authorization + IDOR, SQL injection, N+1, queue safety, controller responses, env/config, rate limits)
- [ ] Phase B: migration safety delegated to `laravel-migration-safety` when migrations changed
- [ ] Phase C: architecture checks applied (thin controllers, services/actions, no model in responses, repository only when justified, multi-tenant isolation, middleware order)
- [ ] Phase D: `complexity-review` + `laravel-overengineering-review` applied; Laravel AI smells addressed
- [ ] Phase E: maintainability checks applied (naming, backed enums, method length, logging hygiene, `declare(strict_types=1)`)
- [ ] Missing tests raised as a named Finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk; every finding has label, file:line, actionable Laravel fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] Step 5: non-Core subagents ran in parallel with pre-resolved diff/log + stack signals
- [ ] Step 6: findings merged with deduplication and highest-severity-wins; raw subagent reports not appended; failed scopes noted as `Scope incomplete: <scope>`
- [ ] Step 7: Next Steps tagged `[Implement]`/`[Delegate]` and ordered Blocker > High > Suggestion (unless none); report written via `review-report-writer`; confirmation printed

## Avoid

- State-changing git commands from this workflow (`git fetch`, `git checkout`, etc.)
- Reviewing without reading the full diff and commit log first
- Generic backend phrasing when a Laravel idiom exists ("wrap in a Form Request", not "validate input")
- Vague feedback without a concrete Laravel fix
- Running extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports instead of merging into one severity-ordered Findings list
