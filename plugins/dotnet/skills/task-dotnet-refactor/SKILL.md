---
name: task-dotnet-refactor
description: .NET refactor planning for fat controllers, anemic services, god classes, `.Result` / `.Wait()` blocking, missing CancellationToken, EF Core N+1, mass assignment via `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>`, single-implementation interfaces, AutoMapper for trivial mappings, MediatR for trivial reads, singleton-capturing-scoped services, static mutable state, and background-worker idempotency. Produces a step-by-step sequence of independently-committable refactoring steps with a `dotnet build + dotnet test + dotnet format` coverage gate. Stack-specific override of task-code-refactor for .NET.
agent: dotnet-tech-lead
metadata:
  category: backend
  tags: [dotnet, aspnet-core, ef-core, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# .NET Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific .NET target (ASP.NET Core controller / Minimal API endpoint, MediatR handler, application service, EF Core repository, EF Core entity, background worker, DTO record). Identifies .NET-specific smells (fat controller, anemic services, god classes, `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` blocking on async, missing `CancellationToken` propagation, EF Core N+1 via lazy loading or per-iteration `.Single()`, `Include` cartesian explosion, missing `AsNoTracking()`, mass assignment via `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)`, package-level mutable state via `static` fields, single-implementation interfaces, MediatR for trivial reads, AutoMapper for trivial mappings, singleton capturing scoped service (captive dependency), `new HttpClient()` per request, background workers lacking idempotency, `unsafe` without SAFETY comment) and proposes independently-committable refactoring steps with `dotnet build` + `dotnet test` + `dotnet format --verify-no-changes` gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for .NET.

## When to Use

- .NET code-smell identification and resolution
- .NET technical-debt reduction with a concrete plan
- Safe refactoring of a controller / handler / service / repository / module / background worker
- Pre-merge "this PR grew the fat-controller / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-dotnet-new`)
- Architecture-level restructuring across many projects (use `task-design-architecture`)
- Bug fixes / exception investigations (use `task-dotnet-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                                  |
| --------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Target scope          | Yes         | File or class to refactor (e.g., `src/Acme.Api/Controllers/OrdersController.cs`, `src/Acme.Application/Orders/Handlers/PlaceOrderHandler.cs`, `src/Acme.Worker/PaymentProcessor.cs`) |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `PlaceOrder` handler from controller, eliminate `.Result` blocking, split `OrdersService` god class) |
| Test coverage status  | Recommended | Whether xUnit / Testcontainers / `WebApplicationFactory` / job coverage exists for the target area; whether `dotnet format --verify-no-changes` is clean        |
| Shared/public surface | Recommended | Whether the target is `public` across project / assembly / NuGet package boundaries                                                                                     |

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If invoked as a subagent of a .NET-aware parent, accept the pre-confirmed stack. If the detected stack is not .NET, stop and tell the user to invoke `/task-code-refactor` instead.

Detect data access (EF Core / Dapper / mixed), mediator (MediatR / none), and messaging (MassTransit / Hangfire / Channel / none). Record `Data Access`, `Mediator`, `Messaging` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target file top-to-bottom; note method count, longest method, sync-vs-async signature mix (`Task<T>` vs `void`, `async Task` vs sync), transaction placement (`db.Database.BeginTransactionAsync(...)`, `db.SaveChangesAsync(ct)`), every external collaborator (`HttpClient`, MediatR `IMediator.Send`, MassTransit `IPublishEndpoint`, mailers, `await` points)
2. Read the matching test file(s) (`tests/<Project>.UnitTests/<Feature>/<Class>Tests.cs`, `tests/<Project>.IntegrationTests/<Feature>/<Class>Tests.cs`, `tests/<Project>.ApiTests/<Controller>Tests.cs`); count cases by outcome (happy path, validation failure, external failure, auth denial). Confirm `dotnet format --verify-no-changes` runs clean and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` is on (or note it isn't)
3. If callers are obvious (controller calling the handler, scheduled job calling the service), read the immediate caller too - removing or reshaping a `public` member without seeing call sites is how silent breakage happens

If the user named only the goal without a target file / class, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat classes. If the file containing the target also contains other smells (e.g., the user names `CreateOrder` but the same controller file has IDOR in `GetOrder` and a `Process.Start("cmd.exe", $"/c {userInput}")` in `BulkImport`), do **not** action them in this plan and do **not** ignore them silently. List them under a `Sibling Smells (Out of Scope)` heading in the output, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-dotnet-review-security`), and recommend follow-up invocations.

**Severity-inversion rule.** When any sibling smell is *higher severity* than the named primary target (e.g., the user asks to extract a fat controller, but the same file contains a working SQL injection via `FromSqlRaw($"...")`, a `Process.Start("cmd.exe", $"/c {input}")` RCE, an authentication bypass, or `BinaryFormatter.Deserialize` on untrusted input), recommend pausing the refactor and routing the security finding first. State this prominently in the `Sibling Smells (Out of Scope)` table's `Recommended follow-up` column with phrasing like `Fix before refactor: invoke task-dotnet-review-security on this file; refactor PR should branch off the security fix, not main`. The refactor skill produces a plan; it does not silently let an in-scope severe finding land via a refactor PR that doesn't address it.

**Severity-inversion banner.** When the inversion rule fires, **also render a one-paragraph banner at the top of the Coverage Gate section** (above the status verdict) so the inversion is impossible to skim past. Suggested form: `> **Severity inversion detected.** This file contains <N> sibling smells of higher severity than the named target (<list>). Recommended next action: pause this refactor; route through task-dotnet-review-security first; branch the eventual refactor PR off the security fix. See Sibling Smells (Out of Scope) below for details.`. The banner is required when inversion fires regardless of whether the Coverage Gate verdict is `Adequate` / `Thin` / `Inadequate` - the gate verdict and the inversion are orthogonal concerns.

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (xUnit unit tests, integration tests under `tests/*.IntegrationTests`, Testcontainers tests, `WebApplicationFactory` API tests, background-worker tests), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                   | What the workflow does                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., validation failure, auth denial, external failure, not-found) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                               | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                        | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-dotnet-test` first             |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves validation, authorization, or error behavior - you would be flying blind.

**Wrong-store disqualifier.** When the test project uses `UseInMemoryDatabase("...")` (or SQLite) but the production project's `.csproj` references `Npgsql.EntityFrameworkCore.PostgreSQL` / `Microsoft.EntityFrameworkCore.SqlServer`, treat coverage as `Inadequate` regardless of case count. The provider mismatch means the cases test a different store than prod (in-memory skips FK enforcement, raw SQL, JSON / array operations, concurrent updates) - adding more boundary cases on top of the wrong store does not unlock the refactor. The Step 0 prerequisite must include migrating the affected tests to Testcontainers before refactor begins.

**Lint-gate check.** `dotnet format --verify-no-changes` must be clean for the target project, AND `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` should be on, OR the refactor plan must include cleaning warnings as Step 0a. Refactoring on top of unaddressed warnings risks masking new warnings behind existing ones. Lint state values: `clean` (no warnings, format clean), `warnings present` (Step 0a covers them), or `not run (no baseline)` (greenfield / net-new project where format/analyzer enforcement hasn't been wired into CI yet - the plan's first step folds it into the coverage prerequisite work).

**Concurrency-gate check.** If the target class spawns `Task.Run` / `Parallel.ForEachAsync` / `BackgroundService`, holds shared state via `ConcurrentDictionary` / `SemaphoreSlim`, or uses channels, also confirm tests exercise the concurrent paths (xUnit's per-collection parallelism settings, real concurrent execution in tests, not single-threaded happy paths). If absent, treat coverage status as one tier worse (Adequate → Thin, Thin → Inadequate) - refactoring concurrent code without concurrent test coverage is unsafe.

**Output of this step:** explicit coverage status using one of the three labels above. Do not proceed past Step 4 if status is `Inadequate`.

### Step 4 - Identify .NET Smells

Inspect the target for these .NET-specific smells. Use judgment - these are signals, not hard rules.

**Controller / Endpoint smells:**

| Smell                                   | Signal                                                                                                                                                                                              | Risk   |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Controller                          | Action method > 30 lines of orchestration (multiple service calls, conditional dispatch, response shaping, business rules)                                                                          | High   |
| Logic in Controller                     | Business rules, validation beyond `[ApiController]` auto-validation / FluentValidation, calculation, or domain decisions inside the action                                                          | High   |
| Direct `DbContext` Query in Controller  | Action methods inject `AppDbContext` directly and run `db.Orders.Where(...)`, bypassing the application / repository layer                                                                          | Medium |
| Domain Entity Returned from Action      | Action returns `Ok(user)` where `user: User` is an EF Core entity (mass-assignment + leak risk: leaks `PasswordHash`, soft-delete columns, internal fields; triggers lazy-loaded navigations during serialization) | High   |
| Manual Validation Duplicating FluentValidation | Action body re-checks `if (req.Name.Length == 0) ...` already covered by FluentValidation rules                                                                                              | Low    |
| Per-action `try { ... } catch { return StatusCode(500, ex.Message); }` | Inline error mapping scattered across actions instead of centralized `IExceptionHandler` + Problem Details                                                                | Medium |
| Missing `[Authorize]` / `[AllowAnonymous]` | Action has neither - relies on conventions, which break silently on new endpoints                                                                                                                | High   |
| Mass Assignment via `[FromBody] DomainEntity` | Action signature `[FromBody] User request` decoded directly into a domain entity - client can override server-set fields like `Id`, `OwnerId`, `Role`                                       | High   |

**Handler / Service smells:**

| Smell                              | Signal                                                                                                                                                                          | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Service Class                  | `*Service.cs` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                                                                              | High   |
| Anemic Domain                      | Entities are pure data containers; business rules live in `*Helpers.cs` static classes with names like `OrderHelpers.CalculateTotal(order)` and could belong as instance methods on `Order` | High   |
| Single-Implementation Interface    | `IOrderRepository` interface + single `OrderRepository` implementation with no NSubstitute mock and no second implementation - the interface adds nothing                       | Medium |
| `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` | Sync-over-async on the request path - thread-pool starvation under load, deadlock under `SynchronizationContext`                                              | High   |
| `async void` outside event handler | Swallows exceptions silently; `UnobservedTaskException` causes process crash                                                                                                    | High   |
| Missing `CancellationToken` Propagation | Async method does not take `CancellationToken ct` parameter, OR takes it but doesn't forward to inner awaited calls                                                        | Medium |
| External I/O Inside Transaction    | `await httpClient.PostAsync(...)` or message publish inside `await using var tx = await db.Database.BeginTransactionAsync(ct); ...; await tx.CommitAsync(ct)` (defers commit, holds DB locks long, races worker pickup before commit) | High   |
| Multiple `SaveChangesAsync` per Use Case | Handler calls `SaveChangesAsync` more than once - splits atomicity, partial state visible                                                                                | High   |
| `Task.Run(() => syncMethod())` on Already-Async Path | Offloads to a thread-pool thread for no concurrency benefit                                                                                                  | Medium |
| Returning `null` from Failure-Capable Operation | Service returns `T?`; caller cannot distinguish failure cases (validation vs not-found vs external) - return `Result<T>` / throw domain exceptions                  | Medium |
| Floating `Task.Run` / `Task.Factory.StartNew` | Fire-and-forget `Task.Run(async () => { ... })` in a service body without awaiting the result and without `CancellationToken` propagation - leak                  | High   |

**Persistence / EF Core smells:**

| Smell                                        | Signal                                                                                                                                                                                                          | Risk   |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Repository                               | Repository class with > 300 lines of methods; mixes mapping, computed properties, business operations, validation                                                                                              | High   |
| EF Core Entity Used as Domain / DTO Type     | Service / controller imports the EF Core entity directly and uses it as the domain type AND the API response type - couples upper layers to EF Core schema and triggers lazy-loaded navigations                | Medium |
| `FromSqlRaw($"... {userInput}")` SQL Injection | Dynamic SQL built via string interpolation instead of parameterized `FromSqlInterpolated($"... {input}")` (parameterizes interpolated holes) or `FromSqlRaw("... {0}", input)` with explicit parameter      | High   |
| EF Core N+1 via Per-Iteration `.Single()`    | `foreach (var parent in parents) { var child = db.Children.Single(c => c.ParentId == parent.Id); ... }` - N round-trips                                                                                        | High   |
| EF Core N+1 via Lazy Loading                 | `UseLazyLoadingProxies()` enabled and access to navigation property in iteration triggers per-row query                                                                                                         | High   |
| `Include` Cartesian Explosion                | `.Include(x => x.Orders).Include(x => x.Addresses)` chain over multiple collections without `AsSplitQuery()` - 100×10×5 = 5000 rows materialized for what should be 1150                                       | High   |
| Missing `AsNoTracking()` on Read Path        | Read-only query running through the change tracker - 30% perf overhead, unnecessary memory                                                                                                                      | Medium |
| `ToListAsync` Without Pagination             | Returns full table without `.Skip/.Take` or keyset pagination                                                                                                                                                   | Medium |
| Long-Running Transaction Holding Connection  | `await using var tx = await db.Database.BeginTransactionAsync(ct);` followed by external I/O before `await tx.CommitAsync(ct)` - holds a `DbContext` pool slot for the network roundtrip                       | High   |
| `new SqlConnection(...)` Per Request         | New connection per handler defeats pooling - Dapper connection comes from a pooled `IDbConnectionFactory`; EF Core uses DI'd `DbContext`                                                                       | High   |

**Configuration / DI smells:**

| Smell                        | Signal                                                                                                                                                              | Risk   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Singleton Capturing Scoped Service | `services.AddSingleton<IFoo, Foo>()` where `Foo` constructor takes `AppDbContext` (scoped) - captive dependency, scoped service lives for process lifetime    | High   |
| Module-level Mutable Statics | `static Dictionary<...> _cache` mutated by request handlers; or worse, `static List<...>` with no synchronization                                                  | High   |
| `Configuration.GetValue<>` Sprinkled | `IConfiguration["X"]` scattered across classes; should be loaded once into `IOptions<T>` typed config at startup                                              | Medium |
| Hardcoded Defaults Inline    | Default values inline in code rather than `IOptions<T>` typed config                                                                                                 | Medium |
| `IServiceProvider.GetRequiredService<T>()` in Constructor / Method | Service-locator anti-pattern; bypasses constructor injection's compile-time dependency contract                                              | Medium |
| Single-Implementation Interface | Interface defined for a single concrete type with no NSubstitute / Moq mock and no second implementation                                                          | Medium |
| `new HttpClient()` Per Request | Socket exhaustion - DNS changes invisible, ephemeral port pool drains; use `IHttpClientFactory.CreateClient(...)` or typed clients via `services.AddHttpClient<TClient>()` | High   |
| AutoMapper for Trivial Mappings | AutoMapper profile for `record OrderResponse(Guid Id, decimal Total)` ↔ `class Order { public Guid Id; public decimal Total; }` - explicit `new OrderResponse(o.Id, o.Total)` is shorter, refactor-safe, faster | Medium |
| MediatR for Trivial Reads    | Every method routed through MediatR even when it's a single `_repo.GetById(id)` - the indirection adds nothing for trivial reads (MediatR is for cross-cutting concerns) | Medium |

**Concurrency / Async smells:**

| Smell                                      | Signal                                                                                                                                                  | Risk   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` | Sync-over-async; thread-pool starvation under load, deadlock under `SynchronizationContext`                                                  | High   |
| `async void` outside event handler         | Swallows exceptions silently; `UnobservedTaskException` causes process crash                                                                            | High   |
| `Task.Run` to Make Sync Code "Async"       | Offloads to thread-pool thread for no benefit; the call is still sync, just on a different thread                                                       | Medium |
| Sequential `await`s Over Independent Calls | `var a = await fetchA(ct); var b = await fetchB(ct);` runs serially - use `Task.WhenAll` for independent calls                                          | Medium |
| Unbounded `Task.WhenAll` Fan-Out           | `Task.WhenAll(items.Select(async i => ...))` over a 10k-item list without `Parallel.ForEachAsync` with `MaxDegreeOfParallelism` - exhausts pool / FDs   | High   |
| `Channel.CreateUnbounded<T>()` Default     | Memory leak under producer-faster-than-consumer; use `Channel.CreateBounded<T>(N)` with explicit `FullMode`                                              | High   |
| `Channel<T>` Reader Without Cancellation   | `await foreach (var item in reader.ReadAllAsync())` without forwarding `stoppingToken` - cannot drain on shutdown                                       | High   |
| `BackgroundService.ExecuteAsync` Without `stoppingToken` Honored | `while (true)` loop ignoring `stoppingToken.IsCancellationRequested` - cannot drain on shutdown                                       | High   |
| `Thread.Sleep` in `BackgroundService.ExecuteAsync` | `Thread.Sleep(N)` instead of `await Task.Delay(N, stoppingToken)` - blocks the worker thread (one less from the pool); does not cooperate with cancellation; prolongs shutdown to the full sleep interval | High |
| Background-Worker Dispatch Inside Transaction | MassTransit publish or Hangfire enqueue inside `tx.CommitAsync` - worker may pick up the message before commit                                       | High   |
| Background-Worker Without Idempotency      | Job that re-runs side effects when delivered twice (no dedup, no upsert, no state check)                                                                | High   |
| `Monitor.Enter` / `lock` Across `await`    | Compile error for `lock`, but `Monitor.Enter` / `SemaphoreSlim.Wait()` + `await` recreates the pattern - blocks the thread, deadlock risk               | High   |

**`unsafe` smells:**

| Smell                       | Signal                                                                                              | Risk   |
| --------------------------- | --------------------------------------------------------------------------------------------------- | ------ |
| `unsafe` Without SAFETY     | `unsafe { ... }` block with no `// SAFETY:` comment naming what the caller must uphold              | High   |
| `unsafe` for Speed Without Bench | `unsafe` used because "it's faster" without a BenchmarkDotNet result proving the win           | Medium |

**Test smells (when refactoring brings tests into scope):**

| Smell                                       | Signal                                                                            | Risk   |
| ------------------------------------------- | --------------------------------------------------------------------------------- | ------ |
| Repository Mocked With In-Process State     | `var repo = new InMemoryRepo();` instead of using a Testcontainers integration test                                                                              | Medium |
| `UseInMemoryDatabase` in Repository Tests for Postgres / SQL Server App | Tests pass on in-memory provider but fail in prod - in-memory provider skips FK enforcement, raw SQL, concurrent updates       | High   |
| In-Process Job Mocking Reality              | Mock processor hides at-least-once / retry / DLQ semantics                        | Medium |
| Copy-Paste `[Fact]` Methods                 | Multiple near-identical `[Fact]` methods where a `[Theory] + [InlineData]` would do | Low    |
| `Mock<T>().Setup(...).ReturnsAsync(default!)` In Test Mocks | Type-cast escape hatch used to bypass a real type bug             | Medium |

**General OO smells (apply with .NET judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl interfaces, abstract base classes for two consumers, premature factory / strategy, redundant mapping layers, MediatR for trivial reads, AutoMapper for trivial mappings) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply .NET judgment - a 25-line handler orchestrating clearly named private methods is fine; a 10-line method doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected by the refactor.

.NET-specific blast-radius signals:

- [ ] **Public API surface**: target is a controller action used by external clients - refactor risks API contract change
- [ ] **Project / assembly boundary**: target is in a published NuGet package, a shared library project consumed by other apps, or carries `public` visibility across project boundaries
- [ ] **Interface with broad implementer surface**: refactoring an interface connected to many implementations / consumers cascades
- [ ] **Service injected widely**: target is registered in `Program.cs` via `services.AddScoped<IFoo, Foo>()` and consumed by many downstream services - signature changes cascade
- [ ] **EF Core entity used in many queries**: refactoring an entity affects every repository / query
- [ ] **DTO record reused across endpoints**: DTO field rename / removal cascades into every dependent endpoint and its tests
- [ ] **Exported `public` symbol**: refactoring a `public` type / method means every importer breaks

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single project, multiple callers) / **Wide** (cross-project, public action API, broad interface) / **Critical** (NuGet-published package, entity used by 5+ consumers).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles with `dotnet build` cleanly and the test suite passes after each step (`dotnet test` and `dotnet format --verify-no-changes`)
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`, see below)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing test suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target (e.g., a fat controller that also has `[FromBody] Order`, blocks via `.Result`, and stashes a `DbContext` in a static field), do **not** concatenate the recipes - that produces a 25-step plan mixing concerns. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly in the output via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs rather than one mega-plan.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a handler that derives `UserId` from JWT claims _requires_ the principal to be available, so adding `[Authorize]` to the route is a structural prerequisite). Label the step `coupled-fix` in the Output Format with its own test gate and rationale.

**Transaction-boundary watch.** When extracting orchestration that runs inside `await using var tx = await db.Database.BeginTransactionAsync(ct); ... await tx.CommitAsync(ct);`, the extracted unit may inherit the transaction context if it takes the same `DbContext` instance (EF Core scopes track the active transaction on the connection). If the extracted code makes HTTP calls, publishes to a queue, or writes files, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's transaction (shares the scoped `DbContext`)" or "callee uses post-commit dispatch (capture inputs, dispatch after `tx.CommitAsync(ct)` returns)." Never silently move I/O across a transaction boundary.

**Async-stance watch.** When restructuring code that calls `.Result` / `.Wait()` / `.GetAwaiter().GetResult()`, state the new async path explicitly. The fix is `await` end-to-end: every method in the chain becomes `async Task`, every call site `await`s, and `CancellationToken` propagates through. Do not partially convert (some callers still using `.Result`) - that's just a different deadlock surface. State whether the conversion is local (handler-only) or cascading (every caller through to `Program.cs`).

**Captive-dependency watch.** When refactoring service registration, state whether the new lifetime is correct (`AddScoped` for `DbContext`, `AddSingleton` for stateless, `AddTransient` for stateful per-call). Singleton capturing scoped is the most common bug; a refactor that consolidates services into a singleton must explicitly check what it captures.

**Cancellation-stance watch.** Adding `BackgroundService` / `Task.Run` introduces work outside the request lifecycle. State whether `CancellationToken` is propagated for graceful shutdown - if not, the new work continues past process termination and may hold resources. State whether tests cover the concurrent path - if not, the new race surface is unguarded.

**Common .NET refactor recipes:**

**Recipe: Extract handler from fat controller**

1. Add `src/<Project>.Application/<Feature>/PlaceOrderHandler.cs` (or new file alongside the existing handlers) implementing `IRequestHandler<PlaceOrderCommand, PlaceOrderResult>` (MediatR) or as a plain service `IPlaceOrderHandler`; copy logic from controller; controller still does the original work
2. Add `tests/<Project>.UnitTests/<Feature>/PlaceOrderHandlerTests.cs` with `[Theory]`-driven tests covering one case per outcome (success, validation failure, external failure)
3. Update controller to call the handler via `IMediator` (MediatR) or constructor-injected handler; preserve response shape; ensure API tests pass unchanged
4. Remove the original logic from the controller; verify API tests pass
5. Add a controller-level test asserting handler failure surfaces as the expected error response (likely via `IExceptionHandler` central mapping)

**Recipe: Eliminate `.Result` / `.Wait()` blocking**

1. Identify the offending blocking call - `var result = service.GetAsync().Result;` or `service.SaveAsync().Wait();`
2. Convert the calling method to `async Task`; add `CancellationToken ct` parameter; replace `.Result` / `.Wait()` with `await`
3. Walk up the call stack: every caller that now invokes an `async Task` method must itself become `async Task` and `await`. Do this in dependency order (innermost first); the chain ends at top-of-`Main` (`await app.RunAsync()`) or at controller actions which already support `async Task<IActionResult>`
4. Forward `CancellationToken ct` through the chain (controller `[FromServices] CancellationToken ct` parameter → handler `Handle(req, ct)` → repository `GetAsync(id, ct)` → EF Core `FirstOrDefaultAsync(ct)`)
5. Run `dotnet build /p:TreatWarningsAsErrors=true` and `dotnet test`; confirm clean. Verify under load (or via load test) that thread-pool stats no longer show starvation
6. **Skip if** the call site is genuinely sync-only (a console app's `Main` before .NET 7's async `Main`, or a synchronous interface contract from a third party that cannot be changed)

**Recipe: Eliminate `Task.Run(() => syncMethod())` on already-async path**

1. Identify the misuse: `var result = await Task.Run(() => syncMethod());` where `syncMethod` is sync but called from an async path
2. Decide: is `syncMethod` actually CPU-bound (e.g., heavy in-memory transformation, image processing, hash computation)? If yes, `Task.Run` is correct - keep it but verify `MaxDegreeOfParallelism` is bounded if called many times. If no (it's I/O-bound or trivial), make `syncMethod` async and `await` it directly:
   ```csharp
   // before
   var result = await Task.Run(() => OrderRepository.GetById(id));
   // after
   var result = await OrderRepository.GetByIdAsync(id, ct);
   ```
3. Run `dotnet build` and `dotnet test`; confirm clean

**Recipe: Add `CancellationToken` propagation**

1. Identify entry points (controller actions, MediatR handlers, BackgroundService.ExecuteAsync): they take `CancellationToken ct` as a parameter
2. Walk the call chain: every `async Task` method called from an entry point should accept `CancellationToken ct` as the last parameter and forward it to every awaited call
3. EF Core async APIs (`FirstOrDefaultAsync(ct)`, `ToListAsync(ct)`, `SaveChangesAsync(ct)`) and `HttpClient` async APIs (`GetAsync(url, ct)`, `PostAsync(url, content, ct)`) all accept `CancellationToken` - forward it
4. Run `dotnet build /p:TreatWarningsAsErrors=true` and `dotnet test`; confirm clean. Roslyn analyzer `Microsoft.VisualStudio.Threading.Analyzers` or `Meziantou.Analyzer` catches missing-CancellationToken patterns in CI

**Recipe: Eliminate single-implementation interface**

1. Confirm the interface has no NSubstitute / Moq mock used in tests, no second implementation, no DI lifetime / decoration need
2. Inline: the consuming code uses the concrete class directly - `services.AddScoped<OrderService>()` instead of `services.AddScoped<IOrderService, OrderService>()`. Delete the interface
3. Run `dotnet build` and `dotnet test`; confirm pass. Caller code is shorter and clearer
4. **Skip if** the interface is part of a public API contract (NuGet package) or has a real second implementation (or NSubstitute mock used in tests) - the smell is fake

**Recipe: Replace AutoMapper with explicit mapping**

1. Identify the AutoMapper profile: `CreateMap<Order, OrderResponse>().ForMember(...)`
2. Inline the mapping at the call site (or extract to a static method): `new OrderResponse(o.Id, o.Total, o.Status.ToString())` instead of `_mapper.Map<OrderResponse>(order)`
3. Delete the profile and remove `IMapper` from the consumer's constructor; remove the AutoMapper DI registration if no other consumers
4. Run `dotnet build` and `dotnet test`; confirm pass. Refactor-safety improves (compile error if `Order` shape changes vs runtime null at the AutoMapper boundary)
5. **Skip if** the mapping is genuinely complex (multi-level reverse mappings, dynamic flattening, conventions used in 20+ profiles) - AutoMapper earns its keep there

**Recipe: Remove MediatR from trivial reads**

1. Identify the trivial query: `public class GetOrderByIdQuery : IRequest<Order> { public Guid Id { get; init; } }` with a handler that just calls `_repo.GetByIdAsync(Id, ct)`
2. Inline: the controller injects `IOrderRepository` directly and calls `_repo.GetByIdAsync(id, ct)`
3. Delete the query record and handler; delete any MediatR pipeline behaviors that only existed for this query
4. Run `dotnet build` and `dotnet test`; confirm pass
5. **Skip if** the query relies on MediatR pipeline behaviors (validation, authorization, transaction wrap, logging) that the controller-direct path would lose - then MediatR is earning its keep

**Recipe: Fix singleton capturing scoped service (captive dependency)**

1. Identify the captive dependency: `services.AddSingleton<IFoo, Foo>()` where `Foo`'s constructor takes `AppDbContext` (scoped) or another scoped service
2. Inject `IServiceScopeFactory` into `Foo` instead; create a scope per operation:
   ```csharp
   public class Foo : IFoo
   {
       private readonly IServiceScopeFactory _scopeFactory;
       public Foo(IServiceScopeFactory scopeFactory) { _scopeFactory = scopeFactory; }

       public async Task DoWorkAsync(CancellationToken ct)
       {
           using var scope = _scopeFactory.CreateScope();
           var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
           // use db within this scope only; do not store it as a field
       }
   }
   ```
3. Run `dotnet build /p:TreatWarningsAsErrors=true` and `dotnet test`; confirm pass; assert in tests that the DbContext is fresh per call (no cross-call entity tracking leaks)

**Recipe: Replace `new HttpClient()` with `IHttpClientFactory`**

1. Identify the per-request client construction: `using var client = new HttpClient(); var resp = await client.GetAsync(url, ct);`
2. Inject `IHttpClientFactory` (registered via `services.AddHttpClient()` in `Program.cs`); use `_factory.CreateClient(name)` or inject a typed client via `services.AddHttpClient<TClient>(c => c.BaseAddress = ...)`
3. Add Polly v8 `ResiliencePipeline` for retry + circuit breaker + timeout: `services.AddHttpClient<TClient>(...).AddResilienceHandler("default", b => b.AddRetry(...).AddCircuitBreaker(...).AddTimeout(...));`
4. Run `dotnet build` and `dotnet test`; confirm pass. Verify under load (or via socket diagnostics) that ephemeral port usage drops

**Recipe: Eliminate mass assignment via `[FromBody] DomainEntity`**

1. Identify the unsafe binding: `public async Task<IActionResult> Update([FromBody] Order request, CancellationToken ct)`
2. Define a request DTO record with explicit fields and FluentValidation rules:
   ```csharp
   public record UpdateOrderRequest(string Notes);

   public class UpdateOrderRequestValidator : AbstractValidator<UpdateOrderRequest>
   {
       public UpdateOrderRequestValidator()
       {
           RuleFor(x => x.Notes).NotEmpty().MaximumLength(500);
       }
   }
   ```
   No `Id`, `OwnerId`, `Role`, `IsAdmin`, etc.
3. Replace the binding: `public async Task<IActionResult> Update([FromBody] UpdateOrderRequest request, CancellationToken ct)`; map to the domain entity with explicit assignment: `order.Notes = request.Notes;`
4. Add a test attempting to inject `OwnerId` / `Role` keys; assert they are stripped
5. Audit other unsafe bindings in the controller / project

**Recipe: Replace static mutable state with constructor-injected service**

1. Identify the mutable state (`static Dictionary<...> _cache`, `static List<...> _things`, `static SqlConnection _conn`)
2. Move into a class with a constructor: `public class Cache : ICache { private readonly ConcurrentDictionary<K, V> _inner = new(); ... }`; register via DI `services.AddSingleton<ICache, Cache>()` (singleton if intended global; scoped if per-request)
3. Replace static reads/writes with method calls on the injected instance
4. Update callers to receive the new dependency explicitly via constructor injection, typically wired in `Program.cs`
5. Run `dotnet build /p:TreatWarningsAsErrors=true` and `dotnet test`; confirm pass; assert cross-test isolation (no leaking state between tests when running with xUnit's parallel test execution)

**Recipe: Convert sync polling worker to cancellation-aware async loop**

1. Identify the worker shape: `BackgroundService.ExecuteAsync(CancellationToken stoppingToken)` containing `while (true)` with `Thread.Sleep(N)` and no `stoppingToken` propagation
2. Replace the loop predicate: `while (!stoppingToken.IsCancellationRequested)`. The `BackgroundService` host signals cancellation by triggering this token on `IHostApplicationLifetime.ApplicationStopping`
3. Replace `Thread.Sleep(N)` with `await Task.Delay(TimeSpan.FromMilliseconds(N), stoppingToken)`. `Task.Delay` cooperates with cancellation (throws `OperationCanceledException` on shutdown so the loop exits cleanly); `Thread.Sleep` blocks the thread for the full interval and ignores the token
4. Wrap each iteration body in `try { ... } catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; } catch (Exception ex) { _logger.LogError(ex, "..."); }` so a transient failure logs and continues, but cancellation exits the loop
5. Forward `stoppingToken` to every awaited call inside the loop body (`db.SaveChangesAsync(stoppingToken)`, `httpClient.PostAsync(url, content, stoppingToken)`)
6. Run `dotnet build /p:TreatWarningsAsErrors=true` and `dotnet test`; add a worker test starting the service then cancelling its host to assert the loop exits within the configured `HostOptions.ShutdownTimeout`

**Recipe: Make background-worker idempotent**

1. Add a worker test asserting the side effect happens exactly once when the same payload is processed twice (different message IDs, same business key)
2. Add an idempotency guard inside the consumer / handler: dedup table keyed by a business key; upsert via `ON CONFLICT DO NOTHING` (PostgreSQL) / `MERGE` (SQL Server) or version check
3. Verify retries on transient failures still complete the work
4. Configure max-retries / DLQ explicit on the consumer / job type so poison messages do not loop forever (MassTransit `UseMessageRetry(r => r.Intervals(...))` + dead-letter exchange; Hangfire `[AutomaticRetry(Attempts = N)]`)
5. For MassTransit, adopt the transactional outbox pattern (`AddEntityFrameworkOutbox<AppDbContext>`) so dispatch happens iff `SaveChangesAsync` commits

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end); `dotnet build /p:TreatWarningsAsErrors=true` and `dotnet test` for every commit
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, interface removals)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## .NET Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common .NET refactor recipes" - this is the spine]
**Stack:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**Mediator:** MediatR <version> | none
**Messaging:** MassTransit | Hangfire | Channel | none

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Lint state:** `dotnet format --verify-no-changes` clean + `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` on | warnings present (Step 0a covers them) | not run (no baseline)
**Concurrency-test coverage:** clean | not exercised cross-thread | n/a (no concurrency in target)

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-dotnet-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce the **Smells Identified**, **Sibling Smells (Out of Scope)**, and the **Coverage prerequisite list** (the `entry-point | outcome | recommended layer` table described below) as a *preview* so the implementer has a target list when filling the coverage gap; mark them clearly as preview-only. The prerequisite table is the most actionable output in this mode - render it inside the Coverage Gate section, not as a separate top-level heading.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure (4xx), authorization denial (401/403), not-found / IDOR, external-collaborator failure, and (when the target spawns / blocks across `.await`) **concurrent path** with bounded xUnit parallelism as the recommended layer. The concurrency row is required whenever the concurrency-gate-check applied above (target uses `Task.Run` / `Parallel.ForEachAsync` / `BackgroundService` / shared `ConcurrentDictionary` / `SemaphoreSlim` / channels) - it makes the concurrency-gate-check directly actionable in the prerequisite table instead of leaving it implicit. Layer options: API test (`WebApplicationFactory<Program>`), unit test (xUnit + NSubstitute), integration test (Testcontainers), background-worker test, multi-thread test (xUnit per-collection parallelism + concurrent execution). Example: `POST /api/orders | unknown-field rejected | API test`. This makes the prerequisite directly actionable rather than a vague "add boundary tests."

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/class that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                              |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-dotnet-review-security` / `task-dotnet-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green; `dotnet format --verify-no-changes` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if format and analyzer state was already clean)_

- **Change:** address the existing format / analyzer warnings on the target project so the refactor's lint gate has a clean baseline
- **Risk:** Low (no behavior change; format / lint-only fixes)
- **Test gate:** `dotnet format --verify-no-changes` clean; `dotnet build /p:TreatWarningsAsErrors=true` succeeds; `dotnet test` still green
- **Rollback:** revert the lint fixes

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - unit / API / Testcontainers integration / background-worker; `dotnet format --verify-no-changes` clean]
- **Transaction stance:** [callee runs inside caller's transaction (shares scoped DbContext) | callee uses post-commit dispatch | not transactional]
- **Async stance:** [no async change | converts `.Result` to `await` (cascading: list affected callers) | adds `CancellationToken ct` propagation | unchanged]
- **DI stance:** [no lifetime change | `AddScoped` (DbContext-bound) | `AddSingleton` (stateless) | `AddTransient` (stateful per call) | `IServiceScopeFactory` for singleton-needing-scoped]
- **Concurrency stance:** [no concurrency change | introduces `BackgroundService` (CancellationToken propagation + concurrent test required) | removes blocking call | lock change]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it. Always state why the coupling is structural, not cosmetic.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `dotnet build /p:TreatWarningsAsErrors=true` clean and `dotnet test` (with `dotnet format --verify-no-changes`) passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` introduced; async chain converted end-to-end where touched
- [ ] No new singleton capturing scoped service; `IServiceScopeFactory` used where singleton needs scoped state per operation
- [ ] No new `BackgroundService` / `Task.Run` without `CancellationToken` propagation
- [ ] No new concurrency without cross-thread test coverage in CI

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as .NET / ASP.NET Core (or accepted from parent dispatcher); data-access mix and messaging recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin`; concurrency-test check applied for concurrent classes; format / analyzer state recorded (Step 3)
- [ ] .NET-specific smells identified using Step 4 catalog (controller, handler/service, persistence, configuration/DI, concurrency/async, `unsafe`) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate`. Step 0a included if format / analyzer state is not clean (Output Format)
- [ ] Transaction stance stated per step (no I/O silently moved across transaction boundary) (Step 6)
- [ ] Async stance stated per step (no partial `.Result` → `await` conversion; cascading callers listed when async chain changes) (Step 6)
- [ ] DI stance stated per step (no silent singleton capturing scoped; `IServiceScopeFactory` used where required) (Step 6)
- [ ] Concurrency stance stated per step (`CancellationToken` propagation + concurrent test required when concurrency added) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, interface removals, signature changes) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `dotnet build /p:TreatWarningsAsErrors=true` clean and `dotnet test` passes between every step
- [ ] `dotnet format --verify-no-changes` clean for any step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Proposing a refactor that introduces concurrency to a class that lacks cross-thread test coverage - the new race surface is unguarded
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing an interface without a real second use case - wait for the second use case before generalizing
- Replacing EF Core with Dapper (or vice versa) on a code path with no measured benefit (premature change)
- Replacing static mutable state with `AsyncLocal<T>` carrying a pointer to the same data - that is the same global with extra steps; use constructor injection instead
- Moving HTTP calls or job dispatches from a non-transactional context to inside a `BeginTransactionAsync...CommitAsync` (or vice versa) without explicitly stating the transaction stance
- Partially converting `.Result` / `.Wait()` to `await` - leaves a different deadlock surface; convert the chain end-to-end or skip the recipe
- Refactoring an exported `public` symbol in a NuGet package without a backward-compatibility plan - that is a public API
- Adding `BackgroundService` / `Task.Run` to "make it concurrent" without `CancellationToken` propagation and bounded fan-out - that is a leak waiting to happen
- Replacing `[FromBody] DomainEntity` mass assignment with another `[FromBody] DomainEntity` (just renamed) - the issue is the entity binding, not the property name; introduce a request DTO record
- Consolidating services into a singleton without checking what scoped services they capture - captive-dependency bug
- Removing AutoMapper / MediatR globally based on one trivial use - they earn their keep on cross-cutting concerns; keep them where they're load-bearing, remove them where they're noise
