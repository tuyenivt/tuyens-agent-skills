---
name: task-dotnet-test
description: ".NET / ASP.NET Core test plan and scaffolds: xUnit, WebApplicationFactory, Testcontainers, NSubstitute, FluentAssertions, Respawn."
agent: dotnet-test-engineer
metadata:
  category: backend
  tags: [dotnet, aspnet-core, testing, xunit, webapplicationfactory, testcontainers, nsubstitute, fluentassertions, workflow]
  type: workflow
user-invocable: true
---

# .NET Test

Stack-specific delegate of `task-code-test` for .NET. Preserves the parent's output shape.

## When to Use

- Test strategy for a new .NET / ASP.NET Core service or module
- Coverage-gap assessment across unit / integration / API / job layers
- Scaffolding tests for controllers, handlers, repositories, jobs
- Adding boundary tests (auth, validation, error paths) to happy-path coverage

**Not for:** test debugging (`task-dotnet-debug`), code review (`task-dotnet-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Stack detect and spec mode

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If not .NET, stop and route to `/task-code-test`. If parent already detected, skip.

If `--spec <slug>` or `.specs/<slug>/spec.md` exists, Use skill: `spec-aware-preamble`. With a spec loaded: generate one test per AC (tag `// Satisfies: AC<N>` or `[Fact(DisplayName = "AC1: ...")]`), cover every NFR from `plan.md`, refuse out-of-scope tests. Never edit spec artifacts; surface gaps as proposed amendments.

Record for output: `Data Access` (EF Core / Dapper / mixed), `Mediator` (MediatR / none), `Messaging` (MassTransit / Hangfire / Channel / none), `Mock Framework` (NSubstitute / Moq), `Assertion Library`, `Test-Data Library`.

### Step 3 - Read code and existing tests

Ground output in real conventions. Read:

- Production code in scope: public types, request/response records, transaction boundaries, collaborators
- `Program.cs`: middleware order the test factory must replicate (auth, exception handler, telemetry)
- A sample of existing tests: one controller, one handler, one repository, one worker; plus `tests/<Project>.Tests/Common/*.cs` and `Fixtures/*.cs`
- `.csproj`, `Directory.Packages.props` (CPM), CI workflow for `dotnet test` / `dotnet format --verify-no-changes`

If no tests exist, propose conventions explicitly (one-line rationale each):

| Decision          | Default                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| Layout            | `tests/<Project>.UnitTests` + `tests/<Project>.IntegrationTests`; one per `src/<Project>` assembly |
| Framework         | xUnit; `[Fact]` single, `[Theory]` + `[InlineData]`/`[MemberData]` parameterized                   |
| Async             | `public async Task` (never `void`)                                                                 |
| API harness       | `WebApplicationFactory<TEntryPoint>`                                                               |
| DB                | Testcontainers Postgres/SqlServer via `IAsyncLifetime`; per-test reset via Respawn or tx rollback  |
| Mocks / data      | NSubstitute; Bogus `Faker<T>`                                                                      |
| Assertions        | FluentAssertions                                                                                   |
| Runner / lint     | `dotnet test`; `dotnet format --verify-no-changes`; `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` |
| Coverage          | `coverlet.collector` + ReportGenerator                                                             |

### Step 4 - Test pyramid

| Layer       | Tooling                                                          | Belongs                                                         |
| ----------- | ---------------------------------------------------------------- | --------------------------------------------------------------- |
| Unit        | xUnit + NSubstitute                                              | Handlers (mocked deps), domain, validators, mappers             |
| Integration | xUnit + Testcontainers + real `DbContext`/Dapper                 | Repository queries, DB invariants, migration smoke              |
| API         | `WebApplicationFactory<Program>` + `HttpClient` + Testcontainers | Routing, binding, validation, middleware, full pipeline         |
| Job         | In-process OR Testcontainers broker + real consumer              | Worker happy path, retry, idempotency, scheduled behavior       |
| E2E         | `WebApplicationFactory` + full app + broker                      | Critical journeys only (signup, checkout, payment)              |

Many unit, some API/integration, few E2E.

### Step 5 - Apply .NET test patterns

**Unit (`tests/<Project>.UnitTests/<Feature>/<Class>Tests.cs`):**
- One test method per outcome (happy / validation / external fail / edge); class per SUT
- No DI container, no `WebApplicationFactory`, no `DbContext` - if needed, the test is misclassified
- NSubstitute at interface boundaries; HTTP stubs via `WireMock.Net` or `RichardSzalay.MockHttp`
- FluentAssertions: `actual.Should().BeEquivalentTo(expected, o => o.Excluding(x => x.UpdatedAt));`

```csharp
var repo = Substitute.For<IOrderRepository>();
repo.SaveAsync(Arg.Any<Order>(), Arg.Any<CancellationToken>())
    .Returns(c => c.Arg<Order>() with { Id = Guid.NewGuid() });
var result = await new PlaceOrderHandler(repo).Handle(cmd, default);
result.OrderId.Should().NotBeEmpty();
```

**Parameterized:** `[InlineData]` for primitives, `[MemberData]` for complex types. Each case gets its own discovered name.

```csharp
[Theory]
[InlineData(0, 0)] [InlineData(10, 10)] [InlineData(100, 95)]
public void CalculateTotal_AppliesTier(decimal subtotal, decimal expected)
    => OrderPricing.CalculateTotal(subtotal).Should().Be(expected);
```

**API (`WebApplicationFactory<Program>`):** Use `IClassFixture<WebApplicationFactory<Program>>` + `factory.WithWebHostBuilder(...)` to override DbContext (Testcontainers connection) and auth (test JWT issuer or test `IAuthenticationHandler` injecting claims). Build with the **same global middleware as `Program.cs`** - skipping auth middleware masks authorization bugs.

Per endpoint: happy + `401` anonymous + `403` wrong-role + validation-error. Response shape: assert status, key fields, `Content-Type`, headers.

**Anti-pattern - controller-direct-call:** `var c = new OrdersController(...); await c.Create(req);` bypasses model binding, `[ApiController]` validation, `[Authorize]`, `IExceptionHandler`, middleware. Treat as `[High]` test-design finding. Use `_client.PostAsync(url, content)`.

**Repository / EF Core integration (Testcontainers):**
- Use `Testcontainers.PostgreSql` / `.MsSql`. **Never** `UseInMemoryDatabase` or SQLite for a Postgres/SqlServer app - the in-memory provider skips FK enforcement, raw SQL, JSON, concurrency semantics. If a test calls `UseInMemoryDatabase` and prod references Npgsql/SqlServer EF Core, raise `[High]` even on green
- Share via `IClassFixture<PostgresFixture>` (or `ICollectionFixture<>` cross-class); per-test container creation dominates suite runtime
- Per-test isolation: transactional rollback (`await using var tx = await db.Database.BeginTransactionAsync();` no commit) or Respawn (`await _respawner.ResetAsync(connection)`)
- Run `await db.Database.MigrateAsync()` in fixture init
- Assert SQL semantics (filter, sort, JOIN) - not "returns something". For unique/FK violations, assert `DbUpdateException` with inner `PostgresException.SqlState`

**FluentValidation:** `validator.TestValidate(req).ShouldHaveValidationErrorFor(x => x.Email);` - faster than full handler tests.

**Background workers / MassTransit / Hangfire:**
- In-process invocation for handler logic; no broker
- `BackgroundService`: assert (a) `ExecuteAsync` exits within `HostOptions.ShutdownTimeout` when `stoppingToken` fires, and (b) one full iteration completes first. Catches `while(true){ Thread.Sleep(N); }` loops that ignore the token
- `InMemoryTestHarness` for MassTransit consumer wiring; Testcontainers RabbitMQ/Kafka for real retry/ack/redelivery
- Required cases on side-effect jobs: idempotency, retry-then-succeed, DLQ/max-retries termination

### Step 6 - Test boundaries

**Unit:** handlers, domain, validators, mappers, custom middleware delegate, concurrent helpers (`Channel<T>`, `Parallel.ForEachAsync`).

**API:** every endpoint with happy + 401 + 403 + validation; IDOR triple for `{id}`-owned resources; pagination, filter/sort, custom `IExceptionHandler` mapping.

**Integration:** every non-trivial repository query; DB constraints; migration smoke; EF Core global query filters (assert tenant isolation actually works).

**Job:** every consumer/job with retry, idempotency, or external side effects; post-commit dispatch (outbox tests).

**Skip:** framework internals (routing, model binding, `[ApiController]` validation), getters, trivial pass-through delegation.

**Web hazards** (default to P1 risk band; security guard at endpoint boundary):

| Hazard               | Action shape signal                                            | Test                                                              |
| -------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------- |
| IDOR                 | Route `{id}` -> owned resource                                 | owner / other-user / anonymous trio                               |
| Open redirect        | `Redirect(userInput)` / request-derived 30x                    | `Url.IsLocalUrl` or domain allowlist; reject `//evil.com`, schemes |
| File upload          | `IFormFile` or `Path.Combine(_, userName)`                     | path traversal, magic-byte vs `Content-Type`, size cap, atomic write |
| Bulk export          | unpaginated `ToListAsync()` / `/admin/export`                  | authz + row-cap + tenant scoping                                  |
| SSRF                 | `HttpClient.GetAsync(userUrl)`                                 | allowlist rejects metadata IP, loopback, RFC1918, link-local      |
| Privilege escalation | `UpdateUser`/`UpdateRole` touching role fields                 | non-admin cannot self-promote; explicit admin policy guard        |
| Command injection    | `Process.Start("cmd.exe", $"/c {input}")`                      | `ProcessStartInfo.ArgumentList.Add(...)`; reject metacharacters   |

### Step 7 - Test data and fixtures

- Bogus `Faker<T>` factories shared via `tests/<Project>.IntegrationTests/Fixtures` - not hand-rolled initializers, not duplicated per project
- Fresh `IServiceScope` / `DbContext` per test; never mutate shared state
- Test data minimal - 100-row `Enumerable.Range(...)` setups signal load-test, not unit-test

### Step 8 - Prioritization (when coverage is low)

If coverage is below ~50%, run this **before** scaffolding. Order by risk:

1. **P1 - Authz/authn:** 401/403 per protected endpoint; JWT middleware (issuer, audience, signature, expiry, algorithm allowlist); custom `AuthorizationHandler<,>`
2. **P2 - Data integrity:** repository integration tests; write-path rollback; worker idempotency; warnings-as-errors clean for concurrent code
3. **P3 - Business-critical:** revenue (checkout, billing), state machines, scheduled jobs touching billing/notifications
4. **P4 - High-churn:** files with recent commits or bug-fix history
5. **P5 - Plumbing:** pass-through controllers, simple CRUD

**Multi-band:** target qualifying for multiple bands files under the **lowest number**; the plan must cover both axes (a refund worker is P2+P3 - assert idempotency AND refund-amount invariants). Web hazards default to P1.

### Step 9 - Infrastructure hygiene

- [ ] Testcontainers shared via `IClassFixture<>` / `ICollectionFixture<>`
- [ ] Integration vs unit tests in separate projects (clean assembly boundary)
- [ ] Test environment overrides only what differs from prod; never disables auth middleware
- [ ] HTTP stubs via `WireMock.Net` / `MockHttp`; **every stub asserts call count > 0** (silent bypass is the worst failure mode)
- [ ] SDK bypass surfaces handled: AWS SDK (`ServiceURL`, `UseHttp`, explicit `BasicAWSCredentials`), Google Cloud (`*_EMULATOR_HOST` env vars), gRPC (`Grpc.Net.Client` needs HTTP/2 - use `WebApplicationFactory<TStartup>`), custom `SocketsHttpHandler`/typed `IHttpClientFactory` clients (replace primary handler via `ConfigurePrimaryHttpMessageHandler`)
- [ ] Non-HTTP doubles: `Papercut-SMTP` Testcontainer for `SmtpClient`; Testcontainers DB for `SqlClient`/`Npgsql`
- [ ] No `Thread.Sleep` for sync - use `TaskCompletionSource`, `Channel<T>` signaling, or await the actual handle
- [ ] `coverlet.collector` -> ReportGenerator; `[ExcludeFromCodeCoverage]` with rationale
- [ ] `dotnet list package --vulnerable` / `<NuGetAudit>true</NuGetAudit>` in CI
- [ ] `[Collection]` for tests sharing global state

## Output Format

Pick output by request shape:

- "what's missing?" / "review coverage" -> **Coverage Assessment**
- "write tests" / "scaffold" -> **Test Scaffolds**
- "test strategy" / "plan", or coverage <50% with no scaffolds asked -> **Strategy Doc**
- Multiple deliverables in one ask -> emit in order separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds. Do not drop one.
- Unclear -> default to Strategy Doc.

**Coverage Assessment:**

```markdown
## .NET Test Coverage Assessment

**Stack:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <v> | Dapper <v> | mixed
**Mediator:** MediatR <v> | none
**Messaging:** MassTransit | Hangfire | Channel | none
**Test framework:** xUnit, WebApplicationFactory<Program>, Testcontainers, NSubstitute, Bogus, FluentAssertions, Respawn

**Coverage gaps:**
- **Unit:** [handlers / validators / mappers without tests]
- **API:** [endpoints missing 401/403/validation paths]
- **Integration:** [repositories without Testcontainers tests; `UseInMemoryDatabase` for Postgres apps]
- **Auth:** [endpoints without authorization tests; JWT middleware untested; custom handlers untested]
- **Web hazards:** [IDOR triples; open redirect; file upload; bulk export scoping; SSRF; privilege escalation]
- **Jobs:** [workers without idempotency / retry tests]
- **Concurrency:** [async code tested single-threaded when it spawns cross-thread work]
- **Contracts:** [OpenAPI / Pact verification missing]

**Pyramid balance:** Unit [n] / API+Integration [n] / E2E [n - keep small]

**Prioritization** (include when coverage <50% or >5 gaps surface):
1. P1 - Authz/authn: [...]
2. P2 - Data integrity: [...]
3. P3 - Business-critical: [...]
4. P4 - High-churn: [...]
5. P5 - Plumbing: [...]
```

**Test Scaffolds** - ready-to-run C# files using project conventions. Each must include:

- Correct test type (unit / integration / API / job)
- Parameterized via `[Theory]` + `[InlineData]`/`[MemberData]` when input-driven
- Bogus `Faker<T>` for data
- API: happy + 401 + 403 + validation; IDOR triple for per-owner resources
- Repository: Testcontainers Postgres/SqlServer; per-test cleanup via Respawn or tx rollback
- Auth: anonymous + wrong-role + correct-role via test-issued JWT
- Jobs: idempotency + retry + max-retries when applicable
- `public async Task` methods; FluentAssertions; `dotnet format`-clean

**Strategy Doc:**

```markdown
## .NET Test Strategy

**Objective:** [what this achieves]
**Pyramid balance:** Unit {x}% / API+Integration {y}% / E2E {z}%
**Tooling:** xUnit, WebApplicationFactory<Program>, Testcontainers Postgres, NSubstitute, Bogus, FluentAssertions, Respawn
**Database isolation:** Testcontainers via `IClassFixture<PostgresFixture>`; per-test reset via Respawn or tx rollback
**Concurrency:** xUnit per-collection parallelism; `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` in CI
**Gaps to close (prioritized):**
1. [highest-risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed as .NET; data-access/mediator/messaging recorded; spec mode honored if `--spec` was passed (one test per AC, no out-of-scope tests)
- [ ] Step 3: code under test and existing tests/fixtures read before scaffolding or strategy
- [ ] Step 4: pyramid balance matched to .NET layers; no duplicated assertions across layers
- [ ] Step 5: patterns applied per layer - unit isolated, API uses `WebApplicationFactory<Program>` with same middleware as `Program.cs`, repository uses Testcontainers (never `UseInMemoryDatabase` for Postgres/SqlServer apps), workers cover idempotency/retry/DLQ
- [ ] Step 6: every endpoint has happy + 401 + 403 + validation; IDOR triple for `{id}`-owned resources; web hazards triggered when action shape signals risk
- [ ] Step 7: Bogus `Faker<T>` used; no shared mutable state; data minimal
- [ ] Step 8: prioritization applied when coverage <50% - P1 authz, P2 data, P3 business, P4 churn, P5 plumbing; multi-band targets filed under lowest number
- [ ] Step 9: infra hygiene satisfied - shared Testcontainers, HTTP stubs assert call count >0, SDK bypass surfaces verified, no `Thread.Sleep`; output uses `public async Task` + FluentAssertions; `dotnet format --verify-no-changes` clean

## Avoid

- Scaffolding before reading existing tests/fixtures - imports the wrong factory or duplicates the integration base
- Chasing coverage percentage over risk - 100% line coverage with no auth tests misses the bigger threat
- Copy-pasted `[Fact]`s where `[Theory]` + `[InlineData]` fits
- `UseInMemoryDatabase`/SQLite for Postgres or SqlServer apps - FK skipped, raw SQL skipped, JSON/concurrency diverge; green tests, prod fails
- Controller-direct-call tests instead of `WebApplicationFactory` - skips binding, validation, auth, middleware
- `WebApplicationFactory` without `Program.cs`'s global middleware - auth and validation differ silently
- NSubstitute mocks of repositories when Testcontainers could assert real DB state
- Mocking auth middleware to silence DTO failures - test now misrepresents prod
- In-process job mocks for non-trivial retry/ack jobs - masks at-least-once and DLQ semantics
- E2E (full stack + broker) for what an API test covers - context cost compounds
- `void` test methods (swallow exceptions); `Thread.Sleep` for async sync (flaky, slow)
- `Mock<T>().Setup(...).ReturnsAsync(default!)` to silence type errors - use the right typed return
- HTTP stubs without asserting call count > 0 - silent bypass is the worst failure mode
