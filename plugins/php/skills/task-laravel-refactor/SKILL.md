---
name: task-laravel-refactor
description: Laravel refactor plan: fat controllers, anemic services, mass assignment, N+1, queue idempotency; phased steps with test+phpstan+pint gate.
agent: php-tech-lead
metadata:
  category: backend
  tags: [php, laravel, eloquent, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Laravel Refactor

## Purpose

Produce a safe, step-by-step refactor plan for a Laravel target (Controller action, Form Request, Eloquent model, Service, Action, Job, Listener, Policy, scheduled command, API Resource). Identifies Laravel-specific smells (Step 5) and proposes independently-committable steps with `php artisan test` + `composer phpstan` + `vendor/bin/pint --test` gates between each. Stack-specific delegate of `task-code-refactor`.

## When to Use

- Laravel code-smell identification and resolution
- Technical-debt reduction with a concrete plan
- Safe refactor of a controller / service / job / Policy / API Resource / model
- Pre-merge cleanup of fat-controller / god-service growth

**Not for:** feature changes (`task-laravel-implement`), cross-package restructuring (`task-design-architecture`), bug fixes (`task-laravel-debug`).

## Inputs

| Input                 | Required    | Description                                                                 |
| --------------------- | ----------- | --------------------------------------------------------------------------- |
| Target scope          | Yes         | File or class (e.g., `app/Http/Controllers/OrderController.php`)            |
| Goal                  | Yes         | What the refactor achieves (e.g., extract `placeOrder` into an Action)      |
| Test coverage status  | Recommended | Pest / PHPUnit coverage; pint / PHPStan state                               |
| Shared/public surface | Recommended | Whether the target is `public` across Composer-package boundaries           |

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Do not skip.

### Step 2 - Confirm Stack and Detect Surface

Use skill: `stack-detect` to confirm PHP / Laravel. If not Laravel, route to `/task-code-refactor`. Record `ORM` (Eloquent / query builder), `Queue` (Redis+Horizon / database / sync), `Auth` (Sanctum / Passport / session), `Tests Framework` (Pest / PHPUnit).

**Input completeness check.** Both **target scope** AND **goal** must be supplied. If only a goal is given, ask for the target - do not guess.

### Step 3 - Read the Target

1. Read the target file; note method count, longest method, transaction placement, every external collaborator (`Http::*`, `Event::dispatch`, `dispatch(...)`, `Mail::*`, `Notification::send`)
2. Read matching tests; count cases per outcome (happy / validation / external / auth); confirm pint and PHPStan state
3. Read obvious callers - reshaping `public` members without seeing call sites silently breaks them

**Sibling-smell disposition.** When the target file contains other smells, do not action them and do not ignore them silently. List under `Sibling Smells (Out of Scope)` with deferral rationale and recommended follow-up.

**Severity-inversion rule.** When any sibling smell outranks the named target (working SQL injection, `exec($userInput)` RCE, auth bypass, `unserialize($userInput)` on untrusted input), recommend pausing the refactor and routing the security finding first.

**Severity-inversion banner.** When the rule fires, render at the top of Coverage Gate (above the verdict): `> **Severity inversion detected.** This file contains <N> sibling smells of higher severity than the named target (<list>). Pause this refactor; route through task-laravel-review-security first; branch the eventual refactor PR off the security fix.`

### Step 4 - Coverage Gate (mandatory)

Refactoring without coverage is a rewrite. Assign one status:

| Status       | Definition                                                          | Workflow action                                                                                            |
| ------------ | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry   | Proceed normally                                                                                           |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                      | Proceed with non-optional `Step 0 - Coverage prerequisite` before any refactor step                        |
| `Inadequate` | No tests, or happy-path-only                                        | **Refuse Steps 1+.** Output only the verdict and recommend running `task-laravel-test` first               |

Happy-path-only is `Inadequate`, not `Thin`.

**Wrong-store disqualifier.** `phpunit.xml` with `<env name="DB_CONNECTION" value="sqlite"/>` (or `:memory:`) while prod uses MySQL/PostgreSQL → `Inadequate` regardless of case count.

**Lint gate.** `vendor/bin/pint --test` and `composer phpstan` (Larastan L5+) must be clean OR Step 0a must address them. Values: `clean` / `warnings present (Step 0a)` / `not run (no baseline)`.

**Octane / shared-state check.** If the target holds mutable state via `static`, registers as singleton capturing request data, or stores per-request context in a non-scoped binding, confirm cross-request leakage tests exist. If absent and the project uses (or plans to use) Octane / FrankenPHP / RoadRunner, drop coverage one tier.

Do not proceed past Step 5 if `Inadequate`.

### Step 5 - Identify Laravel Smells

Signals, not hard rules. Format: `Smell - signal. Risk.`

**Controller**

- Fat Controller - action > 30 lines of orchestration. High
- Logic in Controller - business rules / calculation in the action. High
- Direct Eloquent - bypassing services (OK for trivial CRUD). Medium
- Eloquent Model Returned - leaks `password`, `remember_token`, soft-delete cols. High
- Inline Validation - re-checks rules already in Form Request. Low
- Per-action `try/catch` - inline error mapping vs `bootstrap/app.php` `withExceptions`. Medium
- Missing `auth:` middleware - route group lacks auth. High
- Missing Policy / `$this->authorize` - owner-data action without authz. High
- `$request->all()` Mass Assignment. High

**Form Request**

- Missing Form Request - inline `$request->validate([...])`. Medium
- `authorize()` returns `true` - default-allow on user-data endpoint. High
- Privilege Field in `rules()` - `role`, `is_admin`, `user_id` exposed. High
- Identity Field in `rules()` - `id` exposed; cache-poisoning. High

**Service / Action**

- God Service - `*Service.php` > 500 lines mixing concerns. High
- Anemic Domain - `OrderService::calculateTotal($order)` that belongs as `$order->total()`. Medium
- Single-Implementation Interface - no mocks, no second impl. Medium
- Repository Over Eloquent - `findById($id) { return Order::find($id); }`. Medium
- Container Lookup in Business Code - `app(...)` / `resolve(...)`. Medium
- External I/O Inside Transaction - `Http::post(...)` / `dispatch(...)` inside `DB::transaction(...)` without `afterCommit`. High
- Multiple `save()` per Use Case - >1 `$model->save()` outside a transaction. High
- `null` from Failure-Capable Op - caller can't distinguish validation vs not-found. Medium

**Persistence / Eloquent**

- `$guarded = []` on Model - opens every column. Critical (with `$request->all()`) / High
- Missing `$fillable` - relies on `$guarded` defaults. Medium
- N+1 Lazy Loading in Blade - `@foreach ($orders ...) {{ $order->user->name }}` without upstream `with('user')`. High
- N+1 via Per-Iteration `find()`. High
- Multi-Relation Eager Load - `with(['items','shipments','history','invoices'])`. Medium
- `Model::all()` on Growable Table. High
- `whereRaw($input)` - raw SQL via string interpolation. Critical
- `orderByRaw($request->input('sort'))` - user-supplied column without allowlist. Critical
- Long-Running Transaction - `DB::transaction(...)` containing `Http::post(...)`. High
- Missing FK `->constrained()` - new FK column without `onDelete`. Medium
- Eloquent as Domain + DTO. Medium

**Configuration / DI**

- `env()` Outside Config - breaks `config:cache` (returns null in prod). High
- Hardcoded Defaults Inline - rather than `config()`. Medium
- Singleton Capturing Request State - leaks under Octane. High (Octane) / Medium
- Static Mutable State - `static $cache = []` mutated by handlers. High (Octane) / Medium
- New `Client(...)` Per Request - defeats keep-alive. Medium

**Queue / Job**

- Job Constructor Takes Eloquent - `new ProcessPayment($order)`. High
- Dispatched Inside Transaction - without `->afterCommit()`. High
- Missing `$tries`/`$backoff`/`$timeout`. High
- Missing `failed(Throwable $e)`. Medium
- Not Idempotent - `handle()` re-runs side effects when delivered twice. High
- `QUEUE_CONNECTION=sync` in Prod. Critical

**Tests (when refactor brings tests into scope)**

- SQLite for MySQL/PostgreSQL App. High
- `Queue::fake` masking `handle()`. Medium
- Copy-Paste `it(...)` / `test_*` - cases where Pest `with(...)` / `@dataProvider` would do. Low
- `dd()` / `dump()` left in tests. Low

**General OO.** Use skill: `backend-coding-standards` for cross-language catalog. Use skill: `complexity-review` for over-engineering simplification.

**Atomic skill composition.** Cite the matching skill in the relevant step.

| Signal in target                                                                                                       | Atomic skill                  |
| ---------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| N+1, `Model::all()` on growable, `paginate()` on huge tables, `$with` over-fetch                                       | `laravel-eloquent-patterns`   |
| Fat controller, anemic service, missing API Resource / Form Request, response-shape leak                               | `laravel-api-patterns`        |
| Job ctor takes Eloquent, missing `afterCommit`, missing tries/backoff/timeout, idempotency, `WithoutOverlapping`       | `laravel-queue-patterns`      |
| God service, missing action/service extraction, event-driven side effects, listener-vs-direct-call                     | `laravel-service-patterns`    |
| `$guarded = []`, `Model::create($request->all())`, `whereRaw($input)`, IDOR, missing `$this->authorize`                | `laravel-security-patterns`   |
| Migration touched by recipe (rename / drop / NOT NULL on hot table)                                                    | `laravel-migration-safety`    |

### Step 6 - Cross-Module Risk Assessment

Use skill: `review-blast-radius`. Laravel-specific signals: public API surface used by external clients; Composer-package boundary; interface with broad implementer surface; singleton consumed by many downstream services; Eloquent model used in many queries / Resources / jobs; Form Request reused across endpoints; exported `public` symbol in a published Laravel package.

State: **Narrow** (single file, single caller) / **Moderate** (single namespace, multiple callers) / **Wide** (cross-namespace, public action API, broad interface) / **Critical** (Composer-published, model used by 5+ consumers).

### Step 7 - Propose the Step Sequence

Each step: **independently committable** (`php artisan test` + `composer phpstan` + `vendor/bin/pint --test` pass after), **behaviorally invariant** unless labeled `coupled-fix`, **reversible** in one revert, **tested**.

**Recipe interleaving.** Multiple applicable recipes do not concatenate. Identify the **primary** recipe (usually the user's goal), use it as the spine, fold supporting recipes in as sub-steps. State `Primary recipe:` explicitly. Past ~8 steps, split into two PRs.

**Coupled-fix.** When a refactor genuinely depends on a behavior change, label the step `coupled-fix` with its own test gate and rationale.

**Per-step stances** (state every step):

- **Transaction stance:** `inside caller's transaction` / `post-commit via ->afterCommit()` / `not transactional`
- **Mass-assignment stance:** `no change` / `$request->all() → $request->validated()` (cascading) / `$fillable replacing $guarded = []` / `unchanged`
- **Container stance:** `no change` / `bind` / `singleton` / `scoped` (L11+) / `static replaced with DI`
- **Queue stance:** `no change` / `introduces dispatch` (afterCommit + tries/backoff/timeout/failed + scalar ID + idempotency required) / `scalar-ID ctor` / `adds idempotency guard`

**Common Laravel refactor recipes:**

**Extract action / service from fat controller.** (1) Add `app/Actions/<Feature>/PlaceOrderAction.php` (or `app/Services/OrderService.php`); copy orchestration. (2) Unit test parameterized over success / validation failure / external failure. (3) Controller injects + delegates: `$this->placeOrder->execute($request->validated())`; preserve response shape. (4) Remove original logic; feature tests pass. (5) Feature test asserting action failure surfaces via centralized exception handler.

**Eliminate mass assignment via `$guarded = []` and `$request->all()`.** (1) Identify: `class Order { protected $guarded = []; }` + `Order::create($request->all())`. (2) Replace with explicit `$fillable` - never `user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`. (3) Add Form Request with `authorize()` + `rules()`. (4) Bind: `public function store(StoreOrderRequest $request)`; explicit assignment plus server-set fields:
```php
$order = (new Order)->fill($request->validated());
$order->user_id = $request->user()->id;
$order->status = OrderStatus::Pending;
$order->save();
```
(5) Feature test injecting `user_id` / `role`; assert stripped (or 422). (6) Audit other unsafe bindings.

**Eliminate Eloquent N+1 in Blade / API Resource.** (1) Identify lazy relation in `@foreach` or Resource `toArray()`. (2) Add `with(...)` upstream: `Order::with(['user', 'items'])->cursorPaginate(25)`. (3) Enable `Model::shouldBeStrict()` in `AppServiceProvider::boot` so remaining lazy loads throw in dev.

**Move side effects out of an open DB transaction.** When `Http::post(...)`, `Mail::send(...)`, or `dispatch(...)` runs inside `DB::transaction(...)`, side effect can fire before commit or hold the DB connection. Pick one option; do not stack.

*Option A: Post-commit via `->afterCommit()`* (default). (1) Move side effect out of transaction body; capture inputs, exit, dispatch. (2) Jobs: `dispatch((new ProcessPayment($order->id))->afterCommit())`, or `public bool $afterCommit = true;` on the job. (3) Raw HTTP / mail: capture inputs in locals inside the transaction; run after `DB::transaction(...)` returns. (4) Risk: if the side effect must run before commit (rare), use Option B.

*Option B: Transactional outbox* (when delivery must be exactly-once-after-commit: financial events, audit-required). (1) Add `outbox_messages` table; index `(processed_at, created_at)`. (2) In the same transaction as the business row, `OutboxMessage::create([...])`. (3) Relay (`Schedule::command('outbox:relay')->everyMinute()->withoutOverlapping()->onOneServer()`): select unprocessed, dispatch, mark `processed_at`. Consumer-side idempotency still required.

**Convert job to scalar IDs and `->afterCommit()`.** (1) Identify: `dispatch(new ProcessPayment($order))` with `public function __construct(public Order $order)`. (2) Scalar ctor: `public function __construct(public int $orderId) {}` and `handle(PaymentService $s) { $s->charge(Order::findOrFail($this->orderId)); }`. (3) Dispatch: `dispatch((new ProcessPayment($order->id))->afterCommit())`. (4) Add `$tries`, `$backoff`, `$timeout`, `failed()`. (5) Job test: real `handle()`, idempotency (twice → one side effect), retry, `failed()` invocation.

**Eliminate single-implementation interface.** (1) Confirm no Mockery mock, no second impl, no DI lifetime / decoration need. (2) Consumers use the concrete class. Delete the interface. **Skip if** part of a public API (Composer package) or has a real second impl / mock.

**Replace repository-over-Eloquent with direct Eloquent.** (1) Identify: `class OrderRepository { public function findById(int $id): ?Order { return Order::find($id); } }`. (2) Callers use `Order::find($id)` directly. (3) Delete the class; remove the binding. **Skip if** the repository abstracts non-Eloquent storage or has multiple impls.

**Replace mapper with API Resource.** (1) Identify: `class OrderMapper { public function toResponse(Order $order): array { ... } }`. (2) Replace with `OrderResource extends JsonResource`. (3) Controller: `return OrderResource::make($order);`. (4) Delete mapper + bindings.

**Eliminate `env()` outside config files.** (1) Identify: `env('STRIPE_KEY')` in service/controller/job. (2) Add to `config/services.php`. (3) Replace call with `config('services.stripe.key')`. (4) Verify `php artisan config:cache` works.

**Replace `new GuzzleHttp\Client()` with shared / `Http::*`.** (1) Identify per-request construction. (2) Use `Http::get($url)` (shared handler / connection pool). (3) `Http::timeout(5)->retry(3, 100)->get($url)` per call. (4) SDK-required Guzzle: bind singleton.

**Replace mutable static state with constructor-injected service.** (1) Identify: `class OrderCache { private static array $cache = []; ... }`. (2) Convert to instance + `app()->singleton(OrderCache::class)`. For per-request scope, `app()->scoped(...)` (L11+) so binding resets between requests under Octane. (3) Consumers receive `OrderCache` via constructor. (4) Cross-request isolation test (fresh request → empty cache).

**Make queue job idempotent.** (1) Job test: same payload twice → side effect once (different `job_id`, same business key). (2) Idempotency guard in `handle()`: dedup table on business key, or `Cache::add($key, true, $ttl)` (atomic), or unique constraint + upsert. (3) Verify retries on transient failures still complete. (4) Configure `$tries`, `$backoff`, `failed()`; add `retryUntil()` for time-bounded jobs.

### Step 8 - Validate Plan Against Goal

Goal achieved at end of sequence; each step reviewable in < 30 minutes; test gate runs between every step; steps ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes); rollback is one revert per step; no bundled "while we're here" cleanup.

## Output Format

```markdown
## Laravel Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Laravel refactor recipes"]
**Stack:** PHP <version> / Laravel <version>
**ORM:** Eloquent | Query Builder
**Queue:** redis (Horizon) | database | sync
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Tests Framework:** Pest | PHPUnit

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Lint state:** clean | warnings present (Step 0a) | not run (no baseline)
**Octane / shared-state coverage:** clean | not exercised cross-request | n/a

[Adequate: one sentence on boundary cases. Thin: list missing boundaries; Step 0 covers them. Inadequate: state required coverage; recommend `task-laravel-test`. **Stop here** - omit Blast Radius, Step Sequence, Verification. May still emit **Smells Identified**, **Sibling Smells**, and **Coverage prerequisite list** as preview-only.]

**Coverage prerequisite list shape (Thin or Inadequate).** One row per public entry point: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure (422), authorization denial (401/403), not-found / IDOR, external-collaborator failure, mass-assignment (privileged field stripped), and (under Octane with static state) cross-request isolation. Example: `POST /api/orders | privileged user_id field stripped | feature test`.

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file this plan does NOT address. Omit if none._

| Smell   | Location  | Why deferred                                            | Recommended follow-up                                       |
| ------- | --------- | ------------------------------------------------------- | ----------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / security / perf] | [`task-laravel-review-security` / `task-laravel-refactor`]  |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_

- **Change:** add missing boundary tests
- **Risk:** Low
- **Test gate:** new tests pass; suite green; `vendor/bin/pint --test` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if pint/PHPStan clean)_

- **Change:** address pint / PHPStan warnings on the target
- **Risk:** Low
- **Test gate:** pint + PHPStan clean; `php artisan test` green
- **Rollback:** revert the lint fixes

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [tests + pint + PHPStan clean]
- **Transaction stance:** [inside caller's transaction | post-commit via `->afterCommit()` | not transactional]
- **Mass-assignment stance:** [no change | `$request->all() → $request->validated()` (cascading) | `$fillable` replacing `$guarded = []` | unchanged]
- **Container stance:** [no change | `bind` | `singleton` | `scoped` (L11+) | static replaced with DI]
- **Queue stance:** [no change | introduces `dispatch` (afterCommit + tries/backoff/timeout/failed needed) | scalar-ID ctor | adds idempotency guard]
- **Rollback:** [one git revert]

### Step 2 - [Action verb + noun]

[Same structure. `Step kind: coupled-fix` for any step intentionally changing behavior; state why coupling is structural.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] `php artisan test` + `composer phpstan` + `vendor/bin/pint --test` clean between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback is one revert per step

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

- [ ] **Step 1** - `behavioral-principles` loaded
- [ ] **Step 2** - Stack confirmed; ORM/queue/auth/test framework recorded; input completeness check ran
- [ ] **Step 3** - Target file(s) and matching tests read; sibling smells listed; severity-inversion banner rendered when applicable
- [ ] **Step 4** - Coverage gate evaluated; plan refused if `Inadequate`; happy-path-only and SQLite-for-MySQL-app treated as `Inadequate`; Octane shared-state check applied; lint state recorded
- [ ] **Step 5** - Smells identified using the catalog; relevant atomic skills consulted per composition table
- [ ] **Step 6** - Blast radius stated before proposing steps
- [ ] **Step 7** - `Primary recipe:` named; per-step stances stated; `Step kind: coupled-fix` with rationale where behavior changes; steps ordered low-risk first; plan ≤ ~8 steps or split; Step 0 included if `Thin`; Step 0a included if lint not clean
- [ ] **Step 8** - Goal explicitly mapped to end state of the sequence

**Execution-time gates (commitments to the implementer):**

- [ ] `php artisan test` passes between every step
- [ ] `composer phpstan` clean for any step
- [ ] `vendor/bin/pint --test` clean for any step
- [ ] Each step independently committable
- [ ] Rollback is one revert per step

## Avoid

- Refactoring without a test-coverage gate - that's a rewrite
- Bundling behavior changes with refactoring steps
- "While we're here" unrelated cleanup
- Renaming during a refactor (separate PR)
- Refactoring exported `public` symbols in a Composer package without a backward-compatibility plan
- Moving I/O across a `DB::transaction(...)` boundary without stating the transaction stance
- Partial `$request->all()` → `$request->validated()` conversion
- Consolidating services into a singleton without checking what state they capture
- Replacing static mutable state with `$_SESSION` / `Cache::*` carrying the same data globally
- Replacing `$guarded = []` with another `$guarded = []` - introduce Form Request + `$fillable`
