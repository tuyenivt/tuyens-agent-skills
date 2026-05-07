---
name: task-dotnet-review-perf
description: .NET performance review for EF Core N+1 / `Include` cartesian explosion / `AsNoTracking` discipline / connection pool sizing, async pitfalls (`.Result` blocking, `Task.Run` misuse, `async void`, missing `CancellationToken`), allocation hotspots (`string` concat, LINQ in hot paths, boxed value types), `Newtonsoft.Json` vs `System.Text.Json`, `IMemoryCache` / `IDistributedCache` strategy, response caching / output caching, and EF Core migration safety. Stack-specific override of task-code-review-perf, invoked when stack-detect resolves to .NET / ASP.NET Core.
agent: dotnet-performance-engineer
metadata:
  category: backend
  tags: [dotnet, aspnet-core, ef-core, performance, async, dotnet-counters, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# .NET Performance Review

## Purpose

.NET-aware performance review that names EF Core N+1 patterns (per-iteration `.Single()` / lazy-loaded navigations / missing `Include`), `Include` cartesian explosion without `AsSplitQuery`, missing `AsNoTracking()` on read paths, EF Core compiled queries (`EF.CompileAsyncQuery`), `DbContext` pool sizing (`AddDbContextPool` over `AddDbContext`, `MaxPoolSize`), connection pool sizing (Npgsql/SQL Server connection string `Maximum Pool Size`), async pitfalls (`.Result` / `.Wait()` thread-pool starvation, `async void`, `Task.Run` misuse, missing `CancellationToken`), allocation hotspots (`string` concat, LINQ enumeration in hot paths, boxed value types in collections), `Newtonsoft.Json` vs `System.Text.Json` (with source generation for hot paths), `IMemoryCache` (in-process) vs `IDistributedCache` (Redis), output caching / response caching middleware, `IHttpClientFactory` connection reuse, Polly v8 `ResiliencePipeline` shape, and EF Core migration safety idioms directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count, allocations, GC pressure, request-thread blocking) and concrete fixes using idiomatic C#.

This workflow is the stack-specific delegate of `task-code-review-perf` for .NET. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a .NET / ASP.NET Core PR or branch for performance regressions
- Investigating a slow endpoint, background worker, or MassTransit consumer
- Pre-merge perf pass on changes touching EF Core queries, async paths, allocation hotspots, or caching primitives
- Quarterly N+1 / pool-sizing / `dotnet-counters` review against profiler / OTel data

**Not for:**

- General .NET code review (use `task-code-review` or `task-dotnet-review`)
- Security review (use `task-code-review-security` or `task-dotnet-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-dotnet-new`)

## Severity Rubric

Use these definitions to keep `High` / `Medium` / `Low` Impact labels consistent across runs. Severity is about steady-state production impact and recovery effort, not how scary the code looks.

| Severity     | Definition                                                                                                                                                                                                                                                                              |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **High**     | Production outage shape under steady load: thread-pool starvation from `.Result` / `.Wait()` blocking on async, `DbContext` pool exhaustion under traffic, EF Core N+1 multiplying baseline RPS by O(N), `Include` cartesian explosion materializing 100x rows, `HttpClient` socket exhaustion from per-request `new HttpClient()`, scoped service captured by singleton, unbounded `Channel<T>` reads. Or deploy-time outage on hot tables (NOT NULL ADD with non-constant default on a 10M+-row table, non-online index on hot table on SQL Server Standard SKU). |
| **Medium**   | Degraded p95 / p99 latency, wasted bandwidth, missing pool sizing on a net-new service, `SELECT *` (entity materialization without projection) over wide entities, missing pagination on endpoints that *can* grow but currently don't, `Newtonsoft.Json` in non-trivial JSON paths, missing `IMemoryCache` on cache-friendly read endpoints. Recoverable with a follow-up PR; not paging on-call. |
| **Low**      | CPU / allocation churn (`string.Format` in hot paths, LINQ enumeration over arrays where `for` loop fits, missing `StringBuilder` capacity), missing response compression, missing `[ResponseCache]` / output-cache directives, missing `[ProducesResponseType]` for OpenAPI hot path docs.                                                                                                                                                                |

When uncertain between tiers, ask "would this page on-call within 24 hours of a 2x traffic increase?" - yes ⇒ High; "would this drag the next quarter's perf budget?" - yes ⇒ Medium.

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint or repository ("is this query ok?")          | Steps 4 + 5 only; EF Core hotspots + migrations    |
| `standard` | Default - full .NET perf review                              | All steps                                          |
| `deep`     | Profiling-driven review with `dotnet-trace` / `PerfView` / OTel / `BenchmarkDotNet` data | All steps + capacity guidance and load plan |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                          | Meaning                                                                                               |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-dotnet-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-dotnet-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-dotnet-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If the detected stack is not .NET, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes .NET 8 LTS+ on ASP.NET Core.

Detect data access:

