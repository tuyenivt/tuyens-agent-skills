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

.NET-aware staff-level PR review. Correctness, architecture, AI-quality, maintainability via Phase A-E. Coordinates .NET perf / security / observability subagents in parallel. Stack-specific delegate of `task-code-review` for .NET / ASP.NET Core; **runs standalone** with full PR/branch resolution.

## When to Use

- Reviewing a .NET / ASP.NET Core PR before merge
- Post-AI-generation quality gate
- Architecture drift detection in a Clean Architecture codebase

Not for: pre-implementation design (`task-dotnet-implement`), incident triage (`/task-oncall-start`), single-error debugging (`task-dotnet-debug`), single-scope reviews (delegate directly to `task-dotnet-review-perf` / `-security` / `-observability`).

## Depth Levels

| Depth      | When                                                                | What Runs                                                   |
| ---------- | ------------------------------------------------------------------- | ----------------------------------------------------------- |
| `quick`    | "Is this safe to merge?" - fast risk snapshot                       | Risk snapshot + top 3 findings (Phases A + B summary)       |
| `standard` | Default                                                             | Phases A-E                                                  |
| `deep`     | Architectural PRs, post-incident review, Principal sign-off         | Phases A-E + historical pattern matching + cross-PR context |

Default: `standard`. **Auto-promote to `deep`** when Phase A computes Blast Radius `Wide` or `Critical` and the user did not pass `quick`. Surface in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E only                                                            |
| + Perf          | Core + parallel subagent: `task-dotnet-review-perf`                        |
| + Security      | Core + parallel subagent: `task-dotnet-review-security`                    |
| + Observability | Core + parallel subagent: `task-dotnet-review-observability`               |
| Full            | Core + all three .NET subagents in parallel                                |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals:**

- `IFormFile`, `AddAuthentication` / `AddAuthorization` / policy changes, `[FromBody]` DTO changes, `FromSqlRaw` / `FromSqlInterpolated`, secrets in `appsettings*.json`, background workers consuming user input, `JsonSerializer.Deserialize<DomainEntity>`, `Process.Start` with user input, `unsafe` blocks -> **+Security**
- New EF Core migration, new `IQueryable` materialization, new `Include` / `ThenInclude`, new pagination, new payload endpoints, loops calling DB or HTTP, new `IMemoryCache` / `IDistributedCache`, new `Task.WhenAll` fan-out -> **+Perf**
- New project / assembly, new external client, new `BackgroundService` / MassTransit consumer / Hangfire job, `Program.cs` / Serilog config change, new `Meter` / `Counter`, lifecycle / graceful-shutdown changes -> **+Observability**
- Two or more signal categories -> **Full**

## Invocation

| Invocation                     | Meaning                                                                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-dotnet-review`          | Current branch vs base; fails fast on trunk (`main`/`master`/`develop`)                                                                                       |
| `/task-dotnet-review <branch>` | `<branch>` vs base (3-dot diff)                                                                                                                               |
| `/task-dotnet-review pr-<N>`   | PR head fetched into local branch `pr-<N>` (user runs `git fetch origin pull/<N>/head:pr-<N>`; see `review-precondition-check` for GitLab/Bitbucket variants) |

No checkout required. Stay on your current branch; workflow reads via ref-qualified diffs. **Explicit base override:** pass `--base <branch>` when PR was opened against a non-trunk base. Flags compose: `/task-dotnet-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent dispatcher. If not .NET / ASP.NET Core, stop and route to `/task-code-review`.

Record `Runtime`, `Framework` (ASP.NET Core <version>), `Data Access` (EF Core | Dapper | mixed), `Mediator` (MediatR | none), `Messaging` (MassTransit | Hangfire | Channel | none).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` (forward `--base` if passed). If it stops with a fail-fast message, surface it verbatim and stop.

Once approved, read once and reuse:

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

Skip when a parent dispatcher passed the handle plus pre-read artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan file list and diff for the auto-escalation signals above. Log `signal: <category> -> <file:line>` for each.

- Zero signals or `core-only` -> Core
- One signal category -> matching extra scope
- Two or more -> Full
- User-passed explicit scope -> respect; still record signals so Summary documents what was deferred

Surface decision in Summary. Escalated: `auto-escalated from Core; signals: <list>`. User-pinned with conflicting signals: `Scope user-pinned to Core; +Security signals present: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure-propagation scope
- Output risk level and blast radius before findings

