---
name: task-dotnet-review
description: ".NET / ASP.NET Core / EF Core PR review: async, N+1, mass assignment, authz, migrations; parallel perf/security/obs subagents."
agent: dotnet-tech-lead
metadata:
  category: backend
  tags: [dotnet, aspnet-core, ef-core, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the diff, load `Use skill: spec-aware-preamble` after `behavioral-principles`. Cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an AC, NFR, or task; flag out-of-scope changes as blockers; flag missing AC coverage as gaps. Never edit `spec.md` / `plan.md` / `tasks.md`.

# .NET Code Review

.NET-aware staff-level review umbrella. .NET-specific correctness, architecture, AI-quality, and maintainability checks. Coordinates .NET-specific perf / security / observability subagents in parallel.

Stack-specific delegate of `task-code-review` for .NET / ASP.NET Core. **Runs standalone** with full PR/branch resolution.

## When to Use

- Reviewing a .NET / ASP.NET Core PR before merge
- Post-AI-generation quality gate
- Architecture drift detection in a Clean Architecture codebase
- Pre-merge risk assessment

**Not for:**
- Pre-implementation design (use `task-dotnet-implement`)
- Active incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-dotnet-debug`)
- New-system architecture (use `task-design-architecture`)
- Single-scope reviews - delegate directly to `task-dotnet-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth      | When                                                                | What Runs                                                   |
| ---------- | ------------------------------------------------------------------- | ----------------------------------------------------------- |
| `quick`    | "Is this safe to merge?" - fast risk snapshot                       | Risk snapshot + top 3 findings (Phases A + B summary)       |
| `standard` | Default                                                             | Phases A-E                                                  |
| `deep`     | Architectural PRs, post-incident change review, Principal sign-off  | Phases A-E + historical pattern matching + cross-PR context |

Default: `standard`. **Auto-promote to `deep`** when Phase A computes Blast Radius `Wide` or `Critical` and the user did not pass `quick`. Surface in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E only (.NET-flavored)                                            |
| + Perf          | Core + parallel subagent: `task-dotnet-review-perf`                        |
| + Security      | Core + parallel subagent: `task-dotnet-review-security`                    |
| + Observability | Core + parallel subagent: `task-dotnet-review-observability`               |
| Full            | Core + all three .NET subagents in parallel                                |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (.NET-tuned):**

- `IFormFile`, `AddAuthentication` / `AddAuthorization` / policy changes, `[FromBody]` DTO changes, `FromSqlRaw` / `FromSqlInterpolated`, secrets in `appsettings*.json`, background workers consuming user input (`BackgroundService`, MassTransit, Hangfire), `JsonSerializer.Deserialize<DomainEntity>`, `Process.Start` with user input, `unsafe` blocks → **+Security**
- New EF Core migration, new `IQueryable` materialization (`ToListAsync` / `FirstAsync`), new `Include` / `ThenInclude`, new pagination, new payload endpoints, loops calling DB or HTTP, new `IMemoryCache` / `IDistributedCache`, new `Task.WhenAll` fan-out → **+Perf**
- New project / assembly, new external client (`IHttpClientFactory`, `IDistributedCache`, `Amazon*Client`), new `BackgroundService` / MassTransit consumer / Hangfire job, `Program.cs` / Serilog config change, new `Meter` / `Counter`, lifecycle / graceful-shutdown changes → **+Observability**
- Two or more signal categories → **Full**

## Invocation

| Invocation                     | Meaning                                                                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-dotnet-review`          | Current branch vs base; fails fast on trunk (`main`/`master`/`develop`)                                                                                       |
| `/task-dotnet-review <branch>` | `<branch>` vs base (3-dot diff)                                                                                                                               |
| `/task-dotnet-review pr-<N>`   | PR head fetched into local branch `pr-<N>` (user runs `git fetch origin pull/<N>/head:pr-<N>`; see `review-precondition-check` for GitLab/Bitbucket variants) |

No checkout required. Stay on your current branch; the workflow reads via ref-qualified diffs.

**Explicit base override:** pass `--base <branch>` when the PR was opened against a non-trunk base. Flags compose: `/task-dotnet-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent dispatcher. If not .NET / ASP.NET Core, stop and tell the user to invoke `/task-code-review`.

Detect and record: `Runtime: .NET <version>`, `Framework: ASP.NET Core <version>`, `Data Access: EF Core | Dapper | mixed`, `Mediator: MediatR | none`, `Messaging: MassTransit | Hangfire | Channel | none`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` (forward `--base` if passed). If it stops with a fail-fast message, surface it verbatim and stop.

Once approved, read once and reuse:

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

Skip this step when a parent dispatcher passed the handle plus pre-read artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for auto-escalation signals (above). Log `signal: <category> -> <file:line>` for each.

- Zero signals or `core-only` → Core
- One signal category → matching extra scope
- Two or more → Full
- User-passed explicit scope → respect it; still record signals so the Summary documents what was deliberately deferred

Surface decision in Summary. If escalated: `auto-escalated from Core; signals: <list>`. If user-pinned with conflicting signals: `Scope user-pinned to Core; +Security signals present: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure-propagation scope
- Output risk level and blast radius before findings

**Low-risk short-circuit:** if Phase A yields Risk `Low` and Blast Radius `Narrow`, AND the change does not touch architecture-relevant files (auth middleware, JWT validation, `Program.cs` wiring, MediatR pipeline behaviors, `DbContext` / `IEntityTypeConfiguration`, EF Core migrations), skip Phases C-D - produce a streamlined output with Phase B findings only.

If Blast Radius is `Wide` or `Critical` and the user did not pass `quick`, auto-promote depth to `deep` here, before Phases B-E.

### Phase B - .NET Correctness and Safety

Logical correctness, error handling, edge cases affecting state integrity, backward compatibility, transaction boundary correctness, async cancellation safety.

**Test coverage finding:** if the PR adds or modifies logic without xUnit / WebApplicationFactory / Testcontainers coverage, raise as an explicit finding. Default `[Suggestion]`; escalate to `[High]` for critical paths (JWT / custom auth, `IAuthorizationHandler` / ownership checks, money / billing, multi-step transactions / state machines, `BackgroundService` / MassTransit / Hangfire that mutate data, migrations changing column semantics). A named entry in Findings - not buried in Key Takeaways.

**Wrong-store test finding:** `UseInMemoryDatabase("...")` (or SQLite) when the `.csproj` references `Npgsql.EntityFrameworkCore.PostgreSQL` / `Microsoft.EntityFrameworkCore.SqlServer` is `[High]`. The in-memory provider skips FK enforcement, raw SQL, transactions, JSONB / array operations, and concurrent updates - false confidence is worse than a known gap.

**.NET correctness scan:**

- [ ] **Async / cancellation** - no `async void` outside event handlers; no `.Result` / `.Wait()` / `.GetAwaiter().GetResult()` on async; `CancellationToken ct` propagated end-to-end; `Task.WhenAll` for independent parallel work; `IDisposable` / `IAsyncDisposable` disposed (`using` / `await using`); `BackgroundService.ExecuteAsync` honors `stoppingToken`. See `dotnet-async-patterns`.
- [ ] **Exception handling** - no swallowed `catch (Exception) { }`; rethrow via `throw;` not `throw ex;`; central `IExceptionHandler` + Problem Details, not per-action `try/catch`. See `dotnet-exception-handling`.
- [ ] **EF Core data access** - no `FromSqlRaw($"...{input}")` (use `FromSqlInterpolated` or LINQ); N+1 via per-iteration `.Single()` / `.First()` checked; `AsNoTracking()` on read paths; `UseLazyLoadingProxies()` flagged. See `dotnet-ef-performance`.
- [ ] **Transactions** - writes spanning multiple `SaveChangesAsync` use async `BeginTransactionAsync` / `CommitAsync`; one `SaveChangesAsync(ct)` per use case; background dispatch AFTER commit (outbox for exactly-once). See `dotnet-transaction`, `dotnet-messaging-patterns`.
- [ ] **DI / lifetime** - no Singleton capturing Scoped (`AppDbContext`); use `IServiceScopeFactory.CreateScope()` per operation; `HttpClient` via `IHttpClientFactory` + Polly v8 `ResiliencePipeline`.
- [ ] **Validation / authz** - `[ApiController]` auto-validation OR FluentValidation (not mixed); `[Authorize]` (or `[AllowAnonymous]`) explicit on every action AND ownership check in handler body (`order.UserId == User.GetUserId()`); no user-controlled `Redirect` (use `Url.IsLocalUrl`).
- [ ] **No domain entity returned from controllers** - `Ok(order)` leaks every property and triggers lazy-loaded navigations. Map to a response DTO record at the boundary. Audit the DTO for `PasswordHash`, `MfaSecret`, `ApiKey`, `IsAdmin`, `DeletedAt`, `LastLoginIp`; prefer a separate DTO over `[JsonIgnore]` on the entity.
- [ ] **No mass assignment** via `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)` - request DTO record with explicit FluentValidation rules.
- [ ] **HTTP `Idempotency-Key`** on retry-prone POSTs (`/payments`, `/orders`, `/refunds`) via `request_idempotency` table keyed by `(tenant_id, idempotency_key)` storing request hash + cached response. Distinct from worker-side message dedup - a system needs both.
- [ ] **No hardcoded JWT signing key** (`new SymmetricSecurityKey(Encoding.UTF8.GetBytes("literal"))` or string-literal `IssuerSigningKey` in `Program.cs`) - `[Blocker]`; source from env / Vault / `dotnet user-secrets`. Stays in Core so `core-only` reviews still catch it.
- [ ] **No `Process.Start` with user input** (use `ArgumentList`); `unsafe` blocks carry `// SAFETY:` comments; no `Newtonsoft.Json` in new code paths (System.Text.Json is default); `ILogger<T>` not `Console.WriteLine`.

**Migration PRs** (any change in `Migrations/`):

- [ ] Every `Up()` has a `Down()`. Missing `Down()` is `[Blocker]` on multi-replica; empty `Down()` with a justification comment may be `[High]`.
- [ ] Two-phase deploys for column rename / drop (add → backfill → cut over → remove).
- [ ] `NOT NULL` with non-constant default (`now()`, function call) on existing column requires the two-step (add nullable → backfill → set NOT NULL).
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL) or `WITH (ONLINE = ON)` (SQL Server Enterprise); flag `migrationBuilder.CreateIndex(...)` on hot tables that lack it.
- [ ] `SET lock_timeout` before DDL on large tables.
- [ ] Data migrations isolated from DDL; long backfills via keyset pagination.
- [ ] `db.Database.Migrate()` on startup is `[High]` on multi-replica deployments (replicas race) - use `dotnet ef database update` as a deploy step.
- Use skill: `ops-backward-compatibility` for client/session/in-flight impact.
- Use skill: `dotnet-db-migration-safety` for canonical safe-migration patterns.

