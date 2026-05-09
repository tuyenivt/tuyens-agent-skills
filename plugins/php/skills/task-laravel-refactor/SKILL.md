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

Produce a safe, step-by-step refactoring plan for a specific Laravel target (Controller action, Form Request, Eloquent model, Service, Action, Job, Listener, Policy, scheduled command, API Resource). Identifies Laravel-specific smells (fat controller with business logic, anemic services that just `$model->save()`, god classes, mass assignment via `$guarded = []` or `Model::create($request->all())`, missing Form Request validation, Eloquent N+1 via lazy loading in Blade / Resources / loops, `Include` cartesian explosion via multi-relation eager-load, missing `with()`, `Model::all()` on growable tables, jobs accepting Eloquent model instances in constructors, jobs dispatched inside transactions without `afterCommit`, missing `$tries` / `$backoff` / `$timeout` / `failed()` on jobs, single-implementation interfaces, repository-over-Eloquent for trivial reads, AutoMapper-style mappers when API Resources do the job, MediatR-style indirection in PHP via custom buses, `env()` outside config files breaking `config:cache`, secrets in `.env.example`, raw Eloquent model returned from controllers instead of API Resources, mutable static class state foot-gunning Octane, queue connection `sync` in production, missing rate limiting on auth, `whereRaw($input)` SQL injection / plan-cache pollution) and proposes independently-committable refactoring steps with `php artisan test` + `composer phpstan` + `vendor/bin/pint --test` gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for PHP / Laravel.

## When to Use

