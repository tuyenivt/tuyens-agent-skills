---
name: dotnet-exception-handling
description: Implement centralized exception handling with IExceptionHandler, RFC 7807 Problem Details responses, and a domain exception hierarchy mapped to HTTP status codes.
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

## FluentValidation Integration

When using `FluentValidation`, validation failures throw `ValidationException` with a list of errors. Map them to a 422 response with per-field details:

```csharp
FluentValidation.ValidationException ve => (422, "Validation Error"),
```

In the handler, attach validation errors to the Problem Details extensions:

```csharp
if (exception is FluentValidation.ValidationException validationEx)
{
    var errors = validationEx.Errors
        .GroupBy(e => e.PropertyName)
        .ToDictionary(g => g.Key, g => g.Select(e => e.ErrorMessage).ToArray());

    await Results.Problem(
        statusCode: 422,
        title: "Validation Error",
        extensions: new Dictionary<string, object?> { ["errors"] = errors }
    ).ExecuteAsync(context);
    return true;
}
```

## Edge Cases

- **Multiple IExceptionHandler registrations**: ASP.NET Core 8 chains handlers in registration order. If the first handler returns `true`, subsequent handlers are skipped. Register the most specific handler first.
- **Minimal API vs controllers**: `IExceptionHandler` works for both Minimal APIs and controllers. No separate configuration is needed.
- **OperationCanceledException**: Client disconnections throw `OperationCanceledException`. Do not log these as errors - return early or let the framework handle them (ASP.NET Core returns no response body for cancelled requests).

## Avoid

- `try/catch` in controllers just to return `BadRequest()`
- Different error response shapes across endpoints
- Swallowing exceptions without logging
- Returning `500` for expected domain errors
- Catching `Exception` broadly in service code instead of letting it propagate to the global handler
