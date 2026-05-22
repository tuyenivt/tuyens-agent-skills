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

Laravel-aware test strategy and scaffolding (Pest primary, PHPUnit legacy) with real MySQL/PostgreSQL, `RefreshDatabase`, model factories, HTTP feature tests, facade fakes, and Sanctum/Passport helpers. Stack-specific delegate of `task-code-test` for PHP / Laravel; preserves the core workflow's output contract.

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

Use skill: `behavioral-principles`. Governs every subsequent step. When invoked as a subagent, accept the parent's confirmation and skip re-loading.

### Step 2 - Confirm Stack and Detect Test Framework

Use skill: `stack-detect` to confirm PHP / Laravel. If invoked as a delegate of `task-code-test` (parent already detected), accept the pre-confirmed stack. If not Laravel, stop and tell the user to invoke `/task-code-test` instead.

Detect: test framework (Pest if `tests/Pest.php` and `pestphp/pest`; else PHPUnit), ORM, auth (Sanctum / Passport / session), queue, and DB engine. Record `Tests Framework`, `Database`, `Auth`, `Queue` for the output.

### Step 3 - Read the Code Under Test and Existing Tests

Ground the output in real conventions by reading both production code and a representative sample of existing tests before writing anything.

- Production code for each target: controllers, Form Requests, models, services, actions, jobs, Policies
- Existing tests: one each of controller/feature, service/unit, job, Policy; plus `tests/TestCase.php`, `tests/Pest.php`, `database/factories/*.php`
- `phpunit.xml` env config - critical: `DB_CONNECTION` matches prod engine (MySQL/PostgreSQL, NOT SQLite); also `QUEUE_CONNECTION=sync`, `CACHE_DRIVER=array`, `MAIL_MAILER=array`, `APP_ENV=testing`
- `composer.json` test deps (`pestphp/pest`, `pestphp/pest-plugin-laravel`, `mockery/mockery`, `phpunit/phpunit`, `fakerphp/faker`, `laravel/sanctum`, `nunomaduro/larastan`) and `scripts` (`composer test`, `composer phpstan`, `composer pint`)
- `bootstrap/app.php` for middleware order that feature tests must replicate

If the project has no existing tests, propose conventions explicitly rather than inventing silently. Greenfield defaults (state your choice with one-line rationale):

| Decision           | Default to propose                                                                                  |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| Test layout        | `tests/Feature/` (HTTP via `TestCase`); `tests/Unit/` (no app boot, no DB); `tests/Feature/Jobs/`, `tests/Feature/Policies/` |
| Test framework     | Pest (modern Laravel default)                                                                       |
| HTTP harness       | `$this->getJson(...)` / `postJson(...)` from `Tests\TestCase`; `actingAs($user)`                    |
| DB strategy        | Same engine as prod (MySQL/PostgreSQL via Docker); `RefreshDatabase` for per-test transactional reset |
| Mock library       | Mockery for class mocks; facade fakes (`Queue::fake`, `Event::fake`, etc.) for dispatch              |
| Test-data library  | `fakerphp/faker` via factories under `database/factories/`                                          |
| HTTP stub          | `Http::fake([...])`; never real network in CI                                                       |
| Auth helper        | `actingAs($user)` (session); `Sanctum::actingAs($user, ['ability'])` (token)                        |
| Runner             | `php artisan test` or `composer test`                                                               |
| Coverage           | `--coverage` with PCOV (faster than Xdebug); `--coverage-html` or CI tool                           |
| CI                 | `php artisan test --parallel --coverage --min=80`                                                   |

### Step 4 - Laravel Test Pyramid

| Layer       | Tooling                                                                          | What belongs here                                                              |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | Pest / PHPUnit (no `RefreshDatabase`, no app boot)                              | Pure domain logic, validators, mappers, calculation rules, value objects       |
| Feature     | Pest / PHPUnit + `RefreshDatabase` + real DB                                    | Controllers, Form Requests, Policies, services with DB I/O, multi-aggregate orchestration |
| Job         | Pest / PHPUnit + `RefreshDatabase`; `Queue::fake` for dispatch tests             | Background-worker happy path, retry, idempotency, scheduled commands           |
| E2E         | Laravel Dusk OR HTTP-only feature tests (preferred)                              | Critical user journeys only - signup, checkout, payment                        |
| Contract    | `dedoc/scramble`, Pact                                                           | API contract validation against schema                                         |