**Low-risk short-circuit:** Risk `Low` + Blast Radius `Narrow` AND the change does not touch architecture-relevant files (auth middleware, JWT validation, `Program.cs` wiring, MediatR pipeline behaviors, `DbContext` / `IEntityTypeConfiguration`, EF Core migrations) -> skip Phases C-D; emit Phase B findings only.

Blast Radius `Wide` or `Critical` AND user did not pass `quick` -> auto-promote depth to `deep` here, before Phases B-E.

### Phase B - .NET Correctness and Safety

Apply atomics; this phase adds review-level synthesis on top.

- Use skill: `dotnet-async-patterns` (async/await, `CancellationToken`, `BackgroundService`, `Task.WhenAll` fan-out)
- Use skill: `dotnet-exception-handling` (no swallowed catches, central `IExceptionHandler`)
- Use skill: `dotnet-ef-performance` (`FromSqlRaw` interpolation, N+1, `AsNoTracking`, lazy loading)
- Use skill: `dotnet-transaction` (single `SaveChangesAsync` per use case, async tx boundary, post-commit dispatch)
- Use skill: `dotnet-messaging-patterns` (outbox / idempotency for MassTransit, Hangfire)
- Use skill: `dotnet-security-patterns` (authn/authz, secrets sourcing, OWASP)
- Use skill: `dotnet-db-migration-safety` for any change under `Migrations/`
- Use skill: `ops-backward-compatibility` for migrations and contract changes

**Review-level findings (raise as named entries, not buried in takeaways):**

- **Missing tests.** PR adds/modifies logic without xUnit / `WebApplicationFactory` / Testcontainers coverage. Default `[Suggestion]`; escalate to `[High]` for critical paths (JWT / custom auth, `IAuthorizationHandler` / ownership checks, money / billing, multi-step transactions / state machines, `BackgroundService` / MassTransit / Hangfire that mutate data, migrations changing column semantics).
- **Wrong-store tests.** `UseInMemoryDatabase("...")` (or SQLite) when `.csproj` references Postgres / SQL Server provider is `[High]` - in-memory skips FK enforcement, raw SQL, transactions, JSONB/array ops, concurrent updates.
- **Domain entity in API response.** `Ok(entity)` leaks every property and triggers lazy-loaded navigations. Map to a response DTO record; audit DTO for `PasswordHash`, `MfaSecret`, `ApiKey`, `IsAdmin`, `DeletedAt`, `LastLoginIp`; prefer separate DTO over `[JsonIgnore]` on the entity.
- **Mass assignment.** `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)` -> request DTO record with explicit FluentValidation rules.
- **HTTP `Idempotency-Key`** on retry-prone POSTs (`/payments`, `/orders`, `/refunds`) via `request_idempotency` table keyed by `(tenant_id, idempotency_key)` storing request hash + cached response. Distinct from worker-side message dedup - a system needs both.
- **Hardcoded JWT signing key** (`new SymmetricSecurityKey(Encoding.UTF8.GetBytes("literal"))` or string-literal `IssuerSigningKey` in `Program.cs`) is `[Blocker]`. Stays in Core so `core-only` reviews still catch it.
- **`db.Database.Migrate()` on startup** is `[High]` on multi-replica deployments (replicas race). Use `dotnet ef database update` as a deploy step.

**Concurrency safety:** shared mutable global state (`static Dictionary<...>` mutated by handlers); race-prone updates done in-process instead of with DB-level locking (`SELECT ... FOR UPDATE`, `[ConcurrencyCheck]` / `[Timestamp] byte[] RowVersion`); `Monitor.Enter` across `await` (use `SemaphoreSlim.WaitAsync(ct)`).

### Phase C - .NET Architecture Guardrails (Clean Architecture)

Use skill: `architecture-guardrail` for layer violations, new coupling, circular dependencies, bypassed abstractions.

