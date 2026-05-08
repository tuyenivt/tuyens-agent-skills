---
name: task-code-debug
description: Universal debugging entry point for broken or crashing code. Detects the project stack and dispatches to the matching stack-specific debug workflow. For unknown stacks, runs a minimal generic CLASSIFY/LOCATE/ROOT-CAUSE/FIX/PREVENT protocol.
metadata:
  category: code
  tags: [debug, troubleshooting, root-cause, multi-stack, router]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the affected feature, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles` and propagate the spec context to the dispatched stack workflow.

# Code Debug (Router)

This skill is a thin dispatcher. It detects the project stack and delegates the workflow to the matching stack-specific skill (e.g., `task-spring-debug`, `task-rails-debug`, `task-react-debug`). The stack workflow names ecosystem-specific exception classes, runtime tooling, and gotchas directly.

For unknown stacks, this skill falls back to a minimal generic debug protocol so any project can still use the command.

## When to Use

- Broken or crashing code with a stack trace, exception, or error log
- Test failures or build errors
- Unexpected behavior that used to work correctly

**Not for:** Understanding working code (use `task-code-explain`), production incidents with service degradation (use `/task-oncall-start`), performance analysis without a concrete error (use `task-code-review-perf`).

## Inputs

Paste any of: stack trace, error message, relevant log lines, test failure output, or a description of unexpected behavior with reproduction steps.

If the user provides only a vague description ("it's broken") with no error output, ask for the specific error before proceeding. Do not guess.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect`.

### Step 2 - Dispatch to Stack Workflow

| Detected stack       | Delegate to          |
| -------------------- | -------------------- |
| Java / Spring Boot   | `task-spring-debug`  |
| Kotlin / Spring Boot | `task-kotlin-debug`  |
| Python               | `task-python-debug`  |
| Ruby / Rails         | `task-rails-debug`   |
| Node.js / TypeScript | `task-node-debug`    |
| Go / Gin             | `task-go-debug`      |
| Rust / Axum          | `task-rust-debug`    |
| .NET / ASP.NET Core  | `task-dotnet-debug`  |
| PHP / Laravel        | `task-laravel-debug` |
| React                | `task-react-debug`   |
| Vue                  | `task-vue-debug`     |
| Angular              | `task-angular-debug` |

If matched, delegate, propagate spec context, and stop. Do not run Step 3.

### Step 3 - Generic Fallback (unknown stack only)

Run only when Step 2 finds no match.

**CLASSIFY** the error class before reading code:

| Class                  | Signals                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Null/missing value     | NullPointerException, AttributeError NoneType, undefined property access, nil dereference                          |
| Type mismatch          | ClassCastException, TypeError, type assertion failed                                                               |
| Constraint violation   | UniqueViolation, IntegrityError, foreign key, NOT NULL                                                             |
| Connection failure     | Connection refused, timeout, pool exhausted, host unreachable                                                      |
| Auth / permission      | 401, 403, token expired, permission denied                                                                         |
| Config / env           | Missing environment variable, file not found, wrong path                                                           |
| Concurrency            | Data race, deadlock, stale read, lost update                                                                       |
| Async / event loop     | Unhandled promise rejection, blocking call in async context                                                        |
| Build / import         | Module not found, circular dependency, compilation error                                                           |
| Logic / regression     | No error thrown but output is wrong; "it worked before"                                                            |
| Rendering / hydration  | Hydration mismatch, white screen, SSR/CSR divergence                                                               |
| State / reactivity     | Stale state, infinite re-render, reactivity lost                                                                   |
| Bundle / chunk loading | Chunk loading failed, dynamic import error                                                                         |

State the class and confidence (HIGH / MEDIUM / LOW).

For intermittent errors, analyze frequency, timing correlation (peak load, deploys, GC), and hypothesize the operational cause before reading code.

**LOCATE** the failing line:

1. Read the stack trace top-to-bottom. The first frame in **application code** (not framework internals) is the starting point.
2. Open the source file. Read the failing function and its callers.
3. Trace the data path: where does the bad value or state originate?
4. Identify the exact line and variable responsible.

**ROOT CAUSE** - state **why**, not just what:

- Not "the value is null" - "the value is null because the query returns no rows when condition X is true, and the caller assumes a result always exists"
- Not "connection refused" - "DB_HOST defaults to localhost but the service runs in Docker where the DB is on a different network"

State confidence. If LOW, list what additional information would raise it.

**FIX** - minimal before/after change addressing the root cause. No refactoring. If multiple fixes are possible, recommend one with tradeoffs.

**PREVENT** - one concrete prevention step: a test that would have caught this, a static analysis rule, a guard clause, or a monitoring signal.

## Output Format

When dispatched (Step 2 matched): the stack-specific workflow owns the output.

When fallback runs (Step 3):

```markdown
## Classification

**Error class:** [class from table]
**Confidence:** HIGH | MEDIUM | LOW

## Root Cause

**File:** [file:line]
**Why:** [root cause with full causal chain]
**Confidence:** HIGH | MEDIUM | LOW
[If LOW: what additional information would raise confidence]

## Fix

**Before:**
[code snippet]

**After:**
[code snippet showing the minimal fix]

## Prevention

- [One concrete prevention step]
```

## Self-Check

- [ ] `behavioral-principles` loaded before any other step
- [ ] Spec-aware preamble loaded when `--spec` was passed or `.specs/<slug>/` exists
- [ ] `stack-detect` ran at Step 1
- [ ] If a stack matched, the dispatched workflow ran and Step 3 was skipped
- [ ] If no stack matched, Step 3 fallback produced CLASSIFY/ROOT CAUSE/FIX/PREVENT
- [ ] Insufficient input was challenged with a request for more detail, not guessed at

## Avoid

- Running both Step 2 dispatch and Step 3 fallback (one or the other, never both)
- Producing your own findings when a stack workflow was dispatched
- Proposing a fix before understanding the root cause
- Treating symptoms instead of root cause (adding a null check without explaining why the value is null)
- Treating the fallback as equivalent to a stack workflow - it is a temporary bridge for unsupported stacks; install the matching language plugin when one exists
