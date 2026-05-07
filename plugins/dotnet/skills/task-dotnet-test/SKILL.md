---
name: task-dotnet-test
description: .NET test strategy and scaffolding using xUnit `[Fact]` / `[Theory]` for parametrized cases, `WebApplicationFactory<TEntryPoint>` for full HTTP integration tests, Testcontainers PostgreSQL via `Testcontainers.PostgreSql`, NSubstitute (or Moq) for interface mocks, Bogus `Faker<T>` for test data, FluentAssertions for assertion ergonomics, Respawn for DB reset between tests, and `dotnet test` / `dotnet format` / Roslyn analyzer discipline. Use when designing a test plan, assessing coverage gaps, or scaffolding controller / handler / repository / job tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to .NET / ASP.NET Core.
agent: dotnet-test-engineer
metadata:
  category: backend
  tags: [dotnet, aspnet-core, testing, xunit, webapplicationfactory, testcontainers, nsubstitute, bogus, fluentassertions, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or `[Fact(DisplayName = "AC1: ...")]`), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# .NET Test

## Purpose

.NET-aware test strategy and scaffolding using xUnit `[Fact]` / `[Theory]` (the canonical .NET test attributes) with `[InlineData(...)]` / `[MemberData(...)]` for parameterized cases, `WebApplicationFactory<TEntryPoint>` (from `Microsoft.AspNetCore.Mvc.Testing`) for full HTTP integration tests with the real DI container and pipeline, Testcontainers PostgreSQL / SQL Server (`Testcontainers.PostgreSql` / `Testcontainers.MsSql`) for repository tests, NSubstitute (preferred for new code; Moq for legacy compatibility) for interface mocks, Bogus `Faker<T>` for realistic test data, FluentAssertions for assertion ergonomics, Respawn for fast DB reset between tests, and `dotnet test` / `dotnet format` / Roslyn analyzer (`Microsoft.CodeAnalysis.NetAnalyzers`) discipline. Replaces the generic backend test patterns with .NET-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for .NET. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a test strategy for a new .NET / ASP.NET Core service / module
- Assessing test coverage gaps across unit / integration / API / job layers
- Scaffolding tests for under-covered controllers, handlers, repositories, or auth code
- Reviewing test pyramid balance for a .NET app
- Adding boundary tests (validation, authorization, error paths) to existing happy-path tests

**Not for:**

