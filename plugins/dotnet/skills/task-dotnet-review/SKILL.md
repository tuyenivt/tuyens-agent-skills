---
name: task-dotnet-review
description: ".NET / ASP.NET Core / EF Core code review: async pitfalls, N+1, mass assignment, auth; spawns perf/security/observability subagents."
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

- Pre-implementation feature design (use `task-dotnet-implement`)
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

**Wrong-store test finding:** When a test uses `UseInMemoryDatabase("...")` (or SQLite) but the project's `.csproj` references `Npgsql.EntityFrameworkCore.PostgreSQL` / `Microsoft.EntityFrameworkCore.SqlServer`, raise as `[High]`. The in-memory provider skips FK enforcement, raw SQL, transactions, JSONB / array operations, and concurrent updates - tests pass while prod fails. This is more dangerous than missing tests (false confidence vs known gap).

**.NET-specific correctness checks (delegate-heavy; see canonical owners):**

- [ ] **Async / cancellation**: no `async void` outside event handlers; no `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` on async (top-of-`Main` exception only); `CancellationToken ct` propagated end-to-end; `Task.WhenAll` for independent parallel work (not sequential awaits); `IDisposable` / `IAsyncDisposable` properly disposed (`using` / `await using`); `BackgroundService.ExecuteAsync` honors `stoppingToken`; `ConfigureAwait(false)` reserved for library code (no-op in ASP.NET Core) - see `dotnet-async-patterns`
- [ ] **Exception handling**: no swallowed exceptions (`catch (Exception) { }`); rethrow via `throw;` (not `throw ex;`); central `IExceptionHandler` + Problem Details mapping (not per-action `try/catch`) - see `dotnet-exception-handling`
- [ ] **EF Core data access**: no `FromSqlRaw($"...{input}")` interpolation (use `FromSqlInterpolated` or LINQ); N+1 via per-iteration `.Single()` / `.First()` checked; `AsNoTracking()` on read paths; `UseLazyLoadingProxies()` flagged unless explicitly justified - see `dotnet-ef-performance`
- [ ] **Transactions**: writes spanning multiple `SaveChangesAsync` use async `BeginTransactionAsync` / `CommitAsync` (sync overloads block the thread same as `.Result`); single `SaveChangesAsync(ct)` per use case; background dispatch AFTER commit (use transactional outbox for exactly-once) - see `dotnet-transaction`, `dotnet-messaging-patterns`
- [ ] **DI / lifetime**: no Singleton capturing Scoped (`AppDbContext`); use `IServiceScopeFactory.CreateScope()` per operation; `HttpClient` via `IHttpClientFactory` + Polly v8 `ResiliencePipeline` (retry → circuit breaker → timeout)
- [ ] **Validation / authz**: `[ApiController]` auto-validation OR FluentValidation explicit (not mixed); `[Authorize]` (or `[AllowAnonymous]`) explicit on every action AND ownership check in handler/service body (`order.UserId == User.GetUserId()`); no user-controlled `Redirect(userInput)` (use `Url.IsLocalUrl`)
- [ ] **No domain entity returned from controller actions** (`Ok(order)` leaks every property + triggers lazy-loaded navigations); map to a response DTO record at the boundary
- [ ] **Response-DTO field-stripping audit**: even when a `*Response` record is used, audit for `PasswordHash` / `EncryptedPassword`, `MfaSecret` / `OtpSecret` / `RecoveryCodes`, `ApiKey` / `WebhookSecret`, `InternalNotes` / `AuditLog`, `IsAdmin` / `Role`, `DeletedAt`, `LastLoginIp`. Prefer a separate response DTO over `[JsonIgnore]` on the entity (the attribute is fragile - the next engineer adding a field forgets it). `[JsonInclude]` on private setters is also a leak surface
- [ ] **No mass assignment via `[FromBody] DomainEntity` / `JsonSerializer.Deserialize<DomainEntity>(body)`** - define a request DTO record with explicit FluentValidation rules and explicit field copy
- [ ] **HTTP `Idempotency-Key` header on retry-prone POSTs (distinct from worker-side message dedup)**: client→server replay protection on `POST /payments` / `POST /orders` / `POST /refunds` via a `request_idempotency` table keyed by `(tenant_id, idempotency_key)` storing request hash + cached response. On replay return stored response. Distinct from worker-side message dedup (broker redelivery) - a system needs both
- [ ] **No hardcoded JWT signing key in source** (`new SymmetricSecurityKey(Encoding.UTF8.GetBytes("literal"))` or string-literal `IssuerSigningKey` in `Program.cs`) - `[Blocker]`; sourced from env / Vault / `dotnet user-secrets` (dev). This check lives in Core because `core-only` reviews must still catch it
- [ ] **No `Process.Start("cmd.exe", $"/c {userInput}")`** (use arg-list `ArgumentList = { ... }`); `unsafe` blocks carry `// SAFETY:` comments; `Newtonsoft.Json` not added to new code paths (System.Text.Json is the .NET 6+ default); structured logging via `ILogger<T>` (not `Console.WriteLine`)
- [ ] **Migration PRs (any change in `Migrations/`)**: see the Migration PRs subsection below