- `Microsoft.EntityFrameworkCore` in `.csproj` → **EF Core**
- `Dapper` in `.csproj` → **Dapper**
- Both → **mixed**

Detect mediator: MediatR (`MediatR` package in `.csproj`) or none. Detect messaging: `MassTransit`, `Hangfire`, in-process `Channel<T>`, or none.

The data-access decision drives which checklists in Step 4 apply. Record `Data Access: EF Core <version> | Dapper <version> | mixed`, `Mediator: MediatR | none`, `Messaging: MassTransit | Hangfire | Channel | none` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern query and concurrency behavior so impact estimates ground in real code:

**EF Core surface:**

- Every changed query (`db.Orders.Where(...)`, `.Include(...)`, `.Select(...)`, `.ToListAsync(ct)`, `.FirstOrDefaultAsync(ct)`, `.SingleAsync(ct)`, `.CountAsync(ct)`, `FromSqlRaw`, `FromSqlInterpolated`)
- Every changed handler / repository for transaction usage (`db.Database.BeginTransactionAsync(ct)`, `tx.CommitAsync(ct)`, `db.SaveChangesAsync(ct)`)
- `Program.cs` `AddDbContext` / `AddDbContextPool` / `AddDbContextFactory` registration; pool size; connection string pool config (`Maximum Pool Size`, `Minimum Pool Size`, `Connection Lifetime`)
- Migration files under `Migrations/`
- Lazy loading enabled (`UseLazyLoadingProxies()`) - silent N+1 generator

**Dapper surface (when in use):**

- Every `connection.QueryAsync<T>(...)` / `ExecuteAsync(...)` for parameterization and shape
- Multi-mapper / `splitOn` usage for joins

**Async / runtime surface:**

- Every changed handler / service for `async Task` vs `async void` signatures, `await` placement, `.Result` / `.Wait()` calls, `Task.Run` calls, missing `CancellationToken`
- New `Task.WhenAll(...)` fan-out; new `Channel<T>` patterns; new `Parallel.ForEachAsync`
- `BackgroundService` / `IHostedService` lifecycle (`ExecuteAsync`, `StopAsync`)
- Singleton service definitions touching scoped dependencies (captive-dependency check)

**Both:**

- HTTP / external clients (`IHttpClientFactory.CreateClient(...)` vs `new HttpClient()`); typed clients via `services.AddHttpClient<TClient>(...)`; Polly v8 `ResiliencePipeline` registration
- In-process cache (`IMemoryCache`); distributed cache (`IDistributedCache`, Redis via `Microsoft.Extensions.Caching.StackExchangeRedis`)
- Background workers; MassTransit consumers; Hangfire jobs

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new endpoint calling an existing repository whose query does an N+1), read the unchanged file too - the regression lives there even though the line count attributes it to the new caller.

### Step 4 - EF Core (or Dapper) Hotspots

> If `Data Access: EF Core` was recorded in Step 1, **skip the Dapper subsection entirely** below. Likewise skip the EF Core subsection on Dapper-only projects. The bifurcation exists for mixed codebases - on monoglot projects it should be one read, not two.

**If EF Core** - use skill: `dotnet-ef-performance`:

Inspect every changed query, repository, handler, and controller for:

- [ ] **N+1 in queries**: any per-iteration `.Single()` / `.First()` / `.Where(...).ToList()` inside a `foreach` over a parent set is N+1; resolve via `Include()` / `ThenInclude()`, projection with `.Select(...)` to a flat DTO, or a separate batched `Where(o => parentIds.Contains(o.ParentId))` query plus in-memory grouping
- [ ] **Lazy loading enabled**: `UseLazyLoadingProxies()` in `Program.cs` is a silent N+1 generator - any property access on a navigation triggers a separate query during serialization. Disable; use explicit `Include` or projection
- [ ] **`Include` cartesian explosion**: chaining `.Include(x => x.Orders).Include(x => x.Addresses)` on multiple collections produces a cartesian product (100 customers × 10 orders × 5 addresses = 5,000 rows materialized for what should be 1,150). Use `AsSplitQuery()` to split into separate SQL statements per collection, OR project via `.Select(...)` to a flat DTO that names only the columns you need
- [ ] **Missing `AsNoTracking()` on read-only queries**: `db.Orders.AsNoTracking().Where(...).ToListAsync(ct)` skips change tracker overhead (~30% faster, lower allocations). Mutations use the default tracked path. For repeat-entity scenarios use `AsNoTrackingWithIdentityResolution()`
- [ ] **Projection over entity materialization**: `db.Orders.Select(o => new OrderDto(o.Id, o.Total)).ToListAsync(ct)` materializes only the columns named, skips the change tracker, and skips lazy-loaded navigations during serialization. `db.Orders.ToListAsync(ct)` materializes every column on `Order` even if the response only uses `Id` and `Total`
- [ ] **`AsSplitQuery()` for multi-collection includes**: when `.Include()` chains multiple collection navigations, default behavior is single-query cartesian. Add `.AsSplitQuery()` (or set globally via `optionsBuilder.UseQuerySplittingBehavior(QuerySplittingBehavior.SplitQuery)`)
- [ ] **Compiled queries for hot paths**: `EF.CompileAsyncQuery((AppDbContext db, Guid id) => db.Orders.Where(o => o.Id == id))` cached at startup avoids per-request expression-tree compilation. Use for high-frequency hot queries; over-compiling everything is premature
- [ ] **`fetch_all` without pagination**: `.ToListAsync(ct)` on an unbounded set - require `.Skip(...).Take(...)` (offset pagination) or keyset pagination (`Where(o => o.Id > lastId).Take(N)`) for any list endpoint that can grow
- [ ] **Missing indexes for filter/sort columns**: any property used in `Where` / `OrderBy` / `GroupBy` without a `HasIndex(...)` in the entity configuration / a corresponding migration
- [ ] **Bulk operations**: `db.Orders.AddRange(orders); await db.SaveChangesAsync(ct);` for bulk insert (single round-trip with batched INSERT). For 1000+ rows consider `EFCore.BulkExtensions` or raw `COPY` (PostgreSQL `Npgsql.PostgresCopyHelper`). `ON CONFLICT DO NOTHING` / `MERGE` for idempotent upserts via `EFCore.BulkExtensions.BulkInsertOrUpdate(...)` or raw SQL
- [ ] **Per-row `INSERT` in a loop**: `foreach (var o in orders) { db.Orders.Add(o); await db.SaveChangesAsync(ct); }` is N round-trips and N transactions - batch via `AddRange` + single `SaveChangesAsync`
- [ ] **Transactions**: writes spanning multiple `SaveChangesAsync` use `await using var tx = await db.Database.BeginTransactionAsync(ct); ...; await tx.CommitAsync(ct);`. Long transactions (HTTP calls, message dispatch inside `tx`) hold a connection for the duration - extract I/O outside the transaction, capture inputs, dispatch after commit
- [ ] **Single `SaveChangesAsync` per use case**: handlers should call `SaveChangesAsync` once at the end. Multiple `SaveChangesAsync` calls split atomicity and create race windows where partial state is visible
- [ ] **Per-iteration `SaveChangesAsync` inside `foreach`**: `foreach (var x in xs) { ...; await db.SaveChangesAsync(ct); }` is the worst case of the two patterns above co-occurring - it is BOTH N+1 (each iteration round-trips) AND multiple-`SaveChangesAsync` (each iteration is its own transaction, so a mid-loop failure leaves partial state committed). Treat as one finding describing both halves; the fix is the same: collect all mutations, single `SaveChangesAsync` at the end (or batch via `AddRange` for inserts)
- [ ] **`DbContext` pooling**: `services.AddDbContextPool<AppDbContext>(options => ...)` over `AddDbContext` for high-throughput services. Pool size defaults to 1024; tune via `AddDbContextPool(options, poolSize: N)` and ensure `N × replica count ≤ database max connections`
- [ ] **Connection pool sizing**: connection-string `Maximum Pool Size` (Npgsql / `Microsoft.Data.SqlClient`) tuned per workload; `Minimum Pool Size` for steady-state; default `Maximum Pool Size = 100` is typically too high for a single replica with `DbContext` pooling already capping concurrency
- [ ] **No `Pool::connect` per request**: never `new SqlConnection(connectionString)` inside a handler outside of Dapper code - always go through DI'd `DbContext` (EF Core) or `IDbConnectionFactory` (Dapper)

**If Dapper:**

- [ ] N+1 via per-iteration `connection.QueryFirstAsync<T>("... WHERE id = @id", new { id })` inside a loop - resolve via `connection.QueryAsync<T>("... WHERE id = ANY(@ids)", new { ids })` (PostgreSQL) or `WHERE id IN @ids` (SQL Server with table-valued parameter)
- [ ] **Multi-mapper for joins**: `connection.QueryAsync<Parent, Child, Parent>(sql, (p, c) => { p.Children.Add(c); return p; }, splitOn: "ChildId")` for parent+child shapes; flat projection to a DTO via `connection.QueryAsync<FlatDto>(sql)` is simpler when reshape-on-read fits
- [ ] **`QueryAsync` without bounded `LIMIT` / `TOP`**: pagination missing on list queries
- [ ] **`IDbConnection` reuse**: connections come from a pooled factory; per-call `new SqlConnection(...)` defeats pooling

### Step 5 - Indexes and Migrations

Use skill: `dotnet-db-migration-safety` for safe-migration checks on any change in `Migrations/`.