- Test failure / exception debugging (use `task-dotnet-debug`)
- General code review (use `task-code-review` / `task-dotnet-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If the detected stack is not .NET, stop and tell the user to invoke `/task-code-test` instead.

Detect data access (EF Core / Dapper / mixed), mediator (MediatR / none), and messaging (MassTransit / Hangfire / Channel / none). Detect mock framework (`NSubstitute`, `Moq`, hand-written), assertion library (`FluentAssertions` / xUnit built-in), test-data library (`Bogus`, `AutoFixture`). Record `Data Access`, `Mediator`, `Messaging`, `Mock Framework`, `Assertion Library` for the output.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: `public` types, request / response records, middleware, transaction boundaries, external collaborators
- Glob `tests/**/*.cs` and look for `[Fact]` / `[Theory]` discovery; read at least: one existing controller test, one existing handler / service test, one existing repository test, one existing background-worker test (if applicable), `tests/<Project>.Tests/Common/*.cs` setup files - learn the project's test layout, mock strategy (NSubstitute vs Moq), HTTP-stub library (`WireMock.Net` vs `RichardSzalay.MockHttp`), authentication helpers
- Read `tests/<Project>.Tests/<Project>.Tests.csproj` for the `[dev-dependencies]` equivalent (`<PackageReference>` entries for xUnit, FluentAssertions, NSubstitute / Moq, Testcontainers, Bogus, WebApplicationFactory)
- Read `Directory.Packages.props` (CPM) for centralized package versions
- Read `Makefile` / `nuke` / `Cake` build script / `.github/workflows/*.yml` for `dotnet test` invocation, `dotnet format --verify-no-changes`, integration-test segregation (`tests/*.IntegrationTests` vs `tests/*.UnitTests` projects), `dotnet list package --vulnerable`
- Read `tests/<Project>.Tests/Fixtures/*.cs` (or equivalent) for shared fixtures (Testcontainers init via `IAsyncLifetime`, fake JWT issuer, factory utilities)
- Read `Program.cs` for middleware order that `WebApplicationFactory` tests must replicate (auth, exception handler, telemetry)

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently. Greenfield convention list (state your choice for each, with a one-line rationale):

| Decision           | Default to propose                                                                                  |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| Test layout        | Unit tests in `tests/<Project>.UnitTests`; integration / API tests in `tests/<Project>.IntegrationTests`; one project per `src/<Project>` assembly |
| Test framework     | xUnit (Microsoft's recommended path); `[Fact]` for single cases, `[Theory]` + `[InlineData]` / `[MemberData]` for parameterized |
| Async test form    | All test methods `public async Task` (xUnit's native async support); never `void` test methods      |
| API harness        | `WebApplicationFactory<TEntryPoint>` over a custom test server for greenfield                       |
| DB strategy        | Testcontainers PostgreSQL (or SQL Server) via `IAsyncLifetime` shared per fixture / collection; per-test reset via Respawn or transactional rollback |
| Mock library       | NSubstitute for new projects (cleaner syntax than Moq); Moq for legacy compatibility                |
| Test-data library  | Bogus `Faker<T>` for realistic data; `AutoFixture` only when complex object graphs justify it       |
| Assertion library  | FluentAssertions (`order.Status.Should().Be(OrderStatus.Placed)`) over xUnit's built-in `Assert.Equal` |
| Runner             | `dotnet test` (built-in); `dotnet test --logger "trx;LogFileName=results.trx"` for CI artifacts     |
| Lint / format      | `dotnet format --verify-no-changes` mandatory in CI; warnings-as-errors via `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` |
| Coverage           | `coverlet.collector` (xUnit's default coverage collector) reporting to ReportGenerator              |
| Shared fixtures    | `tests/<Project>.IntegrationTests/Fixtures/*.cs` for Testcontainers init, JWT issuer, factory functions, `WebApplicationFactory<Program>` subclass |
| `[dev-dependencies]` | Bootstrap block: `xunit`, `xunit.runner.visualstudio`, `Microsoft.AspNetCore.Mvc.Testing`, `Testcontainers`, `Testcontainers.PostgreSql`, `NSubstitute`, `Bogus`, `FluentAssertions`, `coverlet.collector`, `Respawn` |

### Step 3 - .NET Test Pyramid

The .NET test pyramid maps to test types:

| Layer       | Tooling                                                                          | What belongs here                                                              |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | xUnit `[Fact]` / `[Theory]` + NSubstitute interface mocks                        | Domain logic, application handlers (with mocks), validators, mappers, calculation rules |
| Integration | xUnit + Testcontainers PostgreSQL + real EF Core `DbContext` / Dapper            | Repository queries, DB-level invariants, EF Core migration smoke               |
| API         | `WebApplicationFactory<Program>` + `HttpClient` + Testcontainers DB              | Routing, request / response binding, validation, middleware, full HTTP pipeline |
| Job         | In-process invocation OR Testcontainers (broker) + real consumer / job processor | Background-worker happy path, retry logic, idempotency, scheduled job behavior |
| E2E         | `WebApplicationFactory` + full app + Testcontainers (DB + broker)                | Critical user journeys only - signup, checkout, payment                        |
| Contract    | Pact .NET / OpenAPI consumer-driven (via `Swashbuckle` schema validation)        | API contract validation against schema                                         |

**Many** unit tests, **some** API / integration tests, **few** full E2E tests. `dotnet test` and `dotnet format --verify-no-changes` on every CI run.

### Step 4 - Apply .NET Test Patterns

**xUnit `[Fact]` for single cases (the canonical async test form):**

```csharp
public class PlaceOrderHandlerTests
{
    [Fact]
    public async Task Handle_ValidInput_ReturnsOrderId()
    {
        // Arrange
        var repo = Substitute.For<IOrderRepository>();
        repo.SaveAsync(Arg.Any<Order>(), Arg.Any<CancellationToken>())
            .Returns(call => call.Arg<Order>() with { Id = Guid.NewGuid() });
        var sut = new PlaceOrderHandler(repo);

        // Act
        var result = await sut.Handle(new PlaceOrderCommand(...), CancellationToken.None);

        // Assert
        result.OrderId.Should().NotBeEmpty();
        await repo.Received(1).SaveAsync(Arg.Is<Order>(o => o.CustomerId == ...), Arg.Any<CancellationToken>());
    }
}
```

**Parameterized tests via `[Theory]` + `[InlineData]` (when behavior varies by input):**

`[InlineData]` for primitives; `[MemberData]` for complex types; `[ClassData]` for shared parameter sets.

```csharp
public class CalculateTotalTests
{
    [Theory]
    [InlineData(0, 0)]
    [InlineData(10, 10)]
    [InlineData(100, 95)] // 5% discount over 50
    public void CalculateTotal_AppliesDiscountTier(decimal subtotal, decimal expected)
    {
        var actual = OrderPricing.CalculateTotal(subtotal);
        actual.Should().Be(expected);
    }

    public static IEnumerable<object[]> InvalidPayloadCases =>
        new[]
        {
            new object[] { new CreateOrderRequest(Quantity: 0, ...), "Quantity must be > 0" },
            new object[] { new CreateOrderRequest(CustomerId: Guid.Empty, ...), "CustomerId is required" },
        };

    [Theory]
    [MemberData(nameof(InvalidPayloadCases))]
    public async Task Validate_RejectsInvalidPayload(CreateOrderRequest req, string expectedError)
    {
        var validator = new CreateOrderValidator();
        var result = await validator.ValidateAsync(req);
        result.IsValid.Should().BeFalse();
        result.Errors.Should().Contain(e => e.ErrorMessage.Contains(expectedError));
    }
}
```

Failure messages cite the parameters automatically (xUnit's discovery names each case with the inline values).

**Unit tests (`tests/<Project>.UnitTests/<Feature>/<Class>Tests.cs`):**

- Test method per outcome (happy / validation failure / external failure / edge); class per System Under Test
- **No DI container, no `WebApplicationFactory`, no DB** in a unit test - if a unit test needs `WebApplicationFactory<Program>` or a `DbContext`, it is misclassified
- Stub external HTTP via `WireMock.Net` or `RichardSzalay.MockHttp` (returning canned responses); do not stub repositories with full SQL behavior - use Testcontainers for that
- NSubstitute for interface mocks at service boundaries: `var repo = Substitute.For<IOrderRepository>(); repo.GetAsync(id, Arg.Any<CancellationToken>()).Returns(order);`. Mock at trait/interface boundaries only (not at concrete classes)
- FluentAssertions for diff-rich failure output: `actual.Should().BeEquivalentTo(expected, options => options.Excluding(x => x.UpdatedAt));`

**API tests (`WebApplicationFactory<Program>`):**

```csharp
public class OrdersControllerTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;

    public OrdersControllerTests(WebApplicationFactory<Program> factory)
    {
        _client = factory.WithWebHostBuilder(b => b.ConfigureServices(services =>
        {
            // override real DbContext registration with Testcontainers connection
            // override IAuthenticationService for test JWT issuer
        })).CreateClient();
    }

    [Fact]
    public async Task GetById_AnonymousUser_Returns401()
    {
        var response = await _client.GetAsync($"/api/v1/orders/{Guid.NewGuid()}");
        response.StatusCode.Should().Be(HttpStatusCode.Unauthorized);
    }

    [Fact]
    public async Task GetById_OtherUser_Returns404OrForbid() { ... }

    [Fact]
    public async Task GetById_Owner_Returns200() { ... }
}
```

**Anti-pattern: controller-direct-call.** A test that does `var controller = new OrdersController(ctx, ...); var result = await controller.Create(req);` bypasses the entire ASP.NET Core pipeline - no model binding, no `[ApiController]` automatic validation, no `FluentValidation` filter, no `[Authorize]` attribute, no `IExceptionHandler`, no middleware, no `[FromBody]` parameter binding semantics. Such a test asserts only the action method body, not the endpoint behavior. The bug it is most likely to miss is the bug a real client would hit. For controller-shape tests use `WebApplicationFactory<Program>` and `_client.PostAsync(url, content)` so the test looks like an HTTP request, not a method call. Treat any new controller-direct-call test in a diff as a `[High]` test-design finding.

For full pipeline tests:

- Build the `WebApplicationFactory` with the **same global middleware** as `Program.cs` (exception handler, auth, telemetry, problem details) - missing auth middleware in tests masks authorization bugs
- One test per `(method, path, principal-state, outcome)` triple
- Authentication via test-issued JWT (a `TestJwtIssuer` shared fixture), OR a test-only `IAuthenticationHandler` that injects fixed claims into `HttpContext.User`
- Authorization: a separate test for "anonymous → 401" and "wrong role → 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any endpoint with a validated DTO body
- Response shape: assert key fields, status, headers, and `Content-Type`
- DB: configure the factory's DI to point `AppDbContext` at the Testcontainers DB; reset state per test via Respawn or transactional rollback (see Repository tests below)

**Repository / EF Core integration tests (Testcontainers):**

- Testcontainers PostgreSQL via `Testcontainers.PostgreSql` - **not SQLite, not in-memory `UseInMemoryDatabase()`** - the in-memory provider does not enforce relational constraints (FK violations succeed silently), does not support raw SQL, and diverges from PostgreSQL/SQL Server on JSON, transactions, and concurrent updates. **Detection rule:** if any test calls `optionsBuilder.UseInMemoryDatabase("...")` and the project's production `.csproj` references `Npgsql.EntityFrameworkCore.PostgreSQL` or `Microsoft.EntityFrameworkCore.SqlServer`, raise `[High]` regardless of whether the test passes - the test is exercising a different store than prod, so green tests provide false confidence rather than coverage
- Shared container per test class via `IClassFixture<PostgresFixture>` (or per assembly via `ICollectionFixture<>` for slower-but-isolated cross-class state) - per-test container creation (~3-5s startup) dominates suite runtime if duplicated
- Per-test isolation: either (a) `await using var tx = await _db.Database.BeginTransactionAsync(); ...` at test start without `CommitAsync` (EF Core auto-rolls back on dispose); or (b) `Respawn` to truncate / reset between tests - `_respawner = await Respawner.CreateAsync(connection, new RespawnerOptions { DbAdapter = DbAdapter.Postgres });` then `await _respawner.ResetAsync(connection)` per test
- Run EF Core migrations against the testcontainer in fixture init (`await db.Database.MigrateAsync()`)
- One test per non-trivial query: assert SQL semantics (filter correctness, sort order, JOIN result), not just "method returns something"
- Custom indexes / constraints: insert violating data and assert the right exception type (`DbUpdateException` with inner `PostgresException` whose `SqlState` is `23505` for unique violation)

**FluentValidation tests:**

- Use `validator.TestValidate(req)` (from `FluentValidation.TestHelper`) for per-rule assertions: `result.ShouldHaveValidationErrorFor(x => x.Email)` - faster than going through a full handler test
- Edge cases: missing required fields, wrong types via JSON deserialization, out-of-range values, custom validators

**Background-worker / MassTransit / Hangfire tests:**

- **In-process for fast tests**: invoke the handler / consumer method directly with a constructed payload; no broker. Best for handler logic
- **`BackgroundService` cancellation test**: the worker is a singleton with an `ExecuteAsync(CancellationToken stoppingToken)` loop. Test (a) the loop exits within `HostOptions.ShutdownTimeout` when the host's cancellation source fires, and (b) at least one full iteration completes before cancellation. Pattern: `using var cts = new CancellationTokenSource(); var task = sut.StartAsync(cts.Token); await Task.Delay(...); cts.Cancel(); await sut.StopAsync(CancellationToken.None);` then assert the side effect happened once and the task completes within the timeout. This catches `while (true) { ... Thread.Sleep(N); }` loops that ignore `stoppingToken` - they hang the shutdown
- **MassTransit `InMemoryTestHarness`** for consumer wiring tests without a real broker: `var harness = new InMemoryTestHarness(); var consumerHarness = harness.Consumer<MyConsumer>(); await harness.Start(); ...`
- **Testcontainers RabbitMQ / Kafka + real consumer** for tests that need actual broker behavior (retry, ack, redelivery)
- Idempotency test: invoke the handler twice with the same payload; assert side effect happens once
- Retry test: stub the external call to fail twice then succeed; assert job completes; assert retry count
- Dead-letter / max-retries test: stub the external call to fail forever; assert job ends in DLQ / max-retries state without infinite loop
- Hangfire: use `BackgroundJobServer` with in-memory storage for happy-path tests; Testcontainers SQL Server / Redis for full-storage tests

**E2E / full-context tests:**

- Reserve for tests that genuinely need the full stack: auth flow end-to-end, transactional commit + background job dispatch, scheduled-job behavior
- Use `WebApplicationFactory<Program>` with the real wired app; pair with Testcontainers Postgres + RabbitMQ / Kafka
- Avoid for tests that an API test could cover - context-load cost compounds

**Lint & runner discipline:**

- `dotnet format --verify-no-changes` mandatory in CI - catches whitespace / using-ordering / EditorConfig violations
- `dotnet test` (with `--collect:"XPlat Code Coverage"` for coverage) on every CI run
- `dotnet build /p:TreatWarningsAsErrors=true` so compiler / Roslyn analyzer warnings block merge
- `dotnet list package --vulnerable --include-transitive` (or `<NuGetAudit>true</NuGetAudit>` in .NET 8+) for dependency vulnerability scanning

### Step 5 - Test Boundaries (.NET-Specific)

**What deserves a unit test:**

- Application handlers (with NSubstitute mocks for repositories / external services), domain logic, validators, mappers, custom middleware (the middleware delegate in isolation), pure functions / utilities
- Domain rules, calculation, state-machine transitions
- Concurrent helpers (`Channel<T>` consumers, `Parallel.ForEachAsync` orchestrators) tested with real concurrent execution and a bounded `xunit.runner.json` parallelism config

**What deserves an API test:**

- Every endpoint: happy path + 401 + 403 + 4xx validation
- **IDOR / per-owner / per-tenant resources**: anonymous → 401, other-user → 403/404, owner → 200. Any action that takes an id route parameter and returns or mutates user-owned data needs this triple
- Pagination contract (`limit` / `offset` / cursor)
- Filtering / sorting / search query params
- Custom `IExceptionHandler` mapping domain exceptions → HTTP status

**Web hazard tests (when controller / action shape signals the risk):**

| Hazard                | When the action shape signals it                                                       | Test to add                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| IDOR                  | Route `{id}` -> user-owned resource lookup or mutation                                 | Owner / other-user / anonymous trio per endpoint                                                  |
| Open redirect         | `Redirect(userInput)` or any action returning a 30x to a request-derived URL          | Allowlist enforcement: `Url.IsLocalUrl` / domain-allowlist; reject `//evil.com`, schemes, encoded forms |
| File upload           | `IFormFile` parameter or any path joining `userFilename`                              | Path traversal (`../../etc/...`), magic-byte vs `Content-Type` lie, size cap, atomic write |
| Bulk export           | Endpoint returning unpaginated `ToListAsync()`; `/admin/export` shape                  | Authz + row-cap + tenant scoping ("export only my tenant's rows, max N rows")                     |
| SSRF                  | `HttpClient.GetAsync(userUrl)` / outbound HTTP with request-derived host               | Allowlist rejects metadata IP, loopback, RFC1918, link-local; DNS rebinding test                  |
| Privilege escalation  | `UpdateUser` / `UpdateRole` / any action that touches role / permission fields        | Non-admin cannot self-promote; admin can; role change requires explicit admin policy guard        |
| Command/shell injection | `Process.Start("cmd.exe", $"/c ...")` or any string-interpolated process invocation | Reject metacharacters in user input; assert arg-list invocation (`ProcessStartInfo.ArgumentList.Add(...)`) is used so shell metacharacters cannot reach a shell |
| Composite (export + path + process) | One action that combines bulk export + user-controlled filename + Process.Start on the result (e.g., `Export(string format, string filename)` writing to `Path.Combine(baseDir, filename)` then spawning a converter) | Single test asserting all three guards co-occur on this action: (a) path-traversal payload rejected (`../../etc/passwd`), (b) tenant scoping enforced (only my tenant's rows in output), (c) shell metacharacters in `format` / `filename` cannot reach the spawned process. Three isolated unit tests miss the composition - the exploit chain is the test target |

These belong in API tests, not buried in service unit tests - the security guard is at the action / middleware boundary, so the test must exercise it through the same boundary. **Web hazards from this table default to Step 7 priority band P1** (security guard is the test's purpose), even when the underlying flow looks like P3 revenue or P2 data integrity - the secondary band still applies via the Multi-band rule.

**What deserves an integration / Testcontainers test:**

- Every repository method with a non-trivial query (filter on multiple columns, JOIN, aggregate)
- DB constraints (unique, check, FK ON DELETE behavior)
- Migration smoke test: apply all migrations on a clean Testcontainers DB; useful when migrations are squashed
- EF Core global query filters (e.g., `HasQueryFilter(x => x.TenantId == _tenant.Id)`) - assert tenant isolation actually works

**What deserves a background-worker / MassTransit / Hangfire test:**

- Every consumer / job with retry logic, idempotency requirements, or external side effects
- Job chains / sagas - assert the workflow completes and aggregates correctly
- Jobs dispatched via post-commit pattern - assert they fire after the parent commits, not before (transactional outbox tests)

**What does NOT need a test:**

- Framework-provided behavior: ASP.NET Core routing resolution, middleware dispatch, default model binding, `[ApiController]` automatic validation (test that you wired things correctly via API tests, not that the framework works)
- Generated boilerplate: DTO records with no logic, getters returning a single field, mappers that only re-arrange properties
- Trivial delegation: `service.GetAsync(id) -> repository.GetAsync(id)` with no logic

### Step 6 - Test Data and Fixtures

- Prefer Bogus `Faker<T>` factories (`new Faker<Order>().RuleFor(o => o.Id, f => Guid.NewGuid()).RuleFor(o => o.CustomerId, f => f.Random.Guid())`) over hand-rolled object initializers; configure factories per project convention
- For repository tests with Testcontainers, use factories to insert; isolate per-test data inside the test (transactional rollback or Respawn) or use a unique-per-test prefix
- Avoid mutating shared test fixtures - use a fresh `IServiceScope` / fresh `DbContext` per test
- Test data must be minimal and focused - 100-row `Enumerable.Range(0, 100).Select(i => ...)` setups signal the test belongs at integration / load-test layer

### Step 7 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go untested while plumbing endpoints get full coverage.

When starting from low test coverage, prioritize by .NET-specific risk:

**Priority 1 - Authorization and authentication:**

- API test per protected endpoint asserting 401 anonymous + 403 wrong-role
- JWT bearer middleware tests covering issuer, audience, signature, expiry, signing-algorithm allowlist
- Custom authorization handlers (`AuthorizationHandler<TRequirement, TResource>`) unit-tested

**Priority 2 - Data integrity:**

- Repository / EF Core integration tests for every non-trivial query
- Service / handler tests for write operations (one happy path + one rollback per write)
- Background-worker idempotency for any consumer / job with side effects
- `dotnet build /p:TreatWarningsAsErrors=true` clean for any concurrent code path
- xUnit's per-test-collection parallelism configured for code that must run cross-thread

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (often modeled as enums in C# - exhaustive `switch` expressions make them testable)
- Scheduled jobs touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through controllers, simple CRUD - lower risk, can wait

**Multi-band rule.** Some targets fall into more than one band - a refund background-worker is both P2 (data-integrity, side-effect idempotency) and P3 (revenue path); a payment-history endpoint is both P1 (authorization on per-owner data) and P3 (revenue). When a target qualifies for multiple bands, file it under the **highest** band (lowest number) and note the secondary band so the test plan covers both axes (e.g., a refund test must assert idempotency *and* the refund-amount invariants, not just one). Do not split the same target across two bands - that hides one of the risks.

### Step 8 - Test Infrastructure Hygiene

- [ ] Testcontainers reused across tests via `IClassFixture<>` / `ICollectionFixture<>` (not per-test container creation)
- [ ] `dotnet test` runs in CI; `dotnet format --verify-no-changes` enforces formatting
- [ ] Test environment only overrides what differs from prod - never silently disables auth middleware
- [ ] Integration tests separated under `tests/*.IntegrationTests` projects; unit tests under `tests/*.UnitTests` projects (clean assembly boundary)
- [ ] HTTP stubs via `WireMock.Net` or `RichardSzalay.MockHttp` returning canned responses; never real network calls in CI
- [ ] No `Thread.Sleep` in tests - use async assertions, `TaskCompletionSource`, or `Channel<T>.Reader.WaitToReadAsync` for synchronization
- [ ] Coverage via `coverlet.collector` reporting to ReportGenerator with per-project thresholds; coverage exclusions documented via `[ExcludeFromCodeCoverage]` attributes (with rationale comment)
- [ ] `dotnet list package --vulnerable` / NuGet Audit in CI - new advisories block merge
- [ ] `WebApplicationFactory<Program>` subclass placed in shared fixtures so every API test class shares the same wiring (DRY)
- [ ] xUnit `[Collection]` attribute used to serialize tests that share global state (Testcontainers fixture instance, etc.)

## .NET Review Checklist

Quick-reference checklist for reviewing existing .NET tests:

- [ ] Test type matches what is being tested (handler/service -> unit + NSubstitute, repository -> Testcontainers integration, controller/endpoint -> WebApplicationFactory)
- [ ] Tests are parameterized (`[Theory] + [InlineData]` / `[MemberData]`), not copy-pasted
- [ ] Every endpoint has at least happy + 401 + 403 + validation-error
- [ ] Every non-trivial repository query has an integration test against Testcontainers (not `UseInMemoryDatabase` / SQLite)
- [ ] Every custom authorization handler has a passing-and-denied test
- [ ] Test data created via Bogus `Faker<T>` factories, not hand-rolled object initializers
- [ ] No `var repo = new InMemoryRepo();` mocks when an integration test could assert real DB state
- [ ] No full-stack E2E tests for what an API test could cover
- [ ] No in-process job mock masking at-least-once / retry semantics on critical jobs
- [ ] `dotnet format --verify-no-changes` clean in CI; `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>`
- [ ] No `Mock<T>().Setup(x => x.SomeAsync()).ReturnsAsync(default)` returning `default` to silence type errors - use the right typed return
- [ ] `[Theory]` data sources strongly typed (no `object[]` casts inside the test body)
- [ ] No `Thread.Sleep(100)` to wait for async work to "probably finish" - use `TaskCompletionSource`, `Channel<T>` synchronization, or `await` the actual completion handle

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% with no scaffolds requested -> Strategy Doc (optionally include Coverage Assessment)
- User asks for **two or more deliverables in the same invocation** ("review coverage AND scaffold tests", "what's missing and write the tests") -> produce them in this order, separated by a horizontal rule (`---`): Coverage Assessment, then Strategy Doc (if requested), then Test Scaffolds. Do not silently drop one.
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## .NET Test Coverage Assessment

**Stack:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**Mediator:** MediatR <version> | none
**Messaging:** MassTransit | Hangfire | Channel | none
**Test framework:** xUnit, `WebApplicationFactory<Program>`, Testcontainers, NSubstitute (or Moq), Bogus, FluentAssertions, Respawn
**Coverage gaps:**

- **Unit tests:** [handlers / services / validators / mappers without test coverage]
- **API tests:** [endpoints without tests; endpoints missing 401/403/validation paths]
- **Integration tests:** [repositories with non-trivial queries without tests; tests running on `UseInMemoryDatabase` or SQLite for a Postgres app]
- **Auth tests:** [endpoints without authorization tests; missing JWT middleware tests; custom authorization handlers untested]
- **Web hazard tests:** [IDOR / per-owner triples missing; open redirect without `Url.IsLocalUrl` allowlist tests; file upload without path-traversal / MIME / size tests; bulk export without scoping / row-cap tests; SSRF without allowlist tests; privilege-escalation guards untested]
- **Job tests:** [background workers / consumers / jobs without tests; jobs without idempotency / retry tests]
- **Concurrency gaps:** [async functions tested only with single-thread assumptions when they spawn cross-thread work]
- **Contract tests:** [OpenAPI / Pact contracts without verification]

**Recommended pyramid balance:**

- Unit (handlers, validators, helpers): [count target]
- API + integration (`WebApplicationFactory` + Testcontainers): [count target]
- E2E (full stack with broker): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or the assessment surfaces > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Authorization & authentication:** [list specific endpoints / flows missing 401/403/ownership tests]
2. **P2 - Data integrity:** [repositories with non-trivial queries / write paths without rollback tests / background workers with unguarded side effects]
3. **P3 - Business-critical flows:** [revenue, state machines, scheduled jobs touching billing or notifications]
4. **P4 - High-churn code:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through controllers / simple CRUD - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run C# test files using project conventions. Each scaffold must include:

- The right test type (API / integration / unit / job)
- Parameterized structure (`[Theory] + [InlineData]` or `[MemberData]`) when behavior varies by input
- Bogus `Faker<T>` factories for test data instead of hand-rolled object initializers
- For API tests: happy path + 401 + 403 + validation-error
- For repository tests: Testcontainers PostgreSQL; assertions against PostgreSQL semantics (not `UseInMemoryDatabase`)
- For auth tests: anonymous + wrong-role + correct-role cases via test-issued JWT
- For job tests: idempotency + retry + max-retries cases when applicable
- `public async Task` test methods (xUnit native async)
- FluentAssertions assertions
- `dotnet format --verify-no-changes`-clean

**Strategy Doc** (when designing a test strategy):

```markdown
## .NET Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / API + Integration {y}% / E2E {z}%
**Tooling:** xUnit, `WebApplicationFactory<Program>`, Testcontainers PostgreSQL, NSubstitute, Bogus, FluentAssertions, Respawn, `dotnet test`, `dotnet format`
**Database isolation:** Testcontainers PostgreSQL via `IClassFixture<PostgresFixture>`; per-test reset via Respawn or transactional rollback (`await using var tx = await db.Database.BeginTransactionAsync();`)
**Concurrency:** xUnit per-collection parallelism configured for code that must run cross-thread; `dotnet build /p:TreatWarningsAsErrors=true` mandatory in CI
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as .NET / ASP.NET Core; data-access mix and messaging recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 2)
- [ ] `dotnet-test-integration` consulted for canonical .NET test patterns
- [ ] Auth testing approach explicit (test-issued JWT or test-only `IAuthenticationHandler` injecting claims)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to .NET idioms (unit -> xUnit + NSubstitute; API -> `WebApplicationFactory<Program>`; integration -> Testcontainers; background-worker -> in-process + real-broker for non-trivial cases)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 authorization, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing
- [ ] Testcontainers used for repository and full-context tests; `UseInMemoryDatabase` flagged as a smell for production-Postgres / production-SqlServer apps
- [ ] `dotnet format --verify-no-changes` and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` CI presence flagged when packages with concurrent code lack lint coverage

**Test Scaffolds only:**

- [ ] Tests are parameterized (`[Theory]` + `[InlineData]` / `[MemberData]`), not copy-pasted per case
- [ ] Test data created via Bogus `Faker<T>`, not hand-rolled object initializers; typed factory return shapes
- [ ] API scaffolds include happy path + 401 + 403 + validation-error; IDOR test for any per-owner / per-tenant resource
- [ ] API scaffolds use `WebApplicationFactory<Program>` with the same global middleware as `Program.cs` (missing auth middleware masks authorization bugs)
- [ ] Repository scaffolds run against Testcontainers PostgreSQL with per-test cleanup (Respawn or transactional rollback) - never `UseInMemoryDatabase` for Postgres apps
- [ ] Background-worker scaffolds include idempotency + retry; real-broker (Testcontainers RabbitMQ / Kafka) variant present for jobs with non-trivial retry / ack semantics
- [ ] Test methods are `public async Task` (never `void`)
- [ ] FluentValidation unit tests scaffolded for any non-trivial DTO with custom rules via `validator.TestValidate(req)`
- [ ] FluentAssertions used for assertion ergonomics

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + setup files - the result imports the wrong factory, uses the wrong HTTP-stub library, or duplicates the integration-test base fixture
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Writing a separate `[Fact]` per case when `[Theory] + [InlineData]` would do - copy-paste tests are harder to maintain and grow inconsistencies
- Full E2E tests (full Testcontainers + real broker) for what an API test could cover - context cost compounds across the suite
- `UseInMemoryDatabase` in repository tests for apps that use PostgreSQL features (JSONB, partial indexes, `ON CONFLICT`, array types) or SQL Server features - tests pass, prod fails. The in-memory provider is not a relational store; it skips FK enforcement, raw SQL, and concurrent updates
- API tests that build the `WebApplicationFactory` without applying the same global middleware as `Program.cs` - validation rules and auth differ between test and prod silently
- Duplicating Bogus factories per project - share via `tests/<Project>.IntegrationTests/Fixtures` referenced by other test projects
- Using `Substitute.For<IRepo>().GetAsync(...).Returns(orders)` mocks when a Testcontainers integration test could assert real DB state
- Mocking auth middleware to silence DTO failures - the test is now incorrect for the prod config
- Skipping FluentValidation unit tests because the controller has an API test - validators are unit-tested separately so they can be reused
- Testing framework internals (e.g., that ASP.NET Core routes match, that `[ApiController]` runs validation) - test your wiring, not the framework
- Using in-process job mocks as a substitute for a real-broker test on jobs with non-trivial retry / ack semantics - the mock skips the broker and masks at-least-once / DLQ semantics
- Using `Mock<T>().Setup(x => x.SomeAsync()).ReturnsAsync(default!)` to silence type errors - use the right typed return
- Using `Thread.Sleep(100)` to wait for async work to "probably finish" - use `TaskCompletionSource`, `Channel<T>` synchronization, or `await` the actual completion handle; sleep-based waits are flaky and slow
- Using `void` test methods for async work - they swallow exceptions; use `public async Task` (xUnit native async)
