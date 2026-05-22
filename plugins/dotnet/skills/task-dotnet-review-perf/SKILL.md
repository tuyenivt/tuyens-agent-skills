---
name: task-dotnet-review-perf
description: ".NET / ASP.NET Core / EF Core perf review: N+1, AsNoTracking, async pitfalls, allocations, caching, pool sizing, migration safety."
agent: dotnet-performance-engineer
metadata:
  category: backend
  tags: [dotnet, aspnet-core, ef-core, performance, async, dotnet-counters, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# .NET Performance Review

Stack-specific delegate of `task-code-review-perf` for .NET. Names EF Core / ASP.NET Core / async / allocation idioms directly. Produces findings with measured or estimated impact (latency, throughput, query count, allocations, thread-pool blocking) and concrete fixes.

## When to Use

- Reviewing a .NET / ASP.NET Core PR for perf regressions
- Investigating a slow endpoint, background worker, or MassTransit consumer
- Pre-merge perf pass on EF Core queries, async paths, allocations, or caching
- Quarterly N+1 / pool-sizing review against profiler / OTel data

**Not for:**

- General .NET review (`task-dotnet-review`)
- Security review (`task-dotnet-review-security`)
- Incident response (`/task-oncall-start`)
- Pre-implementation design (`task-dotnet-implement`)

## Severity Rubric

Impact = steady-state production behavior, not how scary the code looks.

| Severity   | Definition |
| ---------- | ---------- |
| **High**   | Outage-shape under load: `.Result` / `.Wait()` thread-pool starvation, `DbContext` pool exhaustion, N+1 multiplying RPS by O(N), `Include` cartesian explosion, `new HttpClient()` socket exhaustion, singleton capturing scoped `DbContext`, unbounded `Channel<T>`. Or deploy-time outage: non-online DDL on a hot table, `CREATE INDEX CONCURRENTLY` inside a migration transaction (fails at deploy). |
| **Medium** | Degraded p95/p99: missing pool sizing on new service, entity materialization over wide tables without projection, missing pagination on growable lists, `Newtonsoft.Json` in non-trivial paths, missing `IMemoryCache` on cache-friendly reads. Follow-up PR fixable. |
| **Low**    | CPU / allocation churn (`string.Format` in hot paths, LINQ in tight loops), missing response compression / output cache, missing `[ProducesResponseType]`. |

Tiebreaker: "would this page on-call within 24h of a 2x traffic spike?" - yes ⇒ High. "Would this drag next quarter's perf budget?" - yes ⇒ Medium.

## Depth Levels

| Depth      | When                                                      | Runs                                          |
| ---------- | --------------------------------------------------------- | --------------------------------------------- |
| `quick`    | Single endpoint or repository                             | Steps 4 + 5                                   |
| `standard` | Default - full perf review                                | All steps                                     |
| `deep`     | Profiler-driven (`dotnet-trace` / `PerfView` / OTel / BDN)| All steps + capacity guidance + load-test plan |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                          | Meaning                                                                  |
| ----------------------------------- | ------------------------------------------------------------------------ |
| `/task-dotnet-review-perf`          | Review current branch vs base; fails fast on a trunk branch              |
| `/task-dotnet-review-perf <branch>` | Review `<branch>` vs base (3-dot diff)                                   |
| `/task-dotnet-review-perf pr-<N>`   | Review PR head fetched into local `pr-<N>` (user runs the fetch first)   |

When invoked as a subagent of `task-code-review-perf` or `task-dotnet-review`, Steps 1-2 reuse the parent's pre-confirmed stack and pre-read diff / commit log.

## Workflow

### Step 1 - Confirm Stack and Detect Surface

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If not .NET, stop and direct the user to `/task-code-review-perf`.

Record for the Summary block:

- **Data Access:** `EF Core <version>` | `Dapper <version>` | `mixed` (based on `.csproj` packages)
- **Mediator:** `MediatR` | `none`
- **Messaging:** `MassTransit` | `Hangfire` | `Channel` | `none`

Data-access value drives Step 4 branch selection.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once, reuse for all subsequent steps. If the check stops with a fail-fast message, surface it verbatim and stop. Never run state-changing git commands from this workflow.

### Step 3 - Read the Performance Surface

For each finding produced later, cite a real `file:line`. Open the files that govern query and concurrency behavior before applying checklists:

- **EF Core:** changed queries, repositories, handlers; `Program.cs` `AddDbContext` / `AddDbContextPool`; connection string pool config; migrations under `Migrations/`; `UseLazyLoadingProxies()` (silent N+1).
- **Dapper:** `QueryAsync<T>` / `ExecuteAsync` shape; multi-mapper / `splitOn`.
- **Async surface:** `async Task` / `async void` signatures, `.Result` / `.Wait()`, `Task.Run`, missing `CancellationToken`, new `Task.WhenAll` / `Parallel.ForEachAsync` / `Channel<T>`, `BackgroundService` lifecycle, singleton-capturing-scoped.
- **Shared:** `IHttpClientFactory` vs `new HttpClient()`; Polly v8 `ResiliencePipeline`; `IMemoryCache` / `IDistributedCache`; MassTransit / Hangfire consumers.

If the diff is small but ripples into unchanged code (a new caller hitting an existing N+1 repo), read the unchanged file - the regression lives there.

### Step 4 - Data-Access Hotspots

Use skill: `dotnet-ef-performance`. Apply the EF Core checklist on EF Core projects, Dapper checklist on Dapper-only, both on mixed.

**EF Core - changed queries / repositories:**

- [ ] N+1 (per-iteration `.Single()` / `.First()` / `.ToList()` inside `foreach`) - resolve via `Include` / `ThenInclude` (add `AsSplitQuery()` on multi-collection includes to avoid cartesian explosion), or projection via `.Select(new Dto(...))`
- [ ] `UseLazyLoadingProxies()` enabled - silent N+1; flag unless justified
- [ ] `AsNoTracking()` on read-only queries; tracked path only on mutations
- [ ] `.ToListAsync(ct)` without `.Skip().Take()` or keyset pagination on growable lists; missing `HasIndex` for `Where` / `OrderBy` / `GroupBy`
- [ ] Bulk insert via `AddRange` + single `SaveChangesAsync` (or `EFCore.BulkExtensions` for 1000+); per-row INSERT in a loop is N round-trips
- [ ] Single `SaveChangesAsync` per use case; per-iteration `SaveChangesAsync` inside `foreach` is worst case
- [ ] Transactions wrap multi-statement writes; no HTTP / publish I/O inside open transaction (dispatch after commit)
- [ ] `AddDbContextPool` over `AddDbContext` for high-throughput; `Maximum Pool Size × replicas ≤ DB cap`; never `new SqlConnection()` per request
- [ ] `EF.CompileAsyncQuery` reserved for hot queries (premature when applied everywhere)

**Dapper:**

- [ ] N+1 resolved via `WHERE id = ANY(@ids)` (Postgres) / TVP (SQL Server); multi-mapper or flat-DTO for joins; pagination on lists; pooled `IDbConnectionFactory`

### Step 5 - Indexes and Migrations

Use skill: `dotnet-db-migration-safety` for any change under `Migrations/`.

- [ ] Every column in `Where` / `OrderBy` / `GroupBy` is indexed; composite indexes match leftmost-prefix; FKs indexed (Postgres / SQL Server don't auto-index FKs the way you might assume)
- [ ] Online / concurrent indexes on hot tables:
  - Postgres: `migrationBuilder.Sql("CREATE INDEX CONCURRENTLY ...", suppressTransaction: true)` - the typed `migrationBuilder.CreateIndex(...)` runs inside the migration transaction, which is incompatible with `CONCURRENTLY`. Flag typed `CreateIndex` on a hot table as `[High]`; flag `Sql("CREATE INDEX CONCURRENTLY ...")` missing `suppressTransaction: true` as `[High]` (fails at deploy)
  - SQL Server: `WITH (ONLINE = ON)` (Enterprise SKU only)
- [ ] `SET lock_timeout` (Postgres) / `SET LOCK_TIMEOUT` (SQL Server) before DDL on large tables - fail fast over block
- [ ] Partial / filtered indexes for boolean/enum filters selecting a small subset
- [ ] Expand-then-contract on hot-table column changes (add nullable, backfill, switch reads, drop later)
- [ ] Backfill via keyset pagination (`WHERE id > @lastId ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N` (re-scans every iteration)
- [ ] Migrations applied via `dotnet ef database update` as a deploy step, not `db.Database.Migrate()` on startup for multi-replica deployments (replicas race)

**Reasoning rule.** Diff adds an index ⇒ treat the column as hot (someone added it for a reason); validate need, then assess safety. Diff adds a column the app also filters on ⇒ flag missing index proactively.

**Impact template.** Before approving DDL on a hot table, state row count and lock posture: e.g., _"50M rows without `WITH (ONLINE = ON)` blocks writes 5-30 min; Postgres acquires `ACCESS EXCLUSIVE`, SQL Server takes a schema-modification lock; all writes queue."_ Row count not in diff ⇒ ask, or note "row count unknown - confirm before deploy."

### Step 6 - Async, Threading, Concurrency

Use skill: `dotnet-async-patterns`. Scan changes touching `async Task`, `Task.WhenAll`, `Task.Run`, `Channel<T>`, `Parallel.ForEachAsync`, workers:

- [ ] No `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` on async; no `async void` outside event handlers
- [ ] `CancellationToken ct` propagated through every async chain; `Task.Run` only for CPU-bound work (not "making sync code async")
- [ ] Sequential `await`s over independent calls collapsed via `Task.WhenAll`; fan-out bounded via `Parallel.ForEachAsync(items, new ParallelOptions { MaxDegreeOfParallelism = N })`
- [ ] `HttpClient` via `IHttpClientFactory`; Polly v8 `ResiliencePipeline` shape: retry → circuit breaker → timeout (innermost); explicit `HttpClient.Timeout` (default 100s)
- [ ] No singleton capturing scoped (`AppDbContext`); use `IServiceScopeFactory.CreateScope()` per operation
- [ ] `SemaphoreSlim.WaitAsync(ct)` over sync `Wait()` or `Monitor.Enter` across `await`
- [ ] `Channel.CreateBounded<T>(N)` with explicit `FullMode` over `CreateUnbounded` (memory leak under backpressure)
- [ ] `BackgroundService.ExecuteAsync` uses `while (!stoppingToken.IsCancellationRequested)`; `Task.Delay(..., stoppingToken)` over `Thread.Sleep`
- [ ] No HTTP / external I/O inside `BeginTransactionAsync...CommitAsync`; capture inputs, dispatch after commit

**Impact framing.** `.Result` blocking = thread-pool starvation proportional to RPS × blocking duration (pool injects 1 thread / 500ms; arrival > scale ⇒ queue fills, p99 → seconds). Synchronous upstream call = "p99 = max(self, upstream p99)". When RPS / row count aren't in the diff or `CLAUDE.md`, state the assumption alongside the estimate.

**Hot path = per-request on the request thread, per-row in a `.ToListAsync` result, or inside a `BackgroundService` / consumer loop.** Step 7 / Step 8 only fire on hot paths.

### Step 7 - Allocations and CPU

_Skipped at `quick` depth unless the diff touches hot loops or large allocations._

- [ ] `string` concat / `string.Format` in hot loops - use `StringBuilder` (pre-sized) or structured logging templates (`_logger.LogInformation("Order {OrderId} placed", id)`)
- [ ] LINQ chains in tight loops over arrays - profile first; replace with `for` only when measured
- [ ] Boxing: `List<object>` storing `int` / `Guid` - use typed generic collections
- [ ] `ToList()` mid-pipeline materializes twice - chain LINQ, call `ToList()` once at the end
- [ ] `System.Text.Json` over `Newtonsoft.Json` in hot paths; enable source generation (`[JsonSerializable(typeof(T))] partial class TJsonContext : JsonSerializerContext`) for very hot serialization
- [ ] `JsonSerializer.SerializeAsync(stream, ...)` directly to the response body over `Serialize(...)` (allocates full string)
- [ ] `Span<T>` / `Memory<T>` / `ArrayPool<T>.Shared.Rent` for transient large buffers in hot paths
- [ ] `record struct` / `readonly struct` for small value types (< ~16 bytes, copied less than passed)

### Step 8 - Caching and Response

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] `IMemoryCache`: register via `AddMemoryCache()`; **size limit mandatory** (`SizeLimit` on options + per-entry `SetSize`) - unbounded is a memory leak; absolute / sliding expiration mandatory; cache-aside via `GetOrCreateAsync(key, async entry => { entry.SetAbsoluteExpiration(...); return await ...; })`
- [ ] `IDistributedCache` (Redis via `StackExchangeRedis`) for cross-replica state; explicit TTL via `DistributedCacheEntryOptions.SetAbsoluteExpiration`
- [ ] Cache stampede protection on expensive regen: `SemaphoreSlim` per key, `LazyCache` / `FusionCache`, or Redis `SET NX EX`
- [ ] Explicit invalidation strategy - never "expires never, invalidates never"
- [ ] Output caching (`AddOutputCache` / `UseOutputCache` + `[OutputCache(Duration = 60, VaryByQueryKeys = new[] { "page" })]`) on read-heavy GET actions; distinct from client-side `[ResponseCache]`
- [ ] Response compression (`UseResponseCompression()`, Brotli > Gzip) for JSON > 1KB
- [ ] `ETag` / `Last-Modified` on read-heavy endpoints supporting conditional requests

### Step 9 - Background Workers

_Skipped at `quick` depth unless the diff touches workers or brokers._

Use skill: `dotnet-messaging-patterns`.

- [ ] Workers idempotent (re-fetch state, check-then-act); payload carries IDs, not tracked entities; dispatch AFTER `SaveChangesAsync` (use `AddEntityFrameworkOutbox<AppDbContext>` for exactly-once)
- [ ] `BackgroundService`: `IServiceScopeFactory.CreateScope()` per iteration (BackgroundService is Singleton, `DbContext` is Scoped); cancellation propagated
- [ ] MassTransit: `cfg.UseConcurrencyLimit(N)` (default unbounded); explicit `UseMessageRetry` per consumer
- [ ] Hangfire: `WorkerCount` tuned for CPU + I/O profile; dashboard gated by `DashboardOptions.Authorization` (missing prod auth is also a security finding)

### Step 10 - Observability Hand-off

_Skipped at `quick` depth._

Narrow: confirm presence/absence only; depth on observability belongs to `task-dotnet-review-observability`.

- [ ] Slow paths reachable from the PR have some instrumentation (`ILogger` structured log OR a `Meter` / `Histogram<double>`); raise as Low + delegate if absent
- [ ] EF Core SQL logging not at `Information` in prod (floor at `Warning` via `optionsBuilder.LogTo` or `appsettings.json`)
- [ ] `dotnet-counters` / `dotnet-trace` runnable in non-prod (runbook / CI check)

Anything beyond presence/absence → `task-dotnet-review-observability` owns it.

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write the assembled review to the report file; print the confirmation line to console.

## Self-Check

- [ ] **Step 1:** Stack confirmed; `Data Access`, `Mediator`, `Messaging` recorded
- [ ] **Step 2:** `review-precondition-check` ran (or handle received); diff and commit log read once and reused
- [ ] **Step 3:** Performance surface read directly (queries, pool config, migrations, async sites, singleton/scoped registrations)
- [ ] **Step 4:** `dotnet-ef-performance` consulted; N+1, lazy loading, cartesian explosion, projection, `AsNoTracking` checked; pool sizing validated when in diff
- [ ] **Step 5:** `dotnet-db-migration-safety` consulted on any `Migrations/` change; `lock_timeout`, CONCURRENTLY / `ONLINE = ON`, keyset backfill, expand-contract, deploy-vs-startup migration verified
- [ ] **Step 6:** `dotnet-async-patterns` consulted; `.Result` / `.Wait()`, `async void`, `Task.Run` misuse, missing `CancellationToken`, captive scoped, `BackgroundService` cancellation audited
- [ ] **Step 7:** Allocation hotspots assessed when diff touches hot loops or large structs
- [ ] **Step 8:** Caching strategy assessed (size limit, expiration, stampede, invalidation, output caching)
- [ ] **Step 9:** `dotnet-messaging-patterns` consulted on any worker / MassTransit / Hangfire change; idempotency, post-commit dispatch, bounded parallelism verified
- [ ] **Step 10:** Observability presence/absence noted; depth gaps delegated to `task-dotnet-review-observability`
- [ ] **Step 11:** Report written via `review-report-writer`; confirmation line printed
- [ ] Every finding states impact (measured `p95: 800ms -> 120ms`, or estimated `adds ~N queries per request at K rows`) - never just "this is slow"
- [ ] Findings ordered High > Medium > Low; depth honored; Next Steps tagged `[Implement]` / `[Delegate]` (omitted only when no actionable findings)

## Output Format

```markdown
## .NET Performance Review Summary

**Stack Detected:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**Mediator:** MediatR <version> | none
**Messaging:** MassTransit | Hangfire | Channel | none
**Scope:** Backend (.NET)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [.NET idiom named - e.g., "N+1 via per-iteration `.Single()` inside `foreach`", "Singleton capturing scoped `DbContext`", "`CREATE INDEX CONCURRENTLY` inside default migration transaction"]
- **Impact:** [measured `p95 800ms -> 120ms` or estimated `~200 extra queries per request at 100 orders`]
- **Fix:** [specific .NET change with code - `db.Orders.AsNoTracking().Include(o => o.Items).AsSplitQuery().ToListAsync(ct)`, `IHttpClientFactory.CreateClient`, `migrationBuilder.Sql(..., suppressTransaction: true)`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Wrap external HTTP calls in Polly v8 ResiliencePipeline (retry + circuit breaker + timeout)"]

## Next Steps

Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting refactor / schema / load-test work). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Replace `.Result` with `await` in OrdersController.GetById; propagate `CancellationToken ct` from action signature"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add `CREATE INDEX CONCURRENTLY` migration on (TenantId, CreatedAt) - spawn DB migration subagent"]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch` / `git checkout` / any state-changing git command - user runs these
- Reporting "this is slow" without naming the .NET idiom (N+1 via per-iteration `.Single()`, `Include` cartesian without `AsSplitQuery`, singleton-captures-scoped, etc.)
- Generic backend advice when a .NET pattern exists (`Parallel.ForEachAsync` with `MaxDegreeOfParallelism`, not "use a worker pool")
- Recommending caching without an invalidation strategy
- Approving lazy loading (`UseLazyLoadingProxies`) - silent N+1
- Approving `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)` - mass-assignment vector; use a request DTO record
- Approving singleton with scoped dependency - captive-dependency; use `IServiceScopeFactory`
- Approving `ConfigureAwait(false)` blanket-applied to ASP.NET Core handlers - no-op there
- Reporting "missing index" without confirming the column appears in `Where` / `OrderBy` / `GroupBy` in the diff
- Treating background-worker retries as a substitute for idempotency
- Conflating perf review with general or security review - delegate
- `FromSqlRaw($"...{input}")` is dual perf+security: file one perf finding (plan-cache pollution) and add `[Delegate] -> task-dotnet-review-security` to Next Steps for the SQLi half. Don't enumerate parallel security concerns; that's the security delegate's territory.