- [ ] Every property referenced in `Where` / `OrderBy` / `GroupBy` is backed by an index (`builder.HasIndex(x => x.Email)` or `[Index(nameof(Email))]` in the entity config)
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (PostgreSQL does not auto-index FKs; SQL Server's clustered index is on the PK, not FKs)
- [ ] Indexes on large tables use online / concurrent options:
  - PostgreSQL: `migrationBuilder.Sql("CREATE INDEX CONCURRENTLY ix_... ON ...");` (cannot run inside the migration transaction; flag `CREATE INDEX CONCURRENTLY` inside a default migration transaction as a finding)
  - SQL Server: `migrationBuilder.Sql("CREATE INDEX ix_... ON ... WITH (ONLINE = ON);");` (Enterprise SKU only)
- [ ] **`SET lock_timeout`** (PostgreSQL) or `SET LOCK_TIMEOUT` (SQL Server) before DDL on large tables to fail fast instead of blocking
- [ ] Unique constraints enforced at the database level (not just `[Required]` data annotation)
- [ ] Partial / filtered indexes used for boolean/enum filters that select a small subset (PostgreSQL `CREATE INDEX ... WHERE status = 'pending'`; SQL Server filtered index `WHERE Status = 'Pending'`)
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add column nullable, backfill, switch reads, drop old column in a later release)
- [ ] **Backfill via keyset pagination** in `migrationBuilder.Sql(...)` (`WHERE id > @lastId ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N` (re-scans the same rows on every iteration)
- [ ] Data migrations isolated from DDL migrations - separate migration files
- [ ] **Migrations applied via `dotnet ef database update` as a deployment step**, not via `db.Database.Migrate()` on app startup for multi-replica deployments (every replica races the migration on rollout). Single-replica or local dev startup migration is fine; flag startup migration on multi-replica prod

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `Where` / `OrderBy` / `GroupBy` even if no query in the diff currently references it - someone is adding the index for a reason. Validate the index is actually needed (column shape, expected selectivity), then assess migration safety. Conversely, when the diff _adds a column_ the application also queries on, flag the missing index proactively rather than waiting for a separate migration PR.

**Migration impact template.** Before approving any migration step on a hot table, state the impact: _"DDL on a 50M-row table without `WITH (ONLINE = ON)` (SQL Server) or `CREATE INDEX CONCURRENTLY` (PostgreSQL) blocks all writes for the duration of the index build (typically 5-30 min on Postgres at this scale; SQL Server depends on SKU). Acquires `ACCESS EXCLUSIVE` on Postgres, schema-modification lock on SQL Server; every other transaction queues."_ If the row count is unknown, ask, or note "row count not in diff - confirm before deploy."

**EF Core CONCURRENTLY mechanics.** `migrationBuilder.CreateIndex(...)` always runs inside the migration transaction, which is incompatible with `CREATE INDEX CONCURRENTLY` (PostgreSQL requires it outside any transaction). The fix on Postgres is to drop into raw SQL with `migrationBuilder.Sql("CREATE INDEX CONCURRENTLY ix_... ON ...", suppressTransaction: true);` - the `suppressTransaction: true` flag tells EF Core to skip the wrapping transaction for that statement. Flag any `migrationBuilder.CreateIndex(...)` (the typed API) on a hot Postgres table as `[High]` and recommend the raw-SQL form; flag `migrationBuilder.Sql("CREATE INDEX CONCURRENTLY ...")` without `suppressTransaction: true` as `[High]` (will fail at deploy time).

### Step 6 - Async, Threading, and Concurrency

Use skill: `dotnet-async-patterns` for canonical patterns.

Inspect changes touching `async Task`, `Task.WhenAll`, `Task.Run`, `Channel<T>`, `Parallel.ForEachAsync`, and worker pools:

- [ ] **No `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` on async methods**: blocks the calling thread; deadlocks under `SynchronizationContext` (legacy ASP.NET / WPF) or starves the thread pool (modern ASP.NET Core). Under load, this collapses throughput because every blocked thread reduces the pool's concurrency
- [ ] **`async void` outside event handlers**: swallows exceptions silently, cannot be awaited, surfaces only via `UnobservedTaskException` (typically a process crash). Use `async Task` for non-event-handler async work
- [ ] **`CancellationToken` propagated**: every `async Task` method takes `CancellationToken ct` as the last parameter and forwards to every awaited call (DB, HTTP, MediatR send, file I/O). Missing `ct` means a cancelled request continues to consume resources after the client has hung up
- [ ] **`Task.Run` misapplication**: `await Task.Run(() => syncMethod())` on an already-async runtime offloads to a thread-pool thread for no concurrency benefit; the thread is consumed for the same duration. `Task.Run` is for offloading **CPU-bound** work from the request thread (e.g., heavy in-memory transformations), not for "making sync code async." For sync-over-async on the request path, the right fix is to make the underlying API async
- [ ] **`Task.WhenAll` for independent parallel work**: `var (a, b) = (await fetchA(ct), await fetchB(ct));` runs sequentially; `var results = await Task.WhenAll(fetchA(ct), fetchB(ct));` runs concurrently when calls are independent. Flag sequential awaits over independent calls
- [ ] **Bounded fan-out via `Parallel.ForEachAsync`**: `Parallel.ForEachAsync(items, new ParallelOptions { MaxDegreeOfParallelism = 8, CancellationToken = ct }, async (item, ct) => ...)` for controlled fan-out; unbounded `Task.WhenAll(items.Select(async i => ...))` over a 10k-item list will exhaust DB connections / file descriptors
- [ ] **`HttpClient` via `IHttpClientFactory`**: `new HttpClient()` per request leaks sockets (DNS changes invisible until process restart, and TIME_WAIT state under load exhausts ephemeral ports). Inject `IHttpClientFactory` and use `factory.CreateClient(name)`, OR use typed clients via `services.AddHttpClient<TClient>()`. Wrap with Polly v8 `ResiliencePipelineBuilder<HttpResponseMessage>().AddRetry(...).AddCircuitBreaker(...).AddTimeout(...).Build()`
- [ ] **Polly v8 `ResiliencePipeline` shape**: retry → circuit breaker → timeout (timeout is the inner-most so each attempt is bounded). v7-style `Policy.Handle<...>().WaitAndRetryAsync(...)` is deprecated; use `ResiliencePipelineBuilder` (v8). Without explicit timeout, your p99 = upstream's worst-case tail
- [ ] **`HttpClient.Timeout` set explicitly**: default is 100 seconds; for request-path callers, set per-pipeline timeout via Polly (recommended) or `client.Timeout = TimeSpan.FromSeconds(5)` on the typed client setup
- [ ] **No singleton capturing scoped service**: `services.AddSingleton<IFoo, Foo>()` where `Foo`'s constructor takes a scoped dependency (`AppDbContext`, scoped repository) - the scoped service is captured at startup and lives for the process lifetime. Use `IServiceScopeFactory` and create a scope per operation
- [ ] **`SemaphoreSlim.WaitAsync(ct)` over `lock(...)` for async-aware locking**: C# disallows `lock` across `await`, but `Monitor.Enter` / `SemaphoreSlim.Wait()` (sync) misuse can recreate the pattern. `SemaphoreSlim.WaitAsync(ct)` cooperates with the runtime; `Monitor.Enter` blocks the thread
- [ ] **`Channel<T>` bounded by default**: `Channel.CreateBounded<T>(new BoundedChannelOptions(N) { FullMode = BoundedChannelFullMode.Wait })` over `Channel.CreateUnbounded<T>()` - unbounded is a memory leak under backpressure
- [ ] **`Channel<T>` reader cancels on shutdown**: `await foreach (var item in channel.Reader.ReadAllAsync(stoppingToken))` in a `BackgroundService` propagates the host's `stoppingToken`; bare `ReadAllAsync()` cannot drain on shutdown
- [ ] **`BackgroundService` honors `stoppingToken`**: `ExecuteAsync(CancellationToken stoppingToken)` has a `while (!stoppingToken.IsCancellationRequested)` loop and forwards `stoppingToken` to every awaited call. Bare `while (true)` ignores graceful shutdown
- [ ] **`Thread.Sleep` inside an async / `BackgroundService` body**: `Thread.Sleep(N)` blocks the thread synchronously, ignores `stoppingToken`, and prolongs shutdown to the full sleep interval. Use `await Task.Delay(TimeSpan.FromMilliseconds(N), stoppingToken)` - it cooperates with cancellation and yields the thread back to the pool while waiting
- [ ] **No external I/O inside an EF Core transaction**: `await httpClient.PostAsync(url, content, ct)` inside `await using var tx = await db.Database.BeginTransactionAsync(ct); ... await tx.CommitAsync(ct);` holds the transaction's connection for the network roundtrip. Under load this drains the `DbContext` pool faster than QPS would predict, and locked rows stay locked for the upstream's tail latency. Recommend: capture inputs inside the transaction, dispatch the side effect after commit
- [ ] **`ConfigureAwait(false)` in library code only**: in shared library code outside ASP.NET Core, call `.ConfigureAwait(false)` on every awaited call to avoid capturing the caller's `SynchronizationContext`. In pure ASP.NET Core code paths, `ConfigureAwait(false)` is a no-op (no `SynchronizationContext`); blanket-applying it adds noise without value

> **Impact heuristic - blast radius of `.Result` blocking.** A blocking `.Result` call is not just one slow request; under load every blocked thread is removed from the thread pool. With default `MinThreads = ProcessorCount`, the pool initially scales by injecting one thread every 500ms - when arrival rate exceeds this, the queue fills, p99 climbs from milliseconds to multi-second tail latency. Phrase the impact as "thread-pool starvation proportional to RPS × blocking duration," not "this one request is slow."

> **Synchronous external dependency on the request path.** Even when the call uses `IHttpClientFactory` correctly, a request to a critical-path service (fraud, auth, pricing) inherits the upstream's tail latency: your p99 = max(your work, upstream p99). Recommend async patterns (decision cache, circuit breaker, fire-and-forget via background queue) when the call is non-blocking-business; recommend strict Polly `AddTimeout(...)` plus fallback values when blocking-business.

> **Stating impact when load shape isn't in the diff.** Impact estimates need a concrete "at this RPS / at this row count" frame, but PRs rarely ship that data. When RPS, expected page size, or row count aren't in the diff or `CLAUDE.md`, **state the assumption alongside the impact** - e.g., "Assuming 100 RPS and a 5M-row `Orders` table: the missing index forces a sequential scan of ~5M rows per request, p95 likely ~2s on warm cache." Failing to anchor the number leaves the finding as "this is slow" prose, which the Self-Check explicitly bans. If the assumption is load-bearing for severity (e.g., the High-tier "10M+-row" rule), say so and recommend confirming row count pre-merge.

> **Hot loop / hot path defined.** Several checklist items below gate on "hot loop" / "hot path" - by which this workflow means: (a) any code path executed once per HTTP request on the request thread, (b) any code path executed once per row in a `.ToListAsync` / iterator result, (c) any code path inside a `BackgroundService` / consumer loop processing events. Setup code, one-shot startup work, and CLI tools fall outside this definition. The allocation / CPU checks in Step 7 only fire when the code is on a hot path so understood.

### Step 7 - Allocation Hotspots and CPU Cost

_Skipped at `quick` depth unless the diff touches hot loops or large allocations._

- [ ] **`string` concat in hot loops**: `s += part;` in a tight loop allocates a new string per iteration. Use `StringBuilder` (pre-size with `new StringBuilder(capacity)` when known) or `string.Create(length, state, span)` for advanced cases
- [ ] **`string.Format` / interpolation in hot paths**: each call allocates; for high-frequency log lines use structured logging templates (`_logger.LogInformation("Order {OrderId} placed", id)` keeps the template constant and lets the logger defer formatting until needed)
- [ ] **`StringBuilder` without capacity**: when the final size is known, `new StringBuilder(capacity)` avoids the geometric reallocation pattern
- [ ] **LINQ enumeration over arrays / lists in hot paths**: `.Where(...).Select(...).ToArray()` allocates an iterator per stage; for arrays a `for` loop avoids the allocations. Profile before optimizing - LINQ is usually fine outside the hottest paths
- [ ] **Boxed value types in collections**: `List<object>` storing `int` / `Guid` boxes every value. Use `List<int>` / generic typed collections
- [ ] **Avoid `ToList()` mid-pipeline**: `.Where(...).ToList().Select(...).ToList()` materializes twice; chain LINQ and call `.ToList()` once at the end
- [ ] **`Span<T>` / `Memory<T>` for parsing / slicing**: avoid intermediate `string` / `byte[]` allocations when a `ReadOnlySpan<char>` or `ReadOnlySpan<byte>` would slice the existing buffer
- [ ] **`Dictionary<K, V>` capacity hint**: `new Dictionary<K, V>(capacity)` when count is known to avoid rehashing growth
- [ ] **`System.Text.Json` over `Newtonsoft.Json` in hot paths**: System.Text.Json is faster, lower-allocation, and is the .NET 6+ default. For very hot serialization paths, enable source generation: `[JsonSerializable(typeof(OrderResponse))] partial class OrderJsonContext : JsonSerializerContext` to skip runtime reflection
- [ ] **`JsonSerializer.SerializeAsync(stream, ...)` writes directly to the response body**: vs `JsonSerializer.Serialize(...)` which allocates the full string first
- [ ] **`#[ResponseCompression]`**: response compression middleware (`UseResponseCompression()`) for JSON responses > 1KB; configure providers (Brotli > Gzip)
- [ ] **`record struct` / `readonly struct` for small value types**: avoids heap allocation when the type is small and copied less than ~16 bytes
- [ ] **`ArrayPool<T>.Shared.Rent(...)` / `MemoryPool<T>`** for transient large buffers in hot paths

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] **In-process cache (`IMemoryCache`)**: register via `services.AddMemoryCache()`; configure size limit (`SetSize(...)` per entry + `SizeLimit` on options) - unbounded `IMemoryCache` is a memory leak; absolute / sliding expiration mandatory; `_cache.GetOrCreateAsync(key, async entry => { entry.SetAbsoluteExpiration(TimeSpan.FromMinutes(5)); return await fetchAsync(); })` for cache-aside
- [ ] **Distributed cache (`IDistributedCache`)**: Redis via `Microsoft.Extensions.Caching.StackExchangeRedis` for cross-replica state; serialize via `System.Text.Json`; explicit TTL via `DistributedCacheEntryOptions.SetAbsoluteExpiration(...)`
- [ ] **Cache stampede protection**: hot keys with expensive regeneration use single-flight - `IMemoryCache` with a `SemaphoreSlim` per key (or library `LazyCache` / `FusionCache`); for distributed cache, Redis `SET NX EX` lock
- [ ] **Cache invalidation explicit** - no caches that never expire and never invalidate; document staleness budget; prefer event-driven invalidation over time-based when correctness matters
- [ ] **Output caching** (.NET 7+): `services.AddOutputCache(...)` and `app.UseOutputCache()` middleware; `[OutputCache(Duration = 60, VaryByQueryKeys = new[] { "page" })]` on read-heavy GET actions. Replaces the older `[ResponseCache]` for server-side caching
- [ ] **Response caching** (`[ResponseCache]` / `UseResponseCaching`): client / proxy-side via `Cache-Control` headers - distinct from output caching which is server-side
- [ ] **HTTP client response caching**: `IHttpClientFactory` with a delegating handler that respects `Cache-Control`; or `Microsoft.Extensions.Caching.Memory` wrapping the `HttpClient` call site
- [ ] **`ETag` / `Last-Modified` headers** on read-heavy endpoints supporting conditional requests (304 Not Modified saves serialization + transfer)
- [ ] **Per-request memoization**: store on `HttpContext.Items` for values used by multiple middlewares / filters in the same request

