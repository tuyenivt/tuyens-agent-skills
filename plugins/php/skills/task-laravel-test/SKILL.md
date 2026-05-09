---
name: task-laravel-test
description: Laravel test scaffolding with Pest/PHPUnit: factories, RefreshDatabase, HTTP feature tests, Queue/Event/Mail/Storage fakes, Sanctum/Passport helpers.
agent: php-test-engineer
metadata:
  category: backend
  tags: [php, laravel, testing, pest, phpunit, factories, refreshdatabase, sanctum, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or Pest `it('AC1: ...', ...)` description), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope.

# Laravel Test

## Purpose

Laravel-aware test strategy and scaffolding using Pest (primary, the canonical Laravel test framework) or PHPUnit (legacy / explicit project preference), `Tests\TestCase` base, `RefreshDatabase` / `DatabaseTransactions` traits, **real MySQL/PostgreSQL test database** via `phpunit.xml` `<env>` overrides (NEVER SQLite for MySQL/PostgreSQL apps - skips FK behavior, missing JSON / fulltext / window functions, divergent concurrency semantics), Eloquent model factories with states (`User::factory()->admin()->create()`), HTTP feature tests via `$this->getJson(...)` / `postJson(...)` / `putJson(...)` / `deleteJson(...)` / `actingAs($user)` / `actingAs($user, 'sanctum')`, facade fakes (`Queue::fake()`, `Event::fake()`, `Notification::fake()`, `Mail::fake()`, `Storage::fake('private')`, `Bus::fake()`) for dispatch testing without real side effects, `Http::fake([...])` for HTTP stubs, Sanctum / Passport token testing (`Sanctum::actingAs($user, ['order:write'])`), Form Request validation testing, Policy testing, `Artisan::call(...)` for console commands, and `php artisan test` / `composer test` / `--coverage` discipline. Replaces the generic backend test patterns with Laravel-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for PHP / Laravel. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a test strategy for a new Laravel service / module
- Assessing test coverage gaps across feature / unit / job / Policy layers
- Scaffolding tests for under-covered controllers, services, jobs, Policies, or auth code
- Reviewing test pyramid balance for a Laravel app
- Adding boundary tests (validation, authorization, error paths) to existing happy-path tests

**Not for:**

