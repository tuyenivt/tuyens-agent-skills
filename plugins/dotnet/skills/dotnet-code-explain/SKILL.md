---
name: dotnet-code-explain
description: ".NET / ASP.NET Core explanation signals: DI scopes, middleware pipeline, async/ConfigureAwait, EF Core change tracking, Clean Architecture."
metadata:
  category: backend
  tags: [explanation, code-understanding, dotnet, aspnetcore, efcore]
user-invocable: false
---

# .NET Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is .NET / ASP.NET Core.

## When to Use

- A workflow needs .NET-specific signals: DI container scope (Singleton/Scoped/Transient), middleware pipeline order, async semantics with cancellation tokens, EF Core change tracking, MediatR / CQRS patterns, Clean Architecture layer boundaries.
- Target is in a .NET project (`*.csproj`, `Program.cs`, `Startup.cs`).

## Rules

- Identify the target framework first (`net8.0`, `net9.0`) from the `*.csproj`. APIs and conventions differ between LTS and STS.
- For DI, identify the lifetime (Singleton / Scoped / Transient) registered for the service. Mismatched lifetimes are the most common DI bug (Singleton injecting Scoped = captive dependency).
- For ASP.NET Core, list middleware in pipeline order before describing the endpoint. Middleware order is `app.Use*` call order in `Program.cs`.
- Surface `CancellationToken` propagation - missing cancellation tokens means the operation cannot be aborted on disconnect/shutdown.
- For EF Core, identify whether queries are `IQueryable` (deferred, translated to SQL) or in-memory (after `.ToList()`, `.AsEnumerable()`). The boundary determines what is server-side.

## Patterns

### Dependency Injection Lifetimes

| Lifetime    | Behavior                                                          | What to flag                                                                                                      |
| ----------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Singleton   | One instance for the entire app                                   | Cannot inject Scoped or Transient services - they get captured for the app lifetime                                |
| Scoped      | One instance per request (in ASP.NET Core)                        | Default for `DbContext`; injecting Scoped into Singleton is the captive-dependency bug                             |
| Transient   | New instance every time it is resolved                            | Stateless utility services; do not hold state                                                                      |

**Captive dependency:** if `ServiceA` is Singleton and depends on `IServiceB` which is Scoped, `ServiceA` captures one instance of `IServiceB` and uses it forever - across requests. The DI container does not catch this by default; configure `ValidateScopes = true` in development.

### ASP.NET Core Middleware Pipeline

```csharp
app.UseExceptionHandler();        // 1. catches downstream exceptions
app.UseHttpsRedirection();        // 2. redirects http -> https
app.UseStaticFiles();             // 3. serves static; short-circuits if file matches
app.UseRouting();                 // 4. matches request to endpoint
app.UseAuthentication();          // 5. populates HttpContext.User
app.UseAuthorization();           // 6. checks [Authorize]
app.UseEndpoints(...);            // 7. invokes the matched endpoint
```

- Middleware runs forward on request, reverse on response. Each middleware can short-circuit by not calling `next()`.
- `UseAuthentication` must come before `UseAuthorization` - the latter reads `HttpContext.User` populated by the former.
- `UseRouting` must come before middlewares that depend on the matched endpoint (e.g., `UseAuthorization` checks endpoint metadata).
- Custom middleware via `app.Use(async (ctx, next) => { ...; await next(); ... })` or `IMiddleware` class.

### Async / Await and Cancellation

- `async Task` and `async ValueTask`: async methods return Tasks; `ValueTask` avoids allocation when the value is often available synchronously.
- `await` captures the current `SynchronizationContext` by default. In ASP.NET Core, there is no SyncContext, so `ConfigureAwait(false)` is **not needed** in app code (it matters in libraries).
- `CancellationToken` parameters: pass through every async layer. ASP.NET Core supplies `HttpContext.RequestAborted`; EF Core's `ToListAsync(cancellationToken)` honors it.
- `Task.Run` for CPU-bound on threadpool; do NOT use to "make sync code async" - it just hides the blocking.
- Async void: only for event handlers; exceptions become unhandled.

### EF Core Change Tracking

- `DbContext` tracks loaded entities. Mutating a tracked entity sets its state to `Modified`; `SaveChanges()` issues UPDATE.
- `AsNoTracking()` for read-only queries - skips change tracking, faster, less memory.
- `Include(x => x.Posts)` for eager loading; without it, navigation properties are not loaded (no lazy loading by default in EF Core; opt-in via `UseLazyLoadingProxies`).
- `IQueryable` is deferred - LINQ operators build the query tree; SQL is generated on enumeration (`ToList`, `ToListAsync`, `First`, `Count`, etc.).
- Transition to client-side: `AsEnumerable()`, `ToList()`, `AsAsyncEnumerable()`. Operators after the boundary run in memory - common cause of accidental full-table loads.
- `DbContext` is **not thread-safe**. One DbContext per request (Scoped) is the rule.

