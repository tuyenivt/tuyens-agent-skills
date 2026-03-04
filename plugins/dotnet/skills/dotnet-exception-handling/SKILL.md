---
name: dotnet-exception-handling
description: Global exception middleware, Problem Details (RFC 7807), and domain exception hierarchy for ASP.NET Core
metadata:
  category: backend
  tags: [exception-handling, problem-details, middleware, error-responses]
user-invocable: false
---

# Exception Handling

## When to Use

- Setting up centralised error handling in ASP.NET Core
- Mapping domain/application exceptions to HTTP Problem Details responses
- Ensuring consistent error response format across all endpoints

## Rules

- Use `IExceptionHandler` (ASP.NET Core 8+) or `UseExceptionHandler` middleware - never try/catch in controllers
- Always return RFC 7807 Problem Details (`application/problem+json`) for error responses
- Define a domain exception hierarchy: `DomainException` → `NotFoundException`, `ConflictException`, `ValidationException`
- Map domain exceptions to HTTP status codes in one place (the exception handler)
- Log unhandled exceptions at `Error` level with full context; log expected exceptions at `Warning`
- Never expose stack traces or internal details to API consumers

## Pattern

Domain exception hierarchy:

```csharp
public abstract class DomainException(string message) : Exception(message);
public sealed class NotFoundException(string resource, object id)
    : DomainException($"{resource} '{id}' was not found.");
public sealed class ConflictException(string message) : DomainException(message);
```

Global exception handler (.NET 8+):

```csharp
public sealed class GlobalExceptionHandler(ILogger<GlobalExceptionHandler> logger)
    : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(
        HttpContext context, Exception exception, CancellationToken ct)
    {
        var (status, title) = exception switch
        {
            NotFoundException   => (404, "Not Found"),
            ConflictException   => (409, "Conflict"),
            ValidationException => (422, "Validation Error"),
            _                   => (500, "Internal Server Error")
        };

        if (status == 500)
            logger.LogError(exception, "Unhandled exception");
        else
            logger.LogWarning(exception, "Domain exception: {Title}", title);

        await Results.Problem(
            statusCode: status,
            title: title,
            detail: status < 500 ? exception.Message : null
        ).ExecuteAsync(context);

        return true;
    }
}
```

Registration in `Program.cs`:

```csharp
builder.Services.AddExceptionHandler<GlobalExceptionHandler>();
builder.Services.AddProblemDetails();
app.UseExceptionHandler();
```

## Avoid

- `try/catch` in controllers just to return `BadRequest()`
- Different error response shapes across endpoints
- Swallowing exceptions without logging
- Returning `500` for expected domain errors
