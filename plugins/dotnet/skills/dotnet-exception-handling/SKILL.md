---
name: dotnet-exception-handling
description: "ASP.NET Core centralized error handling: IExceptionHandler, RFC 7807 Problem Details, domain exception hierarchy, FluentValidation mapping."
metadata:
  category: backend
  tags: [exception-handling, problem-details, middleware, error-responses]
user-invocable: false
---

# Exception Handling

## When to Use

Centralizing ASP.NET Core error handling, mapping domain/application exceptions to RFC 7807 Problem Details, or replacing ad-hoc `try/catch` + `BadRequest()` in controllers.

## Rules

- Handle errors centrally via `IExceptionHandler` (.NET 8+) or `UseExceptionHandler`; no `try/catch` in controllers for response shaping.
- Return `application/problem+json` (RFC 7807) for every error response, including `traceId`.
- Define one domain exception hierarchy rooted at `DomainException`; map to status codes in exactly one place.
- Disambiguate when both a domain `ValidationException` and `FluentValidation.ValidationException` exist - use the FQN in switch arms.
- Log unhandled (`>= 500`) at `Error` with full context; log expected domain exceptions at `Warning`; do not log `OperationCanceledException` as an error.
- Expose `detail`/stack traces only in Development (`IHostEnvironment.IsDevelopment()`).

## Patterns

### Domain exception hierarchy

```csharp
public abstract class DomainException(string message) : Exception(message);
public sealed class NotFoundException(string resource, object id)
    : DomainException($"{resource} '{id}' was not found.");
public sealed class ConflictException(string message) : DomainException(message);
public sealed class DomainValidationException(IDictionary<string, string[]> errors)
    : DomainException("Validation failed") { public IDictionary<string, string[]> Errors { get; } = errors; }
```

### Unified handler

Single switch maps every exception to `(status, title)`. FluentValidation and cancellation are arms of the same switch - no parallel `if` branches.

```csharp
public sealed class GlobalExceptionHandler(
    ILogger<GlobalExceptionHandler> logger,
    IHostEnvironment env) : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(
        HttpContext ctx, Exception ex, CancellationToken ct)
    {
        if (ex is OperationCanceledException && ct.IsCancellationRequested)
            return true; // client disconnect - no response body

        var (status, title) = ex switch
        {
            NotFoundException                       => (404, "Not Found"),
            ConflictException                       => (409, "Conflict"),
            DomainValidationException               => (422, "Validation Error"),
            FluentValidation.ValidationException    => (422, "Validation Error"),
            _                                       => (500, "Internal Server Error")
        };

        if (status >= 500) logger.LogError(ex, "Unhandled exception");
        else               logger.LogWarning(ex, "Domain exception: {Title}", title);

        var extensions = new Dictionary<string, object?> { ["traceId"] = ctx.TraceIdentifier };
        if (ex is FluentValidation.ValidationException fve)
            extensions["errors"] = fve.Errors
                .GroupBy(e => e.PropertyName)
                .ToDictionary(g => g.Key, g => g.Select(e => e.ErrorMessage).ToArray());
        else if (ex is DomainValidationException dve)
            extensions["errors"] = dve.Errors;

        await Results.Problem(
            statusCode: status,
            title: title,
            detail: status < 500 || env.IsDevelopment() ? ex.Message : null,
            extensions: extensions
        ).ExecuteAsync(ctx);

        return true;
    }
}
```

### Registration

```csharp
builder.Services.AddExceptionHandler<GlobalExceptionHandler>();
builder.Services.AddProblemDetails();
app.UseExceptionHandler();
```

### Anti-pattern: controller try/catch

```csharp
// Bad: per-endpoint shaping, inconsistent payloads, hides 404 as 500
try { return Ok(await svc.Get(id)); }
catch (Exception e) { return BadRequest(new { error = e.Message }); }

// Good: let domain exceptions propagate
return Ok(await svc.Get(id)); // NotFoundException -> 404 Problem Details
```

## Output Format

- **Files**: `GlobalExceptionHandler.cs` (Web layer), `DomainException.cs` + subtypes (Domain layer).
- **Exception map**: table of `Exception -> (HTTP status, log level)`.
- **Registration diff**: lines added to `Program.cs` (`AddExceptionHandler`, `AddProblemDetails`, `UseExceptionHandler`).
- **Removed**: controller `try/catch` blocks deleted.

## Avoid

- Parallel `if (ex is X)` branches alongside the central switch.
- Catching `Exception` broadly in services instead of propagating to the handler.
- Returning `500` for expected domain errors (missing resource, conflict, validation).
- Leaking `ex.Message`, stack traces, or inner exceptions to clients outside Development.