### Step 9 - Background Workers / MassTransit / Hangfire

_Skipped at `quick` depth unless the diff touches background workers or message brokers._

Use skill: `dotnet-messaging-patterns` for canonical patterns.

**If `BackgroundService` / `IHostedService` (in-process):**

- [ ] **`stoppingToken` honored**: `while (!stoppingToken.IsCancellationRequested) { await DoWorkAsync(stoppingToken); }`; bare `while (true)` cannot drain on shutdown
- [ ] **`Task.Delay(interval, stoppingToken)` over `Thread.Sleep`**: `Thread.Sleep` blocks the worker thread; `Task.Delay` cooperates with cancellation
- [ ] **Scoped services per iteration**: `BackgroundService` is singleton; use `IServiceScopeFactory.CreateScope()` per work iteration to get fresh `DbContext` / scoped repositories
- [ ] **Idempotent work**: re-fetch state, check if already done, return early. Pass IDs / value types as payload, never tracked entity references

**If MassTransit:**

- [ ] **Consumer parallelism bounded**: `cfg.UseConcurrencyLimit(N)` on the bus or per-receive-endpoint to control fan-out; default is unbounded
- [ ] **Idempotent consumers**: same idempotency requirement - retries / rebalances cause re-delivery; dedup via business key + DB constraint or outbox/inbox pattern
- [ ] **Transactional outbox**: `services.AddMassTransit(x => x.AddEntityFrameworkOutbox<AppDbContext>(...))` - outbox pattern guarantees message dispatch happens iff `SaveChangesAsync` commits. Without outbox, the post-commit dispatch race is a real bug surface
- [ ] **Retry policy explicit**: `cfg.UseMessageRetry(r => r.Intervals(...))` per consumer; without it, the broker default applies and may not match the cost model

