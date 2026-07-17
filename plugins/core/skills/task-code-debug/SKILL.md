---
name: task-code-debug
description: Debug entry point for broken or crashing code: classify, locate, root-cause, fix, prevent. Detects stack and dispatches debug workflow.
metadata:
  category: code
  tags: [debug, troubleshooting, root-cause, multi-stack, router]
  type: workflow
user-invocable: true
---

# Code Debug (Router)

Detects the project stack and delegates to the matching stack-specific debug workflow. Falls back to a generic protocol for unknown stacks.

## When to Use

- Stack trace, exception, error log, test failure, or build error
- Unexpected behavior that used to work

**Not for:** understanding working code (`task-code-explain`), production incidents (`task-oncall-start`), performance without a concrete error (`task-code-review-perf`).

## Inputs

The error itself: stack trace, error message, log lines, test output, or reproduction steps. If the user gives only "it's broken" with no signal, ask for the error before guessing.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to          |
| -------------------- | -------------------- |
| Java / Spring Boot   | `task-spring-debug`  |
| Kotlin / Spring Boot | `task-kotlin-debug`  |
| Python               | `task-python-debug`  |
| Ruby / Rails         | `task-rails-debug`   |
| Node.js / TypeScript | `task-node-debug`    |
| Go / Gin             | `task-go-debug`      |

On match: delegate, forwarding the original error report and the `stack-detect` result. Stop; skip Step 4.

If the matched workflow's plugin is not installed, tell the user and recommend installing it, then run Step 4.

### Step 4 - Generic Fallback (unknown stack or missing plugin)

**Classify** the error class with confidence (HIGH / MEDIUM / LOW):

| Class                 | Signals                                                                |
| --------------------- | ---------------------------------------------------------------------- |
| Null/missing value    | NullPointerException, AttributeError NoneType, undefined, nil deref    |
| Type mismatch         | ClassCastException, TypeError, assertion failed                        |
| Constraint violation  | UniqueViolation, IntegrityError, FK, NOT NULL                          |
| Connection failure    | Connection refused, timeout, pool exhausted, host unreachable          |
| Auth / permission     | 401, 403, token expired, permission denied                             |
| Config / env          | Missing env var, file not found, wrong path                            |
| Concurrency           | Data race, deadlock, stale read, lost update                           |
| Async / event loop    | Unhandled promise rejection, blocking call in async context            |
| Build / import        | Module not found, circular dependency, compilation error               |
| Logic / regression    | No error thrown but output is wrong; "it worked before"                |
| Rendering / hydration | Hydration mismatch, white screen, SSR/CSR divergence                   |
| State / reactivity    | Stale state, infinite re-render, reactivity lost                       |
| Chunk loading         | Chunk failed, dynamic import error                                     |

For intermittent errors, hypothesize the operational cause (load, deploy, GC) before reading code.

**Locate** the failing line:

1. Read stack trace top-down; first frame in application code is the starting point.
2. Open the file; read the failing function and its callers.
3. Trace the data path back to where the bad value originates.
4. Name the exact line and variable.

No stack trace (logs only, no local repro): locate by evidence instead - trace the logged message to the code that emits it, correlate timestamps with deploys/load/config changes, and name the evidence still missing.

**Root cause** - state **why**, not just what. Tie the symptom to the upstream condition that produces it. State confidence; if LOW, list what would raise it.

- Bad: "the value is null"
- Good: "the value is null because the query returns no rows when X is true, and the caller assumes a result always exists"

**Fix** - minimal before/after addressing the root cause. No refactoring. If multiple fixes exist, recommend one with tradeoffs. If root-cause confidence is LOW, output the diagnostic step that would confirm the cause instead of a code change.

**Prevent** - one concrete step: a test that would have caught this, a static check, a guard clause, or a monitoring signal.

## Output Format

When dispatched (Step 3): the stack workflow owns the output.

When fallback runs (Step 4):

```markdown
## Classification

**Error class:** [class]
**Confidence:** HIGH | MEDIUM | LOW

## Root Cause

**File:** [file:line]
**Why:** [causal chain]
**Confidence:** HIGH | MEDIUM | LOW
[If LOW: what would raise it]

## Fix

**Before:**
[code]

**After:**
[code]
[If confidence LOW: the confirming diagnostic instead of code]

## Prevention

- [One concrete step]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: stack matched -> dispatched with error report and stack-detect result, then stopped; plugin missing -> user told, fell through to Step 4
- [ ] Step 4: stack unmatched or plugin missing -> fallback produced Classify / Locate / Root Cause / Fix / Prevent
- [ ] Vague input was challenged, not guessed at

## Avoid

- Running Step 4 after a successful Step 3 dispatch
- Producing findings yourself when a stack workflow was dispatched
- Proposing a fix before stating the root cause
- Treating symptoms (adding a null check) instead of cause (why is it null)
- Treating the fallback as equivalent to a stack workflow - install the matching language plugin when one exists
