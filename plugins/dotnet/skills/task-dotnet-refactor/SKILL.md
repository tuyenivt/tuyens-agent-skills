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

Phased, commit-safe refactor plan for a .NET target (controller / Minimal API endpoint, MediatR handler, application service, EF Core repository or entity, `BackgroundService`, DTO record). Stack-specific delegate of `task-code-refactor`.

## When to Use

- .NET smell identification and resolution on a named target
- Pre-merge cleanup of fat controllers / god services / handlers
- Technical-debt reduction with a concrete step sequence

Not for: features (`task-dotnet-implement`), cross-project re-architecture (`task-design-architecture`), bug fixes (`task-dotnet-debug`).

## Inputs

| Input                | Required    | Description                                                                                |
| -------------------- | ----------- | ------------------------------------------------------------------------------------------ |
| Target               | Yes         | File / class / endpoint (e.g., `src/Acme.Api/Controllers/OrdersController.cs`)             |
| Goal                 | Yes         | What the refactor achieves (extract handler, eliminate `.Result`, split god service, ...)  |
| Test coverage status | Recommended | xUnit / Testcontainers / `WebApplicationFactory` coverage; format/analyzer baseline state  |
| Shared surface       | Recommended | Whether target is `public` across project / assembly / NuGet boundaries                    |

Goal without a target -> ask for the target before proceeding.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detection

Use skill: `stack-detect`. If invoked by a .NET-aware parent, accept the pre-confirmed stack. If detected stack is not .NET, stop and route to `/task-code-refactor`.

Record `Data Access` (EF Core / Dapper / mixed), `Mediator` (MediatR / none), `Messaging` (MassTransit / Hangfire / Channel / none).

### Step 3 - Read the Target

Plans grounded in prose hallucinate smells. Read directly:

1. Target file top-to-bottom: method count, longest method, sync/async signature mix, transaction placement, external collaborators (`HttpClient`, `IMediator`, `IPublishEndpoint`), await points.
2. Matching tests: cases by outcome (happy / validation / external failure / auth denial). Record `dotnet format --verify-no-changes` baseline and whether `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` is on.
3. Immediate callers of any `public` member being reshaped.

**Sibling smells.** List smells outside the named target under `Sibling Smells (Out of Scope)` with deferral rationale (e.g., security findings -> `task-dotnet-review-security`). Do not action; do not silently omit.

**Severity inversion.** When a sibling smell is *higher severity* than the named target (SQLi via `FromSqlRaw($"...")`, RCE via `Process.Start("cmd.exe", $"/c {input}")`, auth bypass, `BinaryFormatter.Deserialize` on untrusted input), render a banner above the Coverage Gate verdict regardless of verdict:

> **Severity inversion detected.** This file contains <N> higher-severity sibling smells (<list>). Pause this refactor; route through `task-dotnet-review-security` first; branch the refactor PR off the security fix.

A fired banner supersedes the Coverage Gate action regardless of verdict: halt, emit Smells + Sibling Smells only, and route to `task-dotnet-review-security` before any `task-dotnet-test` coverage prerequisite.

### Step 4 - Coverage Gate (mandatory)

| Status       | Definition                                                                              | Action                                                     |
| ------------ | --------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `Adequate`   | Happy path + 2+ boundary outcomes per entry point (validation, auth, external, 404)     | Proceed                                                    |
| `Thin`       | Happy path + exactly 1 boundary outcome                                                 | Proceed; `Step 0 - Coverage prerequisite`                  |
| `Inadequate` | No tests, happy-path-only, or wrong-store provider mismatch                             | Refuse Steps 1+; emit verdict + prerequisite preview only  |

**Disqualifiers** (force `Inadequate` regardless of count):

- Happy-path-only - cannot prove validation, auth, or error behavior preserved.
- Wrong-store - tests use `UseInMemoryDatabase` / SQLite but production targets Postgres / SQL Server. In-memory skips FK enforcement, raw SQL, JSON/array ops, concurrency. Step 0 must migrate to Testcontainers.