### LINQ Boundaries

```csharp
var query = db.Users
    .Where(u => u.Active)          // SQL
    .Select(u => new { u.Id })     // SQL
    .ToList()                       // boundary - SQL executed here
    .Where(u => SomeMethod(u));    // C# in memory
```

- Methods called in `IQueryable` chains must be EF-translatable. Calling a custom C# method in a `Where` after the query started runs the entire collection client-side, often loading the whole table.

### MediatR / CQRS (when present)

- Commands (`IRequest<TResponse>`) and queries; one handler per request type.
- `IPipelineBehavior<TRequest, TResponse>` wraps handlers - validation, logging, transactions live here.
- `INotification` for one-to-many publish; handlers run sequentially or in parallel based on configuration.
- `mediator.Send(...)` resolves the handler from DI - lifetime is whatever was registered.

### Clean Architecture Layering (when present)

```
Domain (entities, value objects, domain events)
  ^
Application (use cases, MediatR handlers, DTOs, interfaces)
  ^
Infrastructure (EF Core implementations, external clients)
  ^
Presentation (controllers, minimal APIs, SignalR)
```

- Domain has no dependencies on other layers.
- Application defines interfaces that Infrastructure implements (DIP).
- Presentation depends on Application; Infrastructure is wired in `Program.cs` via DI extensions.

### Records and Value Equality

- `record` types: structural equality, immutable by default (`init` setters), `with` expression for non-destructive update.
- `record class` (default) vs `record struct` (value type, smaller for small payloads).
- DTOs and value objects are typical record candidates; entities (with identity) usually stay as classes.

### Nullable Reference Types

- Enabled with `<Nullable>enable</Nullable>` in csproj. `string` is non-null; `string?` is nullable.
- Compiler warnings on null dereference, but not runtime checks - external data (deserialization, DB) can violate the annotation.
- `!` (null-forgiving) suppresses the warning; treat as a smell unless documented why.

### Configuration and `IOptions<T>`

- `appsettings.json` + environment-specific (`appsettings.Development.json`) + env vars + user secrets + Azure Key Vault, in order of precedence.
- `IOptions<MyConfig>`: snapshot at app start (Singleton).
- `IOptionsSnapshot<MyConfig>`: per-request reload (Scoped); reloads when file changes.
- `IOptionsMonitor<MyConfig>`: subscribe to changes (Singleton).

### Logging via `ILogger<T>`

- Categorized by the generic type argument; structured logging via templates: `_logger.LogInformation("Order {OrderId} processed", id)`.
- Scopes (`_logger.BeginScope(...)`) for request-correlation.
- Configured in `Program.cs` via `builder.Logging`; sinks via Serilog/NLog if used.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- DI lifetime (Singleton/Scoped/Transient) of the type
- For controllers/minimal API endpoints: middleware pipeline order
- `CancellationToken` parameter and propagation
- For EF Core: `DbContext` lifetime and tracking state of involved entities
- For MediatR: request type, handler, pipeline behaviors

**Into "Non-Obvious Behavior":**

- Captive dependency if Singleton injects Scoped
- Middleware short-circuiting before reaching the endpoint
- IQueryable -> client-side LINQ boundary causing full table load
- DbContext not thread-safe across `await` if reused
- `AsNoTracking` vs tracked queries
- Async void exceptions becoming unhandled
- Nullable reference type annotations not enforced at runtime

**Into "Key Invariants":**

- DbContext is per-request (Scoped); not thread-safe
- Authentication middleware must come before Authorization
- `IQueryable` runs as SQL until a boundary method (`ToList`, `First`) materializes it
- DI container resolves Scoped within a request scope only

**Into "Change Impact Preview":**

- Changing service lifetime: Singleton -> Scoped breaks injection into Singletons
- Adding `Include` to a query: shape and performance change for every consumer
- Removing `AsNoTracking`: query starts updating shared change tracker
- Adding a `[Authorize]` attribute: every handler in the controller now requires auth unless `[AllowAnonymous]`
- Renaming a record's property: structural equality semantics change for any cached value

## Avoid

- Treating `IQueryable` and `IEnumerable` as interchangeable - the boundary is where SQL stops
- Recommending `ConfigureAwait(false)` in ASP.NET Core app code (only matters in libraries)
- Confusing `IOptions`/`IOptionsSnapshot`/`IOptionsMonitor` - they have different lifetimes and reload semantics
- Saying "DbContext is fine across requests" - it is Scoped and not thread-safe
- Using `Task.Run` to "make code async" - it just moves blocking to another thread
- Skipping middleware order when explaining endpoint behavior
