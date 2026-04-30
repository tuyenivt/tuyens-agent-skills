---
name: task-dotnet-debug
description: Developer-level debugging workflow for .NET 8 / ASP.NET Core. Paste a stack trace, exception, or describe unexpected behaviour to get root cause analysis with a minimal before/after fix. Not for production incidents (use /task-oncall-start) or performance profiling without a concrete error (use task-code-perf-review).
metadata:
  category: backend
  tags: [dotnet, aspnet-core, debugging, stack-trace, error-analysis, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Debug .NET Issue

## When to Use

- Diagnosing a .NET exception, stack trace, or unexpected runtime behaviour
- Identifying root cause of failing tests or integration errors
- Analysing EF Core query issues, migration failures, or startup errors
- Investigating ASP.NET Core middleware or dependency injection problems

## Not for

- Production incident postmortems (use `/task-oncall-start`)
- Performance profiling without a concrete symptom (use `task-code-perf-review`)

## Implementation

### Step 1 - Collect Input

Ask the user for (if not already provided):

- The **full stack trace** or error message
- The **.NET version** and ASP.NET Core version
- **What they were doing** when the error occurred (endpoint hit, startup, migration, test run)
- **Any recent changes** before the issue appeared

Do not guess root cause without at least a stack trace or concrete error description.

### Step 2 - Classify the Error

Identify the error category:

| Category                | Indicators                                                                    |
| ----------------------- | ----------------------------------------------------------------------------- |
| **DI / Startup**        | `InvalidOperationException`, `Unable to resolve service`, startup crash       |
| **EF Core / Database**  | `DbUpdateException`, migration errors, `NullReferenceException` on navigation |
| **Null Reference**      | `NullReferenceException`, `ArgumentNullException`                             |
| **Async / Deadlock**    | `.Result`/`.Wait()` in call stack, `TaskCanceledException`, thread starvation |
| **Validation**          | `ValidationException`, 400 responses, FluentValidation failures               |
| **Auth / Middleware**   | 401/403 responses, missing claims, middleware ordering issues                 |
| **Test Failure**        | xUnit assertion failures, Testcontainers startup errors                       |
| **Concurrency**         | `DbUpdateConcurrencyException`, optimistic locking failures, race conditions  |
| **Build / Compilation** | `CS` error codes, nullable warnings, missing package references               |

### Step 3 - Locate Root Cause

Read the relevant files in the codebase to confirm the root cause:

- Identify the **exact line** in the stack trace that originates from user code (not framework internals)
- Read the relevant class / method
- Check DI registration (`Program.cs`, extension methods) for DI errors
- Check EF Core configuration and migrations for database errors
- Check middleware ordering for auth/pipeline errors

State the root cause clearly before proposing a fix.

### Step 4 - Propose Fix

Provide:

1. **Root cause explanation** - why the error occurs (1-3 sentences)
2. **Code fix** - minimal, targeted change with before/after diff
3. **Verification steps** - how to confirm the fix works

For EF Core issues, use skill: `dotnet-ef-performance`
For transaction/save errors, use skill: `dotnet-transaction`
For DI/startup issues, check service lifetime mismatches (singleton capturing scoped)
For async issues, use skill: `dotnet-async-patterns`
For auth issues, use skill: `dotnet-security-patterns`

### Step 5 - Prevent Recurrence

Suggest one concrete guardrail to prevent the same class of error:

- Missing null check → enable `<Nullable>enable</Nullable>` globally
- Blocking async code → add a Roslyn analyser (`AsyncFixer`, `VS Threading Analyzers`)
- DI lifetime mismatch → add a test that validates the DI container on startup
- Migration failure → add migration tests with Testcontainers to CI

## Output Format

```markdown
## Root Cause

[1-3 sentence explanation referencing specific file and line]

## Fix

**Before:**
`[file path]`
// problematic code

**After:**
`[file path]`
// fixed code

## Why This Works

[1-2 sentence explanation of the fix]

## Verification

1. [step to confirm fix]
2. [optional: test to add]

## Prevention

[one guardrail to prevent recurrence]
```

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line - not just the exception type
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Async fixes are context-specific - `.ConfigureAwait(false)` not applied as a blanket solution
- [ ] One concrete prevention guardrail included; verification steps tell developer how to confirm the fix
- [ ] For EF Core issues, `dotnet-ef-performance` patterns applied; for async issues, `dotnet-async-patterns` consulted

## Avoid

- Proposing a fix without reading the relevant code in the codebase
- Suggesting broad rewrites when a targeted fix suffices
- Adding defensive null checks everywhere - identify the actual null source
- Recommending `.ConfigureAwait(false)` as a blanket fix without understanding the context
- Blaming the framework when the root cause is in user code
