---
name: task-dotnet-debug
description: Debug .NET 8 / ASP.NET Core exceptions, stack traces, EF Core, DI, async, and silent-data bugs to root cause with minimal fix.
metadata:
  category: backend
  tags: [dotnet, aspnet-core, debugging, stack-trace, error-analysis, workflow]
  type: workflow
user-invocable: true
---

# Debug .NET Issue

## When to Use

- A .NET exception, stack trace, or unexpected runtime behaviour with a concrete symptom
- Failing tests, EF Core query / migration errors, startup crashes, middleware / DI / auth pipeline issues
- Silent-data bugs (field is `null` / `default` with no exception)

Not for: production incident postmortems (`/task-oncall-start`), performance work without a symptom (`task-code-review-perf`).

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect` to confirm .NET / ASP.NET Core / EF Core versions and adapt diagnosis (e.g., .NET 8 nullable defaults, EF Core 8 `ExecuteUpdate` semantics).

### Step 3 - Collect Input

Require before diagnosis:

- Full stack trace, or for silent bugs: expected vs actual value at a named boundary
- Trigger (endpoint, startup, migration, test) and most recent change

Do not guess without a stack trace or reproducible symptom.

**Silent / wrong-data intake.** No exception almost always means the bug is at a serialization or mapping boundary, not in business logic. Walk these before reading service code:

| Boundary | Failure mode |
| --- | --- |
| `System.Text.Json` | Case-sensitive by default; `[JsonPropertyName]` mismatch or `JsonNamingPolicy` skew silently drops |
| Unknown JSON members | Ignored by default; set `[JsonUnmappedMemberHandling(Disallow)]` on critical records |
| `Newtonsoft.Json` | `MissingMemberHandling = Ignore` by default; set `Error` on critical paths |
| DTO -> entity mapping | New field stays `default` when constructor / mapper not updated; AutoMapper hides this. Prefer positional `record` |
| EF Core column / shadow | `[Column]` name mismatch or `[NotMapped]` / shadow yields `default(T)`. `LogTo(Information)` and compare SELECT to schema |
| Background-job payload | MassTransit / Hangfire record-shape skew between producer and consumer lands as `default` |
| `record` `with` | Carries forward defaults from `original`; inspect the construction of `original`, not the `with` site |

Instrument `LogDebug("{@Payload}", req)` on both sides of the boundary and add a round-trip test so the silent drop becomes a test failure.

### Step 4 - Classify and Locate

Pick one category and apply the named atomic skill if listed.

| Category | Indicators | Atomic skill |
| --- | --- | --- |
| DI / Startup | `Unable to resolve service`, captive scoped, startup crash | - |
| Serialization / Mapping | No exception; wrong / `default` value at a boundary (resolved via Step 3 table) | - |
| EF Core / Database | `DbUpdateException` (constraint violation -> map to 4xx, not 500), migration error, `NullReference` on navigation; query/N+1 -> `dotnet-ef-performance` | `dotnet-ef-performance` (perf only) |
| Transactions / SaveChanges | Partial writes, cross-aggregate atomicity | `dotnet-transaction` |
| Async / Deadlock | `.Result` / `.Wait()` in stack, `TaskCanceledException` | `dotnet-async-patterns` |
| Null Reference | `NullReferenceException`, `ArgumentNullException` | - |
| Validation | `ValidationException`, 400 responses | - |
| Auth / Middleware | 401/403, missing claims, middleware order | `dotnet-security-patterns` |
| Concurrency | `DbUpdateConcurrencyException`, race | - |
| Build / Compilation | `CS` codes, nullable warnings | - |

Read code to confirm: first stack-trace frame in user code; the relevant class / method; the category surface (DI registration in `Program.cs`, `OnModelCreating`, middleware order). State the root cause in one sentence with `file:line` before proposing a fix.

### Step 5 - Propose Fix and Prevention

Fix must be minimal and target root cause, not symptom. Add exactly one guardrail:

| Root cause class | Guardrail |
| --- | --- |
| Missing null check | `<Nullable>enable</Nullable>` project-wide |
| Blocking async | `AsyncFixer` / VS Threading Analyzers |
| DI lifetime mismatch | `ValidateOnBuild = true` + `ValidateScopes = true` |
| Migration failure | Testcontainers migration test in CI |
| Unmapped DB constraint (500) | Translate `DbUpdateException` -> Problem Details in the central handler |
| Silent boundary drop | Round-trip serialization / mapping test |

## Output Format

```markdown
## Root Cause

[1-3 sentences, naming file:line and category from Step 4]

## Fix

**Before:** `[file path]`
// problematic code

**After:** `[file path]`
// fixed code

## Why This Works

[1-2 sentences]

## Verification

1. [step to confirm fix]
2. [optional: test to add]

## Prevention

[one guardrail from Step 5 table]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack and versions confirmed via `stack-detect`
- [ ] Step 3: stack trace or reproducible symptom collected; silent-data table consulted when no exception
- [ ] Step 4: category chosen; root cause stated with file:line; matching atomic skill applied where listed
- [ ] Step 5: minimal before/after fix + verification + one guardrail in Output Format

## Avoid

- Proposing a fix without reading the relevant code
- Broad rewrites when a targeted fix suffices
- Blanket null checks instead of identifying the null source
- Adding downstream guards that hide a boundary bug
- `.ConfigureAwait(false)` as a blanket prescription without context
- Blaming the framework when the root cause is in user code
