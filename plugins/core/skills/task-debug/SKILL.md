---
name: task-debug
description: Universal debugging workflow. Paste a stack trace, error log, test failure, or describe unexpected behavior. Detects stack and delegates to the stack-specific debug workflow, or runs a systematic classify-locate-fix protocol for any stack.
metadata:
  category: backend
  tags: [debug, troubleshooting, root-cause, stack-agnostic]
  type: workflow
user-invocable: true
---

# Debug

Universal entry point for debugging errors. Detects the project stack and delegates to the matching stack-specific debug workflow. For unknown stacks, runs the systematic protocol below.

## Inputs

Paste any of the following - the more context, the better:

- Stack trace or error message
- Relevant log lines around the error
- Test failure output
- Description of unexpected behavior ("it used to work, now X happens")

## Steps

### Step 1 - Detect Stack

Use skill: stack-detect

### Step 2 - Delegate to Stack Workflow

| Detected Stack              | Delegate to         |
| --------------------------- | ------------------- |
| Java / Spring Boot          | `task-spring-debug` |
| Kotlin / Spring Boot        | `task-kotlin-debug` |
| .NET / ASP.NET Core         | `task-dotnet-debug` |
| Python / FastAPI or Django  | `task-python-debug` |
| Ruby / Rails                | `task-rails-debug`  |
| Node.js / NestJS or Express | `task-node-debug`   |
| Go / Gin                    | `task-go-debug`     |

If the detected stack does not match any of the above, continue with the systematic protocol below.

### Step 3 - Systematic Protocol (Any Stack)

#### CLASSIFY

Identify the error class before reading any code:

| Class                | Signals                                                                                             |
| -------------------- | --------------------------------------------------------------------------------------------------- |
| Null/missing value   | NullPointerException, AttributeError NoneType, Cannot read properties of undefined, nil dereference |
| Type mismatch        | ClassCastException, TypeError, type assertion failed                                                |
| Constraint violation | UniqueViolation, IntegrityError, foreign key constraint, NOT NULL violation                         |
| Connection failure   | Connection refused, timeout, pool exhausted, host unreachable                                       |
| Auth / permission    | 401, 403, token expired, permission denied                                                          |
| Config / env         | Missing environment variable, file not found, wrong path                                            |
| Concurrency          | Data race, deadlock, stale read, lost update                                                        |
| Async / event loop   | Unhandled promise rejection, blocking call in async context, event loop blocked                     |
| Build / import       | Module not found, circular dependency, missing dependency, compilation error                        |
| Logic / regression   | No error thrown but output is wrong; "it worked before"                                             |

State the class and confidence (HIGH / MEDIUM / LOW) before proceeding.

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
- A monitoring/alerting signal (if the root cause is operational)
- A "what changed recently?" checklist item if the cause is a regression

## Success Criteria

A well-executed debug session passes all of these. Use as a self-check before presenting the fix.

### Completeness

- [ ] Stack detected and stack-specific workflow invoked, OR systematic protocol applied with explanation
- [ ] Error is classified before any code is read or fix proposed
- [ ] Root cause references the specific file and line
- [ ] A concrete before/after fix is provided - no vague suggestions
- [ ] A prevention step is included

### Correctness

- [ ] The fix addresses the root cause, not the symptom
- [ ] Confidence level is stated - LOW confidence lists what additional info would help
- [ ] The fix is minimal - no unrelated changes
- [ ] Framework/language idioms are preserved in the fix

### Staff-Level Signal

- [ ] The "why" is explained - a developer understands how to avoid this class of bug
- [ ] For concurrency bugs, the fix includes the synchronization or isolation mechanism, not just the symptom
- [ ] For connection/pool issues, configuration is checked alongside the immediate error
- [ ] For regressions, "what changed recently?" is asked if no other root cause is identified