**Many** unit + feature, **few** Dusk. `php artisan test` and `composer phpstan` on every CI run. "Feature test" in Laravel covers what other ecosystems call integration/API test - it boots the full app, exercises the HTTP pipeline, asserts response and DB state. Prefer feature over unit for any framework-touching code.

### Step 5 - Apply Laravel Test Patterns

Canonical Pest/PHPUnit patterns (syntax, `actingAs`, `RefreshDatabase`, factory states, facade fakes, `Http::fake`/`preventStrayRequests`, assertions) live in `laravel-testing-patterns`. Load it for the actual scaffolds. Strategy-side rules:

- **Test type matches the surface.** Unit = no `RefreshDatabase`, no app boot, no DB. Feature = full HTTP round-trip via `$this->getJson(...)` / `postJson(...)` against real MySQL/PostgreSQL with `RefreshDatabase`. Job = real `handle()` for handler logic + `Queue::fake` for dispatch (never mix). Policy = standalone `(new OrderPolicy())->update(...)` or via `$this->assertTrue($user->can(...))`.
- **One test per `(method, path, principal-state, outcome)` triple** for endpoints; one per outcome (happy / validation / auth-denial / external failure / edge) elsewhere. Per-protected-endpoint trio: anonymous -> 401, wrong-user -> 403, owner -> 200.
- **Parameterized over copy-pasted.** Pest `with(...)` or PHPUnit `@dataProvider` for variants.
- **Real MySQL/PostgreSQL, not SQLite.** SQLite while prod is MySQL/PostgreSQL is `[High]` regardless of pass/fail - skips JSON path queries, FULLTEXT, FK enforcement, generated columns, concurrent-update semantics.
- **Job idempotency asserts side-effect call count, not final state.** Final-state-only tests hide non-idempotent code that converges by accident. Real `handle()` is the path; `Queue::fake` masks the handler.
- **Anti-pattern: controller-direct-call.** `new OrderController(); $controller->store($request);` bypasses middleware / Form Request / route model binding / global exception handler. Use `$this->postJson(...)`. Treat any new controller-direct-call test as `[High]` test-design.
- **SDK-direct calls bypass `Http::fake`.** Stripe / AWS / Twilio SDKs construct their own Guzzle client. Mock the SDK class via Mockery, or wrap behind a thin service. Verify SDK HTTP-mock hooks; mock the wrapper when none exists.
- **`Http::preventStrayRequests()` in `Tests\TestCase::setUp`** so unfaked outbound requests fail the test.
- **CI runs all four**: `php artisan test`, `composer phpstan` (Larastan level 5+), `vendor/bin/pint --test`, `composer audit`.

### Step 6 - Test Boundaries

**Unit:** pure functions / value objects / DTOs / readonly classes; validators with custom `ValidationRule`; calculation rules; non-API-Resource mappers.

**Feature:** every controller action (happy + 401 + 403 + validation-error); **IDOR / per-owner / per-tenant resources** (anonymous -> 401, other-user -> 403, owner -> 200); pagination contract; filtering/sorting/search query params (especially allowlisted `sort` columns); custom exception -> HTTP status mapping.

**Web hazard tests** (when action shape signals the risk):

