---
name: task-dotnet-refactor
description: Plan safe .NET / ASP.NET Core / EF Core refactors - fat controllers, .Result blocking, N+1, mass assignment, captive DI; commit-safe phased steps.
agent: dotnet-tech-lead
metadata:
  category: backend
  tags: [dotnet, aspnet-core, ef-core, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# .NET Refactor

Produce a phased, commit-safe refactor plan for a .NET target (controller / Minimal API endpoint, MediatR handler, application service, EF Core repository or entity, `BackgroundService`, DTO record). Stack-specific delegate of `task-code-refactor`.

## When to Use

- .NET smell identification and resolution on a named target
- Pre-merge cleanup of fat controllers / god services / handlers
- Technical-debt reduction with a concrete step sequence

**Not for:** debt prioritization (`task-debt-prioritize`), features (`task-dotnet-implement`), cross-project re-architecture (`task-design-architecture`), bug fixes (`task-dotnet-debug`).

## Inputs

| Input                | Required    | Description                                                                                |
| -------------------- | ----------- | ------------------------------------------------------------------------------------------ |
| Target               | Yes         | File / class / endpoint (e.g., `src/Acme.Api/Controllers/OrdersController.cs`)             |
| Goal                 | Yes         | What the refactor achieves (extract handler, eliminate `.Result`, split god service, ...)  |
| Test coverage status | Recommended | xUnit / Testcontainers / `WebApplicationFactory` coverage; format/analyzer baseline state  |
| Shared surface       | Recommended | Whether target is `public` across project / assembly / NuGet boundaries                    |

If only a goal is given without a target, ask for the target before proceeding.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detection

Use skill: `stack-detect`. If invoked by a .NET-aware parent, accept the pre-confirmed stack. If the detected stack is not .NET, stop and route to `/task-code-refactor`.

Record `Data Access` (EF Core / Dapper / mixed), `Mediator` (MediatR / none), `Messaging` (MassTransit / Hangfire / Channel / none) for the output.

### Step 3 - Read the Target

Read the file(s) named in Inputs before classifying. Plans grounded in prose hallucinate smells. Specifically read:

1. Target file top-to-bottom: method count, longest method, sync/async signature mix, transaction placement (`BeginTransactionAsync` / `SaveChangesAsync`), external collaborators (`HttpClient`, `IMediator`, `IPublishEndpoint`, mailers), `await` points.
2. Matching tests (`tests/<Project>.UnitTests/...`, `IntegrationTests/...`, `ApiTests/...`): cases by outcome (happy / validation / external failure / auth denial). Note `dotnet format --verify-no-changes` baseline and whether `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` is on.
3. Immediate callers of any `public` member being reshaped.

**Sibling smells.** If the file contains smells outside the named target, list them under `Sibling Smells (Out of Scope)` with deferral rationale and recommended follow-up (e.g., security findings → `task-dotnet-review-security`). Do not action them; do not omit them silently.

**Severity inversion.** When any sibling smell is *higher severity* than the named target (SQLi via `FromSqlRaw($"...")`, `Process.Start("cmd.exe", $"/c {input}")` RCE, auth bypass, `BinaryFormatter.Deserialize` on untrusted input), recommend pausing the refactor and routing the security finding first. Render a banner at the top of the Coverage Gate section (above the verdict) so it cannot be skimmed past:

> **Severity inversion detected.** This file contains <N> higher-severity sibling smells (<list>). Pause this refactor; route through `task-dotnet-review-security` first; branch the refactor PR off the security fix.

The banner is required when inversion fires regardless of the Coverage Gate verdict.

### Step 4 - Coverage Gate (mandatory)

Identify tests covering the target. Assign status using sharp boundaries:

| Status       | Definition                                                                          | Action                                                          |
| ------------ | ----------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `Adequate`   | Happy path + 2+ boundary outcomes per entry point (validation, auth, external, 404) | Proceed                                                         |
| `Thin`       | Happy path + exactly 1 boundary outcome                                             | Proceed; plan includes `Step 0 - Coverage prerequisite`         |
| `Inadequate` | No tests, happy-path-only, or wrong-store provider mismatch                         | Refuse Steps 1+; emit verdict + prerequisite preview only       |

**Happy-path-only is `Inadequate`.** A single success case cannot prove the refactor preserved validation, auth, or error behavior.

**Wrong-store disqualifier.** Test project uses `UseInMemoryDatabase` / SQLite but the production `.csproj` references `Npgsql.EntityFrameworkCore.PostgreSQL` or `Microsoft.EntityFrameworkCore.SqlServer` -> coverage is `Inadequate` regardless of count. In-memory skips FK enforcement, raw SQL, JSON/array operations, concurrency. Step 0 prerequisite must migrate to Testcontainers.

**Lint baseline.** `dotnet format --verify-no-changes` must be clean and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` on, else Step 0a covers them. Values: `clean` | `warnings present` | `not run (no baseline)`.

**Concurrency check.** If the target uses `Task.Run` / `Parallel.ForEachAsync` / `BackgroundService` / `ConcurrentDictionary` / `SemaphoreSlim` / channels and tests do not exercise the concurrent path, downgrade one tier (`Adequate` -> `Thin`, `Thin` -> `Inadequate`).

### Step 5 - Identify .NET Smells

Signals, not hard rules. Apply judgment.

**Controllers / endpoints:**

| Smell                                       | Signal                                                                                                                                          | Risk   |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat controller                              | Action > 30 lines of orchestration (multiple service calls, conditional dispatch, response shaping)                                             | High   |
| Logic in controller                         | Business rules, validation beyond FluentValidation, calculation, domain decisions inside the action                                             | High   |
| Direct `DbContext` query                    | Action injects `AppDbContext` and runs `db.Orders.Where(...)`, bypassing application/repository layer                                           | Medium |
| Domain entity returned                      | `Ok(user)` where `user: User` is an EF Core entity - leaks `PasswordHash`, triggers lazy-loaded navigations during serialization                | High   |
| Mass assignment via `[FromBody] DomainEntity` | `[FromBody] User request` binds directly to a domain entity - client overrides `Id`, `OwnerId`, `Role`                                        | High   |
| Manual validation duplicating FluentValidation | Action body re-checks rules already covered by validator                                                                                     | Low    |
| Per-action `try/catch -> StatusCode(500)`   | Inline error mapping instead of centralized `IExceptionHandler` + Problem Details                                                               | Medium |
| Missing `[Authorize]` / `[AllowAnonymous]`  | Action has neither - convention-only auth breaks silently on new endpoints                                                                      | High   |

**Handlers / services:**

| Smell                              | Signal                                                                                                                            | Risk   |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God service class                  | `*Service.cs` > 500 lines mixing orchestration, persistence, mapping, external clients                                            | High   |
| Anemic domain                      | Entities are pure data; rules live in `*Helpers.cs` statics that could be instance methods on the entity                          | High   |
| Multiple `SaveChangesAsync` per use case | Splits atomicity; partial state visible                                                                                     | High   |
| External I/O inside transaction    | `httpClient.PostAsync` / message publish inside `BeginTransactionAsync...CommitAsync` - defers commit, holds locks, races workers | High   |
| Returning `null` from failure-capable op | Caller cannot distinguish failure cases - prefer `Result<T>` / domain exceptions                                            | Medium |

**Async / concurrency:**

| Smell                                      | Signal                                                                                                                          | Risk   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` | Sync-over-async - thread-pool starvation, deadlock under `SynchronizationContext`                                      | High   |
| `async void` outside event handler         | Swallows exceptions; `UnobservedTaskException` -> process crash                                                                 | High   |
| `Task.Run` to fake async on sync code      | Offloads to thread-pool for no benefit; call is still sync                                                                      | Medium |
| Floating `Task.Run` / fire-and-forget      | `Task.Run(async () => ...)` without await or `CancellationToken` - leak                                                         | High   |
| Missing `CancellationToken` propagation    | Async method omits `ct`, or accepts it but doesn't forward                                                                      | Medium |
| Sequential `await`s over independent calls | Run via `Task.WhenAll` for independent operations                                                                               | Medium |
| Unbounded `Task.WhenAll` fan-out           | `Task.WhenAll(items.Select(...))` over large list without `Parallel.ForEachAsync` + `MaxDegreeOfParallelism`                    | High   |
| `Channel.CreateUnbounded<T>()` default     | Memory leak under producer-faster-than-consumer; use `CreateBounded<T>(N)` with explicit `FullMode`                             | High   |
| `Thread.Sleep` in `BackgroundService`      | Blocks the thread, ignores `stoppingToken`; use `await Task.Delay(N, stoppingToken)`                                            | High   |
| `BackgroundService` ignoring `stoppingToken` | `while(true)` without checking the token - cannot drain on shutdown                                                           | High   |
| `Monitor.Enter` / `SemaphoreSlim.Wait()` across `await` | Blocks the thread; deadlock risk                                                                                   | High   |
| Background dispatch inside transaction     | MassTransit publish / Hangfire enqueue before `CommitAsync` - worker picks up before commit                                     | High   |
| Background worker without idempotency      | Re-runs side effects on redelivery (no dedup, upsert, version check)                                                            | High   |

**EF Core / persistence:**

| Smell                                          | Signal                                                                                                                                 | Risk   |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat repository                                 | > 300 lines mixing mapping, business operations, validation                                                                            | High   |
| Entity used as DTO                             | Service / controller imports EF entity as both domain type and response type - couples API to schema                                   | Medium |
| `FromSqlRaw($"... {userInput}")` SQL injection | String interpolation into raw SQL - use `FromSqlInterpolated($"... {input}")` or `FromSqlRaw("... {0}", input)`                        | High   |
| N+1 via per-iteration `.Single()`              | `foreach (var p in parents) { db.Children.Single(c => c.ParentId == p.Id) }` - N round-trips                                            | High   |
| N+1 via lazy loading                           | `UseLazyLoadingProxies()` + iterating navigation properties                                                                            | High   |
| `Include` cartesian explosion                  | Chained `.Include` across multiple collections without `AsSplitQuery()`                                                                | High   |
| Missing `AsNoTracking()` on read path          | Read-only query through change tracker - ~30% overhead                                                                                 | Medium |
| `ToListAsync` without pagination               | Full table without `.Skip/.Take` or keyset                                                                                              | Medium |
| `new SqlConnection(...)` per request           | Defeats pooling - use DI'd `DbContext` or pooled `IDbConnectionFactory`                                                                 | High   |

**Configuration / DI:**

| Smell                                                       | Signal                                                                                                       | Risk   |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| Singleton capturing scoped                                  | `AddSingleton<IFoo, Foo>()` where `Foo` ctor takes `AppDbContext` - captive dependency                       | High   |
| Module-level mutable statics                                | `static Dictionary<...> _cache` mutated by handlers; no synchronization                                      | High   |
| `IConfiguration["X"]` sprinkled                             | Should be `IOptions<T>` loaded at startup                                                                    | Medium |
| `IServiceProvider.GetRequiredService<T>()` in ctor / method | Service-locator anti-pattern; bypasses constructor injection contract                                        | Medium |
| Single-implementation interface                             | `IOrderRepository` + sole `OrderRepository`, no mock in tests, no second impl - interface adds nothing       | Medium |
| `new HttpClient()` per request                              | Socket exhaustion - use `IHttpClientFactory` or typed clients                                                | High   |
| AutoMapper for trivial mappings                             | Profile for `record OrderResponse(Guid Id, decimal Total)` <-> `Order` - explicit `new OrderResponse(...)` is shorter, refactor-safe | Medium |
| MediatR for trivial reads                                   | Every read routed through MediatR when it's a single `_repo.GetById(id)` - indirection adds nothing          | Medium |

**`unsafe`:**

| Smell                            | Signal                                                                              | Risk   |
| -------------------------------- | ----------------------------------------------------------------------------------- | ------ |
| `unsafe` without SAFETY comment  | `unsafe { ... }` block without `// SAFETY:` stating what callers must uphold        | High   |
| `unsafe` for speed without bench | Used "because it's faster" without a BenchmarkDotNet result                         | Medium |

**Test smells (when refactoring brings tests into scope):**

| Smell                                                  | Signal                                                                                       | Risk   |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ------ |
| `UseInMemoryDatabase` for Postgres / SQL Server app    | Tests pass on in-memory provider but fail in prod - migrate to Testcontainers                | High   |
| Repository mocked with in-process state                | `new InMemoryRepo()` instead of Testcontainers integration test                              | Medium |
| `Mock<T>().Setup(...).ReturnsAsync(default!)`          | Type-cast escape hatch bypassing a real bug                                                  | Medium |
| Copy-paste `[Fact]` methods where `[Theory]` would do  | Multiple near-identical facts                                                                | Low    |

**Cross-cutting:**

Use skill: `backend-coding-standards` for the language-agnostic catalog.
Use skill: `complexity-review` when over-engineering signals appear (single-impl interfaces, premature factory / strategy, AutoMapper / MediatR on trivial cases) - those are simplification opportunities, not new abstractions.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. .NET-specific signals:

- Public controller action consumed by external clients
- Symbol crosses project / assembly / NuGet boundary
- Interface with broad implementer surface
- Service injected widely from `Program.cs`
- EF entity used in many queries; DTO record reused across endpoints

State: **Narrow** (single file, single caller) | **Moderate** (single project, multiple callers) | **Wide** (cross-project, public action API, broad interface) | **Critical** (NuGet-published, entity used by 5+ consumers).

### Step 7 - Propose the Step Sequence

Each step is **independently committable** (`dotnet build /p:TreatWarningsAsErrors=true` + `dotnet test` + `dotnet format --verify-no-changes` clean), **behaviorally invariant** (unless labeled `coupled-fix`), **reversible** (one revert), **tested** (existing suite passes; new tests added when extracting new units).

**Recipe interleaving.** When multiple recipes apply, pick one **primary** (usually the named goal) as the spine and fold others as additive sub-steps. Do not concatenate recipes. State `Primary recipe:` in the output. If the spine exceeds ~8 steps, split into two plans / two PRs.

**Coupled-fix label.** When a refactor genuinely requires a behavior change (extracting a handler that needs `[Authorize]` for `User.Claims` access), label the step `coupled-fix` with its own test gate and rationale.

**Per-step stances.** The Output Format requires these fields per step; set each explicitly:

- **Transaction stance** - if extracting inside `BeginTransactionAsync...CommitAsync`, callee inherits the transaction via shared scoped `DbContext`. State `inside caller's transaction` or `post-commit dispatch (captured inputs)`. Never silently move I/O across the boundary.
- **Async stance** - converting `.Result` -> `await` cascades to every caller through to `Program.cs`. State `local` or `cascading (list affected callers)`. No partial conversion.
- **DI stance** - state the lifetime explicitly. Singleton capturing scoped requires `IServiceScopeFactory`.
- **Concurrency stance** - new `BackgroundService` / `Task.Run` requires `CancellationToken` propagation and a cross-thread test.

**Common .NET refactor recipes**

Each recipe omits the trailing `dotnet build` + `dotnet test` + `dotnet format --verify-no-changes` gate - it applies to every step by contract.

**Extract handler from fat controller**

1. Add `src/<Project>.Application/<Feature>/PlaceOrderHandler.cs` implementing `IRequestHandler<PlaceOrderCommand, PlaceOrderResult>` (MediatR) or a plain `IPlaceOrderHandler`; copy logic. Controller still does original work.
2. Add `[Theory]`-driven tests covering one case per outcome (success, validation, external failure).
3. Update controller to call the handler via `IMediator` (or constructor-injected handler); preserve response shape.
4. Remove the original logic from the controller.
5. Add a controller test asserting handler failure surfaces as the expected error response (via central `IExceptionHandler`).

**Eliminate `.Result` / `.Wait()` blocking**

1. Convert the calling method to `async Task`; add `CancellationToken ct`; replace blocking with `await`.
2. Cascade: every caller becomes `async Task` and `await`s, in dependency order (innermost first); chain ends at `await app.RunAsync()` or `async Task<IActionResult>` action.
3. Forward `ct` through every call (`FirstOrDefaultAsync(ct)`, `httpClient.GetAsync(url, ct)`).
4. Skip if the call site is genuinely sync-only (third-party sync contract that cannot be changed).

**Eliminate `Task.Run(syncMethod)` on async path**

1. Decide whether `syncMethod` is CPU-bound (image processing, hash) - if yes, `Task.Run` is correct; verify bounded `MaxDegreeOfParallelism`.
2. Otherwise make `syncMethod` async and await directly: `var x = await OrderRepository.GetByIdAsync(id, ct);`.

**Add `CancellationToken` propagation**

1. Entry points (actions, MediatR handlers, `ExecuteAsync`) already take `ct`.
2. Every `async Task` in the chain accepts `ct` as the last parameter and forwards to every awaited call.
3. EF Core (`...Async(ct)`) and `HttpClient` (`GetAsync(url, ct)`) all accept `CancellationToken`.
4. Enforce via `Microsoft.VisualStudio.Threading.Analyzers` or `Meziantou.Analyzer`.

**Eliminate single-implementation interface**

1. Confirm no mock in tests, no second implementation, no DI lifetime / decoration need.
2. Inline: `AddScoped<OrderService>()` instead of `AddScoped<IOrderService, OrderService>()`; consumers use the concrete type.
3. Skip if part of a public NuGet contract or has a real mock / second implementer.

**Replace AutoMapper / MediatR with explicit code (trivial cases)**

1. Inline the mapping or repository call at the consumer: `new OrderResponse(o.Id, o.Total, o.Status.ToString())` / `_repo.GetByIdAsync(id, ct)`.
2. Delete the profile / handler / `IRequest` record; remove DI registration if no other consumers.
3. Skip if pipeline behaviors (validation, auth, transaction wrap, logging) or complex conventions are load-bearing - they earn their keep.

**Fix singleton capturing scoped (captive dependency)**

1. Inject `IServiceScopeFactory` into the singleton; create a scope per operation.

```csharp
public Foo(IServiceScopeFactory scopeFactory) => _scopeFactory = scopeFactory;
public async Task DoWorkAsync(CancellationToken ct) {
    using var scope = _scopeFactory.CreateScope();
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    // use db only within this scope; never store as field
}
```

2. Test that `DbContext` is fresh per call (no cross-call tracking leaks).

**Replace `new HttpClient()` with `IHttpClientFactory`**

1. Register via `services.AddHttpClient<TClient>(c => c.BaseAddress = ...)` or `services.AddHttpClient()`; inject typed client or `IHttpClientFactory`.
2. Add Polly v8 resilience: `.AddResilienceHandler("default", b => b.AddRetry(...).AddCircuitBreaker(...).AddTimeout(...))`.

**Eliminate `[FromBody] DomainEntity` mass assignment**

1. Define a request DTO record with explicit fields + FluentValidation rules. No `Id` / `OwnerId` / `Role`.

```csharp
public record UpdateOrderRequest(string Notes);
public class UpdateOrderRequestValidator : AbstractValidator<UpdateOrderRequest> {
    public UpdateOrderRequestValidator() => RuleFor(x => x.Notes).NotEmpty().MaximumLength(500);
}
```

2. Replace the binding; map to the entity with explicit assignment (`order.Notes = request.Notes`).
3. Add a test injecting `OwnerId` / `Role` - assert stripped.

**Replace static mutable state with DI**

1. Move into a class with a constructor; register via DI (singleton if global, scoped if per-request).
2. Replace static reads / writes with method calls on the injected instance.
3. Test cross-test isolation (xUnit parallel execution).

**Convert sync polling worker to cancellation-aware loop**

1. Loop predicate: `while (!stoppingToken.IsCancellationRequested)`.
2. Replace `Thread.Sleep(N)` with `await Task.Delay(TimeSpan.FromMilliseconds(N), stoppingToken)`.
3. Iteration body: `try { ... } catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; } catch (Exception ex) { _logger.LogError(ex, ...); }`.
4. Forward `stoppingToken` to every awaited call.
5. Add a worker test starting then cancelling the host; assert exit within `HostOptions.ShutdownTimeout`.

**Move side effects out of an open DB transaction**

Use when HTTP calls, message publishes, or file writes happen inside `BeginTransactionAsync...CommitAsync`. Pick **one** option; do not stack.

*Option A - Post-commit dispatch with captured inputs.* Trade-off: at-most-once on crash between commit and dispatch (acceptable for non-critical notifications).

1. Capture inputs into typed records / `Guid` / `byte[]` **inside** the transaction. Do not capture EF entities - their tracker is gone after scope exit.
2. `await tx.CommitAsync(ct)`.
3. Dispatch after commit; log failures but don't roll back.

*Option B - Transactional outbox.* Trade-off: exactly-once at the cost of one extra table + relay.

1. Add `OutboxMessage` table with a partial / filtered index `WHERE processed_at IS NULL`.
2. Inside the transaction: `INSERT INTO outbox_messages` instead of publishing. Commit.
3. Use MassTransit `AddEntityFrameworkOutbox<AppDbContext>` or a hand-rolled `BackgroundService` polling with `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres) / `WITH (UPDLOCK, READPAST)` (SQL Server).
4. Consumers must be idempotent (retries guaranteed -> duplicates guaranteed).
5. Add metrics: `outbox_unprocessed_count`, `outbox_oldest_age_seconds`.

State the option choice explicitly in the plan.

**Make background worker idempotent**

1. Add a test asserting the side effect occurs exactly once when the same business key is processed twice (different message IDs).
2. Idempotency guard: dedup table on business key; upsert via `ON CONFLICT DO NOTHING` (Postgres) / `MERGE` (SQL Server) / version check.
3. Configure explicit retry + DLQ (MassTransit `UseMessageRetry(r => r.Intervals(...))` + dead-letter exchange; Hangfire `[AutomaticRetry(Attempts = N)]`).
4. For MassTransit, adopt `AddEntityFrameworkOutbox<AppDbContext>` so dispatch fires iff `SaveChangesAsync` commits.

### Step 8 - Validate Against Goal

- [ ] Goal achieved at end of sequence
- [ ] Each step reviewable in < 30 minutes
- [ ] `dotnet build /p:TreatWarningsAsErrors=true` + `dotnet test` + `dotnet format --verify-no-changes` between every step
- [ ] Ordered low-risk first (additions, extractions) before high-risk (deletions, signature changes, interface removals)
- [ ] Rollback is one revert per step
- [ ] No "while we're here" cleanup bundled in

## Output Format

```markdown
## .NET Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [recipe name from Step 7 - the spine]
**Stack:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**Mediator:** MediatR <version> | none
**Messaging:** MassTransit | Hangfire | Channel | none

## Coverage Gate

[Render severity-inversion banner here when applicable, above the verdict.]

**Status:** Adequate | Thin | Inadequate
**Lint state:** clean | warnings present (Step 0a) | not run (no baseline)
**Concurrency-test coverage:** clean | not exercised cross-thread | n/a

[If Adequate: one sentence on boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 covers them.]
[If Inadequate: state what coverage must exist; recommend `task-dotnet-test`. **Stop the workflow here** - omit Blast Radius, Step Sequence, Verification. Still produce Smells Identified, Sibling Smells, and the Coverage Prerequisite Table (below) as preview, labeled preview-only.]

### Coverage Prerequisite Table (when Thin or Inadequate)

One row per public entry point. Required outcomes: validation (4xx), authorization (401/403), not-found / IDOR, external-collaborator failure. Add a **concurrent path** row whenever the concurrency check in Step 4 applied.

| Entry point        | Outcome                  | Recommended layer                                  |
| ------------------ | ------------------------ | -------------------------------------------------- |
| POST /api/orders   | unknown-field rejected   | API test (`WebApplicationFactory<Program>`)        |
| POST /api/orders   | unauthorized denied      | API test                                           |
| ...                | ...                      | unit (xUnit + NSubstitute) | integration (Testcontainers) | background-worker | multi-thread (xUnit per-collection parallelism + concurrent execution) |

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/class this plan does NOT address. Listed for hand-off, not action. Omit if none._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                              |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security / perf review]                   | [`task-dotnet-review-security` / `task-dotnet-refactor` on a different target]     |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add boundary tests from the Coverage Prerequisite Table
- **Risk:** Low (tests-only)
- **Test gate:** new tests pass; suite green; `dotnet format --verify-no-changes` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if lint state is clean)_