- [ ] **Layering** - `Domain` <- `Application` <- `Infrastructure` <- `Api`. Domain references only primitives. No `DbContext` / `HttpClient` / Polly in Application. Infrastructure does not depend on Api.
- [ ] **No `DbContext` in Application** - use repository interfaces in `Application/Interfaces`, EF Core impl in `Infrastructure/Persistence/Repositories`.
- [ ] **No EF entities in API responses** - DTO records at the boundary.
- [ ] **MediatR pipeline order** - `Logging` -> `Validation` -> `Authorization` -> `Transaction` (single `SaveChangesAsync` per request, commit on success, rollback on exception). Order is load-bearing.
- [ ] **Constructor injection only** - no `IServiceProvider.GetRequiredService<T>()` in handlers; no `new` on dependencies. Optional config via `IOptions<T>` / `IOptionsMonitor<T>`.
- [ ] **Typed config** - `services.Configure<JwtOptions>(...)` + `IOptions<JwtOptions>`. No `IConfiguration` injected into handlers. Secrets via env / Key Vault / `user-secrets`.
- [ ] **Multi-tenant isolation** at EF Core query level (global query filters) or repository layer, not the controller alone.
- [ ] **Middleware order in `Program.cs`** - `UseExceptionHandler` -> `UseHsts` -> `UseHttpsRedirection` -> `UseRouting` -> `UseCors` -> `UseAuthentication` -> `UseAuthorization` -> `MapControllers`. **`UseAuthorization` before `UseAuthentication` is `[Blocker]`** - framework default falls through and every `[Authorize]` endpoint silently allows all requests.
- [ ] **Controllers thin** - one per aggregate root with `[Route("api/v1/[controller]")]`; extract -> invoke handler -> map -> return.
- [ ] **Central `IExceptionHandler`** maps domain exceptions to Problem Details.

**Multi-service PRs:** API contract compatibility (OpenAPI diff via `Swashbuckle`, Pact); deployment order documented or independent. Use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity and over-engineering. Use skill: `dotnet-overengineering-review` for redundancy vs EF Core / DB / NRT, defensive guards, premature abstraction (single-impl interfaces, MediatR for trivial reads, AutoMapper, speculative `IOptions<T>`).

Additional review-level signals:

- **Redundant mapping layers** - `Entity -> InternalDto -> ServiceDto -> ResponseDto` when one would suffice.
- **Test verbosity** - Bogus / NSubstitute setup > 30 lines for a single assertion; `result.Should().BeEquivalentTo(fullObject)` when key fields would do.
- **`Task.Run` misapplication** - `await Task.Run(() => syncMethod())` does the same work on a thread-pool thread.
- **Hot-path string allocations** - `string.Format` / `+` / `string.Join` in tight loops where `StringBuilder` / `string.Create` / `Span<char>` fit.
- **`#pragma warning disable`** without `// reason: ...`.

### Phase E - .NET Maintainability

- [ ] **Naming** - types/methods/properties `PascalCase`; locals/parameters `camelCase`; private fields `_camelCase`; interfaces `IPascalCase`; async methods suffixed `Async`. No stutter (`Order.OrderId` -> `Order.Id`).
- [ ] **Magic numbers / strings** - `private static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(5);` over inline literals.
- [ ] **Method length** - > 30 lines reviewed; > 60 flagged unless clearly orchestrating named helpers.
- [ ] **Duplicated query logic** - same `Where` predicate in 3+ places -> repository method or specification.
- [ ] **Nullable reference types enabled** (`<Nullable>enable</Nullable>`); `!` (null-forgiving) requires a justification comment.
- [ ] **`record` for DTOs / value objects** over mutable class with public setters.
- [ ] **`dotnet format` clean / EditorConfig respected**; `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` in CI.
- [ ] **XML doc on public APIs**; `[ProducesResponseType]` on controller actions for OpenAPI.

Use skill: `backend-coding-standards` for cross-language conventions. Use skill: `ops-observability` for cross-cutting logging / metrics presence.

### Step 5 - Delegate Extra Scopes in Parallel

If scope is Core only, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread.

| Scope                | Subagents                                                                                                                    |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | `task-dotnet-review-perf`                                                                                                    |
| Core + Security      | `task-dotnet-review-security`                                                                                                |
| Core + Observability | `task-dotnet-review-observability`                                                                                           |
| Full                 | All three in parallel                                                                                                        |