| Hazard                | When the action shape signals it                                                       | Test to add                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| IDOR                  | Route `{model}` -> user-owned resource lookup or mutation                              | Owner / other-user / anonymous trio per endpoint                                                  |
| Mass assignment       | `Model::create($request->all())` or `update($request->all())`                          | Submit payload with privileged field (`role`, `user_id`, `is_admin`); assert ignored             |
| Open redirect         | `redirect($userInput)` or 30x to a request-derived URL                                 | Allowlist enforcement: reject `//evil.com`, schemes, encoded forms                                |
| File upload           | `$request->file()` or path joining `userFilename`                                      | Path traversal (`../../etc/...`), magic-byte vs `Content-Type` lie, size cap, extension allowlist |
| Bulk export           | Unpaginated `Order::all()`; `/admin/export` shape                                      | Authz + row-cap + tenant scoping                                                                  |
| SSRF                  | `Http::get($userUrl)` / outbound HTTP with request-derived host                        | Allowlist rejects metadata IP, loopback, RFC1918, link-local; DNS rebinding                       |
| Privilege escalation  | `UpdateUser` / `UpdateRole` / role/permission mutations                                | Non-admin cannot self-promote; admin can; role change requires explicit admin Policy guard        |
| Command/shell injection | `exec`/`shell_exec`/`system`/`Process::run` with user-derived strings                | Reject metacharacters; assert allowlist enforcement                                               |
| Webhook signature     | POST endpoint accepting third-party webhook (Stripe, GitHub, ...)                      | Reject wrong/missing signature; reject replayed events (event-ID idempotency)                     |
| Composite (export + path + process) | One action combining bulk export + user filename + `exec`                | Single test asserting all three guards co-occur: (a) path-traversal rejected, (b) tenant scoping, (c) shell metacharacters cannot reach the spawned process |

These belong in feature tests, not service unit tests - the guard is at the action / middleware boundary. **Web hazards default to Step 8 band P1**, even when the underlying flow looks like P3 or P2.

**Policy:** every method (passing + denied + edge case like admin override or soft-deleted), standalone or via `$user->can(...)`.

**Job / queue:** every Job / Listener with non-trivial `handle()` (happy + retry + idempotency + `failed()`); scheduled commands at least one happy-path via `$this->artisan('command:name')`.

**No test needed:** framework behavior (Laravel routing, middleware dispatch, model binding); generated boilerplate (no-logic API Resources, single-field accessors, built-in rule chains); trivial delegation (`service->getById -> repository->find` with no logic).

### Step 7 - Test Data and Fixtures

- Eloquent factories with states (`User::factory()->admin()->withOrders(3)->create()`) over hand-rolled `User::create([...])`
- Factory relationships: `Order::factory()->for(User::factory())->has(OrderItem::factory()->count(3))`
- Fresh per test under `RefreshDatabase`; avoid mutating shared fixtures
- Minimal and focused - 100-row factory loops signal integration/load-test layer
- `Faker` (`fake()->name()`, `fake()->email()`, `fake()->numberBetween(1, 100)`) inside factories; no hardcoded magic values

### Step 8 - Prioritization (when coverage is low)

If coverage is below ~50%, **run before scaffolding** - it determines which tests come first.

**Multi-deliverable invocations.** When the user asks for Coverage Assessment + Test Scaffolds in one go, run prioritization here, then target the top band first in Scaffolds. Do not silently pick the file the user named if a higher-priority gap exists in the same module - surface the order; user can override.

**P1 - Authorization & authentication:**

- Per-protected-endpoint feature test: 401 anonymous + 403 wrong-user
- Sanctum / Passport ability-scope tests
- Policy methods unit-tested
- Form Request `authorize()` (returns false for wrong user)

**P2 - Data integrity:**

- Feature tests for non-trivial queries (filters, joins, multi-tenant scoping)
- Service / job tests for write operations (one happy + one rollback per write)
- Idempotency tests for side-effecting jobs
- Mass-assignment tests (privileged field ignored)

**P3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (backed enums with exhaustive `match`)
- Scheduled jobs touching billing or notifications

**P4 - High-churn code:**

- `git log --since="3 months ago"`; `git log --grep="fix"`

**P5 - Plumbing:**

- Pass-through controllers, simple CRUD

**Multi-band rule.** When a target qualifies for multiple bands (e.g., refund job is P2 + P3; payment-history endpoint is P1 + P3), file at the **highest** band (lowest number) and note the secondary so the test plan covers both axes.

### Step 9 - Test Infrastructure Hygiene

