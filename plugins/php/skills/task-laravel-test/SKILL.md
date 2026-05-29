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

Laravel-aware test strategy and scaffolding (Pest primary, PHPUnit legacy) with real MySQL/PostgreSQL, `RefreshDatabase`, model factories, HTTP feature tests, facade fakes, and Sanctum/Passport helpers. Stack-specific delegate of `task-code-test` for PHP / Laravel.

## When to Use

- Designing a test strategy for a new Laravel service / module
- Assessing test coverage gaps across feature / unit / job / Policy layers
- Scaffolding tests for under-covered controllers, services, jobs, Policies, or auth code
- Reviewing test pyramid balance for a Laravel app
- Adding boundary tests (validation, authorization, error paths) to existing happy-path tests

**Not for:** Test failure debugging (`task-laravel-debug`); general code review (`task-code-review` / `task-laravel-review`); production incident postmortems (`/task-oncall-postmortem`).

## Rules

- **Real MySQL/PostgreSQL, not SQLite.** SQLite skips FK enforcement, JSON path queries, FULLTEXT, generated columns, concurrent updates. SQLite-for-MySQL-app is `[High]` regardless of pass/fail.
- Pyramid: many unit + feature, few Dusk. Prefer feature over unit for any framework-touching code.
- Feature tests via `$this->postJson(...)` against `Tests\TestCase` (bypassing routes/middleware is `[High]`).
- Job idempotency tests assert side-effect call count, not final state. Real `handle()` is the path; `Queue::fake` masks the handler.
- `Http::preventStrayRequests()` in `Tests\TestCase::setUp` so unfaked outbound requests fail.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Governs every subsequent step.

### Step 2 - Confirm Stack and Detect Test Framework

Use skill: `stack-detect` to confirm PHP / Laravel. If not Laravel, route to `/task-code-test`.

Detect: test framework (Pest if `tests/Pest.php` and `pestphp/pest`; else PHPUnit), ORM, auth (Sanctum / Passport / session), queue, DB engine. Record `Tests Framework`, `Database`, `Auth`, `Queue`.

### Step 3 - Read the Code Under Test and Existing Tests

- Production code: controllers, Form Requests, models, services, actions, jobs, Policies
- Existing tests: one each of controller/feature, service/unit, job, Policy; plus `tests/TestCase.php`, `tests/Pest.php`, `database/factories/*.php`
- `phpunit.xml` env config - critical: `DB_CONNECTION` matches prod engine; `QUEUE_CONNECTION=sync`, `CACHE_DRIVER=array`, `MAIL_MAILER=array`
- `composer.json` test deps (`pestphp/pest`, `pestphp/pest-plugin-laravel`, `mockery/mockery`, `fakerphp/faker`, `nunomaduro/larastan`) and `scripts`
- `bootstrap/app.php` for middleware order

**Greenfield defaults** (state choice with one-line rationale):

| Decision           | Default                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------- |
| Test layout        | `tests/Feature/` (HTTP via `TestCase`); `tests/Unit/` (no app boot); `tests/Feature/{Jobs,Policies}/` |
| Test framework     | Pest                                                                                     |
| HTTP harness       | `$this->getJson(...)` / `postJson(...)`; `actingAs($user)`                               |
| DB strategy        | Same engine as prod via Docker; `RefreshDatabase`                                        |
| Mock library       | Mockery; facade fakes for dispatch                                                       |
| Test-data library  | Eloquent factories under `database/factories/` + `fakerphp/faker`                        |
| HTTP stub          | `Http::fake([...])`; never real network in CI                                            |
| Auth helper        | `actingAs($user)` (session); `Sanctum::actingAs($user, [scope])` (token)                 |
| Runner             | `php artisan test --parallel --coverage --min=80`                                        |

### Step 4 - Laravel Test Pyramid

| Layer       | Tooling                                                                          | What belongs here                                                              |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | Pest / PHPUnit (no `RefreshDatabase`, no app boot)                              | Pure domain logic, validators, mappers, calculation rules, value objects       |
| Feature     | Pest / PHPUnit + `RefreshDatabase` + real DB                                    | Controllers, Form Requests, Policies, services with DB I/O                     |
| Job         | Pest / PHPUnit + `RefreshDatabase`; `Queue::fake` for dispatch tests             | Background-worker happy path, retry, idempotency, scheduled commands           |
| E2E         | Laravel Dusk OR HTTP-only feature tests (preferred)                              | Critical user journeys only - signup, checkout, payment                        |
| Contract    | `dedoc/scramble`, Pact                                                           | API contract validation against schema                                         |

"Feature test" in Laravel covers what other ecosystems call integration/API test - boots the full app, exercises the HTTP pipeline, asserts response and DB state.

### Step 5 - Apply Laravel Test Patterns

Canonical Pest/PHPUnit patterns live in `laravel-testing-patterns`. Load it for scaffolds. Strategy-side rules:

- **Test type matches surface.** Unit = no `RefreshDatabase`, no app boot. Feature = full HTTP via `$this->getJson/postJson` with real DB. Job = real `handle()` for handler logic + `Queue::fake` for dispatch (never mix). Policy = standalone or via `$user->can(...)`.
- **One test per `(method, path, principal-state, outcome)` triple** for endpoints; per-protected-endpoint trio: anonymous -> 401, wrong-user -> 403, owner -> 200.
- **Parameterized over copy-pasted.** Pest `with(...)` or PHPUnit `@dataProvider`.
- **SDK-direct calls bypass `Http::fake`.** Stripe / AWS / Twilio SDKs construct their own Guzzle client. Mock the SDK via Mockery or wrap behind a thin service.
- **CI runs all four**: `php artisan test`, `composer phpstan` (Larastan L5+), `vendor/bin/pint --test`, `composer audit`.

### Step 6 - Test Boundaries

**Unit:** pure functions / value objects / DTOs / readonly classes; calculation rules.

**Feature:** every controller action (happy + 401 + 403 + validation-error); **IDOR / per-owner / per-tenant resources** (anonymous -> 401, other-user -> 403, owner -> 200); pagination contract; filter/sort/search params (especially allowlisted `sort` columns); exception -> HTTP status mapping.

**Web hazard tests** (when action shape signals the risk - file only the hazards whose signal fires):

| Hazard                | Signal                                                                                 | Test to add                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| IDOR                  | Route `{model}` -> user-owned resource lookup or mutation                              | Owner / other-user / anonymous trio per endpoint                                                  |
| Mass assignment       | `Model::create($request->all())` or `update($request->all())`                          | Submit payload with privileged field (`role`, `user_id`, `is_admin`); assert ignored             |
| Open redirect         | `redirect($userInput)` or 30x to a request-derived URL                                 | Allowlist enforcement: reject `//evil.com`, schemes, encoded forms                                |
| File upload           | `$request->file()` or path joining `userFilename`                                      | Path traversal, magic-byte vs `Content-Type` lie, size cap, extension allowlist                   |
| Bulk export           | Unpaginated `Order::all()`; `/admin/export` shape                                      | Authz + row-cap + tenant scoping                                                                  |
| SSRF                  | `Http::get($userUrl)` / outbound HTTP with request-derived host                        | Allowlist rejects metadata IP, loopback, RFC1918, link-local                                      |
| Privilege escalation  | `UpdateUser` / role/permission mutations                                               | Non-admin cannot self-promote; admin can; role change requires Policy guard                       |
| Webhook signature     | POST endpoint accepting third-party webhook                                            | Reject wrong/missing signature; reject replayed events (event-ID idempotency)                     |

These belong in feature tests, not unit. **Web hazards default to Step 8 band P1.**

**Policy:** every method (passing + denied + edge cases like admin override), standalone or via `$user->can(...)`.

**Job / queue:** every Job / Listener with non-trivial `handle()` (happy + retry + idempotency + `failed()`); scheduled commands at least one happy-path via `$this->artisan('command:name')`.

**No test needed:** framework behavior (routing, middleware dispatch); generated boilerplate (no-logic API Resources, single-field accessors); trivial delegation.

### Step 7 - Test Data and Fixtures

- Eloquent factories with states (`User::factory()->admin()->withOrders(3)->create()`) over hand-rolled `User::create([...])`
- Factory relationships: `Order::factory()->for(User::factory())->has(OrderItem::factory()->count(3))`
- Fresh per test under `RefreshDatabase`
- Minimal and focused - 100-row factory loops signal integration/load-test layer

### Step 8 - Prioritization (when coverage is low)

If coverage is below ~50%, **run before scaffolding** - determines which tests come first.

**P1 - Authorization & authentication:**
- Per-protected-endpoint trio: 401 anonymous + 403 wrong-user + 200 owner
- Sanctum / Passport ability-scope tests
- Policy methods unit-tested
- Form Request `authorize()` (returns false for wrong user)

**P2 - Data integrity:**
- Feature tests for non-trivial queries (filters, joins, multi-tenant scoping)
- Service / job tests for write operations (one happy + one rollback per write)
- Idempotency tests for side-effecting jobs
- Mass-assignment tests (privileged field ignored)

**P3 - Business-critical flows:** revenue paths, state transitions, scheduled billing jobs.

**P4 - High-churn code:** `git log --since="3 months ago" --grep="fix"`.

**P5 - Plumbing:** pass-through controllers, simple CRUD.

**Multi-band rule.** Target qualifying for multiple bands files at the **highest** band (lowest number), secondary noted.

### Step 9 - Test Infrastructure Hygiene

- [ ] `phpunit.xml` `DB_CONNECTION` matches prod engine
- [ ] Test env overrides only what differs from prod; never silently disable auth
- [ ] No `sleep(N)` - use `Queue::assertPushed`, `Bus::assertDispatched`, or `Bus::dispatchSync(...)`
- [ ] `--coverage` with PCOV; per-package thresholds
- [ ] `php artisan test --parallel`; shared factory states in `database/factories/`

## Output Format

