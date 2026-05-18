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

- Reviewing a .NET / ASP.NET Core diff that adds FluentValidation rules, null checks, service interfaces, MediatR handlers, or AutoMapper profiles
- Phase D of `task-dotnet-review`: catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint that makes the code redundant: FK name, `nullable: false` column, unique index, EF Core `IsRequired()`, FluentValidation rule on the DTO, nullable reference type, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present: extra SELECT in a hot path, blanket `catch (Exception)` masking real bugs, single-impl interface forcing every refactor to touch two files, controller `try/catch` defeating `IExceptionHandler` Problem Details mapping, or MediatR indirection adding latency to a trivial read. Cite the cost in the `Cost:` field.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. Skip it. Classic cases: FluentValidation on a DTO consumed by `[ApiController]` model binding (owns 400 + field errors); defense-in-depth across multiple write paths (HTTP + MassTransit consumer + Hangfire job); interface required by an `[Aspect]`-style proxy or a planned second implementer.

## Patterns

### Category 1: Redundant validation vs EF Core / DB constraints

The .NET validation stack: **nullable reference types → FluentValidation on the DTO → EF Core `IsRequired()` / `[Required]` → DB column `nullable: false`**. FluentValidation owns user-facing errors; EF Core Fluent API owns schema; DB is authoritative. Net-new entity annotations are redundant when the DTO is the sole write path and Fluent API already enforces the column.

#### FluentValidation rule duplicating type guarantees

```csharp
// Bad - .NotNull() on a non-nullable reference type is dead; the NRT already forbids null
RuleFor(x => x.CustomerId).NotEmpty();   // Guid value type - .NotEmpty() is the real constraint
RuleFor(x => x.Items).NotNull();         // List<OrderItem> non-nullable; .NotNull() dead

// Good
RuleFor(x => x.CustomerId).NotEmpty();
```

`Guid.Empty` is the canonical "absent" value for `Guid`, so `.NotEmpty()` carries meaning beyond NRT. `.NotNull()` on a non-nullable reference type does not.

#### Data Annotations on top of FluentValidation

```csharp
// Bad - two validation sources; conflicting error messages
public record CreateOrderRequest(
    [Required] Guid CustomerId,
    [Required, MinLength(1)] List<OrderItem> Items);

// Good - one source of truth
public record CreateOrderRequest(Guid CustomerId, List<OrderItem> Items);
```

This codebase uses FluentValidation; Data Annotations on DTOs are themselves the smell.

#### Manual unique-check before `SaveChangesAsync`

`[High]` - races (two concurrent requests both pass the SELECT) and adds a query per write; the unique index decides anyway.

```csharp
// Bad
if (await _db.Users.AnyAsync(u => u.Email == req.Email, ct))
    throw new DuplicateEmailException();
_db.Users.Add(new User(req));
await _db.SaveChangesAsync(ct);

// Good - the unique index "IX_Users_Email" is authoritative; translate at the catch site
_db.Users.Add(new User(req));
try {
    await _db.SaveChangesAsync(ct);
} catch (DbUpdateException ex) when (ex.InnerException is PostgresException { SqlState: "23505" }) {
    throw new DuplicateEmailException(ex);
}
```

### Category 2: Defensive code for impossible states

NRT, FluentValidation pipelines, and ASP.NET Core's model binder provide overlapping guarantees. Re-checking what one already proved is dead code; it can also defeat `IExceptionHandler` status mapping.

#### `ArgumentNullException.ThrowIfNull` / `null!` on already-non-null values

```csharp
// Bad - req is non-nullable (NRT); the model binder rejected null before the handler ran
public async Task<IResult> Handle(CreateOrderCommand req, CancellationToken ct) {
    ArgumentNullException.ThrowIfNull(req);          // dead
    ArgumentNullException.ThrowIfNull(req.CustomerId); // CustomerId is Guid value type; no-op
    ...
}

// Bad - null-forgiving silences the compiler without proving non-null
public OrderResponse Map(Order order) => new(order!.Id, order!.Total);
```

Legitimate on a method that accepts `T?` and treats null as a programmer bug, or at a public API boundary where untyped callers may pass null. If `order` can be null, accept `Order?` and handle it.

#### Blanket `catch (Exception)` - defeats `IExceptionHandler`

`[High]`. Swallows `DbUpdateException`, `OperationCanceledException`, and domain exceptions that the global handler would map to Problem Details (404, 409, 422). The user gets opaque 500s. `OperationCanceledException` must always propagate.