- [ ] `phpunit.xml` `DB_CONNECTION` matches prod engine; `RefreshDatabase` (or `DatabaseMigrations`) for per-test isolation
- [ ] Test env overrides only what differs from prod (`QUEUE_CONNECTION=sync`, `MAIL_MAILER=array`, `CACHE_DRIVER=array`, `BCRYPT_ROUNDS=4`); never silently disable auth
- [ ] No `sleep(N)` - use `Queue::assertPushed`, `Bus::assertDispatched`, or `Bus::dispatchSync(...)`
- [ ] `--coverage` with PCOV; per-package thresholds; exclusions via `@codeCoverageIgnore` with rationale
- [ ] `php artisan test --parallel` for faster CI; shared factory states in `database/factories/`

## Output Format

**Which output:** "what tests are missing?" / "review coverage" -> Coverage Assessment. "Write/scaffold tests for X" -> Test Scaffolds. "Test strategy/plan" or coverage < 50% with no scaffolds asked -> Strategy Doc. **Two or more deliverables in one invocation** -> produce in order separated by `---`: Coverage Assessment, then Strategy Doc (if requested), then Test Scaffolds; never silently drop one. Default when unclear: Strategy Doc.

**Coverage Assessment:**

```markdown
## Laravel Test Coverage Assessment

**Stack:** PHP <version> / Laravel <version>
**Database:** MySQL <version> | PostgreSQL <version> | MariaDB <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Queue:** redis (Horizon) | database | sync (testing)
**Test framework:** Pest | PHPUnit + factories + RefreshDatabase + facade fakes (Queue / Event / Notification / Mail / Bus / Storage / Http)

**Coverage gaps:**

- **Unit tests:** [pure logic / validators / value objects without coverage]
- **Feature tests:** [endpoints without tests; endpoints missing 401/403/validation paths]
- **DB-engine mismatch:** [SQLite for a MySQL app]
- **Auth tests:** [endpoints without auth tests; missing Sanctum / Passport ability scope tests]
- **Mass-assignment tests:** [controllers using `Model::create($request->all())` without a test asserting privileged fields stripped]
- **Web hazard tests:** [IDOR / per-owner triples missing; open redirect without allowlist; file upload without path-traversal/MIME/size; bulk export without scoping/row-cap; SSRF without allowlist; privilege-escalation guards untested; webhook signature untested]
- **Job tests:** [jobs without tests; without idempotency/retry; missing `failed()`]
- **Policy tests:** [Policies without passing / denied tests]

**Recommended pyramid balance:** Unit [count] / Feature [count] / Job + Policy [count] / Dusk [keep small]

**Prioritization** _(include when coverage is below ~50% or > 5 gaps)_ - apply Step 8 bands P1..P5, listing concrete targets per band.
```

**Test Scaffolds:** ready-to-run PHP test files matching project conventions from Step 3 (Pest `it(...)` or PHPUnit class-based per Step 2). Each must use the right test type, parameterize variants (Pest `with(...)` / PHPUnit `@dataProvider`), use factories with states (not `Model::create([...])`), and apply the Step 5/6 rules for its layer: feature scaffolds cover happy + 401 + 403 + validation-error against real MySQL/PostgreSQL with `RefreshDatabase`; auth via `actingAs(...)` / `Sanctum::actingAs(...)`; jobs run real `handle()` plus idempotency + retry + `failed()` when applicable; assert via `assertJsonValidationErrors`, `assertJsonPath`, `assertDatabaseHas`.

**Strategy Doc:**

