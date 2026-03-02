---
name: dotnet-test-integration
description: xUnit test patterns, WebApplicationFactory slices, Testcontainers, and Bogus test data for .NET 8
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
- Use `NSubstitute` or `Moq` for application-layer unit tests — never spin up infrastructure
- Generate test data with `Bogus` `Faker<T>` — avoid hand-crafted magic strings
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

- `Thread.Sleep` in tests — use `await Task.Delay` or proper async assertions
- Shared mutable state between tests (test isolation)
- Testing implementation details — test observable behaviour
- Hardcoded connection strings — read from `IConfiguration` or Testcontainers