**Concurrency safety:**

- [ ] No shared mutable global state (`static Dictionary<...>` mutated by handlers); use `ConcurrentDictionary` / `IMemoryCache` / `IDistributedCache` with a clear ownership story. `static` mutable fields are a smell.
- [ ] Race-prone updates (counters, balance, state transitions) use DB-level locking (`SELECT ... FOR UPDATE` via `FromSqlInterpolated` in a transaction, or `[ConcurrencyCheck]` / `[Timestamp] byte[] RowVersion`) - not in-process locks.
- [ ] No `Monitor.Enter` across `await`; use `SemaphoreSlim.WaitAsync(ct)` for async-aware locking.
- [ ] `dotnet build` warning-clean; `Microsoft.CodeAnalysis.NetAnalyzers` / `Roslynator` enabled in CI.

### Phase C - .NET Architecture Guardrails (Clean Architecture)

Use skill: `architecture-guardrail` for layer violations, new coupling, circular dependencies, bypassed abstractions, boundary erosion.

- [ ] **Layering** - `Domain` ← `Application` ← `Infrastructure` ← `Api`. Domain references only primitives (no MediatR, EF Core, ASP.NET Core). Application depends only on Domain + abstractions; no `DbContext` / `HttpClient` / Polly in Application. Infrastructure implements Application interfaces; does not depend on Api.
- [ ] **No `DbContext` in Application** - use repository interfaces or MediatR handlers; Infrastructure implements via EF Core.
- [ ] **No EF Core entities in API responses** - handlers / controllers map to DTO records before return.
- [ ] **MediatR pipeline order** - `Logging` → `Validation` → `Authorization` → `Transaction` (single `SaveChangesAsync` per request, commits on success, rolls back on exception). Order is load-bearing.
- [ ] **Repository interfaces in `Application/Interfaces`**, implementations in `Infrastructure/Persistence/Repositories`. Interface in Infrastructure couples Application to Infrastructure.
- [ ] **Constructor injection only** - no `IServiceProvider.GetRequiredService<T>()` in handlers; no `new` on dependencies. Optional config via `IOptions<T>` / `IOptionsMonitor<T>`.
- [ ] **Typed config** - `services.Configure<JwtOptions>(...)` + inject `IOptions<JwtOptions>`. Do not inject `IConfiguration` into handlers.
- [ ] **`appsettings.json` discipline** - defaults in `appsettings.json`, env overrides in `appsettings.{Environment}.json`, secrets from env / Key Vault / `user-secrets`. Never commit prod secrets.
- [ ] **Multi-tenant isolation** - tenant scoping at EF Core query level or via global query filters / repository layer, not the controller alone.
- [ ] **Middleware order in `Program.cs`** - `UseExceptionHandler` → `UseHsts` → `UseHttpsRedirection` → `UseRouting` → `UseCors` → `UseAuthentication` → `UseAuthorization` → `MapControllers`. **`UseAuthorization` before `UseAuthentication` is `[Blocker]`** - the framework default falls through and every `[Authorize]` endpoint silently allows all requests.
- [ ] **Controllers thin** - one per aggregate root with `[Route("api/v1/[controller]")]`; extract → invoke handler → map → return.
- [ ] **`IExceptionHandler` central mapping** - a single `GlobalExceptionHandler` maps domain exceptions to Problem Details. Per-action `try/catch` scattered is inconsistent.