**If Hangfire:**

- [ ] **Job idempotency**: same as above; Hangfire delivers at-least-once, retries on failure
- [ ] **Worker count tuned**: `BackgroundJobServerOptions.WorkerCount` matches CPU + I/O profile; default is `Environment.ProcessorCount * 5`
- [ ] **Dashboard secured**: `app.UseHangfireDashboard("/hangfire", new DashboardOptions { Authorization = new[] { ... } })` - default is open in dev; flag missing auth in prod (also a security finding)

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-dotnet-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (Serilog `_logger.LogInformation(...)` with structured fields OR a `Meter` / `Histogram<double>` instrument); if not, raise as a Low/Recommendation finding and delegate to `task-dotnet-review-observability` for a proper instrumentation pass rather than dictating the design here
- [ ] EF Core logging not at `Information` for SQL in prod (configured via `optionsBuilder.LogTo(Console.WriteLine, LogLevel.Warning)` or via `appsettings.json` `Logging:LogLevel:Microsoft.EntityFrameworkCore.Database.Command = Warning` floor)
- [ ] `dotnet-counters` / `dotnet-trace` runnable in non-prod for live profiling (no code change needed; this is a CI / runbook check)

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process metric aggregation) → `task-dotnet-review-observability` owns it. Note the gap, do not duplicate the audit here.