**Lint baseline.** `dotnet format --verify-no-changes` must be clean and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` on, else `Step 0a` covers them. Values: `clean` | `warnings present` | `not run (no baseline)`.

**Concurrency downgrade.** Target uses `Task.Run` / `Parallel.ForEachAsync` / `BackgroundService` / `ConcurrentDictionary` / `SemaphoreSlim` / channels but tests do not exercise the concurrent path -> downgrade one tier. A `.Result` / `.Wait()` chain being converted to `await` also downgrades when its boundaries are untested (deadlock-removal risk).

### Step 5 - Identify .NET Smells

Signals, not hard rules. Catalog by surface; defer detail to atomics.

**Controllers / endpoints (High unless noted).** Fat action (> 30 lines orchestration); business logic in controller; direct `DbContext` query; domain entity returned from action (`Ok(user)`); mass assignment via `[FromBody] DomainEntity`; missing `[Authorize]` / `[AllowAnonymous]`; per-action `try/catch -> StatusCode(500)` (Medium); manual validation duplicating FluentValidation (Low).

**Handlers / services.** God service > 500 lines; anemic domain with rule-laden `*Helpers` statics; multiple `SaveChangesAsync` per use case; external I/O inside `BeginTransactionAsync`...`CommitAsync`; `null` from a failure-capable op (Medium - prefer `Result<T>` or domain exceptions).

**Async / concurrency.** See `dotnet-async-patterns`. Workflow-level signals: `.Result` / `.Wait()` / `.GetAwaiter().GetResult()`; `async void` outside event handlers; fire-and-forget `Task.Run(async () => ...)`; `Task.Run` to fake async on sync code; missing `CancellationToken` propagation; sequential awaits on independent calls; unbounded `Task.WhenAll` fan-out; `Channel.CreateUnbounded<T>()`; `Thread.Sleep` in `BackgroundService`; `while(true)` without `stoppingToken`; `Monitor.Enter` / `SemaphoreSlim.Wait()` across `await`; background dispatch inside transaction; background worker without idempotency.

**EF Core / persistence.** See `dotnet-ef-performance`. Workflow-level signals: fat repository (> 300 lines); entity used as DTO; `FromSqlRaw($"... {userInput}")` (SQLi); N+1 via per-iteration `.Single()` or lazy loading; `Include` cartesian without `AsSplitQuery()`; missing `AsNoTracking()` on reads; `ToListAsync` without pagination; `new SqlConnection(...)` per request.

**Configuration / DI.** Singleton capturing scoped; module-level mutable statics; `IConfiguration["X"]` instead of `IOptions<T>`; `IServiceProvider.GetRequiredService<T>()` in ctor/method; single-implementation interface; `new HttpClient()` per request.

**Over-engineering.** Use skill: `dotnet-overengineering-review` (single-impl interfaces, MediatR for trivial reads, AutoMapper for 1:1 mappings, premature factory / strategy). These are simplification opportunities, not new abstractions.

**`unsafe`.** Block without `// SAFETY:` (High); used for speed without a BenchmarkDotNet result (Medium).

**Test smells** (when tests are in refactor scope). `UseInMemoryDatabase` for Postgres / SQL Server app (High - migrate to Testcontainers); in-process `InMemoryRepo`; `Mock<T>().Setup(...).ReturnsAsync(default!)` masking a bug; copy-pasted `[Fact]` that should be `[Theory]`.

**Cross-cutting.** Use skill: `backend-coding-standards` for the language-agnostic catalog. Use skill: `complexity-review` when over-engineering signals appear.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. .NET-specific signals: public controller action consumed externally; symbol crosses project / assembly / NuGet boundary; interface with broad implementer surface; service injected widely; EF entity used in many queries; DTO record reused across endpoints.

State: **Narrow** (single file, single caller) | **Moderate** (single project, multiple callers) | **Wide** (cross-project, public action API, broad interface) | **Critical** (NuGet-published, entity used by 5+ consumers).

### Step 7 - Propose the Step Sequence

Each step is **independently committable** (`dotnet build /p:TreatWarningsAsErrors=true` + `dotnet test` + `dotnet format --verify-no-changes` clean), **behaviorally invariant** (unless labeled `coupled-fix`), **reversible** (one revert), **tested** (suite green; new tests added when extracting new units).

**Recipe interleaving.** Multiple recipes applying -> pick one **primary** (usually the named goal) as the spine; fold others as additive sub-steps. State `Primary recipe:` in output. Spine > ~8 steps -> split into two plans / two PRs.

**Coupled-fix label.** Genuine behavior change required (extracting a handler that needs `[Authorize]` for `User.Claims`) -> label `coupled-fix` with its own test gate and rationale.

**Per-step stances** (Output Format requires explicit values):