```csharp
// Bad
try { return await _service.FulfillAsync(orderId, ct); }
catch (Exception ex) {
    _logger.LogError(ex, "fulfillment failed");
    return Result.Failure<OrderResponse>("something went wrong");
}

// Good - name the failures the call can raise; let the rest reach IExceptionHandler
try { return await _service.FulfillAsync(orderId, ct); }
catch (InsufficientStockException ex) { return Result.Failure<OrderResponse>(ex.Message); }
catch (PaymentDeclinedException ex)   { return Result.Failure<OrderResponse>(ex.Message); }
```

Catch-and-rethrow with no transformation (`catch (X) { throw; }`) is the same anti-pattern; HTTP status mapping belongs in `IExceptionHandler`, not every handler.

### Category 3: Premature abstraction

Each pattern below is `[Suggestion]` by default; `[High]` only when the abstraction has measurable cost (MediatR latency on a hot path, two-file refactor friction).

#### Single-implementation service interface

`[High]`. NSubstitute / Moq mock concrete classes via Castle.DynamicProxy; the interface earns nothing without a second implementer or a proxy aspect that requires the seam.

```csharp
// Bad
public interface IOrderService { Task<OrderResponse> FulfillAsync(Guid id, CancellationToken ct); }
public class OrderService : IOrderService { ... }

// Good
public class OrderService { ... }
```

MediatR / MassTransit register handlers via marker interfaces - those are framework-required, not subject to this rule.

#### `BaseRepository<T>` / `BaseService<T>` for one or two consumers

```csharp
// Bad - generic scaffold saves 3 lines at the cost of generics propagation
public abstract class BaseRepository<TEntity, TKey> where TEntity : class { ... }

// Good - inline; abstract once 3+ repositories share genuine cross-cutting behavior
public class OrderRepository {
    private readonly AppDbContext _db;
    public OrderRepository(AppDbContext db) => _db = db;
    public Task<Order?> FindAsync(Guid id, CancellationToken ct) =>
        _db.Orders.FindAsync(new object[] { id }, ct).AsTask();
}
```

#### MediatR for a trivial read

`[High]` on a hot path. MediatR earns its keep through **pipeline behaviors** (validation, logging, transaction, authorization). A handler that only calls `FindAsync` adds latency for no cross-cutting concern.

```csharp
// Bad - MediatR routing for a single repository read
public record GetOrderByIdQuery(Guid Id) : IRequest<OrderResponse?>;
public class GetOrderByIdQueryHandler(AppDbContext db)
    : IRequestHandler<GetOrderByIdQuery, OrderResponse?> {
    public async Task<OrderResponse?> Handle(GetOrderByIdQuery q, CancellationToken ct) =>
        (await db.Orders.FindAsync(new object[] { q.Id }, ct))?.ToResponse();
}

// Good - direct DbContext call; reserve MediatR for commands and cross-cutting concerns
```

Justified when the read shares pipeline behaviors with commands and "everything goes through MediatR" is the documented project standard.

#### AutoMapper / `Result<T>` / `IOptions<T>` speculation

```csharp
// Bad - AutoMapper for a 1:1 mapping (runtime cost, refactor-unsafe)
CreateMap<Order, OrderResponse>();

// Good - explicit; constructor catches refactor breaks at compile time
public static OrderResponse ToResponse(this Order o) => new(o.Id, o.Total, o.Status);
```

```csharp
// Bad - speculative IOptions<T> keys that no code reads
public record PaymentsOptions {
    public required string GatewayUrl { get; init; }
    public bool Audit { get; init; }            // never read
    public string? TracingTag { get; init; }    // never read
}
```

Reserve AutoMapper for genuinely complex transforms; keep `Result<T>` only when callers branch on multiple distinct failure modes carrying data beyond a string.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `RuleFor(x => x.Items).NotNull()`}
- Redundant because: {FK name | `nullable: false` column | unique index | NRT | DTO FluentValidation rule | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | MediatR latency on hot path} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging FluentValidation rules on DTOs - that layer owns user-facing error messages
- Flagging `.NotEmpty()` on `Guid` - `Guid.Empty` is a meaningful "absent" value
- Recommending removal of a unique-check without confirming a unique index exists
- Flagging a single-impl interface required by MediatR / MassTransit / an `[Aspect]` proxy
- Flagging `ArgumentNullException.ThrowIfNull` at public API boundaries where untyped callers may pass null
- Confusing "duplicated" with "defense in depth" when multiple write paths bypass the DTO
- Recommending removal of MediatR for a query that uses pipeline behaviors (logging, authorization, transaction) - cite the reason it earns its keep