**Dispatch:** "what tests are missing?" / "review coverage" -> Coverage Assessment. "Write/scaffold tests for X" -> Test Scaffolds. "Test strategy/plan" or coverage < 50% with no scaffolds asked -> Strategy Doc. **Multiple deliverables** -> produce in order separated by `---`: Coverage Assessment, then Strategy Doc, then Test Scaffolds.

**Coverage Assessment:**

```markdown
## Laravel Test Coverage Assessment

**Stack:** PHP <version> / Laravel <version>
**Database:** MySQL <version> | PostgreSQL <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Queue:** redis (Horizon) | database | sync (testing)
**Test framework:** Pest | PHPUnit + factories + RefreshDatabase + facade fakes

**Coverage gaps:**

- **Unit tests:** [pure logic / validators / value objects without coverage]
- **Feature tests:** [endpoints without tests; missing 401/403/validation paths]
- **DB-engine mismatch:** [SQLite for a MySQL app]
- **Auth tests:** [endpoints without auth tests; missing ability scope tests]
- **Mass-assignment tests:** [controllers using `Model::create($request->all())` without privileged-fields-stripped test]
- **Web hazard tests:** [only firing hazards from Step 6 table]
- **Job tests:** [jobs without tests; without idempotency/retry; missing `failed()`]
- **Policy tests:** [Policies without passing / denied tests]

**Recommended pyramid balance:** Unit [count] / Feature [count] / Job + Policy [count] / Dusk [keep small]

**Prioritization** _(when coverage < 50% or > 5 gaps)_: apply Step 8 bands P1..P5.
```

**Test Scaffolds:** ready-to-run PHP test files matching project conventions from Step 3. Each uses the right test type, parameterizes variants, uses factories with states, applies Step 5/6 rules:

- Feature: happy + 401 + 403 + validation-error against real MySQL/PostgreSQL with `RefreshDatabase`; auth via `actingAs(...)` / `Sanctum::actingAs(...)`
- Job: real `handle()` + idempotency call-count + retry + `failed()`
- Policy: every method with passing + denied
- Assertions: `assertJsonValidationErrors`, `assertJsonPath`, `assertDatabaseHas`

**Strategy Doc:**

```markdown
## Laravel Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Feature {y}% / Job + Policy {z}% / Dusk {w}%
**Tooling:** Pest, PHPUnit, factories, `RefreshDatabase`, facade fakes, Sanctum / Passport helpers
**Database isolation:** real MySQL/PostgreSQL via `phpunit.xml` env override; `RefreshDatabase` per-test rollback
**CI:** `php artisan test --parallel --coverage --min=80`; `composer phpstan`; `composer audit`; `vendor/bin/pint --test`
**Gaps to close (prioritized):**

1. [Highest risk - typically authorization or data integrity]
2. [...]
```

## Self-Check

- [ ] `behavioral-principles` loaded (Step 1)
- [ ] Stack confirmed PHP/Laravel; database, auth, queue, test framework recorded (Step 2)
- [ ] Code under test + representative existing tests + setup files read directly (Step 3)
- [ ] `laravel-testing-patterns` consulted for canonical patterns (Step 5)
- [ ] Auth approach explicit (`actingAs($user)` session; `Sanctum::actingAs($user, [scopes])` token)
- [ ] Spec-aware mode honored when `--spec` was passed
- [ ] SDK-bypass note applied when external SDKs (Stripe / AWS / Twilio) are in scope

**For Strategy Doc / Coverage Assessment:**

- [ ] Pyramid mapped to Laravel idioms (Step 4); boundaries clear (Step 6)
- [ ] Prioritization by risk applied when coverage is low; multi-band rule applied (Step 8)
- [ ] Real MySQL/PostgreSQL recommended; SQLite flagged for prod-MySQL apps (Rules)
- [ ] `composer phpstan` / `vendor/bin/pint --test` / `composer audit` CI presence flagged when missing

**For Test Scaffolds:**

- [ ] Parameterized (Pest `with(...)` / PHPUnit `@dataProvider`), not copy-pasted
- [ ] Factories with states, not `Model::create([...])`
- [ ] Feature scaffolds: happy + 401 + 403 + validation-error; IDOR for per-owner/per-tenant resources; extend `Tests\TestCase`
- [ ] DB-touching scaffolds use `RefreshDatabase` against real MySQL/PostgreSQL
- [ ] Job scaffolds: idempotency call-count + retry + `failed()`; real `handle()`
- [ ] Pest `it(...)` for Pest projects; PHPUnit class-based for legacy (per Step 2)

## Avoid

- Scaffolding without reading existing tests + setup files - wrong base class, wrong factory
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Separate `it(...)` per case when Pest `with(...)` would do
- Dusk E2E for what a feature test could cover
- Bypassing middleware (controller-direct-call) - validation and auth differ between test and prod silently
- `Queue::fake` as a substitute for a real `handle()` test on non-trivial jobs - masks at-least-once / DLQ semantics
- Mocking auth middleware to silence Form Request failures
- `sleep(N)` for async waits
- `dd()` / `dump()` in test files
- PHPUnit class-based syntax for new tests in a Pest-using project
