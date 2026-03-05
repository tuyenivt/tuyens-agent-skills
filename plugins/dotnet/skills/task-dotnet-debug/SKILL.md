---
name: task-dotnet-debug
description: Developer-level debugging workflow for .NET 8 / ASP.NET Core. Paste a stack trace, exception, or describe unexpected behaviour. Analyses root cause in your codebase, suggests a fix with code, and explains why it happened.
metadata:
  category: backend
  tags: [dotnet, aspnet-core, debugging, stack-trace, error-analysis, workflow]
  type: workflow
---

# Debug .NET Issue

## When to Use

- Diagnosing a .NET exception, stack trace, or unexpected runtime behaviour
- Identifying root cause of failing tests or integration errors
- Analysing EF Core query issues, migration failures, or startup errors
- Investigating ASP.NET Core middleware or dependency injection problems

## Not for

- Production incident postmortems (use `task-incident-root-cause`)
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

````markdown
## Root Cause

[1-3 sentence explanation]

## Fix

**Before:**

```csharp
// problematic code
```
````

**After:**

```csharp
// fixed code
```

## Why This Works

[1-2 sentence explanation of the fix]

## Verification

1. [step to confirm fix]
2. [optional: test to add]

## Prevention

[one guardrail to prevent recurrence]

```

## Success Criteria

A well-executed debug session passes all of these. Use as a self-check before presenting the fix.

### Completeness

- [ ] Error is classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line - not just the exception type
- [ ] A concrete before/after code fix is provided - no vague suggestions
- [ ] Verification steps tell the developer exactly how to confirm the fix works

### Correctness

- [ ] The fix addresses the root cause, not the symptom
- [ ] The fix is minimal - it doesn't rewrite unrelated code
- [ ] Framework-specific skills are referenced when the fix involves a known pattern (EF Core, async, auth)
- [ ] One concrete prevention guardrail is included

### Staff-Level Signal

- [ ] The "why" is explained - a developer reading this understands how to avoid this class of error
- [ ] Async fixes are context-specific - `.ConfigureAwait(false)` is not applied as a blanket solution
- [ ] Production incident concerns are not mixed in - this is developer debugging, not blast radius analysis

## Avoid

- Proposing a fix without reading the relevant code in the codebase
- Suggesting broad rewrites when a targeted fix suffices
- Adding defensive null checks everywhere - identify the actual null source
- Recommending `.ConfigureAwait(false)` as a blanket fix without understanding the context
```
