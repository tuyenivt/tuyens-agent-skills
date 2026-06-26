---
name: dotnet-test-integration
description: "Write ASP.NET Core integration tests with WebApplicationFactory, Testcontainers, Respawn isolation, and Bogus test data."
metadata:
  category: backend
  tags: [xunit, testcontainers, webapplicationfactory, integration-testing, bogus, respawn]
user-invocable: false
---

## When to Use

Selecting a test layer, wiring Testcontainers, writing `WebApplicationFactory` API tests, isolating DB state between tests, generating realistic fixtures.

## Rules

- Pick the layer per the table below; do not push API-layer assertions into mocked unit tests.
- Share expensive setup (Testcontainers, `WebApplicationFactory`) via `IClassFixture<T>` or `[Collection]`.
- Reset DB state with `Respawn` in `InitializeAsync`; never `DeleteAsync` per table.
- Generate fixtures with `Bogus` `Faker<T>` bound to domain constructors; no hand-crafted magic values.
- Name tests `Method_Scenario_ExpectedResult`; structure Arrange / Act / Assert.
- Test the API through `WebApplicationFactory`, not by mocking `HttpClient`.
- Override services (DB, external clients) in `ConfigureWebHost`; never hit real external systems.
- Do not substitute SQLite when the production DB is PostgreSQL - drift hides bugs.

| Layer       | Tool                                   | Scope                            |
| ----------- | -------------------------------------- | -------------------------------- |
| Domain      | xUnit                                  | Pure logic, no framework deps    |
| Application | xUnit + NSubstitute                    | Services with mocked dependencies |
| Repository  | xUnit + Testcontainers (PostgreSQL)    | Real DB queries, migrations      |
| API         | `WebApplicationFactory` + `HttpClient` | Full HTTP request/response cycle |

## Patterns

### Shared Testcontainers fixture

One container reused across the class; share across multiple classes via `[CollectionDefinition]`.

```csharp
public sealed class PostgresFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _db = new PostgreSqlBuilder().WithImage("postgres:16-alpine").Build();
    public string ConnectionString => _db.GetConnectionString();
    public async Task InitializeAsync() { await _db.StartAsync(); await Migrate(); } // MigrateAsync(), not EnsureCreated() (bypasses migrations, hides drift)
    public async Task DisposeAsync() => await _db.DisposeAsync();
}
```

### WebApplicationFactory override

```csharp
protected override void ConfigureWebHost(IWebHostBuilder builder) =>
    builder.ConfigureServices(s =>
    {
        s.RemoveAll<DbContextOptions<AppDbContext>>();
        s.AddDbContext<AppDbContext>(o => o.UseNpgsql(_fixture.ConnectionString));
    });
```

### Authenticating API tests

Register a test scheme in `ConfigureWebHost`, then vary the caller's claims per test via a header the handler reads. Avoids minting real JWTs.

```csharp
s.AddAuthentication("Test").AddScheme<AuthenticationSchemeOptions, TestAuthHandler>("Test", _ => { });
// TestAuthHandler builds a ClaimsPrincipal from a "X-Test-Sub"/"X-Test-Role" header (or fixed claims)
_client.DefaultRequestHeaders.Add("X-Test-Sub", ownerId.ToString()); // owner vs other-user vs absent -> 200/403/401
```

Override an external client/bus the same way: `s.RemoveAll<IMessagePublisher>(); s.AddSingleton<IMessagePublisher>(_fakePublisher);`.

### API test through HTTP

```csharp
[Fact]
public async Task CreateOrder_ValidRequest_Returns201()
{
    var request = new CreateOrderRequestFaker().Generate();
    var response = await _client.PostAsJsonAsync("/api/v1/orders", request);
    response.StatusCode.Should().Be(HttpStatusCode.Created);
}
```

### Respawn between tests

Reset in `InitializeAsync`, not `DisposeAsync` (async cleanup is unreliable across runners).

```csharp
public Task InitializeAsync() => _respawner.ResetAsync(_fixture.ConnectionString);
// configure once: await Respawner.CreateAsync(conn, new RespawnerOptions { DbAdapter = DbAdapter.Postgres })
```

### Bogus faker bound to domain constructor

```csharp
public sealed class OrderFaker : Faker<Order>
{
    public OrderFaker() => CustomInstantiator(f =>
        Order.Create(customerId: f.Random.Guid(), totalAmount: f.Finance.Amount(1, 10_000)));
}
```

Read `_fixture.ConnectionString` at runtime; `WebApplicationFactory` assigns a random port. Hardcoded ports or connection strings break parallel runs.

## Output Format

When asked to add or review integration tests, produce:

- **Layer:** `{Domain | Application | Repository | API}`
- **Fixtures:** `IClassFixture` / `[Collection]` types introduced or reused.
- **Isolation:** `{Respawn | per-test transaction | fresh container}` with justification. Use Respawn (not a wrapping transaction) for commit-dependent flows - outbox / post-commit dispatch / `SaveChanges` interceptors fire only on commit, so a rolled-back test transaction makes them silently never run.
- **Test list:** `Method_Scenario_ExpectedResult` names with the assertion target.
- **Service overrides:** DI registrations replaced in `ConfigureWebHost`.

## Avoid

- `Thread.Sleep` - poll instead: `await WaitFor(() => _fakePublisher.Count == 1, timeout)` for async/background assertions.
- Shared mutable state between tests.
- Asserting on implementation details instead of observable behaviour.
- A new container per test class when `[Collection]` would share one.
