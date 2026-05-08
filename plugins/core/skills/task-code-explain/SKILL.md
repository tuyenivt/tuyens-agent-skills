---
name: task-code-explain
description: Explain a single file, function, class, or module - what it does, where it sits in the flow, why it exists, non-obvious gotchas, key invariants, and what to double-check before modifying it. Detects stack and composes a stack-specific atomic for framework-magic, lifecycle, and gotchas. Falls back to universal explanation for unknown stacks.
metadata:
  category: code
  tags: [explanation, code-understanding, onboarding, review, debugging, multi-stack]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Code Explain

## Purpose

Targeted code explanation for a specific file, function, class, or module:

- **What it does** - the observable behavior from the caller's perspective
- **Where it sits in the flow** - what triggers it, what runs before and after
- **Why it exists** - the business or technical reason this code is here
- **Non-obvious gotchas** - behavior that will surprise an engineer unfamiliar with this code
- **Key invariants** - assumptions the code depends on that are not enforced by the type system
- **Change impact preview** - what the engineer must double-check before modifying

This skill explains existing code so an engineer picking up a ticket can modify it safely. It does not review the code for quality, suggest refactoring, or generate new code.

## When to Use

- Understanding unfamiliar code during a review or while picking up a ticket
- Debugging a module you did not write
- Preparing to modify or extend code you need to understand first
- Explaining code to a teammate or in documentation

## Not For

- Mapping a whole codebase or large subsystem - use `task-onboard` (architecture, conventions, hotspots)
- Code quality review - use `task-code-review`
- Broken or crashing code - use `task-code-debug`

## Inputs

| Input             | Required | Description                                                               |
| ----------------- | -------- | ------------------------------------------------------------------------- |
| Code target       | Yes      | File path, function name, class name, or pasted code block                |
| Explanation depth | No       | `quick`, `standard` (default), or `deep`                                  |
| Caller context    | No       | What the caller is trying to do (shapes what to emphasize)                |
| Known confusion   | No       | Specific aspect that is unclear (focus explanation there)                 |

Default depth: `standard`. Infer from caller context: onboarding -> `deep`; debugging triage -> `quick`.

## Workflow

### Step 1 - Detect Stack and Load Stack-Specific Atomic (when available)

Use skill: `stack-detect` to identify language, framework, and `Stack Type`.

If the detected stack matches the table below, load the corresponding atomic. The atomic injects stack-specific signals into the universal explanation produced by Steps 2-9 below. If the stack is unknown, skip this step and produce a universal explanation.

| Detected stack       | Load atomic              |
| -------------------- | ------------------------ |
| Java / Spring Boot   | `spring-code-explain`    |
| Kotlin / Spring Boot | `kotlin-code-explain`    |
| Python               | `python-code-explain`    |
| Ruby / Rails         | `rails-code-explain`     |
| Node.js / TypeScript | `node-code-explain`      |
| Go / Gin             | `go-code-explain`        |
| Rust / Axum          | `rust-code-explain`      |
| .NET / ASP.NET Core  | `dotnet-code-explain`    |
| PHP / Laravel        | `laravel-code-explain`   |
| React                | `react-code-explain`     |
| Vue                  | `vue-code-explain`       |
| Angular              | `angular-code-explain`   |

Read the target code fully before proceeding.

### Step 2 - Purpose Summary (all depths)

State in two to four sentences:

- What this code does from the perspective of its caller or user
- What problem it solves or what responsibility it owns
- What it explicitly does NOT do (scope boundary)

### Step 3 - Flow Context (standard and deep)

Reconstruct where this code sits in the larger story:

- **Triggered by:** HTTP route, event handler, scheduled job, CLI entry, framework lifecycle, parent component render. Trace upstream until you reach a recognizable entry point.
- **Runs before this:** upstream code that prepares state, validates, or authorizes.
- **Runs after this:** downstream code that consumes the output or side effects.
- **Frequency / criticality:** hot path, background job, edge case, one-time bootstrap.
- **Inbound callers (grep):** run a grep for the function/class/module name across the codebase. List concrete callers (file:line). If callers are in many places, summarize the shape.

