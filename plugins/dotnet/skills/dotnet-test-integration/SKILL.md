---
name: dotnet-test-integration
description: Structure integration tests with WebApplicationFactory, Testcontainers for real database testing, Bogus for data generation, and Respawn for state isolation.
metadata:
  category: backend
  tags: [xunit, testcontainers, webapplicationfactory, integration-testing, bogus]
user-invocable: false
---

# Integration Testing

## When to Use

- Selecting the right test type for each layer (unit, integration, API)
- Setting up Testcontainers for real database tests
- Generating realistic test data with Bogus
- Testing HTTP endpoints with `WebApplicationFactory`

## Test Layer Strategy

| Layer       | Tool                                   | Scope                                  |
| ----------- | -------------------------------------- | -------------------------------------- |
| Domain      | xUnit (no framework deps)              | Pure unit tests for domain logic       |
| Application | xUnit + NSubstitute / Moq              | Service tests with mocked repositories |
| Repository  | xUnit + Testcontainers (PostgreSQL)    | Real DB queries, migrations            |
| API         | `WebApplicationFactory` + `HttpClient` | Full HTTP request/response cycle       |

## Rules

- Use `IClassFixture<T>` for shared expensive setup (e.g., Testcontainers database)
- Use `NSubstitute` or `Moq` for application-layer unit tests - never spin up infrastructure
- Generate test data with `Bogus` `Faker<T>` - avoid hand-crafted magic strings
- Every test follows Arrange / Act / Assert structure with clear naming: `Method_Scenario_ExpectedResult`
- Prefer `WebApplicationFactory` over mocking the HTTP layer for API tests
- Use `respawn` to reset database state between tests (not `DeleteAsync` on every table)

## Patterns

Repository test with Testcontainers:

```csharp
public class OrderRepositoryTests(PostgresContainerFixture db) : IClassFixture<PostgresContainerFixture>
{
    [Fact]
    public async Task GetByIdAsync_ExistingOrder_ReturnsOrder()
    {
        // Arrange
        var order = new OrderFaker().Generate();
        await db.Context.Orders.AddAsync(order);
        await db.Context.SaveChangesAsync();

        // Act
        var result = await db.Repository.GetByIdAsync(order.Id, CancellationToken.None);

        // Assert
        result.Should().NotBeNull();
        result!.Id.Should().Be(order.Id);
    }
}
```

API test with WebApplicationFactory:

```csharp
public class OrdersApiTests(CustomWebAppFactory factory) : IClassFixture<CustomWebAppFactory>
{
    [Fact]
    public async Task CreateOrder_ValidRequest_Returns201()
    {
        var client = factory.CreateClient();
        var request = new CreateOrderRequestFaker().Generate();

        var response = await client.PostAsJsonAsync("/api/v1/orders", request);

        response.StatusCode.Should().Be(HttpStatusCode.Created);
    }
}
```

Bogus faker:

```csharp
public sealed class OrderFaker : Faker<Order>
{
    public OrderFaker() =>
        CustomInstantiator(f => Order.Create(
            customerId: f.Random.Guid(),
            totalAmount: f.Finance.Amount(1, 10_000)));
}
```

## Avoid

- `Thread.Sleep` in tests - use `await Task.Delay` or proper async assertions
- Shared mutable state between tests (test isolation)
- Testing implementation details - test observable behaviour
- Hardcoded connection strings - read from `IConfiguration` or Testcontainers

## Testcontainers Fixture

Shared Testcontainers fixture to avoid spinning up a new database per test class:

```csharp
public sealed class PostgresContainerFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _container = new PostgreSqlBuilder()
        .WithImage("postgres:16-alpine")
        .Build();

    public string ConnectionString => _container.GetConnectionString();
    public AppDbContext Context { get; private set; } = null!;

    public async Task InitializeAsync()
    {
        await _container.StartAsync();
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseNpgsql(ConnectionString)
            .Options;
        Context = new AppDbContext(options);
        await Context.Database.MigrateAsync();
    }

    public async Task DisposeAsync() => await _container.DisposeAsync();
}
```

## WebApplicationFactory Fixture

Override services to use Testcontainers instead of a real database:

```csharp
public sealed class CustomWebAppFactory : WebApplicationFactory<Program>, IAsyncLifetime
{
    private readonly PostgreSqlContainer _db = new PostgreSqlBuilder().Build();

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(services =>
        {
            services.RemoveAll<DbContextOptions<AppDbContext>>();
            services.AddDbContext<AppDbContext>(o => o.UseNpgsql(_db.GetConnectionString()));
        });
    }

    public async Task InitializeAsync() => await _db.StartAsync();
    public new async Task DisposeAsync() => await _db.DisposeAsync();
}
```

## Edge Cases

- **Parallel test execution**: xUnit runs test classes in parallel by default. Each class sharing the same `IClassFixture` gets the same instance, but different classes get different instances. Use `[Collection]` to share a single Testcontainers instance across multiple test classes to avoid excessive container creation.
- **Respawn with PostgreSQL**: When using Respawn, pass `new RespawnerOptions { DbAdapter = DbAdapter.Postgres }` and call `ResetAsync` in the test constructor or `InitializeAsync`, not in `Dispose` (async cleanup in `Dispose` is unreliable).
- **WebApplicationFactory port conflicts**: `WebApplicationFactory` uses a random port by default. Do not hardcode ports in test configuration.
- **Docker not available in CI**: Testcontainers requires a Docker-compatible runtime. In CI environments without Docker, use Testcontainers Cloud or fall back to SQLite for a degraded but functional test suite.
