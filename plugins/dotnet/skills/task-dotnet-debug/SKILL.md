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

- Diagnosing a .NET exception, stack trace, or unexpected runtime behaviour
- Failing tests, integration errors, EF Core query / migration failures, startup crashes
- ASP.NET Core middleware, DI, or auth pipeline problems
- Silent-data bugs (field is `null` / `default` with no exception)

Not for: production incident postmortems (`/task-oncall-start`); performance profiling without a concrete symptom (`task-code-review-perf`).

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect` to confirm .NET / ASP.NET Core / EF Core versions and adapt diagnosis (e.g., .NET 8 nullable defaults, EF Core 8 `ExecuteUpdate` semantics).

### Step 3 - Collect Input

Require, before diagnosis:

- Full stack trace or error message (or for silent bugs: expected vs actual value at a named boundary)
- .NET / ASP.NET Core version (from Step 2 or user)
- Trigger (endpoint, startup, migration, test) and recent change

Do not guess root cause without a stack trace or a reproducible symptom.

**Silent / wrong-data intake.** When there is no exception, the bug is almost always at a serialization or mapping boundary, not in business logic. Walk these surfaces in order before reading service code:

| Boundary | Failure mode |
| --- | --- |
| `System.Text.Json` | Case-sensitive by default; `[JsonPropertyName]` mismatch or producer/consumer `JsonNamingPolicy` skew silently drops |
| Unknown JSON members | `System.Text.Json` ignores by default; set `[JsonUnmappedMemberHandling(Disallow)]` (.NET 8+) on critical records |
| `Newtonsoft.Json` | `MissingMemberHandling = Ignore` by default; set `Error` on critical paths |
| DTO -> entity mapping | New target field stays `default` when constructor/mapper not updated; AutoMapper hides this. Prefer positional `record` (fails at compile) |
| EF Core column / shadow | `[Column]` name mismatch or `[NotMapped]` / shadow property yields `default(T)`. Enable `LogTo(Information)` and compare SELECT to schema |
| Background-job payload | MassTransit / Hangfire version skew between producer and consumer record shapes lands as `default` field |
| `record` `with` | Carries forward defaults from `original`; inspect the construction path of `original`, not the `with` site |

Fix: instrument `LogDebug("{@Payload}", req)` at boundary in/out and add a round-trip test through the boundary so the silent drop becomes a test failure. Do not add downstream null checks - they hide the boundary bug.

### Step 4 - Classify

| Category | Indicators |
| --- | --- |
| DI / Startup | `Unable to resolve service`, `Cannot consume scoped service ... from singleton`, startup crash |
| EF Core / Database | `DbUpdateException`, migration errors, `NullReference` on navigation |
| Null Reference | `NullReferenceException`, `ArgumentNullException` |
| Async / Deadlock | `.Result`/`.Wait()` in stack, `TaskCanceledException`, thread starvation |
| Validation | `ValidationException`, 400 responses, FluentValidation failures |
| Auth / Middleware | 401/403, missing claims, middleware ordering |
| Test Failure | xUnit assertion, Testcontainers startup |
| Concurrency | `DbUpdateConcurrencyException`, race conditions |
| Build / Compilation | `CS` codes, nullable warnings, missing references |

### Step 5 - Locate Root Cause

Read code to confirm:

- First stack-trace frame in user code (skip framework internals)
- The relevant class / method
- Category-specific surface: DI registration (`Program.cs`, extension methods) for DI; `OnModelCreating` and migrations for EF Core; middleware order for auth

Apply the matching atomic skill:

| Category | Skill |
| --- | --- |
| EF Core | `dotnet-ef-performance` |
| Transactions / SaveChanges | `dotnet-transaction` |
| Async / Task | `dotnet-async-patterns` |
| Auth / Identity | `dotnet-security-patterns` |

State the root cause in one sentence with file:line before proposing a fix.

### Step 6 - Propose Fix and Prevention

Output in the format below. Fix must be minimal and target the root cause, not the symptom. Include exactly one guardrail:

| Root cause class | Guardrail |
| --- | --- |
| Missing null check | Enable `<Nullable>enable</Nullable>` project-wide |
| Blocking async (`.Result`/`.Wait`) | Add `AsyncFixer` / `VS Threading Analyzers` |
| DI lifetime mismatch | `ValidateOnBuild = true` + `ValidateScopes = true` in test host |
| Migration failure | Testcontainers migration test in CI |
| Silent boundary drop | Round-trip serialization/mapping test |

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

[one guardrail from Step 6 table]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack and versions confirmed via `stack-detect`
- [ ] Step 3: stack trace or reproducible symptom collected; silent-data table consulted if no exception
- [ ] Step 4: error classified into one category from the table
- [ ] Step 5: root cause names file:line; matching atomic skill applied where listed
- [ ] Step 6: minimal before/after fix + verification + exactly one guardrail in Output Format

## Avoid

- Proposing a fix without reading the relevant code
- Broad rewrites when a targeted fix suffices
- Blanket null checks instead of identifying the null source
- `.ConfigureAwait(false)` as a blanket prescription without context
- Blaming the framework when the root cause is in user code