## Self-Check

- [ ] Stack confirmed as .NET / ASP.NET Core; data-access mix, mediator, and messaging recorded before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent)
- [ ] Performance surface read directly (queries / repositories, handlers, pool config, migrations, async sites, channels, singleton/scoped registrations)
- [ ] `dotnet-ef-performance` consulted for the project's data-access mix; N+1, lazy loading, cartesian explosion via `Include`, projection vs entity materialization, `AsNoTracking` checked
- [ ] `dotnet-db-migration-safety` consulted for any migration change; `lock_timeout`, online/concurrent index, keyset-pagination backfill, expand-contract, startup-vs-deploy migration verified
- [ ] `dotnet-async-patterns` consulted; `.Result` / `.Wait()`, `async void`, `Task.Run` misuse, missing `CancellationToken`, captive scoped via singleton, `BackgroundService` cancellation audited
- [ ] `dotnet-messaging-patterns` consulted for any background-worker / MassTransit / Hangfire change; idempotency, post-commit dispatch (outbox), bounded consumer parallelism verified
- [ ] `DbContext` pool sizing + connection-string `Maximum Pool Size` validated against worker / replica concurrency model **if pool config is in the diff**; otherwise note as Low / Recommendation and skip rather than fail the check
- [ ] Allocation hotspots assessed when the diff touches hot loops or large structs (`string` concat, LINQ in tight loops, boxing, `Newtonsoft.Json` in hot paths)
- [ ] Caching strategy assessed (`IMemoryCache` vs `IDistributedCache`, output caching, single-flight, invalidation explicit)
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when profiler / OTel data exists, estimated otherwise (`adds ~N queries per request at K rows` or `each blocked thread starves the pool`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)

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
- **Issue:** [what the problem is - name the .NET idiom: N+1 via per-iteration `.Single()` inside a `foreach`, missing `Include` triggering lazy load, `Include` cartesian explosion without `AsSplitQuery`, missing `AsNoTracking()`, sync `.Result` blocking on async, `new HttpClient()` per request leaking sockets, singleton capturing scoped `DbContext`, dispatch inside transaction without outbox, `[FromBody] DomainEntity` mass assignment, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrdersController.List adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific .NET change with code example - `db.Orders.AsNoTracking().Include(o => o.Items).AsSplitQuery().ToListAsync(ct)`, `Parallel.ForEachAsync` with bounded `MaxDegreeOfParallelism`, `IHttpClientFactory.CreateClient`, `IServiceScopeFactory.CreateScope` per iteration in singleton, MassTransit transactional outbox, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Move PDF generation to a Hangfire job", "Wrap external HTTP calls in Polly v8 ResiliencePipeline with retry + circuit breaker + timeout"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Replace `.Result` with `await` in OrdersController.GetById; propagate `CancellationToken ct` from action signature through the call chain"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add `CREATE INDEX CONCURRENTLY` migration on (TenantId, CreatedAt) - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the .NET idiom ("this is slow" vs "N+1 from per-iteration `.Single()` inside `foreach`; replace with `.Where(o => ids.Contains(o.Id)).ToListAsync(ct)`")
- Recommending generic backend advice when a .NET pattern applies (say "use `Parallel.ForEachAsync` with `MaxDegreeOfParallelism`", not "use a worker pool")
- Suggesting `Task.Run(() => syncMethod())` to "make sync code async" - offloads the thread without changing the work; make the underlying API async instead
- Suggesting `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` for sync-over-async on the request path - thread-pool starvation and deadlock surface
- Suggesting `lock(...) { await ... }` (compile error) or `Monitor.Enter` across `await` - use `SemaphoreSlim.WaitAsync(ct)`
- Suggesting `Channel.CreateUnbounded<T>()` to "avoid backpressure" - that is a memory leak; use `CreateBounded<T>(N)` with explicit `FullMode`
- Suggesting `new HttpClient()` per request - socket exhaustion under load; use `IHttpClientFactory`
- Suggesting caching without an invalidation strategy
- Conflating performance review with general code review or security review - delegate those to their workflows
- Treating background-worker retries as a substitute for idempotency - retries with non-idempotent jobs cause double-charging / double-emailing
- Recommending `FromSqlRaw($"... {input}")` for "dynamic" queries - parameterize via `FromSqlInterpolated` (parameterizes interpolated holes), `FromSqlRaw("... {0}", input)` with explicit parameters, or LINQ. When `FromSqlRaw($"...")` is found, the perf concern (defeats query plan reuse, plan-cache pollution) is the smaller half - the SQL injection surface is the bigger half. Add a `[Delegate] -> task-dotnet-review-security` entry to Next Steps so the security half doesn't get silently absorbed into a perf finding

> **Cross-workflow finding ownership.** When a finding is dual perf+security (the `FromSqlRaw($"...")` interpolation above, `Process.Start` shell-out, deserialization of untrusted input via `JsonSerializer.Deserialize<DomainEntity>`), the perf review reports it once with a `[Delegate] -> task-dotnet-review-security` entry in Next Steps and stops there - it does **not** enumerate every parallel security concern in the file (auth bypass, IDOR, mass assignment, open redirect, JWT misvalidation). Those are the security delegate's territory. The perf review's job is to surface the perf half cleanly and hand off; trying to be exhaustive on the security half drowns the perf signal and produces two parallel security audits.
- Reporting "missing index" without confirming the column actually appears in a `Where` / `OrderBy` / `GroupBy` in the diff
- Approving lazy loading (`UseLazyLoadingProxies()`) - silent N+1 generator; use explicit `Include` / `ThenInclude` or projection
- Approving `[FromBody] DomainEntity` parameter binding or `JsonSerializer.Deserialize<DomainEntity>(body)` - mass-assignment vector; use a request DTO record
- Approving singleton with scoped dependency - captive-dependency bug; use `IServiceScopeFactory`
- Approving `ConfigureAwait(false)` blanket-applied to ASP.NET Core handlers - it's a no-op there and adds noise; reserve for shared library code