When a stack-specific atomic was loaded, inject its **Flow Context** signals here (e.g., Spring stereotype, NestJS DI scope, FastAPI dependency tree, Rails filter chain).

If callers cannot be determined (dynamic dispatch, framework auto-wiring, external API entry), say so under Confidence Gaps.

### Step 4 - Why It Exists (standard and deep)

State the business or technical reason this code is here:

- **Domain reason:** what product or business problem this solves
- **Technical reason:** what architectural constraint forced this shape

If the reason is not inferable, mark under Confidence Gaps rather than guessing.

### Step 5 - Structure and Data Flow (standard and deep)

Explain how the code is organized internally:

- **Entry points:** public methods, event handlers, HTTP handlers, constructors
- **Data flow:** how data moves through the code; what transforms, validates, persists it
- **Key branches:** main conditional paths and what triggers each
- **External calls:** databases, caches, queues, HTTP, other services
- **Return values / side effects:** what the caller gets back; what state this changes

For complex flows, trace one representative path end-to-end.

Use skill: `architecture-guardrail` to identify whether the code respects expected layer boundaries.

### Step 6 - Non-Obvious Behavior and Gotchas (standard and deep)

Surface behavior that will surprise a developer who has not read the code carefully. Universal gotcha categories:

| Type                      | Examples                                                                                  |
| ------------------------- | ----------------------------------------------------------------------------------------- |
| Silent failures           | Returns null/empty instead of throwing; swallows exceptions                               |
| Hidden state dependencies | Behavior changes based on external state (DB flags, feature toggles, request context)     |
| Ordering requirements     | Method A must be called before method B; initialization order matters                     |
| Thread safety assumptions | Not thread-safe; requires external synchronization                                        |
| Mutability surprises      | Modifies the input parameter; returns a shared mutable reference                          |
| Implicit retries          | Retries internally; can amplify downstream load                                           |
| Async traps               | Blocking call inside async context; unhandled rejection paths; fire-and-forget effects    |
| Lazy evaluation           | Computation deferred; result differs by access timing                                     |
| Caching behavior          | Result cached; stale data may return; cache not invalidated on writes                     |
| Framework magic           | Behavior injected by framework lifecycle (handled by stack-specific atomic when loaded)   |

When a stack-specific atomic was loaded, inject its **Non-Obvious Behavior** signals here (Spring AOP self-invocation, Kotlin platform types, Python sync I/O blocking event loop, Rails callback events, React stale closures, etc.).

Use skill: `architecture-concurrency` if concurrency gotchas are present.

### Step 7 - Key Invariants (standard and deep)

State assumptions the code depends on that are NOT enforced by types or compiler:

- Preconditions the caller must satisfy
- Postconditions the caller can rely on
- Environmental assumptions (DB state, config values, init order)
- Data shape assumptions not captured in types

Format each as:

> **Invariant:** [statement]
> **If violated:** [what breaks]

When a stack-specific atomic was loaded, inject its **Key Invariants** signals here.

### Step 8 - Change Impact Preview (standard and deep)

Frame as checks to perform, not changes to make:

- **If you change the logic / behavior:** which callers from Step 3 must be re-verified, which tests likely cover this path
- **If you change the return shape or signature:** which call sites must be updated, which serialization or API boundary is affected
- **If you change the side effects:** which downstream consumers (DB tables written, events published, caches invalidated, logs/metrics emitted) are affected
- **If you change timing or ordering:** which async jobs, retries, or sequenced operations may break
- **If you remove or rename this:** which features or flows depend on it
- **Tests to run / add:** existing test files that exercise this code, gaps that should be covered

When a stack-specific atomic was loaded, inject its **Change Impact Preview** signals here.

### Step 9 - Confidence Gaps (standard and deep)

State explicitly where the explanation is inferred rather than verified:

- "Callers cannot be enumerated - invoked via reflection / DI auto-wiring / dynamic dispatch. Verify by [specific check]."
- "Likely part of the authentication flow based on naming and imports, but the entry point was not located. Confirm by tracing from `AuthController`."
- "Business reason inferred from method name; no comments or ticket reference found."