- Laravel code-smell identification and resolution
- Laravel technical-debt reduction with a concrete plan
- Safe refactoring of a controller / service / job / Policy / API Resource / model
- Pre-merge "this PR grew the fat-controller / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-laravel-implement`)
- Architecture-level restructuring across many packages (use `task-design-architecture`)
- Bug fixes / exception investigations (use `task-laravel-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                                  |
| --------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Target scope          | Yes         | File or class to refactor (e.g., `app/Http/Controllers/OrderController.php`, `app/Jobs/ProcessPayment.php`, `app/Services/OrderService.php`)                  |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `placeOrder` action into a Service, eliminate mass assignment, split `OrderService` god class)            |
| Test coverage status  | Recommended | Whether Pest / PHPUnit feature / unit / job coverage exists for the target area; whether `composer phpstan` / `vendor/bin/pint --test` is clean              |
| Shared/public surface | Recommended | Whether the target is `public` across package / Composer-published-package boundaries                                                                                     |

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every step that follows (think before acting, simplicity first, surgical changes, surface confusion, push back when the user is likely wrong). Do not skip - downstream steps assume these constraints are in scope.

### Step 2 - Confirm Stack and Detect ORM / Queue / Auth Surface

Use skill: `stack-detect` to confirm PHP / Laravel. If invoked as a subagent of a Laravel-aware parent, accept the pre-confirmed stack. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-refactor` instead.

Detect ORM (Eloquent / query builder), queue (Redis with Horizon / database / sync), auth (Sanctum / Passport / session), test framework (Pest / PHPUnit). Record `ORM`, `Queue`, `Auth`, `Tests Framework` for the output.

**Input completeness check.** Before proceeding, confirm the user named both a **target scope** (file or class) AND a **goal**. If only a goal is given (e.g., "extract the fat controller logic" without naming the controller), ask for the target. Do not guess from recent git history or the largest controller in the project - the user knows which one they meant; you do not.

### Step 3 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target file top-to-bottom; note method count, longest method, transaction placement (`DB::transaction(...)`, explicit `$model->save()` chains), every external collaborator (`Http::*`, `Event::dispatch`, `dispatch(...)`, `Mail::to(...)->send(...)`, `Notification::send(...)`)
2. Read the matching test file(s) (`tests/Feature/<Feature>/<Class>Test.php`, `tests/Unit/<Feature>/<Class>Test.php`); count cases by outcome (happy path, validation failure, external failure, auth denial). Confirm `composer phpstan` / `vendor/bin/pint --test` runs clean (or note it doesn't)
3. If callers are obvious (controller calling the service, scheduled command calling the job), read the immediate caller too - removing or reshaping a `public` member without seeing call sites is how silent breakage happens

If the user named only the goal without a target file / class, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat classes. If the file containing the target also contains other smells (e.g., the user names `placeOrder` but the same controller file has IDOR in `getOrder` and `whereRaw($input)` in `searchOrders`), do **not** action them in this plan and do **not** ignore them silently. List them under a `Sibling Smells (Out of Scope)` heading in the output, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-laravel-review-security`), and recommend follow-up invocations.

**Severity-inversion rule.** When any sibling smell is *higher severity* than the named primary target (e.g., the user asks to extract a fat controller, but the same file contains a working SQL injection via `whereRaw("col = '$input'")`, an `exec($userInput)` RCE, an authentication bypass, or `unserialize($userInput)` on untrusted input), recommend pausing the refactor and routing the security finding first. State this prominently in the `Sibling Smells (Out of Scope)` table's `Recommended follow-up` column with phrasing like `Fix before refactor: invoke task-laravel-review-security on this file; refactor PR should branch off the security fix, not main`. The refactor skill produces a plan; it does not silently let an in-scope severe finding land via a refactor PR that doesn't address it.

**Severity-inversion banner.** When the inversion rule fires, **also render a one-paragraph banner at the top of the Coverage Gate section** (above the status verdict) so the inversion is impossible to skim past. Suggested form: `> **Severity inversion detected.** This file contains <N> sibling smells of higher severity than the named target (<list>). Recommended next action: pause this refactor; route through task-laravel-review-security first; branch the eventual refactor PR off the security fix.`

### Step 4 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (Pest / PHPUnit feature tests, unit tests, job tests, Policy tests), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                   | What the workflow does                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., validation failure, auth denial, external failure, not-found) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                               | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                        | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-laravel-test` first            |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves validation, authorization, or error behavior - you would be flying blind.

**Wrong-store disqualifier.** When `phpunit.xml` carries `<env name="DB_CONNECTION" value="sqlite"/>` (or `:memory:`) but the production `.env` (or `config/database.php`'s default) uses MySQL/PostgreSQL, treat coverage as `Inadequate` regardless of case count. The provider mismatch means the cases test a different store than prod (SQLite skips FK enforcement, JSON path queries, fulltext, concurrent updates) - adding more boundary cases on top of the wrong store does not unlock the refactor. The Step 0 prerequisite must include migrating the affected tests to real MySQL/PostgreSQL before refactor begins.

**Lint-gate check.** `vendor/bin/pint --test` (Laravel's official code style fixer) must be clean for the target, AND `composer phpstan` (Larastan at level 5+) must be clean, OR the refactor plan must include cleaning warnings as Step 0a. Refactoring on top of unaddressed warnings risks masking new warnings behind existing ones. Lint state values: `clean` (pint and PHPStan clean), `warnings present` (Step 0a covers them), or `not run (no baseline)` (greenfield / net-new project where pint / PHPStan enforcement hasn't been wired into CI yet - the plan's first step folds it into the coverage prerequisite work).

**Octane / shared-state check.** If the target class holds mutable state via `static` properties, registers as a singleton via `app()->singleton(...)` capturing request data, or stores per-request context in a non-scoped binding, also confirm that tests cover the cross-request leakage scenario. If absent and the project uses (or plans to use) Octane / FrankenPHP / RoadRunner, treat coverage status as one tier worse (Adequate → Thin, Thin → Inadequate) - refactoring stateful code under long-running workers without explicit isolation tests is unsafe.

**Output of this step:** explicit coverage status using one of the three labels above. Do not proceed past Step 5 (smell identification preview) if status is `Inadequate`.

### Step 5 - Identify Laravel Smells

Inspect the target for these Laravel-specific smells. Use judgment - these are signals, not hard rules.

**Controller smells:**

| Smell                                   | Signal                                                                                                                                                                                              | Risk   |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Controller                          | Action method > 30 lines of orchestration (multiple service calls, conditional dispatch, response shaping, business rules)                                                                          | High   |
| Logic in Controller                     | Business rules, validation beyond Form Request `rules()`, calculation, or domain decisions inside the action                                                                                        | High   |
| Direct Eloquent in Controller           | Action method does `Order::where(...)->get()`, bypassing service / repository layer (acceptable for trivial CRUD; smell on multi-step orchestration)                                                | Medium |
| Eloquent Model Returned from Action     | Action returns `$user` or `$order` directly (mass-assignment + leak risk: leaks `password`, `remember_token`, `two_factor_secret`, soft-delete columns)                                              | High   |
| Manual Validation Duplicating Form Request | Action body re-checks `if (! $request->has('email')) ...` already covered by Form Request rules                                                                                              | Low    |
| Per-action `try { ... } catch { return response()->json([...], 500); }` | Inline error mapping scattered across actions instead of centralized exception handler (`bootstrap/app.php` `withExceptions(...)` rule)                  | Medium |
| Missing `auth:` middleware              | Route group lacks `auth:sanctum` / `auth` middleware - relies on per-action checks, which break silently on new endpoints                                                                          | High   |
| Missing `$this->authorize` / Policy     | Owner-data action lacks Policy enforcement; relies on `auth:` only (auth ≠ authz)                                                                                                                  | High   |
| Mass Assignment via `$request->all()`   | Controller calls `Model::create($request->all())` or `update($request->all())` - bypasses validation discipline; even with `$fillable`, this opens future fillable changes as silent attack surface | High   |

**Form Request smells:**

| Smell                                   | Signal                                                                                                                                                              | Risk   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Missing Form Request                    | Controller action validates inline via `$request->validate([...])` instead of injecting a typed Form Request                                                       | Medium |
| `authorize()` Returns `true`            | Form Request's `authorize()` returns `true` (default) on a user-data endpoint - silently default-allow                                                              | High   |
| Privilege Field in `rules()`            | `'role' => 'required|string'`, `'is_admin' => 'boolean'`, `'user_id' => 'integer'` exposed to client input                                                          | High   |
| Identity Field in `rules()`             | `'id' => 'integer'` lets the client control the row id - cache-poisoning surface                                                                                    | High   |

**Service / Action smells:**

| Smell                              | Signal                                                                                                                                                                          | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Service Class                  | `*Service.php` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                                                                             | High   |
| Anemic Domain                      | Eloquent models are pure data containers; business rules live in services with names like `OrderService::calculateTotal($order)` and could belong as instance methods on `Order` | Medium |
| Single-Implementation Interface    | `OrderRepositoryInterface` + single `EloquentOrderRepository` implementation with no Mockery mock and no second implementation - the interface adds nothing                     | Medium |
| Repository Over Eloquent for Trivial Reads | `OrderRepository::findById($id)` that just calls `Order::find($id)` - Eloquent already abstracts storage                                                                  | Medium |
| Container Lookup in Business Code  | `app(OrderService::class)` or `resolve(...)` inside a service - bypasses constructor injection's compile-time dependency contract                                              | Medium |
| External I/O Inside Transaction    | `Http::post(...)` or `dispatch(...)` inside `DB::transaction(...)` (defers commit, holds DB locks long, races worker pickup before commit if no `afterCommit`)               | High   |
| Multiple `save()` Per Use Case     | Service calls `$model->save()` more than once outside a transaction - splits atomicity, partial state visible                                                                  | High   |
| Returning `null` from Failure-Capable Operation | Service returns `?Model`; caller cannot distinguish failure cases (validation vs not-found vs external) - throw domain exceptions or return a typed Result               | Medium |
| Floating `dispatch` / `Bus::dispatch` | Fire-and-forget `dispatch(new SomeJob)` in a service body without after-commit guarantee in transactional contexts                                                          | High   |

**Persistence / Eloquent smells:**

| Smell                                        | Signal                                                                                                                                                                                                          | Risk   |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `$guarded = []` on Model                     | Opens every column to mass assignment via `Model::create($request->all())` or `update($request->all())`                                                                                                         | Critical (when used with `$request->all()`) / High (otherwise)   |
| Missing `$fillable` Whitelist                | No explicit whitelist; relies on `$guarded` defaults                                                                                                                                                            | Medium |
| Eloquent N+1 via Lazy Loading in Blade       | `@foreach ($orders as $order) {{ $order->user->name }} @endforeach` without `Order::with('user')` upstream                                                                                                      | High   |
| N+1 via Per-Iteration `find()`               | `foreach ($parents as $parent) { $child = Child::where('parent_id', $parent->id)->first(); }` - N round-trips                                                                                                  | High   |
| Multi-Relation Eager Load                    | `Order::with(['items', 'shipments', 'history', 'invoices'])->get()` materializes one query per relation; consider join-style flat read or scoped projection                                                    | Medium |
| `Model::all()` on Growable Table             | Returns full table without `chunk` / `lazy` / `cursor` / `paginate`                                                                                                                                            | High   |
| `whereRaw($input)` SQL Injection             | Raw SQL built via string interpolation instead of bindings or Eloquent query builder                                                                                                                            | Critical |
| `orderByRaw($request->input('sort'))`        | User-supplied sort column without allowlist                                                                                                                                                                     | Critical |
| Long-Running Transaction Holding Connection  | `DB::transaction(fn () => ...)` followed by `Http::post(...)` inside before any commit - holds connection for network roundtrip                                                                                | High   |
| Missing FK `->constrained()`                 | New FK column in migration without `->constrained()` and `onDelete` policy                                                                                                                                     | Medium |
| Eloquent Used as Domain / DTO Type           | Service / controller imports the Eloquent model and uses it as the domain type AND the API response type - couples upper layers to schema and triggers lazy-loaded navigations                                  | Medium |

**Configuration / DI smells:**

| Smell                        | Signal                                                                                                                                                              | Risk   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `env()` Outside Config       | `env('STRIPE_KEY')` inside controllers / services / jobs - breaks `config:cache` (returns null in prod)                                                            | High   |
| Container Lookup in Business Code | `app(...)` / `resolve(...)` / `App::make(...)` inside a service / controller / job - bypasses constructor injection                                            | Medium |
| Hardcoded Defaults Inline    | Default values inline in code rather than `config()`                                                                                                                | Medium |
| Single-Implementation Interface | Interface defined for a single concrete type with no Mockery mock and no second implementation                                                                   | Medium |
| Singleton Capturing Request State | `app()->singleton(...)` whose closure captures `request()` / `auth()->user()` / current tenant - leaks across requests under Octane / FrankenPHP                | High (under Octane) / Medium (otherwise) |
| Static Mutable State         | `static $cache = []` / `private static $things` mutated by request handlers - leaks across requests in long-running workers (Octane / Swoole)                      | High (under Octane) / Medium (otherwise) |
| New `Client(...)` Per Request | `new \GuzzleHttp\Client(...)` instantiated per request - defeats keep-alive; bind as singleton via container                                                       | Medium |

**Queue / Job smells:**

| Smell                                      | Signal                                                                                                                                                  | Risk   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Job Constructor Takes Eloquent Model       | `new ProcessPayment($order)` - serializes a snapshot of the model into queue payload; pass `$order->id` and re-fetch in `handle()`                      | High   |
| Job Dispatched Inside Transaction          | `DB::transaction(fn () => dispatch(new ProcessPayment($id)))` without `->afterCommit()` - worker may pick up message before commit                      | High   |
| Missing `$tries` / `$backoff` / `$timeout` | Defaults are unbounded retries plus a 60s timeout - runaway failure cascade                                                                              | High   |
| Missing `failed(Throwable $e)`             | No notification on permanent failure - DLQ-bound jobs are invisible                                                                                     | Medium |
| Not Idempotent                             | `handle()` re-runs side effects when delivered twice (no dedup, no upsert, no state check)                                                              | High   |
| `QUEUE_CONNECTION=sync` in Prod            | Inline execution defeats every queue guarantee                                                                                                           | Critical |

**Test smells (when refactoring brings tests into scope):**

| Smell                                       | Signal                                                                            | Risk   |
| ------------------------------------------- | --------------------------------------------------------------------------------- | ------ |
| SQLite for MySQL / PostgreSQL App           | `phpunit.xml` `<env DB_CONNECTION>` is `sqlite` while prod is MySQL/PostgreSQL    | High   |
| `Queue::fake` Masking `handle()` Test       | Job test only asserts dispatch; never runs `handle()`                             | Medium |
| Copy-Paste `it(...)` / `test_*` Methods     | Multiple near-identical cases where Pest `with(...)` / PHPUnit `@dataProvider` would do | Low    |
| `dd()` / `dump()` Left in Test File         | Leaks in test output; `phpunit.xml` may not catch it                              | Low    |

**General OO smells (apply with Laravel judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl interfaces, abstract base classes for two consumers, premature factory / strategy, redundant mapping layers, repository-for-trivial-reads, AutoMapper-style mappers when API Resources do the job) - those are simplification opportunities, not refactor steps to extract more abstractions.

**Atomic skill composition.** Consult these atomic skills when the corresponding signal is present in the target, then cite the recommendation in the relevant step. Do not paste their content verbatim - reference them by name so the implementer can re-derive the canonical guidance.

| Signal in target                                                                                                          | Atomic skill                  |
| ------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| Eloquent N+1, `Model::all()` on growable, `paginate()` on huge tables, `$with` over-fetch                                | `laravel-eloquent-patterns`   |
| Fat controller, anemic service, missing API Resource, missing Form Request, response-shape leak                           | `laravel-api-patterns`        |
| Job constructor takes Eloquent, missing `afterCommit`, missing tries/backoff/timeout, idempotency gaps, `WithoutOverlapping` | `laravel-queue-patterns`      |
| God service, missing action / service layer extraction, event-driven side effects, listener-vs-direct-call decisions      | `laravel-service-patterns`    |
| `$guarded = []`, `Model::create($request->all())`, `whereRaw($input)`, IDOR, missing `$this->authorize`                  | `laravel-security-patterns`   |
| Migration touched by recipe (rename / drop / NOT NULL on hot table)                                                       | `laravel-migration-safety`    |

Apply Laravel judgment - a 25-line controller orchestrating clearly named private methods is fine; a 10-line method doing three unrelated things is not.

### Step 6 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected by the refactor.

Laravel-specific blast-radius signals:

- [ ] **Public API surface**: target is a controller action used by external clients - refactor risks API contract change
- [ ] **Composer-package boundary**: target is in a package consumed by other apps via `composer require`, or in a Laravel package the team publishes
- [ ] **Interface with broad implementer surface**: refactoring an interface connected to many implementations / consumers cascades
- [ ] **Service registered as singleton**: target is bound via `app()->singleton(...)` and consumed by many downstream services - signature changes cascade
- [ ] **Eloquent model used in many queries / Resources / jobs**: refactoring a model affects every consumer
- [ ] **Form Request reused across endpoints**: rule changes cascade into every dependent endpoint and its tests
- [ ] **Exported `public` symbol in a published Laravel package**: refactoring means every importer breaks

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single namespace, multiple callers) / **Wide** (cross-namespace, public action API, broad interface) / **Critical** (Composer-published package, model used by 5+ consumers).

### Step 7 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase passes `composer install`, `php artisan test`, `composer phpstan`, and `vendor/bin/pint --test` after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`, see below)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing test suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target (e.g., a fat controller that also has `$guarded = []`, `Model::create($request->all())`, and stashes a `DB::connection` in a static field), do **not** concatenate the recipes - that produces a 25-step plan mixing concerns. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs rather than one mega-plan.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a service that derives `tenant_id` from `auth()->user()` _requires_ the caller to be authenticated, so adding `auth:` middleware to the route is a structural prerequisite). Label the step `coupled-fix` in the Output Format with its own test gate and rationale.

**Transaction-boundary watch.** When extracting orchestration that runs inside `DB::transaction(fn () => ...)`, the extracted unit may inherit the transaction context if invoked via the same connection. If the extracted code makes HTTP calls, dispatches jobs, or sends mail, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's transaction" or "callee uses post-commit dispatch (capture inputs, dispatch via `->afterCommit()` after the transaction returns)." Never silently move I/O across a transaction boundary.

**Mass-assignment-stance watch.** When restructuring code that calls `Model::create($request->all())` or has `$guarded = []`, state the new fillable contract explicitly. The fix is a request DTO record / Form Request validated payload + explicit field assignment + `$fillable` whitelist. Do not partially convert (some fields explicit, others still flowing through `$request->all()`) - that's just a different mass-assignment surface. State whether the conversion is local (this controller only) or cascading (every controller using the model).

**Container-binding watch.** When refactoring service registration, state whether the new lifetime is correct. `app()->bind(...)` (transient: new instance per resolve) vs `app()->singleton(...)` (one instance for the app lifecycle - dangerous under Octane if state captures request data) vs scoped. A refactor that consolidates services into a singleton must explicitly check what it captures.

**Queue-stance watch.** Adding job dispatch from within transactions, scheduled commands, or HTTP callbacks introduces work outside the request lifecycle. State whether `->afterCommit()` is needed (yes when inside a transaction), whether `$tries` / `$backoff` / `$timeout` / `failed()` are set (always yes for new jobs), whether the job is idempotent (always yes for jobs with side effects), and whether it accepts scalar IDs (never Eloquent models in constructors).

**Common Laravel refactor recipes:**

**Recipe: Extract action / service from fat controller**

1. Add `app/Actions/<Feature>/PlaceOrderAction.php` (or `app/Services/OrderService.php`) implementing the orchestration logic; copy from controller; controller still does the original work
2. Add `tests/Unit/Actions/<Feature>/PlaceOrderActionTest.php` with parameterized tests covering one case per outcome (success, validation failure, external failure)
3. Update controller to inject the action via constructor and delegate (`$this->placeOrder->execute($request->validated())`); preserve response shape; ensure feature tests pass unchanged
4. Remove the original logic from the controller; verify feature tests pass
5. Add a feature test asserting action failure surfaces as the expected error response (likely via centralized exception handler)

**Recipe: Eliminate mass assignment via `$guarded = []` and `$request->all()`**

1. Identify the unsafe model + controller: `class Order extends Model { protected $guarded = []; }` + `Order::create($request->all())`
2. Replace `$guarded = []` with explicit `$fillable`: `protected $fillable = ['shipping_address', 'notes', 'items'];` listing exactly the user-supplied columns; no `user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`
3. Add a Form Request with explicit `rules()` and `authorize()`:
   ```php
   class StoreOrderRequest extends FormRequest
   {
       public function authorize(): bool
       {
           return $this->user()->can('create', Order::class);
       }

       public function rules(): array
       {
           return [
               'shipping_address' => ['required', 'string', 'max:500'],
               'notes' => ['nullable', 'string', 'max:1000'],
               'items' => ['required', 'array', 'min:1'],
               'items.*.product_id' => ['required', 'integer', 'exists:products,id'],
               'items.*.quantity' => ['required', 'integer', 'min:1'],
           ];
       }
   }
   ```
   No `user_id`, `role`, `is_admin`, etc.
4. Replace the controller binding: `public function store(StoreOrderRequest $request)`; map to the model with explicit assignment plus server-set fields:
   ```php
   $order = (new Order)->fill($request->validated());
   $order->user_id = $request->user()->id;
   $order->status = OrderStatus::Pending;
   $order->save();
   ```
5. Add a feature test attempting to inject `user_id` / `role` keys; assert they are stripped (or that 422 is returned if they're not in the rules)
6. Audit other unsafe bindings in the controller / project

**Recipe: Eliminate Eloquent N+1 in Blade / API Resource**

1. Identify the lazy-loaded relation in Blade `@foreach` or in API Resource `toArray()`
2. Add `with('relation')` (or `with(['rel1', 'rel2.subrel'])`) to the controller's query before passing to the view / Resource: `Order::with(['user', 'items'])->cursorPaginate(25)`
3. Run `php artisan test`; confirm tests pass; verify in dev mode by enabling `Model::preventLazyLoading()` in `AppServiceProvider::boot` so any remaining lazy loads throw
4. **Skip if** the relation is conditional and the value is rarely accessed - over-eager-loading is a cost too. Use `whenLoaded` in the API Resource (`'user' => new UserResource($this->whenLoaded('user'))`) and only eager-load on routes that need it

**Recipe: Move side effects out of an open DB transaction**

When a controller / service runs `Http::post(...)`, `Mail::send(...)`, or `dispatch(new SomeJob(...))` inside `DB::transaction(fn () => ...)`, the side effect can fire before the row commits (queue worker faster than commit) or hold the DB connection across an upstream's tail latency. Two options - pick one per refactor; do not stack them.

**Option A: Post-commit dispatch via `->afterCommit()`** (default; use unless guaranteed delivery is required)

1. Move the side effect out of the transaction body; capture inputs, exit transaction, then dispatch
2. For jobs: `dispatch((new ProcessPayment($order->id))->afterCommit())` - the queue layer holds the dispatch until commit, then releases. Or set `public bool $afterCommit = true;` on the job so `afterCommit` is the default. For `QUEUE_AFTER_COMMIT=true` set globally in `config/queue.php`, `afterCommit` is the default - the recipe is to remove explicit `withoutCommit()` overrides
3. For raw HTTP / mail: capture the inputs into local variables inside the transaction; after `DB::transaction(...)` returns, run `Http::post(...)` / `Mail::send(...)` outside the transaction. Failure of the side effect no longer rolls back the row - acceptable when the side effect is retryable (job) or the row is the source of truth (mail can be re-triggered from the saved record)
4. Risk: if the side effect must run before the row is durable (rare), `afterCommit` is wrong - use Option B

**Option B: Transactional outbox** (use when delivery must be guaranteed exactly-once-after-commit, e.g., financial events, audit trail required by compliance)

1. Add an `outbox_messages` table: `id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload (json)`, `created_at`, `processed_at (nullable)`. Migration includes index on `(processed_at, created_at)` for the relay scan
2. In the same transaction that writes the business row, also `OutboxMessage::create([...])` with the event payload. Both rows commit atomically or both roll back
3. Add a relay job (scheduled via `Schedule::command('outbox:relay')->everyMinute()->withoutOverlapping()->onOneServer()`) that selects unprocessed rows in chunks, dispatches the real job / HTTP call / mail per row, then marks `processed_at = now()`. Idempotency on the consumer side is still required (outbox guarantees at-least-once)
4. Trade-off: adds a table, a relay command, and ~minute latency vs. immediate dispatch. Use only when post-commit-dispatch's "fire after commit but no guarantee on relay failure" is unacceptable

**Recipe: Convert job to use scalar IDs and `->afterCommit()`**

1. Identify the offending dispatch and constructor: `dispatch(new ProcessPayment($order))` inside `DB::transaction(fn () => ...)` with `class ProcessPayment { public function __construct(public Order $order) {} }`
2. Change job constructor to scalar: `public function __construct(public int $orderId) {}` and `handle(PaymentService $service): void { $order = Order::findOrFail($this->orderId); $service->charge($order); }`
3. Update dispatch site: `dispatch((new ProcessPayment($order->id))->afterCommit())` - or set `public bool $afterCommit = true;` on the job class so `afterCommit` is the default
4. Add `$tries`, `$backoff`, `$timeout`, `failed()` if missing:
   ```php
   public int $tries = 3;
   public array $backoff = [10, 60, 300];
   public int $timeout = 120;
   public function failed(Throwable $e): void { Log::error('Payment failed', ['order_id' => $this->orderId, 'exception' => $e]); }
   ```
5. Add a job test (`tests/Feature/Jobs/ProcessPaymentTest.php`): real `handle()` execution, idempotency (call twice, side effect once), retry (stub fails twice, succeeds), `failed()` invocation
6. Run `php artisan test`; confirm clean. Verify under load that no jobs run before their parent transaction commits

**Recipe: Add `CancellationToken` analog (Laravel doesn't have one)**

Laravel's queue model is at-least-once with explicit retry budget; "cancellation" is achieved via `$tries`, `retryUntil()`, and the `WithoutOverlapping` middleware. The recipe equivalent of "add CancellationToken propagation" is:

1. Set `$timeout` per job to bound execution
2. Set `retryUntil()` for time-bounded jobs (e.g., webhook delivery): `public function retryUntil(): DateTime { return now()->addHours(2); }`
3. Add `WithoutOverlapping` middleware to resource-bound jobs (per-key serialization)
4. Add `RateLimited` middleware to third-party-API-bound jobs

**Recipe: Eliminate single-implementation interface**

1. Confirm the interface has no Mockery mock used in tests, no second implementation, no DI lifetime / decoration need
2. Inline: the consuming code uses the concrete class directly - `app()->bind(OrderService::class, ...)` instead of `app()->bind(OrderServiceInterface::class, OrderService::class)`. Delete the interface
3. Run `php artisan test` and `composer phpstan`; confirm pass. Caller code is shorter and clearer
4. **Skip if** the interface is part of a public API contract (Composer package) or has a real second implementation (or Mockery mock used in tests) - the smell is fake

**Recipe: Replace repository-over-Eloquent with direct Eloquent**

1. Identify the trivial repository: `class OrderRepository { public function findById(int $id): ?Order { return Order::find($id); } }`
2. Inline: the controller / service injects the model class or uses `Order::find($id)` directly
3. Delete the repository class; remove the binding from the service provider
4. Run `php artisan test`; confirm pass. Eloquent is the abstraction; double-wrapping it is over-abstraction
5. **Skip if** the repository abstracts non-Eloquent storage (Redis, external API) or genuinely has multiple implementations - keep it

**Recipe: Replace AutoMapper-style mapper with API Resource**

1. Identify the mapper: `class OrderMapper { public function toResponse(Order $order): array { ... } }`
2. Replace with an API Resource: `class OrderResource extends JsonResource { public function toArray($request): array { return [...]; } }`
3. Update the controller: `return OrderResource::make($order);` (or `OrderResource::collection($orders)` for lists)
4. Delete the mapper; remove DI bindings
5. Run `php artisan test`; confirm pass. API Resources have built-in `whenLoaded`, conditional fields, pagination meta - all the things mappers usually re-implement

**Recipe: Eliminate `env()` outside config files**

1. Identify the offender: `$key = env('STRIPE_KEY')` in a service / controller / job
2. Add a config entry in `config/services.php`:
   ```php
   'stripe' => [
       'key' => env('STRIPE_KEY'),
       'secret' => env('STRIPE_SECRET'),
   ],
   ```
3. Replace the offending call: `$key = config('services.stripe.key')`
4. Verify `php artisan config:cache` works without error and `config('services.stripe.key')` returns the expected value
5. Run `php artisan test`; confirm clean. PHPStan / Larastan rule `larastan/largestan-strict-rules.neon` can catch this if enabled

**Recipe: Replace `new GuzzleHttp\Client()` with shared / `Http::*`**

1. Identify the per-request client construction: `$client = new \GuzzleHttp\Client(); $resp = $client->get($url);`
2. Use Laravel's HTTP client: `$resp = Http::get($url);` (uses Guzzle under the hood with shared handler / connection pool)
3. Set timeout / retry: `Http::timeout(5)->retry(3, 100)->get($url)` per call site, or via a pending request macro registered in `AppServiceProvider`
4. For SDK-required Guzzle (e.g., Stripe SDK), bind as singleton in `AppServiceProvider`: `$this->app->singleton(\Stripe\StripeClient::class, fn () => new \Stripe\StripeClient(config('services.stripe.secret')));`
5. Run `php artisan test`; verify under load that ephemeral port usage drops

**Recipe: Replace mutable static state with constructor-injected service**

1. Identify the static state: `class OrderCache { private static array $cache = []; public static function get(int $id): ?Order { return self::$cache[$id] ?? null; } }`
2. Move into a class with constructor: `class OrderCache { private array $cache = []; public function get(int $id): ?Order { return $this->cache[$id] ?? null; } }`; register as singleton via `app()->singleton(OrderCache::class)`. For per-request scope, use `app()->scoped(OrderCache::class)` (Laravel 11+) so the binding is reset between requests under Octane
3. Replace static reads/writes with method calls on the injected instance; consumers receive `OrderCache` via constructor injection
4. Run `php artisan test` + `composer phpstan`; confirm pass. Add a test asserting cross-request isolation under Octane (a fresh request gets an empty cache)
5. Static mutable state is especially dangerous under Octane / FrankenPHP / RoadRunner where workers persist across requests; flag any new static mutable property even when the project doesn't currently use Octane

**Recipe: Make queue job idempotent**

1. Add a job test asserting the side effect happens exactly once when the same payload is processed twice (different `job_id`, same business key)
2. Add an idempotency guard inside the consumer / handler: dedup table keyed by a business key, or `Cache::add($key, true, $ttl)` (atomic; returns false if exists), or `unique` constraint + `INSERT ... ON DUPLICATE KEY UPDATE` (MySQL) / `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL)
3. Verify retries on transient failures still complete the work
4. Configure `$tries`, `$backoff`, and `failed()` so poison messages do not loop forever; for time-bounded jobs add `retryUntil()`

### Step 8 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end); `php artisan test` + `composer phpstan` + `vendor/bin/pint --test` for every commit
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, interface removals)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Laravel Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Laravel refactor recipes" - this is the spine]
**Stack:** PHP <version> / Laravel <version>
**ORM:** Eloquent | Query Builder
**Queue:** redis (Horizon) | database | sync
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Tests Framework:** Pest | PHPUnit

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Lint state:** `vendor/bin/pint --test` clean + `composer phpstan` clean | warnings present (Step 0a covers them) | not run (no baseline)
**Octane / shared-state coverage:** clean | not exercised cross-request | n/a (no static state in target)

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-laravel-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce the **Smells Identified**, **Sibling Smells (Out of Scope)**, and the **Coverage prerequisite list** as a *preview* so the implementer has a target list when filling the coverage gap; mark them clearly as preview-only.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure (422), authorization denial (401/403), not-found / IDOR, external-collaborator failure, mass-assignment (privileged field stripped), and (when the target uses static state under Octane) **cross-request isolation** as the recommended layer. Layer options: feature test (`Tests\TestCase` + RefreshDatabase + real DB), unit test (Mockery), job test (real `handle()` + Queue::fake for dispatch), Policy test, cross-request isolation test (Octane scenario simulation). Example: `POST /api/orders | privileged user_id field stripped | feature test`.

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/class that this plan does NOT address._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                                |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-laravel-review-security` / `task-laravel-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green; `vendor/bin/pint --test` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if pint and PHPStan were already clean)_

- **Change:** address the existing pint / PHPStan warnings on the target so the refactor's lint gate has a clean baseline
- **Risk:** Low (no behavior change; format / lint-only fixes)
- **Test gate:** `vendor/bin/pint --test` clean; `composer phpstan` clean; `php artisan test` still green
- **Rollback:** revert the lint fixes

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - feature / unit / job / Policy; `vendor/bin/pint --test` and `composer phpstan` clean]
- **Transaction stance:** [callee runs inside caller's transaction (shares connection) | callee uses post-commit dispatch via `->afterCommit()` | not transactional]
- **Mass-assignment stance:** [no mass-assignment change | converts `$request->all()` to `$request->validated()` (cascading: list affected fields) | adds `$fillable` whitelist replacing `$guarded = []` | unchanged]
- **Container stance:** [no binding change | `bind` (transient) | `singleton` (one per app) | `scoped` (one per request, Laravel 11+) | static state replaced with DI]
- **Queue stance:** [no queue change | introduces `dispatch` (after-commit + tries/backoff/timeout/failed needed) | converts model-typed constructor to scalar ID | adds idempotency guard]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it. Always state why the coupling is structural, not cosmetic.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `php artisan test` passes and `composer phpstan` clean and `vendor/bin/pint --test` clean between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No partial mass-assignment conversion (every field is either explicit or validated, never falling through to `$request->all()`)
- [ ] No new singleton capturing request state; `scoped` used where needed under Octane
- [ ] No new job dispatch without `->afterCommit()` (when inside transaction), `$tries`/`$backoff`/`$timeout`/`failed()`, scalar ID constructor, and idempotency guard
- [ ] No new mutable static state without an Octane cross-request isolation test

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation (Step 1)
- [ ] Stack confirmed as PHP / Laravel (or accepted from parent dispatcher); ORM / queue / auth / test framework recorded; input completeness check ran (target + goal both supplied) (Step 2)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 3)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 3)
- [ ] Severity-inversion banner rendered above Coverage Gate when sibling smells are higher severity than the named target (Step 3)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin`; SQLite-for-MySQL-app treated as `Inadequate`; Octane-shared-state check applied; pint / PHPStan state recorded (Step 4)
- [ ] Laravel-specific smells identified using Step 5 catalog (controller, Form Request, service / action, persistence / Eloquent, configuration / DI, queue / job); relevant atomic skills (`laravel-eloquent-patterns`, `laravel-api-patterns`, `laravel-queue-patterns`, `laravel-service-patterns`, `laravel-security-patterns`, `laravel-migration-safety`) consulted per the composition table (Step 5)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 6)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 7)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate`. Step 0a included if pint / PHPStan state is not clean (Output Format)
- [ ] Transaction stance stated per step (no I/O silently moved across transaction boundary) (Step 7)
- [ ] Mass-assignment stance stated per step (no partial `$request->all()` → `$request->validated()` conversion) (Step 7)
- [ ] Container stance stated per step (no silent singleton capturing request state; `scoped` used where required under Octane) (Step 7)
- [ ] Queue stance stated per step (`->afterCommit()`, scalar ID, `$tries`/`$backoff`/`$timeout`/`failed()`, idempotency guard required when adding dispatch) (Step 7)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 7)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, interface removals, signature changes) (Step 7)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 7)
- [ ] No step bundles unrelated cleanup (Step 7)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 8)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `php artisan test` passes between every step
- [ ] `composer phpstan` clean for any step
- [ ] `vendor/bin/pint --test` clean for any step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Proposing a refactor that introduces shared state to a class that lacks Octane / cross-request isolation tests - the new race surface is unguarded
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing an interface without a real second use case - wait for the second use case before generalizing
- Replacing Eloquent with the query builder (or vice versa) on a code path with no measured benefit (premature change)
- Replacing static mutable state with `$_SESSION` / `Cache::*` keys carrying the same data globally - that is the same global with extra steps; use constructor injection
- Moving HTTP calls or job dispatches from a non-transactional context to inside `DB::transaction(...)` (or vice versa) without explicitly stating the transaction stance
- Partially converting `$request->all()` to `$request->validated()` - leaves a different mass-assignment surface; convert end-to-end or skip the recipe
- Refactoring an exported `public` symbol in a Composer package without a backward-compatibility plan - that is a public API
- Adding `dispatch(...)` from inside a transaction without `->afterCommit()` - worker may pick up before commit
- Adding new jobs without `$tries` / `$backoff` / `$timeout` / `failed()` - unbounded retries are a runaway-failure surface
- Adding new jobs that take Eloquent models in constructors - serializes a stale snapshot; pass scalar IDs and re-fetch
- Replacing `$guarded = []` mass assignment with another `$guarded = []` (just renamed) - the issue is the lack of fillable whitelist; introduce a Form Request and `$fillable`
- Consolidating services into a singleton without checking what state they capture - request-state-capturing singletons are foot-guns under Octane
- Removing Form Request validation in favor of inline `$request->validate(...)` - inline validation scatters rules and bypasses `authorize()` hook
