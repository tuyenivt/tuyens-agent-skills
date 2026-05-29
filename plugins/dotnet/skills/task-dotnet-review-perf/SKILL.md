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

# .NET Performance Review

Stack-specific delegate of `task-code-review-perf` for .NET. Names EF Core / ASP.NET Core / async / allocation idioms directly. Produces findings with measured or estimated impact (latency, throughput, query count, allocations, thread-pool blocking) and concrete fixes.

## When to Use

- .NET / ASP.NET Core PR for perf regressions
- Investigating a slow endpoint, background worker, or MassTransit consumer
- Pre-merge perf pass on EF Core queries, async paths, allocations, or caching
- Quarterly N+1 / pool-sizing review against profiler / OTel data

**Not for:** general review (`task-dotnet-review`); security review (`task-dotnet-review-security`); incident response (`/task-oncall-start`); pre-implementation design (`task-dotnet-implement`).

## Severity Rubric

Impact = steady-state production behavior, not how scary the code looks.

| Severity   | Definition |
| ---------- | ---------- |
| **High**   | Outage-shape under load: `.Result` / `.Wait()` thread-pool starvation, `DbContext` pool exhaustion, N+1 multiplying RPS by O(N), `Include` cartesian explosion, `new HttpClient()` socket exhaustion, singleton capturing scoped `DbContext`, unbounded `Channel<T>`. Or deploy-time outage: non-online DDL on a hot table, `CREATE INDEX CONCURRENTLY` inside a migration transaction. |
| **Medium** | Degraded p95/p99: missing pool sizing, entity materialization over wide tables without projection, missing pagination on growable lists, `Newtonsoft.Json` in non-trivial paths, missing `IMemoryCache` on cache-friendly reads. Follow-up PR fixable. |
| **Low**    | CPU / allocation churn (`string.Format` in hot paths, LINQ in tight loops), missing response compression / output cache, missing `[ProducesResponseType]`. |

Tiebreaker: "would this page on-call within 24h of a 2x traffic spike?" - yes -> High. "Would this drag next quarter's perf budget?" - yes -> Medium.

## Depth Levels

| Depth      | When                                                      | Runs                                          |
| ---------- | --------------------------------------------------------- | --------------------------------------------- |
| `quick`    | Single endpoint or repository                             | Steps 5 + 6                                   |
| `standard` | Default                                                   | All steps                                     |
| `deep`     | Profiler-driven (`dotnet-trace` / `PerfView` / OTel / BDN)| All steps + capacity guidance + load-test plan |

Default: `standard`.

## Invocation