**Subagent prompt contract:**

- Resolved review target (`base_ref`, `head_ref`) + already-read diff and commit log; subagent skips `review-precondition-check` and `git diff`
- Depth level
- Pre-confirmed stack and detected data-access / mediator / messaging
- Instruction to return findings via its own Output Format

**Failure isolation:** subagent fails / times out -> continue; note the missing scope in synthesized output.

### Step 6 - Synthesize

(Skip if Step 5 didn't run.) Merge subagent findings into one Output Format - do not append raw reports.

- **Deduplicate cross-cutting findings** - one entry citing all scopes.
- **Severity wins** when labels differ (`Blocker` > `High` > `Suggestion` > `Question`). Subagent scales map: `Critical` -> `Blocker`, `High` -> `High`, `Medium` / `Low` -> `Suggestion`. No `Critical` / `Medium` / `Low` in merged Findings.
- **Preserve `file:line`** citations.
- **Order by severity, not by scope.**
- **Note missing scopes** under Summary: `Scope incomplete: <scope> review did not complete`.
- **Merge Next Steps** - dedupe items mapping to the same fix; re-sort by severity; preserve `[Implement]` / `[Delegate]`.

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

- Issue: [name the .NET idiom: `async void`, `.Result` blocking, EF Core N+1, `FromSqlRaw` interpolation, mass assignment via `[FromBody] DomainEntity`, missing `[Authorize]`, Singleton capturing Scoped, missing `CancellationToken`, swallowed exception, dispatch inside transaction, hardcoded JWT key, `UseAuthorization` before `UseAuthentication`]
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

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed as .NET / ASP.NET Core; data access / mediator / messaging recorded
- [ ] Step 3 - `review-precondition-check` ran (or handle received); `base_ref` / `head_ref` / `current_branch` / `head_matches_current` captured; if `--base` was passed, `base_source: explicit-override`; diff and commit log read once; when `head_matches_current` was false, explicit user approval obtained
- [ ] Step 4 - scope auto-escalation evaluated; promotion (or `core-only`) recorded with firing signals
- [ ] Phase A - risk and blast radius stated before findings; depth auto-promoted when Blast Radius is Wide/Critical and not `quick`
- [ ] Phase B - atomics (`dotnet-async-patterns`, `dotnet-exception-handling`, `dotnet-ef-performance`, `dotnet-transaction`, `dotnet-messaging-patterns`, `dotnet-security-patterns`, `dotnet-db-migration-safety`) applied; review-level findings raised as named entries (missing tests, wrong-store, entity-in-response, mass assignment, idempotency, hardcoded JWT key, `db.Database.Migrate()` on startup)
- [ ] Phase C - layering, no `DbContext` in Application, MediatR pipeline order, repository placement, constructor injection, typed config, multi-tenant, middleware order, central `IExceptionHandler`
- [ ] Phase D - `complexity-review` + `dotnet-overengineering-review` applied; remaining .NET AI smells covered
- [ ] Phase E - maintainability applied
- [ ] Every Blocker cites system risk; every finding has label, `file:line`, actionable .NET fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged out-of-scope
- [ ] Step 5 - for non-Core scopes, .NET subagents ran in parallel with pre-resolved diff handle + stack detection
- [ ] Step 6 - subagent findings merged with dedup + highest-severity-wins; raw reports not appended; failed/missing scope noted under Summary
- [ ] Step 7 - review report written via `review-report-writer`; confirmation printed
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Blocker > High > Suggestion (omit if none)

## Avoid

- Running `git fetch`, `git checkout`, or state-changing git from this workflow
- Reviewing without reading full diff + commit log first
- Generic backend conventions when a .NET idiom exists (say "register the repository interface in `Application/Interfaces`", not "use dependency inversion")
- Nitpicking style where `dotnet format` applies; no `[Nitpick]` or `[Praise]`
- Vague feedback without a concrete .NET fix
- Blocking on personal preference
- Running perf / security / observability when user passed `core-only`
- Treating auto-escalation signals as advisory (default is to promote; user opts out via `core-only`)
- Duplicating subagent depth checks here
- Sequential subagent runs when they could be parallel
- Appending raw subagent reports instead of merging into one severity-ordered list
