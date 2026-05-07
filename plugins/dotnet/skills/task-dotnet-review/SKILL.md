---
name: task-dotnet-review
description: .NET staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with ASP.NET Core / EF Core / async idioms (`async void` in non-event-handler code, `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` blocking on async, missing `CancellationToken` propagation, EF Core N+1 via lazy loading or per-iteration `.Single()`, `JsonSerializer.Deserialize<DomainEntity>` mass assignment, raw SQL string interpolation via `FromSqlRaw($"...")`, missing `[Authorize]` / `[AllowAnonymous]` decoration, scoped service captured by singleton, missing `AsNoTracking()` on read paths, `Newtonsoft.Json` in hot paths). Spawns .NET-specific perf / security / observability subagents for extra scopes. Stack-specific override of task-code-review for .NET. Runs standalone with full PR/branch resolution.
agent: dotnet-tech-lead
metadata:
  category: backend
  tags: [dotnet, aspnet-core, ef-core, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# .NET Code Review

## Purpose

.NET-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with .NET-specific correctness, architecture, AI-quality, and maintainability checks (`async void` outside event handlers, `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` blocking on async, missing `CancellationToken` plumbing, EF Core N+1 via lazy loading or per-iteration query, `Include` cartesian explosion without `AsSplitQuery`, missing `AsNoTracking()` on read paths, raw SQL string interpolation via `FromSqlRaw($"... {input}")`, mass assignment via `JsonSerializer.Deserialize<DomainEntity>(body)`, missing `[Authorize]` / `[AllowAnonymous]` decoration, singleton capturing scoped service, IDisposable not disposed, `Newtonsoft.Json` in hot paths, multiple `SaveChangesAsync` per use case, primitive obsession in domain models, single-implementation interface). Coordinates .NET-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for .NET. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a .NET / ASP.NET Core PR before merge
- Post-AI-generation quality gate on a .NET change set
- Architecture drift detection in a Clean Architecture .NET codebase
- Pre-merge risk assessment on a .NET branch

**Not for:**

- Pre-implementation feature design (use `task-dotnet-new`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error / exception debugging (use `task-dotnet-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-dotnet-review-perf`, `task-dotnet-review-security`, or `task-dotnet-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full .NET staff-level review                                    | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E only (.NET-flavored)                                            |
| + Perf          | Core + parallel subagent: `task-dotnet-review-perf`                        |
| + Security      | Core + parallel subagent: `task-dotnet-review-security`                    |
| + Observability | Core + parallel subagent: `task-dotnet-review-observability`               |
| Full            | Core + Performance + Security + Observability (3 parallel .NET subagents)  |

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (.NET-tuned):**

- File uploads (`IFormFile`, `Microsoft.AspNetCore.Http.IFormCollection`), JWT middleware / `AddAuthentication().AddJwtBearer(...)` / `AddAuthorization(options => options.AddPolicy(...))` changes, request DTO records bound via `[FromBody]` extractors, raw SQL via `FromSqlRaw($"... {input}")` or `FromSqlInterpolated`, secrets in `appsettings*.json` / config, background workers reading user-supplied input (`BackgroundService`, MassTransit consumers, Hangfire jobs), `JsonSerializer.Deserialize<DomainEntity>(body)` patterns, `Process.Start` with user input, `unsafe` blocks → auto-add **+Security**
- New EF Core migration, new `IQueryable` materialization site (`ToListAsync` / `FirstAsync` / `CountAsync`), new `Include` / `ThenInclude`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `IMemoryCache` / `IDistributedCache` read paths, new `Task.WhenAll` fan-out → auto-add **+Perf**
- New project / assembly, new external client (`HttpClient` via `IHttpClientFactory`, `IDistributedCache`, `Amazon*Client`), new `BackgroundService` / MassTransit consumer / Hangfire recurring job, change to `Program.cs` / Serilog config, new `Meter` registration / `Counter` instrument, lifecycle changes (`IHostApplicationLifetime`, graceful shutdown, signal handling) → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                     | Meaning                                                                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-dotnet-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-dotnet-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-dotnet-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-dotnet-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-dotnet-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-dotnet-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If invoked as a delegate of `task-code-review` (parent already detected .NET), accept the pre-detected stack and skip re-detection. If the detected stack is not .NET, stop and tell the user to invoke `/task-code-review` instead.

Detect data access: EF Core (typical), Dapper (for complex reads), or mixed. Detect mediator: MediatR (CQRS) or direct service calls. Detect messaging: MassTransit, Hangfire, in-process `Channel<T>` workers, or none. Record `Runtime: .NET <version>`, `Framework: ASP.NET Core <version>`, `Data Access: EF Core | Dapper | mixed`, `Mediator: MediatR | none`, `Messaging: MassTransit | Hangfire | Channel | none`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 3 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. Make this explicit because the default of "skip if user did not pass `+security` etc." silently misses the cases where the change itself signals the need.

For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals so the Summary documents why the chosen scope was correct

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`. If the user passed a scope and signals contradicted it, surface a one-line note so reviewers see what was deliberately deferred.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth middleware, JWT validation, `Program.cs` / `Startup.cs` wiring, MediatR pipeline behaviors, EF Core `DbContext` / `IEntityTypeConfiguration`, EF Core migrations), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 3.5 - Re-evaluate Depth After Phase A

If `Blast Radius` (from Phase A) is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors (historical pattern matching, cross-PR context, anemic-domain assessment) are in scope for the rest of the review.

### Phase B - .NET Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness, async cancellation safety - through a .NET lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding xUnit / WebApplicationFactory / Testcontainers coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication (JWT validation, custom auth handlers), authorization (`IAuthorizationHandler`, policy enforcement, ownership checks), money or billing flows, data-integrity writes (multi-step transactions, state machines), background workers that mutate data (`BackgroundService`, MassTransit consumers, Hangfire jobs), EF Core migrations that change column semantics. Do not bury this finding in Key Takeaways - a separate, named entry in Findings.

**.NET-specific correctness checks (all data-access mixes):**

- [ ] **No `async void` outside event handlers**: `async void` swallows exceptions silently and cannot be awaited - causes process crashes via `UnobservedTaskException`. `async Task` (or `async Task<T>`) for everything except UI event handlers
- [ ] **No `.Result`, `.Wait()`, `.GetAwaiter().GetResult()` on async methods**: blocks the calling thread; deadlocks on `SynchronizationContext` (legacy ASP.NET / WPF) or starves the thread pool (modern ASP.NET Core). Use `await` end-to-end. Top-of-`Main` is the only legitimate exception
- [ ] **`CancellationToken` propagated through every async chain**: every `async Task` method takes `CancellationToken ct` (or `CancellationToken cancellationToken`) as the last parameter and forwards it to every awaited call. Controllers receive `CancellationToken ct` from the action signature; MediatR handlers receive it via `IRequestHandler<TRequest, TResponse>.Handle(TRequest request, CancellationToken cancellationToken)`. Missing `ct` parameter or unused `ct` is a finding
- [ ] **`ConfigureAwait(false)` on library / shared code**: outside of ASP.NET Core (which has no `SynchronizationContext` so `ConfigureAwait` is a no-op there), library code should call `.ConfigureAwait(false)` to avoid capturing the caller's context. Do **not** flag missing `ConfigureAwait(false)` in pure ASP.NET Core code paths - it's a no-op and adds noise
- [ ] **`Task.WhenAll` for parallel async work, not sequential `await`s**: `var a = await fetchA(); var b = await fetchB();` runs serially. `var (a, b) = (await Task.WhenAll(fetchA(), fetchB())); / pattern destructuring` runs concurrently when the calls are independent
- [ ] **`IDisposable` / `IAsyncDisposable` properly disposed**: `using var conn = ...;` or `await using var conn = ...;` for async-disposable. `HttpClient` via `IHttpClientFactory` (do **not** instantiate per-request - socket exhaustion); `DbContext` is scoped via DI, not manually disposed
- [ ] **No exceptions swallowed**: bare `catch (Exception) { }` or `catch (Exception) { return null; }` loses telemetry and root-cause information. Catch specific exception types; rethrow with `throw;` (not `throw ex;` which loses the stack); or wrap with context via custom exception types and `innerException`
- [ ] **`IExceptionHandler` (ASP.NET Core 8+) or middleware-based central error handling**: error responses produced via Problem Details (RFC 7807) by a single `IExceptionHandler` registered via `services.AddExceptionHandler<...>().AddProblemDetails()`. Per-controller `try { ... } catch { return StatusCode(500, ...); }` scattered across actions is inconsistent and leaks internal details
- [ ] **No domain entity returned from controller actions**: controllers map to response DTO records (`record OrderResponse(...)`) before returning. Returning an EF Core entity directly via `return Ok(order)` leaks every property the entity defines (including `PasswordHash`, `MfaSecret`, audit columns) **and** triggers lazy-loaded navigations during serialization (silent N+1 on the response path)
- [ ] **No mass assignment via `JsonSerializer.Deserialize<DomainEntity>(body)` or `[FromBody] DomainEntity`**: deserializing the request body directly into an EF Core entity lets the client set every property (`Id`, `UserId`, `TenantId`, `Role`, `IsAdmin`, `PasswordHash`, `CreatedAt`). Define a request DTO record (`record CreateOrderRequest(...)`) listing only client-supplied properties; map to the domain entity via explicit assignment. This is the request-side mirror of the response-side leak above
- [ ] **`[ApiController]` model validation enabled OR FluentValidation explicit**: with `[ApiController]`, model state validation runs automatically and returns 400 ValidationProblemDetails when invalid; with FluentValidation, the validator is registered via DI and invoked via `validator.ValidateAsync(req, ct)` at handler entry. Mixing patterns silently OR disabling auto-validation via `services.Configure<ApiBehaviorOptions>(o => o.SuppressModelStateInvalidFilter = true)` without re-wiring is a finding
- [ ] **No `[Required]` data annotations on DTOs when FluentValidation is the project standard**: if the codebase uses FluentValidation, mixing `[Required]` annotations on DTOs creates two parallel validation paths and inconsistent error responses
- [ ] **Authorization on every protected action**: every action method touching user data has `[Authorize]` (with policy if applicable) AND the handler/service performs an ownership check (`order.UserId == User.GetUserId()`) before mutating or returning the row. `[Authorize]` proves authentication; ownership scoping proves authorization. An `[Authorize] GET api/orders/{id}` with no ownership scope is an IDOR finding
- [ ] **Explicit `[Authorize]` or `[AllowAnonymous]` on every action**: do not rely on conventions - decorate every controller / action explicitly so a missed decoration on a new endpoint is a compile-time-visible omission, not a silent default-allow / default-deny
- [ ] **No raw SQL string interpolation via `FromSqlRaw($"... {input}")`**: SQL injection. Use `FromSqlInterpolated($"... {input}")` (which parameterizes interpolated holes) or `FromSqlRaw("... {0}", input)` with explicit parameters - or, better, parameterized LINQ. Dapper: `connection.QueryAsync<T>("... WHERE id = @id", new { id })` parameterized; never `connection.QueryAsync<T>($"... WHERE id = {id}")`
- [ ] **N+1 in queries**: any per-iteration `.Single()` / `.First()` / `.Where(...).ToList()` inside a `foreach` over a parent set is N+1; resolve via `Include()` / `ThenInclude()` (with `AsSplitQuery()` to avoid cartesian explosion when joining multiple collections), or via projection with `.Select(...)` to a flat DTO. Lazy loading enabled (`UseLazyLoadingProxies()`) compounds this silently - flag enabled lazy loading as a finding unless explicitly justified
- [ ] **`AsNoTracking()` on read-only queries**: read-only queries should run `AsNoTracking()` (or `AsNoTrackingWithIdentityResolution()` when entity references repeat) to skip the change-tracker overhead. Mutations use the default tracked path
- [ ] **Single `SaveChangesAsync(ct)` per use case**: handlers should call `SaveChangesAsync` once at the end of the use case, not per entity write. Multiple `SaveChangesAsync` calls inside one handler split atomicity and create race windows
- [ ] **Transaction boundaries**: writes spanning multiple use cases or multiple `DbContext` instances run inside an explicit `IDbContextTransaction` (`await using var tx = await db.Database.BeginTransactionAsync(ct); ...; await tx.CommitAsync(ct);`). For single-`SaveChangesAsync` use cases, EF Core's implicit transaction suffices
- [ ] **Background dispatch AFTER commit**: enqueueing a MassTransit message, Hangfire job, or `Channel<T>` task happens after `SaveChangesAsync(ct)` returns successfully (or after explicit `tx.CommitAsync(ct)`), never inside the transaction - the worker may pick up the message before the row is visible. For exactly-once eventing across the commit boundary, use the transactional outbox pattern (MassTransit ships one)
- [ ] **`IHostedService` / `BackgroundService` cancellation**: every `BackgroundService.ExecuteAsync(CancellationToken stoppingToken)` has a `while (!stoppingToken.IsCancellationRequested)` loop and forwards `stoppingToken` to every awaited call. Bare `while (true)` ignores graceful shutdown
- [ ] **Singleton not capturing scoped services**: `services.AddSingleton<IFoo, Foo>()` where `Foo`'s constructor takes a scoped dependency (`AppDbContext`, scoped repository) is a captive-dependency bug - the scoped service is captured at app startup and lives for the process lifetime. Use `IServiceScopeFactory` and create a scope per operation: `using var scope = _scopeFactory.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();`
- [ ] **`HttpClient` via `IHttpClientFactory`**: never `new HttpClient()` inline (socket exhaustion under load); inject `IHttpClientFactory` and use `_factory.CreateClient(name)` or inject named/typed clients via DI. For external dependencies, wrap with Polly v8 `ResiliencePipeline` (retry + circuit breaker + timeout)
- [ ] **No user-controlled redirect targets**: `return Redirect(userInput);` without an allowlist or `IsLocalUrl` check is an open-redirect / phishing primitive. Use `Url.IsLocalUrl(target)` or allowlist relative paths only
- [ ] **No `Process.Start` with concatenated user input**: `Process.Start("cmd.exe", $"/c {userInput}")` is RCE. Use `Process.Start(new ProcessStartInfo("convert") { ArgumentList = { userInput, "/tmp/out" } })` (arg-by-arg, no shell)
- [ ] **`unsafe` blocks justified**: `unsafe { ... }` blocks have a `// SAFETY:` comment naming what the caller must uphold; bare `unsafe` is a finding
- [ ] **`Newtonsoft.Json` not added to new code paths**: `System.Text.Json` is the .NET 6+ default and is faster, lower-allocation. New `[JsonProperty]` / `JsonConvert.SerializeObject` usage in new code is a smell unless a concrete `Newtonsoft`-only feature is required and named
- [ ] **`Serilog` (or `Microsoft.Extensions.Logging`) for structured logging, not `Console.WriteLine`**: `Console.WriteLine` evades structured-field extraction, correlation IDs, and redaction. `_logger.LogInformation("Placing order {OrderId}", id)` for state transitions; named placeholders, not `string.Format`-style positional
- [ ] **Migration PRs (any change in `Migrations/`)**: see the Migration PRs subsection below

**Migration PRs (any change under `Migrations/` for EF Core):**

- [ ] EF Core reversible migrations: every `Up()` migration has a corresponding `Down()` method. Missing or empty `Down()` is a finding (not a one-way "we'll document it later" exception) - revert path needs to exist before the change ships, even if rolling back means accepting data loss for the new column
- [ ] Two-phase deploys for column rename / drop (add new → backfill → cut over → remove old)
- [ ] `NOT NULL` on existing columns: SQL Server / PostgreSQL add-column-NOT-NULL-with-default depends on engine and version. For PostgreSQL 11+, `ADD COLUMN ... NOT NULL DEFAULT <constant>` is metadata-only and safe. For SQL Server, `ALTER TABLE ... ADD <col> <type> NOT NULL DEFAULT <literal>` is metadata-only on Enterprise SKUs (`ALTER TABLE` online); on Standard it can rewrite the table. For non-constant defaults (`now()`, function calls), or for adding `NOT NULL` to an existing nullable column on a hot table, require the two-step (add nullable → backfill → set NOT NULL via separate migration). The row count and engine SKU determine the verdict
- [ ] Indexes on large tables use online / concurrent options - PostgreSQL `CREATE INDEX CONCURRENTLY`, SQL Server `WITH (ONLINE = ON)` (Enterprise SKU). EF Core migration files contain the raw `migrationBuilder.Sql(...)` for these cases; flag indexes added via `migrationBuilder.CreateIndex(...)` on hot tables that lack the online/concurrent option
- [ ] **`SET lock_timeout`** (PostgreSQL) or `SET LOCK_TIMEOUT` (SQL Server) before DDL on large tables to fail fast
- [ ] Foreign keys added with validation deferred (or as a separate validate step on PostgreSQL via `NOT VALID` then `VALIDATE CONSTRAINT`)
- [ ] Data migrations isolated from DDL migrations; long-running data backfills not in the same migration as the schema change; backfills via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] Migration runs on app startup vs out-of-band: `dotnet ef database update` as a deployment step is safer than `db.Database.Migrate()` on app startup (which causes every replica to race the migration on rollout). Flag startup migrations on multi-replica deployments
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `dotnet-db-migration-safety` for canonical safe-migration patterns

**Concurrency safety:**

- [ ] No shared mutable global state (`static Dictionary<...> _cache` mutated by request handlers); if state is required, encapsulate in a service with a clear ownership / locking story (`ConcurrentDictionary<TKey, TValue>` for sharded concurrent maps, `IMemoryCache` for time-bounded entries, `IDistributedCache` for cross-replica shared state). `static` mutable fields are a smell
- [ ] Race-prone updates (counters, balance changes, state transitions) use database-level locking (`SELECT ... FOR UPDATE` via `FromSqlInterpolated` inside an explicit transaction, or EF Core optimistic concurrency via `[ConcurrencyCheck]` / `[Timestamp] byte[] RowVersion` and handle `DbUpdateConcurrencyException`) - not in-process locks, which only protect a single replica
- [ ] No `lock(...) { ... await ... }` - the C# compiler errors on this, but `Monitor.Enter` / `SemaphoreSlim` misuse can recreate the pattern. Use `SemaphoreSlim.WaitAsync(ct)` for async-aware locking; never `Monitor.Enter` across `await`
- [ ] `dotnet build` clean with no warnings; analyzers (`Microsoft.CodeAnalysis.NetAnalyzers`, `Roslynator`) enabled in CI

Use skill: `dotnet-ef-performance` for canonical EF Core correctness patterns.
Use skill: `dotnet-exception-handling` for `IExceptionHandler` / Problem Details / error mapping patterns.
Use skill: `dotnet-async-patterns` for `CancellationToken`, `BackgroundService`, async lifecycle design.
Use skill: `dotnet-transaction` for `SaveChangesAsync` boundaries and `IDbContextTransaction` design.
Use skill: `dotnet-messaging-patterns` for MassTransit consumer / outbox / Hangfire patterns when the diff touches messaging.

### Phase C - .NET Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**.NET-specific architecture checks (Clean Architecture):**

- [ ] **Layering**: `Domain` ← `Application` ← `Infrastructure` ← `Api`. Domain has no project references except primitives (no MediatR, no EF Core, no ASP.NET Core). Application depends only on Domain and abstractions (`IRepository<T>`, `IUnitOfWork`); no `DbContext` / EF Core types in Application; no `HttpClient` / Polly types in Application. Infrastructure implements Application interfaces (dependency inversion); Infrastructure does not depend on Api. Api wires DI and HTTP; controllers thin, delegate to MediatR handlers or application services
- [ ] **No `DbContext` in Application layer**: Application uses repository interfaces or MediatR handlers; Infrastructure implements them via EF Core. Direct `DbContext` injection into an Application handler couples the layer to EF Core
- [ ] **No EF Core entities crossing into API responses**: handlers and controllers map to DTO records before returning. EF Core entities returned via `[FromBody]` or `Ok(entity)` leak schema and trigger lazy-loaded navigations during serialization
- [ ] **MediatR pipeline behaviors registered in correct order**: `LoggingBehavior` -> `ValidationBehavior` (FluentValidation) -> `AuthorizationBehavior` (resource-based authz) -> `TransactionBehavior` (single `SaveChangesAsync` per request). The order is load-bearing - put validation before authorization, and transaction wrap last so it commits on success and rolls back on exception
- [ ] **Repository / interface placement**: interfaces in `Application/Interfaces` (the consumer module), implementations in `Infrastructure/Persistence/Repositories`. Interface co-located with its implementation in `Infrastructure` is the wrong direction (couples Application to Infrastructure)
- [ ] **Constructor injection only**: dependencies received via constructor parameters; no `IServiceProvider.GetRequiredService<T>()` inside handlers (service-locator anti-pattern); no `new` on dependencies. Optional dependencies via `IOptions<T>` / `IOptionsMonitor<T>`
- [ ] **`IOptions<T>` / `IOptionsMonitor<T>` for typed config**: `services.Configure<JwtOptions>(configuration.GetSection("Jwt"))` and inject `IOptions<JwtOptions>` (or `IOptionsMonitor<T>` for hot-reload). Do not inject `IConfiguration` directly into handlers - hide config behind typed records
- [ ] **`appsettings.json` discipline**: `appsettings.json` for defaults; `appsettings.{Environment}.json` for env overrides; secrets from environment variables / Azure Key Vault / AWS Secrets Manager / `dotnet user-secrets` (dev). Never commit production secrets to `appsettings.*.json`
- [ ] **Multi-tenant isolation**: tenant scoping enforced at the EF Core query level (`db.Orders.Where(o => o.TenantId == _tenantContext.TenantId)`), via global query filters (`modelBuilder.Entity<Order>().HasQueryFilter(o => o.TenantId == _tenantContext.TenantId)`), or at the repository layer - not at the controller layer alone
- [ ] **Middleware order in `Program.cs`**: `UseExceptionHandler` (or `UseStatusCodePages`) → `UseHsts` (prod) → `UseHttpsRedirection` → `UseRouting` → `UseCors` → `UseAuthentication` → `UseAuthorization` → `MapControllers`. `UseAuthentication` must precede `UseAuthorization`; both must follow `UseRouting`. Out-of-order middleware silently breaks auth or CORS
- [ ] **Controller convention per resource**: `OrdersController : ControllerBase` with `[Route("api/v1/[controller]")]`; one controller per aggregate root; thin actions (extract → invoke MediatR handler → map → return)
- [ ] **`IExceptionHandler` central mapping**: a single `GlobalExceptionHandler : IExceptionHandler` maps domain exceptions → HTTP status via Problem Details. Per-action `try { ... } catch { return StatusCode(...); }` scattered is inconsistent

**Multi-service PRs (when change spans 2+ services or this .NET app + a separate service):**

- API contract compatibility checked (OpenAPI diff via `Swashbuckle` or `Microsoft.AspNetCore.OpenApi`, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**.NET-specific AI smells:**

- [ ] **Pattern inflation**: a `Manager` / `Service` / `Helper` class with one method that wraps a single function call where a static method or extension method would do; abstract base class hidden behind an interface with one implementer; a custom `Result<T>` type alias used inconsistently
- [ ] **Single-implementation interface**: interface declared with one implementation, no `NSubstitute` mock, no second implementer - inline to the concrete class via constructor injection. Interfaces for testability are fine; interfaces for abstraction's sake are smells
- [ ] **AutoMapper for trivial mappings**: configuring AutoMapper profiles for `record OrderResponse(Guid Id, decimal Total)` ↔ `class Order { public Guid Id; public decimal Total; }` adds runtime cost, hides errors, and the explicit `new OrderResponse(o.Id, o.Total)` is shorter and refactor-safe. Reserve AutoMapper for genuinely complex transforms with reverse mappings
- [ ] **MediatR for non-CQRS**: every method routed through MediatR even when the call is a simple `_repository.GetById(id)` - the indirection adds nothing for trivial reads. MediatR is for cross-cutting concerns (validation pipeline, transaction wrapping, authorization behavior, logging); not for hiding a single repository call
- [ ] **Over-abstraction**: `BaseRepository<T>` with one consumer; premature interface for one consumer; factory classes for objects with one constructor path; generics used for code that handles only one type
- [ ] **Speculative configurability**: config keys with documented but unused values; environment-conditional code paths for environments that do not exist; feature flags with no off path; `IFeatureManager.IsEnabledAsync("X")` for features no consumer enables
- [ ] **Redundant mapping layers**: `Entity → InternalDto → ServiceDto → ResponseDto` when one mapping would suffice
- [ ] **Test verbosity**: Bogus / NSubstitute setup helpers > 30 lines for a single assertion; deeply nested mock chains; `result.Should().BeEquivalentTo(full_object)` when a few key field assertions would do
- [ ] **`Task.Run` misapplication**: `await Task.Run(() => syncMethod())` on an already-async runtime offloads to a thread-pool thread for no reason; the call ships the thread but does the same work. `Task.Run` is for offloading CPU-bound work from the request thread, not for "making sync code async"
- [ ] **Excessive `string` allocations in hot paths**: `string.Format` / `+` concatenation / `string.Join` in tight loops where `StringBuilder`, `string.Create`, or `Span<char>` would work
- [ ] **Comment cruft**: XML doc comments restating method names; `// end of method` markers; `/// <summary>...</summary>` on private helpers that just repeat the signature
- [ ] **`Exception` catch-all**: `catch (Exception ex)` at every level - prefer specific exception types; a top-level `IExceptionHandler` handles the fallthrough
- [ ] **`#pragma warning disable` to silence analyzers**: each suppression must have a `// reason: ...` comment; bare `#pragma warning disable` on a file or block is a finding

### Phase E - .NET Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**.NET-specific maintainability checks:**

- [ ] **Naming conventions**: namespaces `PascalCase` (`Acme.Orders.Application`); types `PascalCase`; methods / properties `PascalCase`; parameters / locals `camelCase`; private fields `_camelCase`; constants `PascalCase` (or `UPPER_SNAKE_CASE` per project standard); interfaces `IPascalCase` (the `I` prefix is mandatory in .NET); async methods suffixed `Async`. No stutter (`Order.OrderId` → `Order.Id`)
- [ ] **Magic numbers / strings**: extracted to `const` or `static readonly`; `private static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(5);` over raw `TimeSpan.FromSeconds(5)` mid-expression
- [ ] **Hardcoded URLs / credentials**: in `IOptions<T>` config / environment variables, not inline in code
- [ ] **Method length**: methods > 30 lines reviewed for extraction; methods > 60 lines flagged unless they are a clearly orchestrating handler calling intention-revealing private helpers
- [ ] **Duplicated query logic**: same `Where` predicate in 3+ places extracted to a repository method or a typed query helper / specification
- [ ] **Nullable reference types enabled**: `<Nullable>enable</Nullable>` in the `.csproj`; nullability warnings respected (`string?` vs `string`); no `!` (null-forgiving) operator without a comment justifying why the value is non-null
- [ ] **`record` for DTOs and value objects**: `record OrderResponse(Guid Id, decimal Total)` over mutable class with public setters; init-only properties (`{ get; init; }`) when records aren't a fit
- [ ] **Logging hygiene**: surface obvious offenders as Core findings at `[Suggestion]` - `Console.WriteLine` in production code path, log lines without correlation IDs, wrong log levels (`LogInformation` for debug spam, `LogError` for things that aren't actionable). The observability subagent owns depth (sampling, structured-field schemas, OTel correlation, log redaction, log level filter config); do not duplicate that audit here
- [ ] **`dotnet format` clean / EditorConfig respected**: no manual formatting deviations; warnings-as-errors enabled in CI (`<TreatWarningsAsErrors>true</TreatWarningsAsErrors>`)
- [ ] **XML doc comments on public APIs**: every `public` type, method, and property has `/// <summary>`; methods document `<param>`, `<returns>`, `<exception>`; controllers also carry `[ProducesResponseType]` for OpenAPI

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-dotnet-review-observability` subagent owns the depth review).

### Step 4 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Core + Perf          | 1 subagent running `task-dotnet-review-perf`                                                                                   |
| Core + Security      | 1 subagent running `task-dotnet-review-security`                                                                               |
| Core + Observability | 1 subagent running `task-dotnet-review-observability`                                                                          |
| Full                 | 3 subagents running `task-dotnet-review-perf`, `task-dotnet-review-security`, `task-dotnet-review-observability` in parallel   |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (.NET / ASP.NET Core) and detected data-access (EF Core / Dapper / mixed) plus mediator / messaging signal so the subagent skips its own `stack-detect` and data-access branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 5 - Synthesize (only if Step 4 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a per-iteration EF Core query inside a request loop can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`). Subagent reviews (perf / security / observability) use their own scales (`Critical` / `High` / `Medium` / `Low`); when merging, map subagent severities into this skill's labels: `Critical` → `Blocker`, `High` → `High`, `Medium` → `Suggestion`, `Low` → `Suggestion`. Do not introduce `Critical` / `Medium` / `Low` into the merged Findings list.
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**Mediator:** MediatR <version> | none
**Messaging:** MassTransit | Hangfire | Channel | none
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the .NET idiom: `async void` outside event handler, `.Result` blocking on async, EF Core N+1 via lazy load, raw SQL via `FromSqlRaw($"...")`, mass assignment via `[FromBody] DomainEntity`, missing `[Authorize]`, singleton capturing scoped, missing `CancellationToken`, exception swallowed, dispatch inside transaction, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete .NET change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

### [Question] file:line

- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on - author intent, business rule, deployment topology, etc.]

_Use [Question] when the change is genuinely ambiguous and the right action depends on author intent. Do NOT use it as a softer Blocker._

## Architecture Notes

_Summary commentary on systemic patterns. **Do not restate individual findings here.** If a pattern is severe enough to be a finding, keep it in Findings and reference it by file:line from these notes. Use this section for cross-cutting observations the per-file findings cannot carry on their own._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes - summary commentary, not duplicated findings._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Convert `OrdersController.Get` from `.Result` to `await`; propagate `CancellationToken ct` from action signature through the call chain"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply .NET conventions (Microsoft Framework Design Guidelines, ASP.NET Core conventions, Roslyn analyzers), not generic backend conventions
- Provide actionable feedback with C# code examples
- Never comment on trivial formatting or style where no project standard exists - assume `dotnet format` / EditorConfig applies
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate .NET subagent rather than duplicating the check here

## Self-Check

- [ ] Stack confirmed as .NET / ASP.NET Core (or accepted from parent dispatcher); data-access, mediator, and messaging detected and recorded
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If user passed `--base`, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated in Step 3; promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; promotion recorded in Summary
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B - no `async void` outside event handlers, no `.Result` / `.Wait()` / `.GetAwaiter().GetResult()`, `CancellationToken` propagated; exceptions not swallowed; central `IExceptionHandler` for error mapping
- [ ] Phase B - no singleton capturing scoped service; `HttpClient` via `IHttpClientFactory`; `IDisposable` properly disposed
- [ ] Phase B - extractor validation present (`[ApiController]` auto-validation OR FluentValidation); authentication AND authorization both checked (ownership scoping, not just `[Authorize]`)
- [ ] Phase B - EF Core parameterization (no `FromSqlRaw($"...")` interpolation); N+1 via per-iteration query checked; `AsNoTracking()` on read paths checked; lazy loading flagged
- [ ] Phase B - domain-entity-in-controller leak (no entity returned from `Ok(...)`) checked
- [ ] Phase B - mass assignment via `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>` checked
- [ ] Phase B - single `SaveChangesAsync` per use case + post-commit dispatch checked
- [ ] Phase B - migration safety (online/concurrent index, lock_timeout, expand-contract, keyset backfill, startup-vs-deploy migration) checked when migrations changed
- [ ] Phase C .NET architecture checks applied: layering (Domain ← Application ← Infrastructure ← Api), no `DbContext` in Application, MediatR pipeline order, repository interfaces in Application/Interfaces, `IOptions<T>` for typed config, multi-tenant
- [ ] Phase D AI-quality checks applied: pattern inflation, single-impl interfaces, MediatR-for-trivial-reads, AutoMapper-for-trivial, speculative configurability, `Task.Run` misapplication, redundant mapping layers
- [ ] Phase E .NET maintainability checks applied: naming, magic numbers, method length, structured logging vs `Console.WriteLine`, XML doc comments, nullable reference types
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable .NET fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, .NET-specific subagents (`task-dotnet-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus stack detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a .NET idiom exists (say "register the repository interface in Application/Interfaces and implement in Infrastructure", not "use dependency inversion")
- Nitpicking style where `dotnet format` already applies; no `[Nitpick]` or `[Praise]` labels
- Providing vague feedback without a concrete .NET fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated .NET subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `async void` outside UI event handlers - swallows exceptions and cannot be awaited
- Recommending `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` for "synchronous compatibility" - deadlocks under `SynchronizationContext`, starves the thread pool
- Recommending `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)` - always a mass-assignment surface; use a request DTO record
- Recommending `FromSqlRaw($"... {input}")` for "dynamic" queries - use `FromSqlInterpolated` (parameterizes interpolated holes) or `FromSqlRaw("... {0}", input)` with explicit parameters
- Recommending `Task.Run(() => syncMethod())` to "make sync code async" - this offloads the thread without changing the work; use a real async API
- Recommending `ConfigureAwait(false)` blanket-applied to ASP.NET Core handlers - it's a no-op there and adds noise
- Recommending lazy loading (`UseLazyLoadingProxies()`) - silent N+1 generator; use explicit `Include` / `ThenInclude` or projection
