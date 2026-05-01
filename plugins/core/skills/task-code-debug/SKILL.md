---
name: task-code-debug
description: Universal debugging workflow for broken or crashing code. Paste a stack trace, exception, error log, test failure, build error, or describe unexpected behavior. Detects your stack and routes to the stack-specific debug workflow.
metadata:
  category: code
  tags: [debug, troubleshooting, root-cause, stack-agnostic]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the affected feature, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, classify the bug as one of: (a) **spec violation** - code disagrees with an acceptance criterion or NFR; fix the code; (b) **spec gap** - the buggy behavior is undefined by the spec; surface as a proposed amendment to `spec.md` rather than guessing intent; (c) **out-of-scope drift** - code path executes behavior the spec excludes; remove or gate the path. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Debug

Universal entry point for debugging errors. Detects the project stack and delegates to the matching stack-specific debug workflow. For unknown stacks, runs the systematic protocol below.

## When to Use

- Broken or crashing code with a stack trace, exception, or error log
- Test failures or build errors
- Unexpected behavior that used to work correctly
- Runtime errors with a reproducible (or intermittent) trigger

**Not for:** Understanding working code (use `task-code-explain`), production incidents with service degradation (use `/task-oncall-start`), performance analysis without a concrete error (use `task-code-perf-review`).

## Inputs

Paste any of the following - the more context, the better:

- Stack trace or error message
- Relevant log lines around the error
- Test failure output
- Description of unexpected behavior ("it used to work, now X happens")

**Insufficient input handling:** If the user provides only a vague description (e.g., "it's broken") with no error message, stack trace, or reproduction steps, ask for the specific error output before proceeding. Do not guess at the problem.

## Steps

### Step 1 - Detect Stack

Use skill: stack-detect

### Step 2 - Delegate to Stack Workflow

**Backend stacks:**

| Detected Stack              | Delegate to          |
| --------------------------- | -------------------- |
| Java / Spring Boot          | `task-spring-debug`  |
| Kotlin / Spring Boot        | `task-kotlin-debug`  |
| .NET / ASP.NET Core         | `task-dotnet-debug`  |
| Python / FastAPI or Django  | `task-python-debug`  |
| Ruby / Rails                | `task-rails-debug`   |
| Node.js / NestJS or Express | `task-node-debug`    |
| Go / Gin                    | `task-go-debug`      |
| Rust / Axum                 | `task-rust-debug`    |
| PHP / Laravel               | `task-laravel-debug` |

**Frontend stacks:**

| Detected Stack         | Delegate to          |
| ---------------------- | -------------------- |
| React / Next.js / Vite | `task-react-debug`   |
| Vue / Nuxt / Vite      | `task-vue-debug`     |
| Angular                | `task-angular-debug` |

If the detected stack does not match any of the above, continue with the systematic protocol below.

### Step 3 - Systematic Protocol (Any Stack)

#### CLASSIFY

Identify the error class before reading any code:

| Class                  | Signals                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Null/missing value     | NullPointerException, AttributeError NoneType, Cannot read properties of undefined, nil dereference                |
| Type mismatch          | ClassCastException, TypeError, type assertion failed                                                               |
| Constraint violation   | UniqueViolation, IntegrityError, foreign key constraint, NOT NULL violation                                        |
| Connection failure     | Connection refused, timeout, pool exhausted, host unreachable                                                      |
| Auth / permission      | 401, 403, token expired, permission denied                                                                         |
| Config / env           | Missing environment variable, file not found, wrong path                                                           |
| Concurrency            | Data race, deadlock, stale read, lost update                                                                       |
| Async / event loop     | Unhandled promise rejection, blocking call in async context, event loop blocked                                    |
| Build / import         | Module not found, circular dependency, missing dependency, compilation error                                       |
| Logic / regression     | No error thrown but output is wrong; "it worked before"                                                            |
| Rendering / hydration  | Hydration mismatch, white screen, component not rendering, SSR/CSR content divergence, blank page after navigation |
| State / reactivity     | Stale state, infinite re-render loop, reactivity lost, computed not updating, state not reflecting in UI           |
| Bundle / chunk loading | Chunk loading failed, dynamic import error, tree-shaking removed needed code, HMR not applying                     |

State the class and confidence (HIGH / MEDIUM / LOW) before proceeding.

**Pattern analysis (for intermittent or non-deterministic errors):**
If the error does not reproduce on every request, analyze the pattern before reading code:

1. Frequency: what percentage of requests fail?
2. Timing: does it correlate with peak load, time of day, or specific operations?
3. Correlation: do failures correlate with high connection pool usage, memory pressure, GC pauses, or recent deployments?
4. State the hypothesized operational cause (connection exhaustion, race condition, cache eviction, timeout) before proceeding to LOCATE. This hypothesis guides where to look in code.

#### LOCATE

1. Read the full stack trace top-to-bottom. The **first frame in application code** (not framework internals) is the starting point.
2. Open that source file. Read the failing function and its callers.
3. Trace the data path: where does the bad value or state originate?
4. Identify the exact line and variable responsible.

#### ROOT CAUSE

State **why** this happened - not just what happened. Examples of root cause depth:

- Not: "the value is null" → Yes: "the value is null because the query returns no rows when X condition is true, and the caller assumes a result always exists"
- Not: "connection refused" → Yes: "connection refused because the DB_HOST env var defaults to localhost but the service runs in Docker where the DB is on a different network"

State confidence level. If LOW, list what additional information (logs, config, code) would raise confidence.

#### FIX

Provide a minimal before/after code change that addresses the root cause.

- Change only what is necessary - no refactoring, no style changes
- If the fix requires a config or environment change, state it explicitly
- If multiple fixes are possible, state the tradeoffs and recommend one

#### PREVENT

State one concrete prevention step:

- A test that would have caught this (unit, integration, or property-based)
- A static analysis rule, linter, or type annotation
- A guard clause, assertion, or input validation
- A monitoring/alerting signal (if the root cause is operational)
- A defensive coding pattern (null check, default value, timeout)
- A "what changed recently?" checklist item if the cause is a regression

## Output Format

```markdown
## Classification

**Error class:** [class from table above]
**Confidence:** HIGH | MEDIUM | LOW

## Root Cause

**File:** [file:line]
**Why:** [root cause explanation with full causal chain]
**Confidence:** HIGH | MEDIUM | LOW
[If LOW: what additional information would raise confidence]

## Fix

**Before:**
[code snippet showing the problematic code]

**After:**
[code snippet showing the minimal fix]

[If config/env change needed, state explicitly]
[If multiple fixes possible, state tradeoffs and recommend one]

## Prevention

- [One concrete prevention step with specifics]
```

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific file and line; confidence level stated
- [ ] Concrete before/after fix provided - no vague suggestions
- [ ] Fix is minimal and addresses root cause, not symptom; idioms preserved
- [ ] Prevention step included (test, lint rule, or monitoring signal)
- [ ] The "why" is explained; concurrency/connection/regression specifics addressed where relevant

## Avoid

- Proposing a fix before understanding the root cause
- Refactoring or cleaning up code alongside the fix - change only what is necessary
- Guessing at the problem when the user provides insufficient context - ask for more details
- Treating symptoms instead of root cause (e.g., adding a null check without understanding why the value is null)
- Providing multiple fix options without a clear recommendation