| Invocation                          | Meaning                                                                  |
| ----------------------------------- | ------------------------------------------------------------------------ |
| `/task-dotnet-review-perf`          | Current branch vs base; fails fast on a trunk branch                     |
| `/task-dotnet-review-perf <branch>` | `<branch>` vs base (3-dot diff)                                          |
| `/task-dotnet-review-perf pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)                    |

When invoked as a subagent of `task-code-review-perf` or `task-dotnet-review`, Steps 1-3 reuse the parent's pre-confirmed stack and pre-read diff / commit log.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Detect Surface

Use skill: `stack-detect`. If not .NET, stop and route to `/task-code-review-perf`.

Record for the Summary:

- **Data Access:** `EF Core <version>` | `Dapper <version>` | `mixed` (from `.csproj` packages)
- **Mediator:** `MediatR` | `none`
- **Messaging:** `MassTransit` | `Hangfire` | `Channel` | `none`

Data-access value drives Step 5 branch selection.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. If the check stops with a fail-fast message, surface verbatim and stop. Never run state-changing git.

### Step 4 - Read the Performance Surface

Open files that govern query and concurrency behavior before applying checklists:

- **EF Core:** changed queries, repositories, handlers; `Program.cs` `AddDbContext` / `AddDbContextPool`; connection string pool config; migrations under `Migrations/`; `UseLazyLoadingProxies()` (silent N+1)
- **Dapper:** `QueryAsync<T>` / `ExecuteAsync` shape; multi-mapper / `splitOn`
- **Async surface:** `async Task` / `async void`, `.Result` / `.Wait()`, `Task.Run`, missing `CancellationToken`, new `Task.WhenAll` / `Parallel.ForEachAsync` / `Channel<T>`, `BackgroundService`, singleton-capturing-scoped
- **Shared:** `IHttpClientFactory` vs `new HttpClient()`; Polly v8 `ResiliencePipeline`; `IMemoryCache` / `IDistributedCache`; MassTransit / Hangfire consumers

If a small diff ripples into unchanged code (new caller hitting an existing N+1 repo), read the unchanged file - the regression lives there.

### Step 5 - Data-Access Hotspots

Use skill: `dotnet-ef-performance` (EF Core checklist on EF Core projects, Dapper on Dapper-only, both on mixed). Apply its findings against the diff; cite real `file:line`.

Workflow-specific gates:

- Pool sizing: `AddDbContextPool` over `AddDbContext` for high-throughput; `Maximum Pool Size × replicas <= DB cap`. Flag missing on a new service as Medium
- `UseLazyLoadingProxies()` in the diff is High unless justified

### Step 6 - Indexes and Migrations

Use skill: `dotnet-db-migration-safety` for any change under `Migrations/`. Apply against the diff.

Workflow-specific gates:

- **Reasoning rule.** Diff adds an index -> treat the column as hot (someone added it for a reason); validate need, then assess safety. Diff adds a column the app also filters on -> flag missing index proactively
- **Impact template.** Before approving DDL on a hot table, state row count and lock posture: e.g., _"50M rows without `WITH (ONLINE = ON)` blocks writes 5-30 min; Postgres acquires `ACCESS EXCLUSIVE`, SQL Server takes a schema-modification lock; all writes queue."_ If row count not in diff, ask or note "row count unknown - confirm before deploy."

### Step 7 - Async, Threading, Concurrency

Use skill: `dotnet-async-patterns`. Apply against changes touching `async Task`, `Task.WhenAll`, `Task.Run`, `Channel<T>`, `Parallel.ForEachAsync`, workers.

Workflow-specific gates:

- **Impact framing.** `.Result` blocking = thread-pool starvation proportional to RPS × blocking duration (pool injects 1 thread / 500ms; arrival > scale -> queue fills, p99 -> seconds). Synchronous upstream call -> "p99 = max(self, upstream p99)". When RPS / row count aren't in the diff or `CLAUDE.md`, state the assumption alongside the estimate
- **Hot path = per-request on the request thread, per-row in a `.ToListAsync` result, or inside a `BackgroundService` / consumer loop.** Steps 8-9 fire only on hot paths

### Step 8 - Allocations and CPU

_Skipped at `quick` unless the diff touches hot loops or large allocations._

- [ ] `string` concat / `string.Format` in hot loops - use `StringBuilder` (pre-sized) or structured logging templates
- [ ] LINQ chains in tight loops - profile first; replace with `for` only when measured
- [ ] Boxing: `List<object>` storing `int` / `Guid` - use typed generic collections
- [ ] `ToList()` mid-pipeline materializes twice - chain LINQ, `ToList()` once at the end
- [ ] `System.Text.Json` over `Newtonsoft.Json` in hot paths; source generation for very hot serialization (`[JsonSerializable(typeof(T))] partial class TJsonContext : JsonSerializerContext`)
- [ ] `JsonSerializer.SerializeAsync(stream, ...)` directly to the response body over `Serialize(...)` (avoids full-string allocation)
- [ ] `Span<T>` / `Memory<T>` / `ArrayPool<T>.Shared.Rent` for transient large buffers in hot paths
- [ ] `record struct` / `readonly struct` for small value types (< ~16 bytes, copied less than passed)

### Step 9 - Caching and Response

_Skipped at `quick` unless the diff touches caching primitives._

- [ ] `IMemoryCache`: `AddMemoryCache()`; **size limit mandatory** (`SizeLimit` on options + per-entry `SetSize`) - unbounded is a memory leak; absolute / sliding expiration mandatory; cache-aside via `GetOrCreateAsync(key, entry => { entry.SetAbsoluteExpiration(...); return ...; })`
- [ ] `IDistributedCache` (Redis via `StackExchangeRedis`) for cross-replica state; explicit TTL via `DistributedCacheEntryOptions.SetAbsoluteExpiration`
- [ ] Cache stampede protection on expensive regen: `SemaphoreSlim` per key, `LazyCache` / `FusionCache`, or Redis `SET NX EX`
- [ ] Explicit invalidation - never "expires never, invalidates never"
- [ ] Output caching (`AddOutputCache` / `UseOutputCache` + `[OutputCache(Duration = 60, VaryByQueryKeys = ["page"])]`) on read-heavy GETs; distinct from client-side `[ResponseCache]`
- [ ] Response compression (`UseResponseCompression()`, Brotli > Gzip) for JSON > 1KB
- [ ] `ETag` / `Last-Modified` on read-heavy endpoints supporting conditional requests

### Step 10 - Background Workers

_Skipped at `quick` unless the diff touches workers or brokers._

Use skill: `dotnet-messaging-patterns`. Apply against the diff.

Workflow-specific gates:

- Workers idempotent (re-fetch state, check-then-act); payload carries IDs, not tracked entities; dispatch AFTER `SaveChangesAsync` (use `AddEntityFrameworkOutbox<AppDbContext>` for exactly-once)
- `BackgroundService`: `IServiceScopeFactory.CreateScope()` per iteration (Singleton service, Scoped `DbContext`)
- MassTransit: `cfg.UseConcurrencyLimit(N)` (default unbounded); explicit `UseMessageRetry` per consumer
- Hangfire: `WorkerCount` tuned for CPU + I/O profile; dashboard gated by `DashboardOptions.Authorization`

### Step 11 - Observability Hand-off

_Skipped at `quick`._

Narrow: confirm presence/absence only. Depth belongs to `task-dotnet-review-observability`.

- [ ] Slow paths reachable from the PR have some instrumentation (`ILogger` structured log OR a `Meter` / `Histogram<double>`); raise as Low + delegate if absent
- [ ] EF Core SQL logging not at `Information` in prod (floor at `Warning` via `optionsBuilder.LogTo` or `appsettings.json`)
- [ ] `dotnet-counters` / `dotnet-trace` runnable in non-prod

Anything beyond presence/absence -> `task-dotnet-review-observability`.

### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write the assembled review; print the confirmation line.

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed; `Data Access`, `Mediator`, `Messaging` recorded
- [ ] Step 3 - `review-precondition-check` ran (or handle received); diff and commit log read once
- [ ] Step 4 - performance surface read directly (queries, pool config, migrations, async sites, singleton/scoped registrations)
- [ ] Step 5 - `dotnet-ef-performance` applied; pool sizing and lazy-loading gates checked
- [ ] Step 6 - `dotnet-db-migration-safety` applied on any `Migrations/` change; reasoning rule + impact template applied
- [ ] Step 7 - `dotnet-async-patterns` applied; hot-path scope set for Steps 8-9
- [ ] Step 8 - allocation hotspots assessed when diff touches hot loops or large structs
- [ ] Step 9 - caching strategy assessed (size limit, expiration, stampede, invalidation, output caching)
- [ ] Step 10 - `dotnet-messaging-patterns` applied on any worker / MassTransit / Hangfire change
- [ ] Step 11 - observability presence/absence noted; depth gaps delegated
- [ ] Step 12 - report written via `review-report-writer`; confirmation line printed
- [ ] Every finding states impact (measured `p95: 800ms -> 120ms`, or estimated `adds ~N queries per request at K rows`) - never just "this is slow"
- [ ] Findings ordered High > Medium > Low; depth honored; Next Steps tagged `[Implement]` / `[Delegate]`

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
- **Issue:** [.NET idiom named - "N+1 via per-iteration `.Single()` inside `foreach`", "Singleton capturing scoped `DbContext`", "`CREATE INDEX CONCURRENTLY` inside default migration transaction"]
- **Impact:** [measured `p95 800ms -> 120ms` or estimated `~200 extra queries per request at 100 orders`]
- **Fix:** [specific .NET change with code - `db.Orders.AsNoTracking().Include(o => o.Items).AsSplitQuery().ToListAsync(ct)`, `IHttpClientFactory.CreateClient`, `migrationBuilder.Sql(..., suppressTransaction: true)`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Wrap external HTTP calls in Polly v8 ResiliencePipeline (retry + circuit breaker + timeout)"]

## Next Steps

Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting refactor / schema / load-test work). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Replace `.Result` with `await` in OrdersController.GetById; propagate `CancellationToken ct` from action signature"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add `CREATE INDEX CONCURRENTLY` migration on (TenantId, CreatedAt) - spawn DB migration subagent"]

_Omit this section if there are no actionable findings._
```

## Avoid

- State-changing git from this workflow - user runs these
- "This is slow" without naming the .NET idiom (N+1 via per-iteration `.Single()`, `Include` cartesian without `AsSplitQuery`, singleton-captures-scoped, etc.)
- Generic backend advice when a .NET pattern exists (`Parallel.ForEachAsync` with `MaxDegreeOfParallelism`, not "use a worker pool")
- Recommending caching without an invalidation strategy
- Approving `UseLazyLoadingProxies` (silent N+1), `[FromBody] DomainEntity` (mass assignment - delegate to security), singleton with scoped dependency, blanket `ConfigureAwait(false)` on ASP.NET Core handlers (no-op there)
- "Missing index" without confirming the column appears in `Where` / `OrderBy` / `GroupBy` in the diff
- Treating background-worker retries as a substitute for idempotency
- Conflating perf with general or security review - delegate
- `FromSqlRaw($"...{input}")` is dual perf+security: file one perf finding (plan-cache pollution) and add `[Delegate] -> task-dotnet-review-security` to Next Steps. Don't enumerate parallel security concerns
