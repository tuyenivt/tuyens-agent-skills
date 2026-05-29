---
name: dotnet-code-explain
description: ".NET / ASP.NET Core explanation signals: DI scopes, middleware pipeline, async/ConfigureAwait, EF Core change tracking, Clean Architecture."
metadata:
  category: backend
  tags: [explanation, code-understanding, dotnet, aspnetcore, efcore]
user-invocable: false
---

# .NET Code Explain (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-code-explain` when the detected stack is .NET / ASP.NET Core.

## When to Use

A workflow needs .NET-specific signals for a target in a .NET project (`*.csproj`, `Program.cs`): DI lifetime, middleware order, `CancellationToken` propagation, EF Core tracking/query boundaries, MediatR pipeline, Clean Architecture layer.

## Rules

- Read TFM from `*.csproj` before naming APIs - conventions differ across LTS/STS.
- Resolve DI lifetime (Singleton / Scoped / Transient) for every type named; flag Singleton holding Scoped/Transient as a captive dependency.
- List middleware in `app.Use*` order before describing endpoint behavior.
- Mark the `IQueryable` -> in-memory boundary (`ToList`, `ToListAsync`, `First`, `AsEnumerable`); operators after the boundary run in memory.
- Note missing `CancellationToken` on async DB / HTTP calls.

## Patterns

### DI Lifetimes

| Lifetime  | Scope              | Flag                                                    |
| --------- | ------------------ | ------------------------------------------------------- |
| Singleton | App lifetime       | Cannot depend on Scoped/Transient - captive dependency  |
| Scoped    | One per request    | Default for `DbContext`; not thread-safe across `await` |
| Transient | New per resolution | Must be stateless                                       |

`ValidateScopes = true` (dev) catches captive dependencies.

### Middleware Pipeline

```csharp
app.UseExceptionHandler();   // catches downstream exceptions
app.UseAuthentication();     // populates HttpContext.User
app.UseAuthorization();      // reads User + endpoint metadata
```

Forward on request, reverse on response; short-circuit by skipping `next()`. `UseRouting` -> `UseAuthentication` -> `UseAuthorization` is the required order.

### Async and Cancellation

- No `SynchronizationContext` in ASP.NET Core - `ConfigureAwait(false)` is unnecessary in app code.
- Controllers receive `HttpContext.RequestAborted`; EF Core honors it via `ToListAsync(ct)`.
- `Task.Run` does not make sync code async - it moves blocking to the thread pool.

### EF Core

```csharp
db.Users.Where(u => u.Active)   // SQL
        .ToList()                // boundary - SQL runs here
        .Where(u => Calc(u));    // in-memory
```

- `DbContext` is Scoped and not thread-safe; one per request, one operation at a time.
- `AsNoTracking()` for read-only queries.
- Navigation properties require explicit `Include(...)` unless lazy-loading proxies are configured.
- Non-translatable methods after the boundary cause full-table client evaluation.

### MediatR / CQRS (when present)

- `IRequest<TResponse>` -> single handler resolved from DI.
- `IPipelineBehavior<TRequest, TResponse>` wraps every handler (validation, logging, transactions).
- `INotification` is one-to-many publish.

### Clean Architecture (when present)

Domain (no deps) <- Application (use cases, interfaces) <- Infrastructure (EF, clients), Presentation. Application defines interfaces that Infrastructure implements; wired in `Program.cs`.

## Output Format

Signals consumed by `task-code-explain`. Emit only fields that apply.

**Flow Context:**

- DI lifetime of the target type
- For endpoints: middleware pipeline order up to the endpoint
- `CancellationToken` parameter present / propagated
- For EF Core: tracked vs `AsNoTracking`; `Include`s present
- For MediatR: request type, handler, pipeline behaviors

**Non-Obvious Behavior:**

- Captive dependency (Singleton holds Scoped/Transient)
- Middleware short-circuit before the endpoint
- `IQueryable` -> in-memory boundary causing full-table load
- `DbContext` reuse across `await` on parallel paths
- Missing `CancellationToken` on long-running calls

**Key Invariants:**

- `DbContext` is per-request, not thread-safe
- `UseAuthentication` precedes `UseAuthorization`
- `IQueryable` is SQL until a materializing operator

**Change Impact Preview:**

- Lifetime change (Singleton <-> Scoped): breaks captive-dependency invariants
- Adding / removing `Include`: shape and N+1 risk for every consumer
- Removing `AsNoTracking`: query now mutates the change tracker
- Adding `[Authorize]`: every action requires auth unless `[AllowAnonymous]`

## Avoid

- Treating `IQueryable` and `IEnumerable` as interchangeable
- Recommending `ConfigureAwait(false)` in ASP.NET Core app code
- Calling `DbContext` safe across requests or threads
- Using `Task.Run` to "make code async"
- Describing an endpoint without naming middleware order