- **Transaction stance** - `inside caller's transaction` (callee inherits via shared scoped `DbContext`) | `post-commit dispatch (captured inputs)` | `not transactional`. Never silently move I/O across the boundary.
- **Async stance** - `unchanged` | `local` | `cascading (list affected callers)`. No partial `.Result` -> `await` - convert the chain end-to-end.
- **DI stance** - lifetime explicit. Singleton capturing scoped requires `IServiceScopeFactory`.
- **Concurrency stance** - new `BackgroundService` / `Task.Run` requires `CancellationToken` propagation and a cross-thread test.

**Common .NET refactor recipes** (each step ends in the gate above; assume it):

**Extract handler from fat controller.**
1. Add `IRequestHandler<...>` / plain handler; copy logic. Controller still routes the original way.
2. `[Theory]` tests per outcome (success, validation, external failure).
3. Controller calls handler via `IMediator`; preserve response shape.
4. Remove original logic from controller.
5. Test: handler failure surfaces via central `IExceptionHandler`.

**Eliminate `.Result` / `.Wait()`** (see `dotnet-async-patterns`).
1. Convert calling method to `async Task`; add `CancellationToken ct`.
2. Cascade innermost-first to every caller through to `async Task<IActionResult>` / `await app.RunAsync()`.
3. Forward `ct` to every call (`...Async(ct)`, `httpClient.GetAsync(url, ct)`).
4. Skip only if call site is genuinely sync-only (third-party sync contract).

**Eliminate `Task.Run(syncMethod)` on async path.**
1. If `syncMethod` is CPU-bound (image, hash) -> `Task.Run` is correct; verify bounded `MaxDegreeOfParallelism`.
2. Otherwise make it async and `await` directly.

**Add `CancellationToken` propagation** (see `dotnet-async-patterns`).
Verify chain: entry points have `ct`; every `async Task` accepts and forwards `ct`; EF Core and `HttpClient` calls receive it. Enforce via `Microsoft.VisualStudio.Threading.Analyzers` or `Meziantou.Analyzer`.

**Eliminate single-implementation interface** (see `dotnet-overengineering-review`).
Confirm no mock, no second impl, no DI lifetime/decoration need, no public NuGet contract. Inline `AddScoped<OrderService>()`; consumers use the concrete type.

**Replace AutoMapper / MediatR for trivial cases** (see `dotnet-overengineering-review`).
Inline the mapping or repository call; delete profile/handler/`IRequest`. Skip if pipeline behaviors (validation, auth, transaction wrap, logging) are load-bearing.

**Fix singleton capturing scoped.**
Inject `IServiceScopeFactory`; `using var scope = _scopeFactory.CreateScope();` per operation; resolve scoped services within scope; never store as field. Test that `DbContext` is fresh per call.

**Replace `new HttpClient()` with `IHttpClientFactory`.**
Register `services.AddHttpClient<TClient>(...)`; add Polly v8 resilience (`.AddResilienceHandler("default", b => b.AddRetry(...).AddCircuitBreaker(...).AddTimeout(...))`).

**Eliminate `[FromBody] DomainEntity` mass assignment.**
1. Request DTO record with explicit fields + FluentValidation; no `Id` / `OwnerId` / `Role`.
2. Map to entity with explicit assignment.
3. Test: injecting `OwnerId` / `Role` is stripped.

**Replace static mutable state with DI.**
Move into a class; register (singleton if global, scoped if per-request); replace static reads/writes with instance calls. Test cross-test isolation under parallel execution.

**Convert sync polling worker to cancellation-aware loop** (see `dotnet-async-patterns`).
`while (!stoppingToken.IsCancellationRequested)`; `await Task.Delay(N, stoppingToken)`; catch `OperationCanceledException when (stoppingToken.IsCancellationRequested)` and break; forward `stoppingToken`. Test: start then cancel within `HostOptions.ShutdownTimeout`.

**Move side effects out of an open DB transaction** (see `dotnet-transaction`, `dotnet-messaging-patterns`).
Pick one option; do not stack. State the choice in the plan.

- *Option A - Post-commit dispatch with captured inputs.* Capture typed records / `Guid` / `byte[]` inside the tx (never EF entities); commit; dispatch after. Trade-off: at-most-once on crash between commit and dispatch.
- *Option B - Transactional outbox.* `OutboxMessage` table with `WHERE processed_at IS NULL` partial index; insert inside tx; relay via MassTransit `AddEntityFrameworkOutbox<AppDbContext>` or `BackgroundService` polling with `FOR UPDATE SKIP LOCKED` (Postgres) / `WITH (UPDLOCK, READPAST)` (SQL Server). Consumers must be idempotent. Add `outbox_unprocessed_count`, `outbox_oldest_age_seconds`.

