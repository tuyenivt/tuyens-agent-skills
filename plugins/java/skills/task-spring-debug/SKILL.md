---
name: task-spring-debug
description: Developer-level debugging workflow. Paste a stack trace, error log, or describe unexpected behavior. Analyzes the error, identifies root cause in your codebase, suggests a fix with code, and explains why it happened. For developer debugging, not production incident analysis (use task-root-cause for incidents).
metadata:
  category: backend
  tags: [debug, stack-trace, error, fix, troubleshooting]
  type: workflow
---

# Debug — Developer Debugging Workflow

## Purpose

Daily developer debugging: paste an error, get a fix. This is not incident response — it's "here's a stack trace, help me fix it" work.

- **Understand the error** — classify it before jumping to code
- **Trace through your codebase** — follow the call chain to the actual bug
- **Explain why, not just what** — root cause understanding prevents repeat bugs
- **Minimal fix** — smallest correct change, aligned with project patterns

For production incident analysis with containment and blast radius assessment, use `task-root-cause` instead.

## When to Use

- Java exception or stack trace you need help understanding
- Unexpected HTTP error response from your API
- Test failure you can't figure out
- Build or compilation error
- Spring Boot startup failure
- Behavior that doesn't match expectations (no error, but wrong result)

## Inputs

| Input                       | Required | Description                                       |
| --------------------------- | -------- | ------------------------------------------------- |
| Stack trace or error        | Yes      | The primary failure signal                        |
| Relevant source file        | No       | File where the error occurs (if known)            |
| Steps to reproduce          | No       | What triggers the error                           |
| Expected vs actual behavior | No       | For logic bugs without exceptions                 |
| Test output                 | No       | Full test failure output including assertion diff |

## Rules

- Always classify the error before reading code
- Show the exact code change needed — no vague suggestions
- Explain WHY the error happened, not just how to fix it
- Prefer minimal fixes over refactors — fix the bug, don't redesign
- If confidence is LOW, say so and state what additional info would help
- Do not suggest unrelated improvements or style changes
- Reference atomic skills only when the fix involves a pattern they cover

## Workflow

### Step 1 — Intake

Accept one or more of:

- Stack trace (Java exception)
- Application log snippet
- HTTP error response
- Description of unexpected behavior
- Test failure output

If the input is ambiguous, ask one clarifying question before proceeding.

### Step 2 — Classify the Error

Identify the error category to guide investigation:

**Compilation error** → syntax or type issue, check imports and type signatures

**Runtime exception** → identify exception type and likely cause:

| Exception                         | Likely Cause                         | Load Skill                              |
| --------------------------------- | ------------------------------------ | --------------------------------------- |
| `NullPointerException`            | Null reference in call chain         | —                                       |
| `LazyInitializationException`     | JPA session/transaction scope issue  | Use skill: `spring-jpa-performance`     |
| `DataIntegrityViolationException` | DB constraint violation              | Use skill: `spring-db-migration-safety` |
| `HttpMessageNotReadableException` | JSON deserialization failure         | —                                       |
| `TransactionSystemException`      | Nested exception in `@Transactional` | Use skill: `spring-transaction`         |
| `NoSuchBeanDefinitionException`   | Spring context wiring issue          | —                                       |
| Virtual Thread pinning            | `synchronized` block in VT context   | —                                       |

**Test failure** → analyze assertion mismatch, check test setup and mocks

**Build failure** → Gradle configuration or dependency issue → Use skill: `java-gradle-build-optimization`

### Step 3 — Locate in Codebase

1. Read the stack trace to identify the **source file and line number**
2. Open the file and surrounding context (~50 lines above and below)
3. Trace the call chain from entry point: **controller → service → repository**
4. Identify which layer the bug is in (Controller | Service | Repository | Configuration | Build)

### Step 4 — Root Cause Analysis

- Explain **WHY** this error occurred, not just what happened
- Reference the **specific code** that causes the issue
- If it's a pattern violation (not just a one-off bug), name the pattern
- Rate confidence:
  - **HIGH** — certain, evidence is clear
  - **MEDIUM** — likely, but alternative causes exist
  - **LOW** — need more info to confirm

### Step 5 — Propose Fix

- Show the **exact code change** needed (before → after)
- If multiple fixes are possible, rank by:
  1. Correctness — does it actually fix the bug?
  2. Minimal change surface — smallest diff that's correct
  3. Alignment with project patterns — follows existing conventions
- Explain any trade-offs between alternatives

### Step 6 — Prevent Recurrence

- Suggest a **test that would have caught this bug**
- If it's a pattern violation, reference the relevant atomic skill
- If the same bug could exist elsewhere, identify other occurrences (grep for similar patterns)

## Output

````markdown
## 🐛 Bug Analysis

**Error**: {exception type or error description}
**Confidence**: HIGH | MEDIUM | LOW
**Layer**: Controller | Service | Repository | Configuration | Build

## 📍 Root Cause

{explanation of why this happened, referencing specific code}

## 🔧 Fix

**Before:**

```java
// the problematic code
```
````

**After:**

```java
// the corrected code
```

{explanation of why this change fixes the issue}

## 🛡️ Prevention

**Test to add:**

```java
// test that would catch this bug
```

**Pattern to follow:** {reference to atomic skill or convention if applicable}

**Other occurrences:** {grep results for similar patterns, or "None found"}

```

### Output Constraints

- Keep the analysis focused — one bug, one fix
- Omit Prevention section if the fix is trivial (e.g., typo, missing import)
- If confidence is LOW, add a **Needs Clarification** section listing what info would help
- No code style commentary unrelated to the bug
- No suggestions for unrelated improvements

## Avoid

- Generic debugging advice ("add more logging", "set a breakpoint")
- Fixing symptoms instead of root causes
- Suggesting refactors when a targeted fix suffices
- Analysis without reading the actual source code
- Proposing fixes that violate domain constraints (e.g., adding `synchronized`, using `@Autowired`)
- Mixing incident response concerns into developer debugging

## Key Skills Reference

**Error-Specific Skills:**

- Use skill: `spring-jpa-performance` for LazyInitializationException and N+1 query issues
- Use skill: `spring-transaction` for transaction scope and propagation errors
- Use skill: `spring-db-migration-safety` for constraint violation and migration issues
- Use skill: `spring-exception-handling` for error handling and propagation patterns
- Use skill: `java-gradle-build-optimization` for build and dependency errors

> For stack-agnostic debugging workflows, use the core plugin's `task-root-cause`.
```
