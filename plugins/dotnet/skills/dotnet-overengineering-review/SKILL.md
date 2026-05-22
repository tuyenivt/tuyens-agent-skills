---
name: dotnet-overengineering-review
description: .NET necessity review - FluentValidation duplicating EF Core/NRT, defensive null checks, single-impl interfaces, MediatR for trivial reads.
metadata:
  category: backend
  tags: [dotnet, aspnet-core, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a .NET / ASP.NET Core diff that adds FluentValidation rules, null checks, service interfaces, MediatR handlers, or AutoMapper profiles.
- Phase D of `task-dotnet-review`: code that is correct, performant, and safe but does not need to exist.

## Rules

- Every finding cites the constraint that makes the code redundant: FK, `nullable: false` column, unique index, EF Core `IsRequired()`, FluentValidation rule on the DTO, NRT, or framework guarantee.
- Severity:
  - **`[Suggestion]`** is the default. Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present (extra SELECT in a hot path, blanket `catch (Exception)` masking real bugs, single-impl interface forcing two-file refactors, controller `try/catch` defeating `IExceptionHandler`, MediatR latency on a trivial read). State the cost in `Cost:`.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- Skip when justification is visible: FluentValidation on a DTO whose `[ApiController]` model binding owns 400 + field errors; defense-in-depth across multiple write paths (HTTP + MassTransit + Hangfire); interface required by an `[Aspect]` proxy or planned second implementer; MediatR with registered pipeline behaviors (validation, logging, transaction, authorization).

## Patterns

### Category 1: Redundant validation vs EF Core / DB constraints

Validation stack: **NRT -> FluentValidation (DTO) -> EF Core `IsRequired()` -> DB `nullable: false`**. FluentValidation owns user-facing errors; Fluent API owns schema; DB is authoritative. Net-new annotations are redundant when the DTO is the sole write path.

#### FluentValidation rule duplicating type guarantees

```csharp
// Bad - .NotNull() on a non-nullable reference type is dead; NRT already forbids null
RuleFor(x => x.Items).NotNull();         // List<OrderItem> non-nullable
RuleFor(x => x.CustomerId).NotNull();    // Guid value type

// Good - .NotEmpty() carries meaning (Guid.Empty is the canonical absent value)
RuleFor(x => x.CustomerId).NotEmpty();
RuleFor(x => x.Items).NotEmpty();
```

#### Data Annotations on top of FluentValidation

```csharp
// Bad - two validation sources; conflicting error messages
public record CreateOrderRequest([Required] Guid CustomerId, [Required, MinLength(1)] List<OrderItem> Items);

// Good
public record CreateOrderRequest(Guid CustomerId, List<OrderItem> Items);
```

#### Manual unique / FK existence check before `SaveChangesAsync`

`[High]` - races (two concurrent requests both pass the SELECT) and adds a query per write; the index / FK decides anyway.

```csharp
// Bad - unique pre-check
if (await _db.Users.AnyAsync(u => u.Email == req.Email, ct)) throw new DuplicateEmailException();

// Bad - FK existence pre-check; the FK on Orders.CustomerId catches missing customer at SaveChanges
if (!await _db.Customers.AnyAsync(c => c.Id == req.CustomerId, ct)) throw new CustomerNotFoundException();

// Good - let the constraint decide, translate at the catch site
try { await _db.SaveChangesAsync(ct); }
catch (DbUpdateException ex) when (ex.InnerException is PostgresException { SqlState: "23505" }) {
    throw new DuplicateEmailException(ex);
}
```

### Category 2: Defensive code for impossible states

NRT + FluentValidation + ASP.NET Core model binder give overlapping guarantees. Re-checking what one already proved is dead and can defeat `IExceptionHandler` status mapping.

#### `ArgumentNullException.ThrowIfNull` / `null!` on already-non-null values

```csharp
// Bad - req is non-nullable (NRT); the model binder rejected null before the handler ran
ArgumentNullException.ThrowIfNull(req);
ArgumentNullException.ThrowIfNull(req.CustomerId);  // Guid value type; no-op

// Bad - null-forgiving silences the compiler without proving non-null
public OrderResponse Map(Order order) => new(order!.Id, order!.Total);
```

Legitimate at a public API boundary where untyped callers may pass null. If `order` can be null, accept `Order?` and handle it.

#### Blanket `catch (Exception)` - defeats `IExceptionHandler`

`[High]`. Swallows `DbUpdateException`, `OperationCanceledException`, and domain exceptions the global handler maps to Problem Details (404, 409, 422). Users see opaque 500s. `OperationCanceledException` must always propagate. Catch-and-rethrow with no transformation (`catch (X) { throw; }`) is the same anti-pattern.

```csharp
// Bad
try { return await _service.FulfillAsync(orderId, ct); }
catch (Exception ex) { _logger.LogError(ex, "failed"); return Result.Failure<OrderResponse>("oops"); }

// Good - name the failures this call can raise; let the rest reach IExceptionHandler
try { return await _service.FulfillAsync(orderId, ct); }
catch (InsufficientStockException ex) { return Result.Failure<OrderResponse>(ex.Message); }
catch (PaymentDeclinedException ex)   { return Result.Failure<OrderResponse>(ex.Message); }
```

### Category 3: Premature abstraction

`[Suggestion]` by default; `[High]` only when the abstraction has measurable cost (MediatR latency, two-file refactor friction).

#### Single-implementation service interface

`[High]`. NSubstitute / Moq mock concrete classes via Castle.DynamicProxy; the interface earns nothing without a second implementer or a proxy aspect that requires the seam. MediatR / MassTransit marker interfaces are framework-required, not subject to this rule.

```csharp
// Bad
public interface IOrderService { Task<OrderResponse> FulfillAsync(Guid id, CancellationToken ct); }
public class OrderService : IOrderService { ... }

// Good
public class OrderService { ... }
```

#### `BaseRepository<T>` / `BaseService<T>` for one or two consumers

```csharp
// Bad - generic scaffold saves 3 lines at the cost of generics propagation
public abstract class BaseRepository<TEntity, TKey> where TEntity : class { ... }

// Good - inline; abstract once 3+ repositories share genuine cross-cutting behavior
public class OrderRepository(AppDbContext db) {
    public Task<Order?> FindAsync(Guid id, CancellationToken ct) =>
        db.Orders.FindAsync(new object[] { id }, ct).AsTask();
}
```

#### MediatR for a trivial read

`[High]` on a hot path. MediatR earns its keep through pipeline behaviors (validation, logging, transaction, authorization). A handler that only calls `FindAsync` adds latency for no cross-cutting concern.

```csharp
// Bad
public record GetOrderByIdQuery(Guid Id) : IRequest<OrderResponse?>;
public class GetOrderByIdQueryHandler(AppDbContext db) : IRequestHandler<GetOrderByIdQuery, OrderResponse?> {
    public async Task<OrderResponse?> Handle(GetOrderByIdQuery q, CancellationToken ct) =>
        (await db.Orders.FindAsync(new object[] { q.Id }, ct))?.ToResponse();
}

// Good - direct DbContext call; reserve MediatR for commands and cross-cutting concerns
```

#### AutoMapper for 1:1 mappings; speculative `IOptions<T>` / `Result<T>`

```csharp
// Bad - AutoMapper for a 1:1 mapping (runtime cost, refactor-unsafe)
CreateMap<Order, OrderResponse>();

// Good - explicit; constructor catches refactor breaks at compile time
public static OrderResponse ToResponse(this Order o) => new(o.Id, o.Total, o.Status);

// Bad - speculative IOptions<T> keys that no code reads
public record PaymentsOptions { public required string GatewayUrl { get; init; } public bool Audit { get; init; } }
```

Reserve AutoMapper for genuinely complex transforms; keep `Result<T>` only when callers branch on multiple distinct failure modes carrying data beyond a string.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `RuleFor(x => x.Items).NotNull()`}
- Redundant because: {FK | `nullable: false` column | unique index | NRT | DTO FluentValidation rule | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | MediatR latency on hot path} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging FluentValidation rules on DTOs - that layer owns user-facing error messages.
- Flagging `.NotEmpty()` on `Guid` - `Guid.Empty` is a meaningful "absent" value.
- Recommending removal of a unique / FK pre-check without confirming the index or FK exists.
- Flagging a single-impl interface required by MediatR / MassTransit / `[Aspect]` proxy.
- Flagging `ArgumentNullException.ThrowIfNull` at public API boundaries where untyped callers may pass null.
- Flagging MediatR for a query that uses registered pipeline behaviors - cite the behavior that earns its keep.
- Confusing "duplicated" with "defense in depth" when multiple write paths bypass the DTO.