**Make background worker idempotent** (see `dotnet-messaging-patterns`).
Dedup on business key (upsert via `ON CONFLICT DO NOTHING` / `MERGE` / version check); explicit retry + DLQ; for MassTransit, adopt `AddEntityFrameworkOutbox<AppDbContext>`. Test: side effect occurs exactly once when same business key arrives twice with different message IDs.

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

[Severity-inversion banner here when applicable, above verdict.]

**Status:** Adequate | Thin | Inadequate
**Lint state:** clean | warnings present (Step 0a) | not run (no baseline)
**Concurrency-test coverage:** clean | not exercised cross-thread | n/a

[Adequate: one sentence on boundary cases that exist.]
[Thin: list missing boundary tests; Step 0 covers them.]
[Inadequate: state what coverage must exist; recommend `task-dotnet-test`. **Stop the workflow here** - omit Blast Radius, Step Sequence. Still emit Smells Identified, Sibling Smells, and the Coverage Prerequisite Table below as preview-only.]

### Coverage Prerequisite Table (when Thin or Inadequate)

One row per public entry point. Required outcomes: validation (4xx), authz (401/403), not-found / IDOR, external-collaborator failure. Add a **concurrent path** row whenever the concurrency check in Step 4 applied.

| Entry point        | Outcome                  | Recommended layer                                  |
| ------------------ | ------------------------ | -------------------------------------------------- |
| POST /api/orders   | unknown-field rejected   | API test (`WebApplicationFactory<Program>`)        |
| POST /api/orders   | unauthorized denied      | API test                                           |
| ...                | ...                      | unit (xUnit + NSubstitute) | integration (Testcontainers) | background-worker | multi-thread |

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/class this plan does NOT address. Omit if none._

| Smell   | Location  | Why deferred                                          | Recommended follow-up                                                              |
| ------- | --------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / severity / security / perf]        | [`task-dotnet-review-security` / `task-dotnet-refactor` on a different target]     |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one paragraph citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add boundary tests from the Coverage Prerequisite Table
- **Risk:** Low (tests-only)
- **Test gate:** new tests pass; suite green; `dotnet format --verify-no-changes` clean
- **Rollback:** revert added test files

### Step 0a - Lint prerequisite _(skip if lint state is clean)_

- **Change:** address existing format / analyzer warnings on the target project
- **Risk:** Low (no behavior change)
- **Test gate:** `dotnet format --verify-no-changes` clean; `dotnet build /p:TreatWarningsAsErrors=true`; `dotnet test` green
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
- **Rollback:** [one git revert]

[... continue numbering ...]

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed; data access / mediator / messaging recorded
- [ ] Step 3 - target and matching tests read directly; sibling smells listed with deferral rationale (or omitted); severity-inversion banner rendered when applicable
- [ ] Step 4 - Coverage Gate verdict assigned with sharp boundaries (happy-path-only and wrong-store are `Inadequate`); concurrency downgrade applied when applicable; lint state recorded; Steps 1+ refused if `Inadequate`
- [ ] Step 5 - smells identified across controllers, handlers/services, async/concurrency, EF Core, DI, over-engineering, `unsafe`, tests
- [ ] Step 6 - blast radius stated before steps
- [ ] Step 7 - `Primary recipe:` named; supporting recipes folded as sub-steps; plan <= ~8 steps or split; per-step stances (transaction / async / DI / concurrency) set; `coupled-fix` only when structurally required; ordered low-risk first; goal mapped to end state

## Avoid

- Proposing a refactor without a Coverage Gate (that's a rewrite)
- Bundling behavior changes with refactoring (label `coupled-fix` or split)
- Renaming during a refactor (separate PR)
- Removing an interface without a real second use case or mock
- Replacing EF Core <-> Dapper without a measured win
- Replacing static mutable state with `AsyncLocal<T>` pointing at the same data
- Moving I/O across a transaction boundary without stating the stance
- Partial `.Result` -> `await` (convert end-to-end or skip the recipe)
- Refactoring a `public` NuGet symbol without a backward-compat plan
- Adding `BackgroundService` / `Task.Run` without `CancellationToken` propagation and bounded fan-out
- Replacing `[FromBody] DomainEntity` with another `[FromBody] DomainEntity`
- Consolidating into a singleton without checking captured scoped services
- Removing AutoMapper / MediatR globally based on one trivial case (keep where pipeline behaviors / conventions earn their keep)