**Migration PRs (any change under `Migrations/` for EF Core):**

- [ ] EF Core reversible migrations: every `Up()` migration has a corresponding `Down()` method. Missing `Down()` (the override absent entirely, not just empty) is `[Blocker]` on a multi-replica deployment - there is no in-band rollback path; reverting the deploy requires out-of-band SQL or a forward-fix migration. Empty `Down()` with a comment justifying irreversibility (e.g., column drop with data loss accepted) may be `[High]` instead, depending on whether the data is recoverable from backup
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
- [ ] **Middleware order in `Program.cs`**: canonical pipeline is `UseExceptionHandler` (or `UseStatusCodePages`) → `UseHsts` (prod) → `UseHttpsRedirection` → `UseRouting` → `UseCors` → `UseAuthentication` → `UseAuthorization` → `MapControllers`. The most explosive drift is `app.UseAuthorization()` registered **before** `app.UseAuthentication()` - the authorization step then runs with no principal and `[Authorize]` falls through to the framework default; on this path every protected endpoint silently allows all requests. Treat this drift as `[Blocker]` - the rest of the app appears to work, masking the regression. `UseAuthentication` must precede `UseAuthorization`; both must follow `UseRouting`
- [ ] **Controller convention per resource**: `OrdersController : ControllerBase` with `[Route("api/v1/[controller]")]`; one controller per aggregate root; thin actions (extract → invoke MediatR handler → map → return)
- [ ] **`IExceptionHandler` central mapping**: a single `GlobalExceptionHandler : IExceptionHandler` maps domain exceptions → HTTP status via Problem Details. Per-action `try { ... } catch { return StatusCode(...); }` scattered is inconsistent

**Multi-service PRs (when change spans 2+ services or this .NET app + a separate service):**

- API contract compatibility checked (OpenAPI diff via `Swashbuckle` or `Microsoft.AspNetCore.OpenApi`, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.
Use skill: `dotnet-overengineering-review` for redundancy vs EF Core / DB / NRT, defensive guards on framework guarantees, and premature abstraction (single-impl interfaces, MediatR for trivial reads, AutoMapper, speculative `IOptions<T>`). Each finding cites the redundancy source.

**Additional .NET AI smells not covered by the above:**

- [ ] **Redundant mapping layers**: `Entity → InternalDto → ServiceDto → ResponseDto` when one mapping would suffice
- [ ] **Test verbosity**: Bogus / NSubstitute setup helpers > 30 lines for a single assertion; deeply nested mock chains; `result.Should().BeEquivalentTo(full_object)` when a few key field assertions would do
- [ ] **`Task.Run` misapplication**: `await Task.Run(() => syncMethod())` on an already-async runtime offloads to a thread-pool thread for no reason; the call ships the thread but does the same work. `Task.Run` is for offloading CPU-bound work from the request thread, not for "making sync code async"
- [ ] **Excessive `string` allocations in hot paths**: `string.Format` / `+` concatenation / `string.Join` in tight loops where `StringBuilder`, `string.Create`, or `Span<char>` would work
- [ ] **Comment cruft**: XML doc comments restating method names; `// end of method` markers; `/// <summary>...</summary>` on private helpers that just repeat the signature
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


### Step 6 - Write Report

Use skill: `review-report-writer` with `report_type: review`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
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
- [ ] Phase D applied via `complexity-review` and `dotnet-overengineering-review`; .NET-specific AI smells covered: redundant mapping layers, `Task.Run` misapplication, hot-path string allocations
- [ ] Phase E .NET maintainability checks applied: naming, magic numbers, method length, structured logging vs `Console.WriteLine`, XML doc comments, nullable reference types
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable .NET fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, .NET-specific subagents (`task-dotnet-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus stack detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

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
