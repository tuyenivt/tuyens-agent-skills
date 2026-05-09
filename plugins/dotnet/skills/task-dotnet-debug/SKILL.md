---
name: task-dotnet-debug
description: ".NET 8 / ASP.NET Core debugging from a stack trace, exception, or unexpected behavior; root cause analysis with minimal before/after fix."
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
- Performance profiling without a concrete symptom (use `task-code-review-perf`)

## Implementation

### Step 1 - Collect Input

Ask the user for (if not already provided):

- The **full stack trace** or error message
- The **.NET version** and ASP.NET Core version
- **What they were doing** when the error occurred (endpoint hit, startup, migration, test run)
- **Any recent changes** before the issue appeared

Do not guess root cause without at least a stack trace or concrete error description.

**No-error / wrong-behavior intake.** When the user reports "no exception, just wrong data" (a field is `null` / `default` after deserialization, an EF Core write silently drops a column, a DTO->entity mapping returns the wrong shape, a background-job consumer reads a different value than was published), the bug is almost always at a serialization or mapping boundary, not in business logic. Trace these surfaces in order before reading service code:

1. **`System.Text.Json` rename mismatch**: `[JsonPropertyName("user_id")]` on the DTO does not match the producer's `userId` casing; or `JsonNamingPolicy.CamelCase` set on the consumer but not the producer (or vice versa). Default `System.Text.Json` is **case-sensitive** for property names - `userId` vs `UserId` silently misses unless `PropertyNameCaseInsensitive = true` is set
2. **Missing `JsonSerializerOptions.UnknownTypeHandling` / no `[JsonExtensionData]`**: by default `System.Text.Json` ignores unknown JSON properties. A producer-side rename (`amount` -> `total`) lands as a missing field on the consumer with no error - the property is just `default`. Make `UnmappedMemberHandling.Disallow` explicit on critical record types: `[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]` (.NET 8+) so unknown fields throw at deserialize time
3. **`Newtonsoft.Json` `MissingMemberHandling`**: legacy `Newtonsoft.Json` defaults to `Ignore` - producer-side renames silently drop. Set `MissingMemberHandling = MissingMemberHandling.Error` on critical paths
4. **DTO-to-domain mapping silent-drop**: `var order = new Order { Id = req.Id, Total = req.Total };` - if `Order` later grows a `TenantId` field but the constructor is not updated, `tenantId` from the request never reaches the domain. AutoMapper makes this worse: the unmapped target field stays at default, no error. `record` types with positional constructors fail at compile time when the shape changes; class-with-property-init does not - read the mapping site
5. **EF Core column-name mismatch**: `[Column("user_id")]` on the entity property does not match the actual DB column `userId` - EF Core sets the property to `default(T)` on read with no error when the column does not exist (it is a missing-column case, not a mismatch). With `Database.LogTo(...)` at `Information`, the SELECT shows the columns EF asked for; compare to the actual schema
6. **EF Core `[NotMapped]` / shadow property**: a property marked `[NotMapped]` is excluded from queries silently; a shadow property declared in `OnModelCreating` (`builder.Property<DateTime>("UpdatedAt")`) is not on the entity class - reads via the entity property return `default(T)`
7. **Background-job payload boundary**: `MassTransit` / `Hangfire` serializes the payload to bytes at publish; the consumer's `Consume(ConsumeContext<TMessage>)` deserializes. A version skew between the producer's record shape and the consumer's expected shape (added/renamed/removed property) produces a `default`-valued field on the consumer with no error. MassTransit has `Headers` for envelope correlation; the body schema is its own contract
8. **`record` `with` expression silent-drop**: `var updated = original with { Total = newTotal };` preserves all other fields - but if `original` was constructed with a default on a recently added property, `updated` carries that default forward. Check the construction path of `original`, not just the `with` site

Once the boundary is identified, propose `tracing::debug!` / `_logger.LogDebug("Decoded request: {@Request}", req)` at the boundary in / boundary out plus an assertion test that round-trips a representative payload through the boundary so the silent drop becomes a test failure. Do **not** propose adding null checks downstream - that hides the boundary bug as a "not found" instead of fixing the drop.

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