```markdown
## Laravel Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Feature {y}% / Job + Policy {z}% / Dusk {w}%
**Tooling:** Pest, PHPUnit, factories, `RefreshDatabase`, facade fakes, Sanctum / Passport helpers, `php artisan test`, `composer phpstan`, `vendor/bin/pint --test`
**Database isolation:** real MySQL/PostgreSQL via `phpunit.xml` env override; `RefreshDatabase` per-test transactional rollback
**CI:** `php artisan test --parallel --coverage --min=80`; `composer phpstan`; `composer audit`; `vendor/bin/pint --test`
**Gaps to close (prioritized):**

1. [Highest risk - typically authorization or data integrity]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation (Step 1)
- [ ] Stack confirmed PHP/Laravel; database, auth, queue, test framework recorded (Step 2)
- [ ] Code under test + representative existing tests + setup files read directly (Step 3)
- [ ] `laravel-testing-patterns` consulted for canonical patterns (Step 5)
- [ ] Auth approach explicit (`actingAs($user)` session; `Sanctum::actingAs($user, [scopes])` token)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage, no out-of-scope tests)
- [ ] SDK-bypass note applied when external SDKs (Stripe / AWS / Twilio) are in scope

**Strategy Doc / Coverage Assessment only:**

- [ ] Pyramid mapped to Laravel idioms (Step 4); boundaries clearly defined, no duplicated assertions across layers (Step 6)
- [ ] Prioritization by risk applied when coverage is low - P1..P5; multi-band rule applied (file at highest band, secondary noted) (Step 8)
- [ ] Multi-deliverable invocations produce sections in order Coverage Assessment -> Strategy Doc -> Test Scaffolds, separated by `---`, with scaffolds targeting the top priority band first (Step 8 / Output Format)
- [ ] Real MySQL/PostgreSQL recommended; SQLite flagged for prod-MySQL/PostgreSQL apps (Step 9)
- [ ] `composer phpstan` / `vendor/bin/pint --test` / `composer audit` CI presence flagged when missing (Step 9)

**Test Scaffolds only:**

- [ ] Parameterized (Pest `with(...)` / PHPUnit `@dataProvider`), not copy-pasted; factories with states, not `Model::create([...])`
- [ ] Feature scaffolds: happy + 401 + 403 + validation-error; IDOR for per-owner/per-tenant resources; extend `Tests\TestCase` so middleware matches `bootstrap/app.php`
- [ ] DB-touching scaffolds use `RefreshDatabase` against real MySQL/PostgreSQL
- [ ] Job scaffolds: idempotency + retry + `failed()`; real `handle()` for non-trivial jobs
- [ ] Pest `it(...)` for Pest projects; PHPUnit class-based for legacy (per Step 2)

**Review-existing-tests mode only:**

- [ ] Test type matches surface (per Step 5); parameterized not copy-pasted; every endpoint has happy + 401 + 403 + validation-error; every Policy method has passing + denied
- [ ] Real MySQL/PostgreSQL (not SQLite); `Http::preventStrayRequests()` in bootstrap; no `sleep()`, `dd()`, `dump()`
- [ ] No `Mockery::mock(InMemoryRepo::class)` when a feature test could assert real DB state; no `Queue::fake` masking at-least-once/retry on critical jobs; no Dusk for what feature tests could cover

## Avoid

- Scaffolding without first reading existing tests + setup files - imports wrong base class, uses wrong factory, duplicates the test base
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Separate `it(...)` per case when Pest `with(...)` would do
- Dusk E2E for what a feature test could cover
- SQLite in feature tests for prod-MySQL/PostgreSQL apps - skips FK enforcement, JSON path, FULLTEXT, generated columns, concurrent updates; tests pass, prod fails
- Bypassing middleware (controller-direct-call) - validation and auth differ between test and prod silently; duplicating factories per project instead of sharing via `database/factories/`
- `Mockery::mock(OrderRepository::class)->shouldReceive('find')->andReturn($model)` when a feature test could assert real DB state
- Mocking auth middleware to silence Form Request failures - test is now wrong for the prod config
- Skipping Form Request unit tests because the controller has a feature test - validators are reused
- Testing framework internals (routes match, middleware runs) - test wiring, not the framework
- `Queue::fake` as a substitute for a real `handle()` test on non-trivial jobs - masks at-least-once / DLQ semantics
- `Mockery::mock(...)->shouldReceive(...)->andReturn(null)` to silence type errors - use the right typed return
- `sleep(N)` for async waits - use `Queue::fake` + `Queue::assertPushed`, `Bus::assertDispatched`, or inline processing
- `dd()` / `dump()` in test files
- PHPUnit class-based syntax for new tests in a Pest-using project
