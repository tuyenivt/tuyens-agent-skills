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

Reviewing a .NET / ASP.NET Core diff that adds FluentValidation rules, null checks, service interfaces, MediatR handlers, or AutoMapper profiles. Phase D of `task-dotnet-review`: code that is correct but does not need to exist.

## Rules

- Every finding cites the constraint that makes the code redundant: FK, `nullable: false`, unique index, EF Core `IsRequired()`, FluentValidation rule on the DTO, NRT, or framework guarantee.
- Severity:
  - `[Suggestion]` is the default. Cite the constraint, recommend the edit.
  - `[High]` when a measurable cost is present (extra SELECT in a hot path, blanket `catch (Exception)` masking real bugs, single-impl interface, controller `try/catch` defeating `IExceptionHandler`, MediatR latency on a trivial read). State the cost in `Cost:`.
  - `[Question]` when justification is plausible but not visible in the diff.
- Do not flag when the justification is visible in the diff: DTO-side FluentValidation owning 400 errors, defense-in-depth across non-HTTP write paths (MassTransit, Hangfire), interface required by a proxy aspect or planned second implementer, MediatR with registered pipeline behaviors.

## Patterns

### Category 1: Redundant validation vs EF Core / DB constraints

Validation stack: NRT -> FluentValidation (DTO) -> EF Core `IsRequired()` -> DB `nullable: false`. FluentValidation owns user-facing errors; Fluent API owns schema; DB is authoritative. Net-new annotations on the entity or extra runtime checks are redundant when the DTO is the sole write path.

```csharp
// Bad - .NotNull() on a non-nullable reference type or value type is dead
RuleFor(x => x.Items).NotNull();         // List<OrderItem> non-nullable
RuleFor(x => x.CustomerId).NotNull();    // Guid value type

// Good - .NotEmpty() carries meaning (Guid.Empty is the canonical absent value)
RuleFor(x => x.CustomerId).NotEmpty();
RuleFor(x => x.Items).NotEmpty();
```

```csharp
// Bad - DataAnnotations stacked on FluentValidation: two sources, conflicting messages
public record CreateOrderRequest([Required] Guid CustomerId, [Required, MinLength(1)] List<OrderItem> Items);
```

`[High]` Manual unique / FK existence check before `SaveChangesAsync`: races (two concurrent requests both pass) and adds a query per write; the constraint decides anyway.

```csharp
// Bad - unique pre-check before insert
if (await _db.Users.AnyAsync(u => u.Email == req.Email, ct)) throw new DuplicateEmailException();

// Good - let the constraint decide, translate at the catch site
try { await _db.SaveChangesAsync(ct); }
catch (DbUpdateException ex) when (ex.InnerException is PostgresException { SqlState: "23505" }) {
    throw new DuplicateEmailException(ex);
}
```

### Category 2: Defensive code for impossible states

NRT + FluentValidation + ASP.NET Core model binder give overlapping guarantees. Re-checking what one already proved is dead and can defeat `IExceptionHandler` status mapping. Legitimate at a public API boundary where untyped callers may pass null; otherwise accept `T?` and handle it.

```csharp
// Bad - req is non-nullable (NRT); model binder rejected null before the handler ran
ArgumentNullException.ThrowIfNull(req);
ArgumentNullException.ThrowIfNull(req.CustomerId);  // Guid value type; no-op

// Bad - null-forgiving silences the compiler without proving non-null
public OrderResponse Map(Order order) => new(order!.Id, order!.Total);
```

`[High]` Blanket `catch (Exception)` defeats `IExceptionHandler`. Swallows `DbUpdateException`, domain exceptions the global handler maps to Problem Details (404, 409, 422); users see opaque 500s. `OperationCanceledException` must always propagate. Catch-and-rethrow with no transformation (`catch (X) { throw; }`) is the same anti-pattern.

```csharp
// Bad
catch (Exception ex) { _logger.LogError(ex, "failed"); return Result.Failure<OrderResponse>("oops"); }

// Good - name the failures this call can raise; let the rest reach IExceptionHandler
catch (InsufficientStockException ex) { return Result.Failure<OrderResponse>(ex.Message); }
catch (PaymentDeclinedException ex)   { return Result.Failure<OrderResponse>(ex.Message); }
```

### Category 3: Premature abstraction

`[High]` Single-implementation service interface. NSubstitute / Moq mock concrete classes via Castle.DynamicProxy; the interface earns nothing without a second implementer or a proxy aspect that requires the seam. MediatR / MassTransit marker interfaces are framework-required and exempt.

```csharp
// Bad
public interface IOrderService { Task<OrderResponse> FulfillAsync(Guid id, CancellationToken ct); }
public class OrderService : IOrderService { ... }

// Good - direct class; mock it directly in tests
public class OrderService { ... }
```

`[High]` MediatR for a trivial read on a hot path. MediatR earns its keep through pipeline behaviors (validation, logging, transaction, authorization). A handler that only calls `FindAsync` adds latency for no cross-cutting concern. Direct DbContext call; reserve MediatR for commands and cross-cutting concerns.

`[Suggestion]` AutoMapper for 1:1 mappings; `BaseRepository<T>` / `BaseService<T>` for one or two consumers; speculative `IOptions<T>` keys with no readers; `Result<T>` when no caller branches on multiple distinct failure modes.

```csharp
// Bad - AutoMapper for a 1:1 mapping (runtime cost, refactor-unsafe)
CreateMap<Order, OrderResponse>();

// Good - explicit; constructor catches refactor breaks at compile time
public static OrderResponse ToResponse(this Order o) => new(o.Id, o.Total, o.Status);
```

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
- Flagging a single-impl interface required by MediatR / MassTransit / proxy aspect.
- Flagging `ArgumentNullException.ThrowIfNull` at public API boundaries where untyped callers may pass null.
- Flagging MediatR for a query when registered pipeline behaviors apply - cite the behavior.
- Confusing "duplicated" with "defense in depth" when multiple write paths bypass the DTO.