- Test failure / exception debugging (use `task-laravel-debug`)
- General code review (use `task-code-review` / `task-laravel-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step (think before acting, surgical changes, no speculative additions, surface confusion). When invoked as a subagent of a parent workflow, accept the parent's confirmation and skip re-loading.

### Step 2 - Confirm Stack and Detect Test Framework

Use skill: `stack-detect` to confirm PHP / Laravel. If invoked as a delegate of `task-code-test` (parent already detected Laravel), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-test` instead.

Detect test framework: Pest (`tests/Pest.php` exists, `pestphp/pest` in `composer.json`) or PHPUnit (no Pest, just `phpunit.xml` + class-based tests). Detect ORM (Eloquent / query builder), auth (Sanctum / Passport / session), queue (Redis / database / sync), and database engine (MySQL / PostgreSQL / MariaDB) for test-environment guidance. Record `Tests Framework`, `Database`, `Auth`, `Queue` for the output.

### Step 3 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: controllers, Form Requests, models, services, actions, jobs, Policies
- Glob `tests/**/*.php` and read at least: one existing controller / feature test, one existing service / unit test, one existing job test, one existing Policy test, `tests/TestCase.php` (project base), `tests/Pest.php` (Pest config), `database/factories/*.php` - learn the project's test layout, factory conventions, custom helpers
- Read `phpunit.xml` for the test environment config: `<env name="DB_CONNECTION" value="..."/>`, `<env name="DB_DATABASE" value="..."/>`, `<env name="QUEUE_CONNECTION" value="sync"/>`, `<env name="CACHE_DRIVER" value="array"/>`, `<env name="MAIL_MAILER" value="array"/>`, `<env name="APP_ENV" value="testing"/>`. Critical check: `DB_CONNECTION` is the same engine as production (MySQL `mysql_testing` -> `mysql`, NOT `sqlite`)
- Read `composer.json` for test dependencies: `pestphp/pest`, `pestphp/pest-plugin-laravel`, `mockery/mockery`, `phpunit/phpunit`, `fakerphp/faker`, `laravel/sanctum`, `nunomaduro/larastan`
- Read `Makefile` / `composer.json` `scripts` for `composer test`, `composer phpstan`, `composer pint`, `composer test:coverage` invocation
- Read `tests/CreatesApplication.php` (legacy) or `tests/TestCase.php` for base setup (custom global setup, environment overrides)
- Read `bootstrap/app.php` for middleware order that feature tests must replicate

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently. Greenfield convention list (state your choice for each, with a one-line rationale):

| Decision           | Default to propose                                                                                  |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| Test layout        | Feature tests in `tests/Feature/` (HTTP via `TestCase` base); Unit tests in `tests/Unit/` (no app boot, no DB); job/Policy tests in `tests/Feature/Jobs/`, `tests/Feature/Policies/` |
| Test framework     | Pest (the modern Laravel default; `it('does X', fn () => ...)` syntax)                              |
| HTTP harness       | Built-in `$this->getJson(...)` / `postJson(...)` from `Tests\TestCase`; `actingAs($user)` for auth   |
| DB strategy        | Same engine as prod (MySQL/PostgreSQL via Docker for local + CI); `RefreshDatabase` trait for per-test reset (transactional rollback after each test) |
| Mock library       | Mockery for class mocks (Laravel ships with it); facade fakes (`Queue::fake`, `Event::fake`, etc.) for dispatch testing |
| Test-data library  | `fakerphp/faker` (factory built-in); model factories under `database/factories/`                     |
| HTTP stub          | `Http::fake([...])` for outbound HTTP calls; never real network in CI                                |
| Auth helper        | `actingAs($user)` for session; `Sanctum::actingAs($user, ['ability'])` for token; both built-in     |
| Runner             | `php artisan test` (wraps PHPUnit / Pest with Laravel's bootstrap) or `composer test`               |
| Coverage           | `--coverage` flag with PCOV (faster than Xdebug); reporting via `--coverage-html` or via Coverage CI tool |
| CI                 | `php artisan test --parallel --coverage --min=80` for parallel runs with coverage threshold        |

### Step 4 - Laravel Test Pyramid

The Laravel test pyramid maps to test types:

| Layer       | Tooling                                                                          | What belongs here                                                              |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | Pest / PHPUnit (no `RefreshDatabase`, no app boot via `Tests\TestCase` base)    | Pure domain logic, validators, mappers, calculation rules, value objects       |
| Feature     | Pest / PHPUnit + `RefreshDatabase` + real DB (matching prod engine)             | Controllers (full HTTP request/response), Form Requests, Policies, services with DB I/O, multi-aggregate orchestration |
| Job         | Pest / PHPUnit + `RefreshDatabase` for jobs that touch DB; `Queue::fake` for dispatch tests | Background-worker happy path, retry logic, idempotency, scheduled commands |
| E2E         | Browser tests via Laravel Dusk OR HTTP-only feature tests (preferred)            | Critical user journeys only - signup, checkout, payment                        |
| Contract    | Custom (e.g., `dedoc/scramble` schema validation, Pact)                          | API contract validation against schema                                         |

**Many** unit + feature tests, **few** Dusk E2E tests. `php artisan test` and `composer phpstan` on every CI run.

Note that "feature test" in Laravel terminology covers what other ecosystems call "integration test" or "API test" - it boots the full app, exercises the HTTP pipeline, and asserts both response shape and DB state. Prefer feature tests over unit tests for any code that involves the framework (controllers, Form Requests, Policies, Eloquent models).

### Step 5 - Apply Laravel Test Patterns

**Pest syntax (the canonical form for new Laravel projects):**

```php
<?php

use App\Models\User;
use App\Models\Order;

uses(Tests\TestCase::class, Illuminate\Foundation\Testing\RefreshDatabase::class)
    ->in('Feature');

describe('OrderController', function () {
    it('returns 401 when not authenticated', function () {
        getJson('/api/orders/'.fake()->uuid())
            ->assertStatus(401);
    });

    it('returns 403 when accessing another user\'s order', function () {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $order = Order::factory()->for($owner)->create();

        actingAs($other)
            ->getJson("/api/orders/{$order->id}")
            ->assertStatus(403);
    });

    it('returns the order for its owner', function () {
        $user = User::factory()->create();
        $order = Order::factory()->for($user)->create();

        actingAs($user)
            ->getJson("/api/orders/{$order->id}")
            ->assertStatus(200)
            ->assertJsonPath('data.id', $order->id);
    });
});
```

**PHPUnit class-based syntax (for legacy projects):**

```php
<?php

namespace Tests\Feature;

use App\Models\Order;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class OrderControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_returns_401_when_not_authenticated(): void
    {
        $this->getJson('/api/orders/'.fake()->uuid())
            ->assertStatus(401);
    }

    public function test_returns_403_when_accessing_another_users_order(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $order = Order::factory()->for($owner)->create();

        $this->actingAs($other)
            ->getJson("/api/orders/{$order->id}")
            ->assertStatus(403);
    }
}
```

**Parameterized / data-driven tests (Pest `with(...)`):**

```php
it('rejects invalid payload', function (array $payload, string $expectedField) {
    $user = User::factory()->create();
    actingAs($user)
        ->postJson('/api/orders', $payload)
        ->assertStatus(422)
        ->assertJsonValidationErrors([$expectedField]);
})->with([
    'missing email' => [['quantity' => 1], 'email'],
    'invalid email' => [['email' => 'not-an-email', 'quantity' => 1], 'email'],
    'zero quantity' => [['email' => 'a@b.com', 'quantity' => 0], 'quantity'],
    'negative quantity' => [['email' => 'a@b.com', 'quantity' => -1], 'quantity'],
]);
```

PHPUnit's equivalent is `@dataProvider`:

```php
/** @dataProvider invalidPayloadProvider */
public function test_rejects_invalid_payload(array $payload, string $expectedField): void { ... }

public static function invalidPayloadProvider(): array { ... }
```

**Unit tests (`tests/Unit/<Feature>/<Class>Test.php`):**

- Test method per outcome (happy / validation failure / external failure / edge); class per System Under Test
- **No `RefreshDatabase`, no app boot, no DB** in a unit test - if a unit test needs `RefreshDatabase` or the application container, it is misclassified - move to `tests/Feature/`
- Mockery for class mocks: `$repo = Mockery::mock(OrderRepository::class); $repo->shouldReceive('find')->with($id)->andReturn($order);`
- Test pure functions / value objects / DTOs / calculation rules; not Eloquent models (those need DB)

**Feature tests (`tests/Feature/<Feature>/<Class>Test.php`):**

- Full HTTP round-trip via `$this->getJson(...)` / `postJson(...)` etc.; assert status code, JSON shape, DB state
- Use `actingAs($user)` for session-based auth; `Sanctum::actingAs($user, ['order:read', 'order:write'])` for token-based auth with abilities; `Passport::actingAs($user, ['*'])` for Passport
- Database asserted via `$this->assertDatabaseHas('orders', ['id' => $order->id, 'status' => 'placed'])` and `$this->assertDatabaseMissing(...)` and `$this->assertDatabaseCount('orders', 1)`
- Build the test app the same as prod by calling the real route (no `Route::*` overrides); test must replicate prod middleware stack so missing auth / Form Request validation surfaces

**Anti-pattern: controller-direct-call.** A test that does `$controller = new OrderController(); $result = $controller->store($request);` bypasses the entire Laravel pipeline - no middleware (auth, throttle, CSRF), no Form Request validation, no `[Authorize]`, no global exception handler, no route model binding. Such a test asserts only the action method body, not the endpoint behavior. The bug it is most likely to miss is the bug a real client would hit. For controller-shape tests use `$this->postJson(...)` so the test looks like an HTTP request, not a method call. Treat any new controller-direct-call test in a diff as a `[High]` test-design finding.

For full pipeline tests:

- Build the test against the **same middleware stack** as `bootstrap/app.php` - feature tests inherit the real stack via `Tests\TestCase`. Missing middleware in tests masks authorization bugs
- One test per `(method, path, principal-state, outcome)` triple
- Authorization: a separate test for "anonymous → 401" and "wrong user → 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any endpoint with a Form Request - assert specific `assertJsonValidationErrors([...])`
- Response shape: assert key fields, status, headers, content-type via `assertJsonPath` or `assertJsonStructure`

**Form Request / Policy tests:**

- Form Request: `(new StoreOrderRequest())->setMethod('POST')->merge($payload)` then run validator; OR (preferred) test through the controller via feature test asserting `assertJsonValidationErrors([...])`
- Policy: `(new OrderPolicy())->update($user, $order)` returns `true` / `false` as expected; or via `$this->assertTrue($user->can('update', $order))` in a feature test
- Per-rule edge cases: missing required fields, wrong types, out-of-range values, custom validators

**Repository / Eloquent feature tests (real DB):**

- Real MySQL/PostgreSQL via `phpunit.xml` `<env name="DB_CONNECTION" value="mysql"/>` and a dedicated test database (`DB_DATABASE=acme_test`) - NEVER SQLite for prod-MySQL apps. **Detection rule:** if `phpunit.xml` carries `<env name="DB_CONNECTION" value="sqlite"/>` and the production `.env` (or `config/database.php`'s `DB_CONNECTION` default) is `mysql` / `pgsql`, raise `[High]` regardless of whether the test passes - the test is exercising a different store than prod, so green tests provide false confidence rather than coverage. SQLite in-memory is fast but skips: `JSON` column behavior (MySQL JSON path queries don't translate), FULLTEXT, fulltext indexes, transaction isolation level differences, FK ON DELETE CASCADE quirks, generated column behavior
- `RefreshDatabase` trait for per-test reset (wraps each test in a transaction that rolls back); fast and correct for most cases. Alternative: `DatabaseMigrations` runs full migrations before each test (slow); `DatabaseTransactions` is the manual `RefreshDatabase` equivalent
- Run migrations once via `php artisan migrate:fresh --env=testing` before the suite (or via `RefreshDatabase` which handles this)
- One test per non-trivial query: assert SQL semantics (filter correctness, sort order, JOIN result), not just "method returns something"
- Custom indexes / constraints: insert violating data and assert the right exception type (`Illuminate\Database\QueryException` with SQLSTATE 23000 for unique violation)

**Job tests (`tests/Feature/Jobs/<Job>Test.php`):**

- **Real handle() execution** for non-trivial jobs: `(new ProcessPayment($order->id))->handle($paymentService)`; assert side effects (DB state changes, mail sent, notifications dispatched). Use `Queue::fake()` ONLY when testing dispatch, not when testing the handler logic
- **Idempotency test**: invoke `handle()` twice with the same payload; assert side effect happens once (this catches missing dedup guards)
- **Retry test**: stub the external call to fail twice then succeed; assert job retries; assert eventual success
- **`failed()` test**: invoke `failed(new RuntimeException('...'))`; assert notification sent / failure logged
- **Dispatch test (separate from handler test)**: `Queue::fake(); dispatch(new ProcessPayment($id)); Queue::assertPushed(ProcessPayment::class, fn ($job) => $job->orderId === $id);` - tests that the dispatch happened, not the job logic
- **`afterCommit` test**: dispatch inside a transaction; assert the job did not run while the transaction was uncommitted; assert it ran after commit. Use `DB::transaction(fn () => dispatch(...))` and `Queue::assertNotPushed(...)` mid-transaction (tricky; usually the contract test is `assert pushed exactly once after commit`)

**Facade fakes (for dispatch testing):**

```php
Queue::fake();          // intercept queue dispatches
Event::fake();          // intercept event::dispatch
Notification::fake();   // intercept Notification::send
Mail::fake();           // intercept Mail::to(...)->send(...)
Bus::fake();            // intercept Bus::dispatch (for job batching)
Storage::fake('private'); // intercept Storage::disk('private') with a fake filesystem
Http::fake([...]);      // intercept Http::* with canned responses

// Then assert:
Queue::assertPushed(ProcessPayment::class, fn ($job) => $job->orderId === $id);
Event::assertDispatched(OrderPlaced::class);
Notification::assertSentTo($user, OrderConfirmation::class);
Mail::assertQueued(OrderShipped::class);
Storage::disk('private')->assertExists("uploads/{$file->id}.pdf");
Http::assertSent(fn ($request) => $request->url() === 'https://api.example.com/charge');
```

Use fakes ONLY for dispatch-side testing. For handler-side testing, run the real `handle()` method.

**HTTP stubs:**

- `Http::fake([...])` for outbound HTTP calls returning canned responses - works for any code using Laravel's `Http::*` facade
- **SDKs that ship their own HTTP client (Stripe SDK, AWS SDK, Twilio SDK, etc.) bypass `Http::fake`** - they construct their own Guzzle client and `Http::fake` only intercepts the facade's pending request. Mock the SDK class directly via Mockery (`$stripe = Mockery::mock(\Stripe\StripeClient::class)`), or wrap the SDK in a thin service class you can mock. Verify the SDK's HTTP-mock hook (Stripe's official PHP SDK supports a `setHttpClient` method for testing); when no hook exists, mocking the wrapper is the only safe path. Treat any "the SDK calls real Stripe in CI" as a test-design bug
- `Http::preventStrayRequests()` in `Tests\TestCase::setUp` so any unfaked outbound request fails the test - prevents accidental real network calls. Note: this catches `Http::*` facade calls only; SDK direct calls still escape unless wrapped (see above)

**Console command tests:**

- `$this->artisan('orders:reconcile --since=yesterday')->assertExitCode(0)->expectsOutput('...')`
- For commands that interact with the queue, dispatch, etc., wire fakes as for any other test

**Pint / PHPStan / Larastan in CI:**

- `vendor/bin/pint --test` (Laravel's official code style fixer; "test" mode = check without modifying)
- `vendor/bin/phpstan analyse` with Larastan extension (Laravel-aware static analysis at level 5+)
- `composer audit` for dependency vulnerability scanning
- All three on every CI run alongside `php artisan test`

### Step 6 - Test Boundaries (Laravel-Specific)

**What deserves a unit test:**

- Pure functions / value objects / DTOs / readonly classes
- Validators with custom rules (custom rule classes implementing `ValidationRule`)
- Calculation rules / domain logic that doesn't touch the DB
- Mappers / transformers between domain and external shapes (when not just an API Resource)

**What deserves a feature test:**

- Every controller action: happy path + 401 + 403 + validation-error
- **IDOR / per-owner / per-tenant resources**: anonymous → 401, other-user → 403, owner → 200. Any action that takes an id route parameter and returns or mutates user-owned data needs this triple
- Pagination contract (`page` / `per_page` / `cursor` / `next_page_url`)
- Filtering / sorting / search query params - especially user-supplied `sort` columns where the validator must allowlist
- Custom exception handling mapping domain exceptions → HTTP status

**Web hazard tests (when controller / action shape signals the risk):**

| Hazard                | When the action shape signals it                                                       | Test to add                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| IDOR                  | Route `{model}` -> user-owned resource lookup or mutation                              | Owner / other-user / anonymous trio per endpoint                                                  |
| Mass assignment       | Controller calls `Model::create($request->all())` or `update($request->all())`        | Submit a payload containing a privileged field (`role`, `user_id`, `is_admin`); assert it's ignored |
| Open redirect         | `redirect($userInput)` or any action returning a 30x to a request-derived URL         | Allowlist enforcement: reject `//evil.com`, schemes, encoded forms                                |
| File upload           | `$request->file()` or any path joining `userFilename`                                 | Path traversal (`../../etc/...`), magic-byte vs `Content-Type` lie, size cap, extension allowlist |
| Bulk export           | Endpoint returning unpaginated `Order::all()`; `/admin/export` shape                  | Authz + row-cap + tenant scoping ("export only my tenant's rows, max N rows")                     |
| SSRF                  | `Http::get($userUrl)` / outbound HTTP with request-derived host                       | Allowlist rejects metadata IP, loopback, RFC1918, link-local; DNS rebinding test                  |
| Privilege escalation  | `UpdateUser` / `UpdateRole` / any action that touches role / permission fields        | Non-admin cannot self-promote; admin can; role change requires explicit admin Policy guard        |
| Command/shell injection | `exec`/`shell_exec`/`system` / `Process::run` with user-derived strings              | Reject metacharacters in user input; assert allowlist enforcement                                 |
| Webhook signature     | POST endpoint accepting third-party webhook (Stripe, GitHub, etc.)                    | Reject payload with wrong / missing signature; reject replayed events (idempotency by event ID)  |
| Composite (export + path + process) | One action that combines bulk export + user-controlled filename + `exec` on the result | Single test asserting all three guards co-occur on this action: (a) path-traversal payload rejected (`../../etc/passwd`), (b) tenant scoping enforced (only my tenant's rows in output), (c) shell metacharacters in filename cannot reach the spawned process |

These belong in feature tests, not buried in service unit tests - the security guard is at the action / middleware boundary, so the test must exercise it through the same boundary. **Web hazards from this table default to Step 8 priority band P1** (security guard is the test's purpose), even when the underlying flow looks like P3 revenue or P2 data integrity.

**What deserves a Policy test:**

- Every Policy method: passing case + denied case + (when applicable) edge case (admin override, soft-deleted record)
- Either standalone (`(new OrderPolicy())->update($user, $order)`) or via feature test (`$this->assertTrue($user->can('update', $order))`)

**What deserves a job / queue test:**

- Every Job / Listener with non-trivial `handle()`: happy path + retry + idempotency + `failed()` notification
- Scheduled commands: at least one happy-path test via `$this->artisan('command:name')`
- Jobs dispatched via post-commit pattern - assert they fire after the parent commits, not before (more of a code-review concern; tests cover the in-process behavior)

**What does NOT need a test:**

- Framework-provided behavior: Laravel routing resolution, middleware dispatch, default model binding, `[ApiController]` automatic validation (test that you wired things correctly via feature tests, not that the framework works)
- Generated boilerplate: API Resources with no logic beyond field mapping, accessor returning a single field, validation rule chains that just compose built-in rules
- Trivial delegation: `service->getById($id) -> repository->find($id)` with no logic

### Step 7 - Test Data and Fixtures

- Prefer Eloquent factories: `User::factory()->admin()->withOrders(3)->create()` over hand-rolled `User::create([...])`. Define states for variants
- Factory states for variants: `User::factory()->admin()`, `Order::factory()->placed()`, `Order::factory()->cancelled()`. Defined as methods on the Factory class
- Factory relationships: `Order::factory()->for(User::factory())->has(OrderItem::factory()->count(3))` for parent + children in one call
- Avoid mutating shared test fixtures - factory creates fresh per test under `RefreshDatabase`
- Test data must be minimal and focused - 100-row factory loops signal the test belongs at integration / load-test layer
- Use `Faker` (`fake()->name()`, `fake()->email()`, `fake()->numberBetween(1, 100)`) inside factories for realistic data; not hardcoded magic values

### Step 8 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go untested while plumbing endpoints get full coverage.

**Multi-deliverable invocations.** When the user asks for both Coverage Assessment and Test Scaffolds in one go (a common case on under-covered modules), run prioritization here, then have the Test Scaffolds section in the output target the top band first. Do not silently pick the file the user named if a higher-priority gap exists in the same module - surface the priority order, then scaffold in priority order. The user can override.

When starting from low test coverage, prioritize by Laravel-specific risk:

**Priority 1 - Authorization and authentication:**

- Feature test per protected endpoint asserting 401 anonymous + 403 wrong-user
- Sanctum / Passport token tests covering ability scopes
- Policy methods unit-tested
- Form Request `authorize()` tested (returning false for wrong user)

**Priority 2 - Data integrity:**

- Feature tests for every non-trivial query (filters, joins, multi-tenant scoping)
- Service / job tests for write operations (one happy path + one rollback per write)
- Idempotency tests for any job with side effects
- Mass-assignment tests: submit privileged field; assert ignored

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (often modeled as backed enums in PHP - exhaustive `match` expressions make them testable)
- Scheduled jobs touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through controllers, simple CRUD - lower risk, can wait

**Multi-band rule.** Some targets fall into more than one band - a refund job is both P2 (data-integrity, side-effect idempotency) and P3 (revenue path); a payment-history endpoint is both P1 (authorization on per-owner data) and P3 (revenue). When a target qualifies for multiple bands, file it under the **highest** band (lowest number) and note the secondary band so the test plan covers both axes.

### Step 9 - Test Infrastructure Hygiene

- [ ] `phpunit.xml` `<env DB_CONNECTION>` matches production engine (MySQL / PostgreSQL) - never SQLite for prod-MySQL apps
- [ ] `RefreshDatabase` trait used (or `DatabaseMigrations` for slower-but-stricter); per-test reset is required for isolation
- [ ] `php artisan test` runs in CI; `composer phpstan` (Larastan); `vendor/bin/pint --test` enforces code style
- [ ] `composer audit` clean in CI
- [ ] Test environment overrides only what differs from prod: `QUEUE_CONNECTION=sync` (for synchronous queue execution), `MAIL_MAILER=array` (in-memory mail), `CACHE_DRIVER=array` (in-memory cache), `BCRYPT_ROUNDS=4` (faster password hashing). Never silently disable auth
- [ ] HTTP stubs via `Http::fake([...])` and `Http::preventStrayRequests()`; never real network in CI
- [ ] No `sleep(N)` in tests - use `Queue::assertPushed`, `Bus::assertDispatched`, or process the queue directly via `Queue::fake` + `Bus::dispatchSync(...)`
- [ ] Coverage via `--coverage` (PCOV preferred over Xdebug for speed); per-package thresholds documented; coverage exclusions via `@codeCoverageIgnore` annotations (with rationale)
- [ ] `php artisan test --parallel` for faster CI runs (Pest / PHPUnit support parallelization since Laravel 8+)
- [ ] Shared factory states defined in `database/factories/` so every test class shares conventions (DRY)

## Laravel Review Checklist

Quick-reference checklist for reviewing existing Laravel tests:

- [ ] Test type matches what is being tested (controller -> feature, service with DB -> feature, job -> feature, pure logic -> unit, Policy -> unit OR feature via `can`)
- [ ] Tests are parameterized (Pest `with(...)` / PHPUnit `@dataProvider`), not copy-pasted per case
- [ ] Every endpoint has at least happy + 401 + 403 + validation-error
- [ ] Every non-trivial query has a feature test against real MySQL/PostgreSQL (not SQLite)
- [ ] Every Policy method has at least a passing-and-denied test
- [ ] Test data created via factories with states, not hand-rolled `User::create([...])`
- [ ] No `Mockery::mock(InMemoryRepo::class)` mocks when a feature test could assert real DB state
- [ ] No Dusk E2E tests for what a feature test could cover
- [ ] No `Queue::fake` masking at-least-once / retry semantics on critical jobs (use `Queue::fake` for dispatch tests; real `handle()` for handler tests)
- [ ] `php artisan test` clean; `composer phpstan` clean; `vendor/bin/pint --test` clean in CI
- [ ] No `sleep()` to wait for async work to "probably finish" - use facade fakes and assertions
- [ ] No `dd()` / `dump()` left in tests
- [ ] PHPUnit `@dataProvider` data providers strongly typed (no `array` casts inside the test body)
- [ ] No real network calls - `Http::preventStrayRequests()` in test bootstrap

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% with no scaffolds requested -> Strategy Doc (optionally include Coverage Assessment)
- User asks for **two or more deliverables in the same invocation** ("review coverage AND scaffold tests", "what's missing and write the tests") -> produce them in this order, separated by a horizontal rule (`---`): Coverage Assessment, then Strategy Doc (if requested), then Test Scaffolds. Do not silently drop one.
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Laravel Test Coverage Assessment

**Stack:** PHP <version> / Laravel <version>
**Database:** MySQL <version> | PostgreSQL <version> | MariaDB <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Queue:** redis (Horizon) | database | sync (testing)
**Test framework:** Pest | PHPUnit + factories + RefreshDatabase + facade fakes (Queue / Event / Notification / Mail / Bus / Storage / Http)

**Coverage gaps:**

- **Unit tests:** [pure logic / validators / value objects without test coverage]
- **Feature tests:** [endpoints without tests; endpoints missing 401/403/validation paths]
- **DB-engine mismatch:** [tests running on SQLite for a MySQL app]
- **Auth tests:** [endpoints without authorization tests; missing Sanctum / Passport ability scope tests]
- **Mass-assignment tests:** [controllers using `Model::create($request->all())` without a test asserting privileged fields are stripped]
- **Web hazard tests:** [IDOR / per-owner triples missing; open redirect without allowlist tests; file upload without path-traversal / MIME / size tests; bulk export without scoping / row-cap tests; SSRF without allowlist tests; privilege-escalation guards untested; webhook signature verification untested]
- **Job tests:** [jobs without tests; jobs without idempotency / retry tests; missing `failed()` test]
- **Policy tests:** [Policies without passing / denied tests]

**Recommended pyramid balance:**

- Unit (pure logic): [count target]
- Feature (HTTP + DB): [count target]
- Job + Policy: [count target]
- Dusk E2E (full stack): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or the assessment surfaces > 5 gaps)_

Apply the Step 8 risk bands. Order follow-up work as:

1. **P1 - Authorization & authentication:** [list specific endpoints / Policies missing 401/403/ownership tests]
2. **P2 - Data integrity:** [non-trivial queries / write paths / job idempotency without tests]
3. **P3 - Business-critical flows:** [revenue, state machines, scheduled jobs touching billing or notifications]
4. **P4 - High-churn code:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through controllers / simple CRUD - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run PHP test files using project conventions. Each scaffold must include:

- The right test type (feature / unit / job / Policy)
- Parameterized structure (Pest `with(...)` or PHPUnit `@dataProvider`) when behavior varies by input
- Eloquent factories with states for test data, not hand-rolled `Model::create([...])`
- For feature tests: happy path + 401 + 403 + validation-error
- For DB-touching tests: `RefreshDatabase` trait + real MySQL/PostgreSQL semantics (not SQLite)
- For auth tests: anonymous + wrong-user + correct-user cases via `actingAs($user)` / `Sanctum::actingAs(...)`
- For job tests: real `handle()` execution + idempotency + retry + `failed()` cases when applicable
- Pest `it(...)` syntax (or PHPUnit class-based for legacy projects per Step 2 detection)
- `assertJsonValidationErrors`, `assertJsonPath`, `assertDatabaseHas` for response/state shape

**Strategy Doc** (when designing a test strategy):

```markdown
## Laravel Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Feature {y}% / Job + Policy {z}% / Dusk {w}%
**Tooling:** Pest, PHPUnit, factories, `RefreshDatabase`, facade fakes, Sanctum / Passport helpers, `php artisan test`, `composer phpstan`, `vendor/bin/pint --test`
**Database isolation:** real MySQL/PostgreSQL via `phpunit.xml` env override; `RefreshDatabase` per-test transactional rollback
**CI:** `php artisan test --parallel --coverage --min=80`; `composer phpstan`; `composer audit`; `vendor/bin/pint --test`
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or data integrity]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation (Step 1)
- [ ] Stack confirmed as PHP / Laravel; database, auth, queue, test framework recorded before any framework-specific guidance applied (Step 2)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 3)
- [ ] `laravel-testing-patterns` consulted for canonical Laravel test patterns
- [ ] Auth testing approach explicit (`actingAs($user)` for session, `Sanctum::actingAs($user, [scopes])` for token)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)
- [ ] SDK-bypass note applied when external SDKs (Stripe / AWS / Twilio) are in scope - tests mock the SDK class, not just `Http::fake`

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to Laravel idioms (unit -> Pest + Mockery; feature -> Pest + RefreshDatabase + real DB; job -> Pest + real `handle()`; Dusk only for browser-dependent flows) (Step 4)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers (Step 6)
- [ ] Prioritization by risk applied when coverage is low - P1 authorization, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing (Step 8)
- [ ] Multi-band rule applied when a target qualifies for multiple priority bands; filed at the highest band, secondary band noted (Step 8)
- [ ] Multi-deliverable invocations produce sections in order Coverage Assessment → Strategy Doc → Test Scaffolds, separated by `---`, with scaffolds targeting the top priority band first (Step 8 / Output Format)
- [ ] Real MySQL/PostgreSQL recommended for repository / feature tests; SQLite flagged as a smell for production-MySQL/PostgreSQL apps (Step 9)
- [ ] `composer phpstan` / `vendor/bin/pint --test` / `composer audit` CI presence flagged when packages with concurrent code lack lint coverage (Step 9)

**Test Scaffolds only:**

- [ ] Tests are parameterized (Pest `with(...)` / PHPUnit `@dataProvider`), not copy-pasted per case
- [ ] Test data created via Eloquent factories with states, not hand-rolled `Model::create([...])`
- [ ] Feature scaffolds include happy path + 401 + 403 + validation-error; IDOR test for any per-owner / per-tenant resource
- [ ] Feature scaffolds extend `Tests\TestCase` so the same middleware stack as `bootstrap/app.php` runs (missing middleware in tests masks authorization bugs)
- [ ] DB-touching scaffolds use `RefreshDatabase` against real MySQL/PostgreSQL - never SQLite for prod-MySQL apps
- [ ] Job scaffolds include idempotency + retry + `failed()`; real `handle()` execution for non-trivial jobs
- [ ] Pest scaffolds use `it(...)` syntax; PHPUnit scaffolds use class-based `test_*` methods (per project convention from Step 2)

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + setup files - the result imports the wrong base class, uses the wrong factory, or duplicates the test base
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Writing a separate `it(...)` per case when Pest `with(...)` would do - copy-paste tests are harder to maintain and grow inconsistencies
- Dusk E2E tests for what a feature test could cover - context cost compounds across the suite
- SQLite in feature tests for apps that use MySQL features (JSON path queries, fulltext, generated columns) or PostgreSQL features - tests pass, prod fails. SQLite is not a relational store match; it skips FK enforcement, fulltext, and concurrent updates
- Feature tests that bypass middleware (instantiating the controller directly) - validation rules and auth differ between test and prod silently
- Duplicating factories per project - share via `database/factories/` referenced by other test classes
- Using `Mockery::mock(OrderRepository::class)->shouldReceive('find')->andReturn($model)` mocks when a feature test could assert real DB state
- Mocking auth middleware to silence Form Request failures - the test is now incorrect for the prod config
- Skipping Form Request unit tests because the controller has a feature test - validators are unit-tested separately so they can be reused
- Testing framework internals (e.g., that Laravel routes match, that middleware runs) - test your wiring, not the framework
- Using `Queue::fake` as a substitute for a real `handle()` test on jobs with non-trivial logic - the fake skips the handler and masks at-least-once / DLQ semantics
- Using `Mockery::mock(...)->shouldReceive(...)->andReturn(null)` to silence type errors - use the right typed return
- Using `sleep(N)` to wait for async work to "probably finish" - use `Queue::fake` + `Queue::assertPushed`, `Bus::assertDispatched`, or process the queue inline
- Using `dd()` / `dump()` in test files - they leak in test output and slow CI
- Using PHPUnit class-based syntax for new tests in a Pest-using project - inconsistency with project convention
- SQLite in `phpunit.xml` for a MySQL/PostgreSQL production app - tests pass on a different store than prod