- **Change:** address existing format / analyzer warnings on the target project
- **Risk:** Low (no behavior change)
- **Test gate:** `dotnet format --verify-no-changes` clean; `dotnet build /p:TreatWarningsAsErrors=true` succeeds; `dotnet test` green
- **Rollback:** revert lint fixes

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** Low | Medium | High
- **Step kind:** refactor | coupled-fix _(if coupled-fix, state why coupling is structural)_
- **Test gate:** [unit / API / Testcontainers / worker; `dotnet format --verify-no-changes` clean]
- **Transaction stance:** inside caller's transaction | post-commit dispatch | not transactional
- **Async stance:** unchanged | adds `CancellationToken` | converts `.Result` -> `await` (local | cascading: <callers>)
- **DI stance:** unchanged | AddScoped | AddSingleton | AddTransient | IServiceScopeFactory
- **Concurrency stance:** unchanged | introduces `BackgroundService` (CT + concurrent test) | removes blocking | lock change
- **Rollback:** [how to revert in one git revert]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] `dotnet build /p:TreatWarningsAsErrors=true` + `dotnet test` + `dotnet format --verify-no-changes` clean between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` introduced; async chain converted end-to-end where touched
- [ ] No new singleton capturing scoped; `IServiceScopeFactory` used when needed
- [ ] No new `BackgroundService` / `Task.Run` without `CancellationToken` propagation and bounded fan-out
- [ ] No new concurrency without cross-thread test coverage

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed as .NET / ASP.NET Core (or accepted from parent); data access / mediator / messaging recorded
- [ ] Step 3 - target file(s) and matching tests read directly; sibling smells listed under `Sibling Smells (Out of Scope)` with deferral rationale (or section omitted); severity-inversion banner rendered when applicable
- [ ] Step 4 - Coverage Gate verdict assigned with sharp boundaries; happy-path-only is `Inadequate`; wrong-store mismatch is `Inadequate`; concurrency check downgrades when applicable; lint state recorded; plan refuses Steps 1+ if `Inadequate`
- [ ] Step 5 - smells identified using the catalog (controllers, handlers/services, async/concurrency, EF Core, DI, `unsafe`, tests)
- [ ] Step 6 - blast radius stated before steps
- [ ] Step 7 - `Primary recipe:` named; supporting recipes folded as sub-steps; plan ≤ ~8 steps or split into multiple PRs; per-step stances (transaction / async / DI / concurrency) set; `Step kind: coupled-fix` used only when structurally required; ordered low-risk first
- [ ] Step 8 - goal mapped to end state

## Avoid

- Proposing a refactor without a Coverage Gate - that's a rewrite
- Bundling behavior changes with refactoring (label `coupled-fix` or split)
- Renaming during a refactor (separate PR)
- Removing an interface without a real second use case or mock
- Replacing EF Core <-> Dapper without a measured win (premature)
- Replacing static mutable state with `AsyncLocal<T>` pointing at the same data - same global, extra steps
- Moving I/O across a transaction boundary without stating the stance
- Partial `.Result` -> `await` - convert the chain end-to-end or skip the recipe
- Refactoring a `public` NuGet symbol without a backward-compat plan
- Adding `BackgroundService` / `Task.Run` without `CancellationToken` propagation and bounded fan-out
- Replacing `[FromBody] DomainEntity` with another `[FromBody] DomainEntity` - the issue is the binding, not the name
- Consolidating into a singleton without checking captured scoped services
- Removing AutoMapper / MediatR globally based on one trivial case - keep them where pipeline behaviors / conventions earn their keep