### Step 10 - Design Intent (deep only)

Explain why the code is structured this way - the design decisions embedded in the implementation:

- What pattern is being implemented and why (repository, strategy, decorator, etc.)
- What alternatives were likely considered and what this approach trades off
- What constraints shaped the design (performance, backward compatibility, framework requirements)
- What would need to change if a key assumption changed

Use skill: `complexity-review` to assess whether complexity is accidental or essential.

## Output Format

### Quick Depth

```markdown
## [Target Name]

**What it does:** [2-4 sentence summary]

**Key gotchas:**

- [Gotcha 1]
- [Gotcha 2]
```

### Standard Depth (default)

```markdown
## [Target Name]

**What it does:** [2-4 sentence summary]
**Scope boundary:** [What it explicitly does NOT handle]
**Stack:** [language / framework, or "unknown"]

### Flow Context

- **Triggered by:** [HTTP route / event / job / lifecycle hook / parent caller]
- **Runs before this:** [upstream]
- **Runs after this:** [downstream]
- **Frequency:** [hot path / background / edge case]
- **Inbound callers:**
  - `path/to/file.ext:LINE` - [brief caller context]

### Why It Exists

[2-3 sentences: domain reason and/or technical reason]

### Data Flow

[Entry points, key branches, external calls, return/side effects]

### Non-Obvious Behavior

| Behavior | Detail                  |
| -------- | ----------------------- |
| [Type]   | [What happens and when] |

### Key Invariants

- **Invariant:** [statement] - **If violated:** [consequence]

### Change Impact Preview

- **If you change the logic:** re-verify [`caller.ext:LINE`], run [test file]
- **If you change the return shape:** update [call sites], affects [API/serialization boundary]
- **If you change the side effects:** affects [DB table / event / cache / log]
- **If you change timing or ordering:** may break [async job / retry / sequence]
- **If you remove or rename this:** depended on by [feature / flow]
- **Tests to run / add:** [existing test files], [coverage gaps]

### Confidence Gaps

- [Where inferred rather than verified, and how to confirm]
```

### Deep Depth

Add to standard depth:

```markdown
### Design Intent

[Pattern used, trade-offs, constraints that shaped the design]

### Complexity Assessment

[Whether complexity is essential or accidental; what could be simplified without loss]
```

## Output Constraints

- No code review findings or refactoring suggestions unless explicitly asked
- No generated code
- Omit sections with nothing to say
- Match depth to requested level - do not over-explain for `quick`
- Omit obvious observations - high-signal content only

## Self-Check

- [ ] `behavioral-principles` loaded
- [ ] `stack-detect` ran; stack-specific atomic loaded if available; otherwise universal explanation
- [ ] Code was read before explaining - no explanation from names alone
- [ ] Purpose stated from the caller's perspective with scope boundary
- [ ] Flow Context populated; inbound callers grepped (or marked under Confidence Gaps)
- [ ] Stack-specific signals injected into Flow Context, Non-Obvious Behavior, Key Invariants, and Change Impact Preview when atomic was loaded
- [ ] Why It Exists stated, or marked under Confidence Gaps
- [ ] Data flow covers entry points, branches, external calls, side effects
- [ ] Non-obvious behavior explicitly flagged
- [ ] Key invariants named with violation consequence
- [ ] Change Impact Preview lists concrete checks tied to actual callers and side effects
- [ ] Confidence Gaps section present where any item was inferred
- [ ] Explanation specific to this code, not a generic description of the pattern

## Avoid

- Reviewing the code for quality or suggesting improvements (use `task-code-review`)
- Prescribing refactors in Change Impact ("prefer adding a new function instead") - list checks, not edits
- Explaining from function signatures or names without reading the implementation
- Listing inbound callers as "discoverable in IDE" - actually grep and cite file:line
- Stating a business reason that is not supported by the code, comments, or surrounding context
- Generic descriptions ("this is a service layer") without concrete specifics
- Burying gotchas in prose where they will be missed
- Generating new code or proposing refactoring
