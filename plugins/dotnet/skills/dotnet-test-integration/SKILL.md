---
name: dotnet-test-integration
description: "Write ASP.NET Core integration tests with WebApplicationFactory, Testcontainers, Respawn isolation, and Bogus test data."
metadata:
  category: backend
  tags: [xunit, testcontainers, webapplicationfactory, integration-testing, bogus, respawn]
user-invocable: false
---

# Integration Testing

## When to Use

Selecting a test layer, wiring Testcontainers, writing `WebApplicationFactory` API tests, isolating DB state between tests, generating realistic fixtures.

## Test Layer Strategy

| Layer       | Tool                                   | Scope                            |
| ----------- | -------------------------------------- | -------------------------------- |
| Domain      | xUnit                                  | Pure logic, no framework deps    |
| Application | xUnit + NSubstitute                    | Services with mocked dependencies |
| Repository  | xUnit + Testcontainers (PostgreSQL)    | Real DB queries, migrations      |
| API         | `WebApplicationFactory` + `HttpClient` | Full HTTP request/response cycle |

## Rules

- Share expensive setup (Testcontainers, `WebApplicationFactory`) via `IClassFixture<T>` or `[Collection]`.
- Reset DB state with `Respawn` between tests; never `DeleteAsync` per table.
- Generate fixtures with `Bogus` `Faker<T>`; no hand-crafted magic values.
- Name tests `Method_Scenario_ExpectedResult`; structure Arrange / Act / Assert.
- Test the API through `WebApplicationFactory`, not by mocking `HttpClient`.
- Override services (DB, external clients) in `ConfigureWebHost`; never hit real external systems.

## Patterns

**Shared Testcontainers fixture** - one container, reused across the class:

```csharp
public sealed class PostgresFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _db = new PostgreSqlBuilder().WithImage("postgres:16-alpine").Build();
    public string ConnectionString => _db.GetConnectionString();
    public async Task InitializeAsync() { await _db.StartAsync(); /* migrate */ }
    public async Task DisposeAsync() => await _db.DisposeAsync();
}
```

Share one container across multiple test classes via `[CollectionDefinition]` instead of one per class.

**WebApplicationFactory override** - swap DB to the container:

```csharp
protected override void ConfigureWebHost(IWebHostBuilder builder) =>
    builder.ConfigureServices(s =>
    {
        s.RemoveAll<DbContextOptions<AppDbContext>>();
        s.AddDbContext<AppDbContext>(o => o.UseNpgsql(_fixture.ConnectionString));
    });
```

**API test** - Arrange / Act / Assert through HTTP:

```csharp
[Fact]
public async Task CreateOrder_ValidRequest_Returns201()
{
    var request = new CreateOrderRequestFaker().Generate();
    var response = await _client.PostAsJsonAsync("/api/v1/orders", request);
    response.StatusCode.Should().Be(HttpStatusCode.Created);
}
```

**Respawn between tests** - reset in `InitializeAsync`, not `Dispose`:

```csharp
public Task InitializeAsync() =>
    _respawner.ResetAsync(_fixture.ConnectionString); // not in DisposeAsync - async cleanup unreliable
```

Configure once: `await Respawner.CreateAsync(conn, new RespawnerOptions { DbAdapter = DbAdapter.Postgres })`.

**Bogus faker** - bind to the domain constructor, not raw properties:

```csharp
public sealed class OrderFaker : Faker<Order>
{
    public OrderFaker() => CustomInstantiator(f =>
        Order.Create(customerId: f.Random.Guid(), totalAmount: f.Finance.Amount(1, 10_000)));
}
```

**Bad:** hardcoded ports or connection strings in test config.
**Good:** read `_fixture.ConnectionString` at runtime; `WebApplicationFactory` assigns a random port.

## Output Format

When asked to add or review integration tests, produce:

- **Layer:** `{Domain | Application | Repository | API}`
- **Fixtures:** list of `IClassFixture` / `[Collection]` types introduced or reused.
- **Isolation:** `{Respawn | per-test transaction | fresh container}` with justification.
- **Test list:** `Method_Scenario_ExpectedResult` names with the assertion target.
- **Service overrides:** which DI registrations replaced in `ConfigureWebHost`.

## Avoid

- `Thread.Sleep` - use `await Task.Delay` or polling assertions.
- Shared mutable state between tests.
- Asserting on implementation details instead of observable behaviour.
- Spinning up a new container per test class when `[Collection]` would share one.
- Falling back to SQLite when the production DB is PostgreSQL - drift hides bugs.