**Multi-service PRs:**

- API contract compatibility checked (OpenAPI diff via `Swashbuckle` / `Microsoft.AspNetCore.OpenApi`, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for changed inter-service contracts

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity and over-engineering. Use skill: `dotnet-overengineering-review` for redundancy vs EF Core / DB / NRT, defensive guards on framework guarantees, premature abstraction (single-impl interfaces, MediatR for trivial reads, AutoMapper, speculative `IOptions<T>`). The atomic owns the catalog and citation contract.

**.NET AI smells not covered by the necessity skill:**

- [ ] **Redundant mapping layers** - `Entity → InternalDto → ServiceDto → ResponseDto` when one would suffice.
- [ ] **Test verbosity** - Bogus / NSubstitute setup > 30 lines for a single assertion; `result.Should().BeEquivalentTo(fullObject)` when key fields would do.
- [ ] **`Task.Run` misapplication** - `await Task.Run(() => syncMethod())` does the same work on a thread-pool thread. `Task.Run` is for CPU-bound offload, not making sync code async.
- [ ] **Hot-path string allocations** - `string.Format` / `+` / `string.Join` in tight loops where `StringBuilder` / `string.Create` / `Span<char>` fit.
- [ ] **Comment cruft** - XML doc restating method names; `/// <summary>` on private helpers; `// end of method` markers.
- [ ] **`#pragma warning disable`** without `// reason: ...` is a finding.

### Phase E - .NET Maintainability

- [ ] **Naming** - namespaces / types / methods / properties `PascalCase`; parameters / locals `camelCase`; private fields `_camelCase`; interfaces `IPascalCase` (mandatory); async methods suffixed `Async`. No stutter (`Order.OrderId` → `Order.Id`).
- [ ] **Magic numbers / strings** - `private static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(5);` over inline literals.
- [ ] **Hardcoded URLs / credentials** - in `IOptions<T>` / env, never inline.
- [ ] **Method length** - > 30 lines reviewed; > 60 flagged unless clearly orchestrating named helpers.
- [ ] **Duplicated query logic** - same `Where` predicate in 3+ places → repository method or specification.
- [ ] **Nullable reference types enabled** - `<Nullable>enable</Nullable>` in `.csproj`; warnings respected; `!` (null-forgiving) requires a justification comment.
- [ ] **`record` for DTOs / value objects** - over mutable class with public setters; `{ get; init; }` when records don't fit.
- [ ] **Logging hygiene** - obvious offenders at `[Suggestion]` (`Console.WriteLine` in prod path, missing correlation IDs, wrong levels). Depth → `task-dotnet-review-observability`.
- [ ] **`dotnet format` clean / EditorConfig respected**; `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` in CI.
- [ ] **XML doc on public APIs**; `[ProducesResponseType]` on controller actions for OpenAPI.

Use skill: `backend-coding-standards` for cross-language conventions. Use skill: `ops-observability` for cross-cutting logging / metrics presence.

### Step 5 - Delegate Extra Scopes in Parallel

If scope is Core only, skip this step.

For each extra scope, spawn an independent subagent **in parallel** with the main thread.

| Scope                | Subagents                                                                                                                    |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | `task-dotnet-review-perf`                                                                                                    |
| Core + Security      | `task-dotnet-review-security`                                                                                                |
| Core + Observability | `task-dotnet-review-observability`                                                                                           |
| Full                 | All three in parallel                                                                                                        |

**Subagent prompt contract:**

- Resolved review target from Step 3 (`base_ref`, `head_ref`) + already-read diff and commit log - subagent skips `review-precondition-check` and `git diff`
- Depth level
- Pre-confirmed stack and detected data-access / mediator / messaging
- Instruction to return findings using its own skill's Output Format

**Failure isolation:** if a subagent fails / times out, continue with the rest. Note the missing scope in the synthesized output.

### Step 6 - Synthesize

(Skip if Step 5 didn't run.) Merge subagent findings into the single Output Format - do not append raw reports.

- **Deduplicate cross-cutting findings** - same issue across scopes (e.g., per-iteration EF Core query flagged by Core/Phase B and Perf). One entry citing all scopes.
- **Severity wins** when labels differ across scopes (`Blocker` > `High` > `Suggestion` > `Question`). Subagent scales map: `Critical` → `Blocker`, `High` → `High`, `Medium` / `Low` → `Suggestion`. Do not introduce `Critical` / `Medium` / `Low` into the merged Findings list.
- **Preserve `file:line` citations.**
- **Order by severity, not by scope.**
- **Note missing scopes** under Summary: `Scope incomplete: <scope> review did not complete`.
- **Merge Next Steps** - combine Core + subagent steps; preserve `[Implement]` / `[Delegate]`; dedupe items mapping to the same fix; re-sort by severity.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write the assembled review to the report file before ending; print confirmation.

## Feedback Labels

| Label          | Meaning                                     |
| -------------- | ------------------------------------------- |
| `[Blocker]`    | Must fix before merge - correctness or risk |
| `[High]`       | Should fix - significant impact or smell    |
| `[Suggestion]` | Would improve - non-blocking                |
| `[Question]`   | Need clarity from author                    |

No `[Nitpick]` or `[Praise]`.

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

- Issue: [name the .NET idiom: `async void`, `.Result` blocking, EF Core N+1, `FromSqlRaw` interpolation, mass assignment via `[FromBody] DomainEntity`, missing `[Authorize]`, Singleton capturing Scoped, missing `CancellationToken`, swallowed exception, dispatch inside transaction, hardcoded JWT key, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete .NET change with C# example]

### [High] file:line
- Issue:
- Impact:
- Fix:

### [Suggestion] file:line
- Improvement:

### [Question] file:line
- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on]

_Use [Question] only when the change is genuinely ambiguous. Not a softer Blocker._

## Architecture Notes
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes
- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized, each tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit if no actionable findings._
```

Omit empty sections.

## Rules

- Review the whole change as a system impact, not file-by-file
- Lead with risk before line-level findings
- Apply .NET conventions (Framework Design Guidelines, ASP.NET Core, Roslyn analyzers) over generic backend ones
- Provide actionable feedback with C# examples
- No nitpicking on style where `dotnet format` / EditorConfig applies
- Default to Core scope; auto-escalate on signals; honor `core-only`
- Delegate perf / security / observability depth to dedicated .NET subagents

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed as .NET / ASP.NET Core; data-access / mediator / messaging recorded
- [ ] `review-precondition-check` ran (or handle received); `base_ref` / `head_ref` / `current_branch` / `head_matches_current` captured. If `--base` was passed, `base_source: explicit-override`
- [ ] Diff and commit log read once and reused (and shared with subagents) - no mid-review re-issuing
- [ ] For `pr-ref` mode, user-run fetch surfaced; local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval obtained
- [ ] Scope auto-escalation evaluated; promotion (or `core-only`) recorded with firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Risk level and blast radius stated before findings
- [ ] Phase B .NET correctness applied: async/cancellation, exception handling, EF Core data access, transactions, DI lifetime, validation/authz, no domain entity in API, no mass assignment, idempotency, JWT key sourcing, migration safety, concurrency
- [ ] Phase C architecture applied: layering, no `DbContext` in Application, MediatR pipeline order, repository placement, constructor injection, typed config, multi-tenant, middleware order, central `IExceptionHandler`
- [ ] Phase D via `complexity-review` + `dotnet-overengineering-review`; remaining .NET AI smells covered
- [ ] Phase E maintainability applied
- [ ] Missing tests raised as a named finding (not in Takeaways); wrong-store tests flagged when present
- [ ] Every Blocker cites system risk
- [ ] Every finding has label, `file:line`, actionable .NET fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged out-of-scope
- [ ] For non-Core scopes, .NET subagents ran in parallel with pre-resolved diff handle + stack detection
- [ ] Subagent findings merged with dedup + highest-severity-wins; raw subagent reports not appended
- [ ] Failed/missing subagent scope noted under Summary
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Blocker > High > Suggestion (omit if none)
- [ ] Review report written via `review-report-writer`; confirmation printed

## Avoid

- Running `git fetch`, `git checkout`, or state-changing git from this workflow
- Reviewing without reading full diff + commit log first
- Generic backend conventions when a .NET idiom exists (say "register the repository interface in `Application/Interfaces` and implement in `Infrastructure`", not "use dependency inversion")
- Nitpicking style where `dotnet format` applies; no `[Nitpick]` or `[Praise]`
- Vague feedback without a concrete .NET fix
- Blocking on personal preference
- Running perf / security / observability when user passed `core-only`
- Treating auto-escalation signals as advisory - default is to promote; user opts out via `core-only`
- Duplicating subagent depth checks here
- Sequential subagent runs when they could be parallel
- Appending raw subagent reports instead of merging into one severity-ordered list
- Approving `async void` outside event handlers, `.Result` / `.Wait()` / `.GetAwaiter().GetResult()`, `[FromBody] DomainEntity`, `FromSqlRaw($"...")`, hardcoded JWT keys, `UseAuthorization` before `UseAuthentication`, or `UseLazyLoadingProxies()`
