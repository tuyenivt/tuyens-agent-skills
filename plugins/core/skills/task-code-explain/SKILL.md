---
name: task-code-explain
description: Explain a file, function, class, or module: behavior, role in flow, invariants, gotchas, framework magic, what to check before modifying.
metadata:
  category: code
  tags: [explanation, code-understanding, onboarding, review, debugging, multi-stack]
  type: workflow
user-invocable: true
---

# Code Explain

Targeted explanation of an existing code unit so an engineer can modify it safely. Not a quality review, refactor, or code-generation skill.

## When to Use

- Picking up a ticket in unfamiliar code
- Debugging a module you did not write
- Preparing to modify or extend code you need to understand first

**Not for:** whole-codebase map (`task-onboard`), quality review (`task-code-review`), broken code (`task-code-debug`).

## Inputs

| Input         | Required | Notes                                                       |
| ------------- | -------- | ----------------------------------------------------------- |
| Code target   | Yes      | File path, symbol name, or pasted code                      |
| Depth         | No       | `quick`, `standard` (default), or `deep`                    |
| Caller intent | No       | What the caller is trying to do; shapes emphasis            |

Infer depth from intent: onboarding -> `deep`; debug triage -> `quick`; trivial self-contained unit (short pure function, no external calls) -> `quick`.

Pasted code absent from the repo: skip repo lookups (inbound callers, tests) and record them under Confidence Gaps instead.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack and Load Stack Atomic

Use skill: `stack-detect`.

If the detected stack has an atomic below, load it; it injects stack-specific signals into Flow Context, Non-Obvious Behavior, Key Invariants, and Change Impact (e.g., Spring stereotype, Rails filter chain, React stale closures). If the stack is unknown or has no atomic, produce a universal explanation from the steps below - framework magic still belongs in the output, sourced from general knowledge.

| Stack                | Atomic                  |
| -------------------- | ----------------------- |
| Java / Spring Boot   | `spring-code-explain`   |
| Kotlin / Spring Boot | `kotlin-code-explain`   |
| Python               | `python-code-explain`   |
| Ruby / Rails         | `rails-code-explain`    |
| Node.js / TypeScript | `node-code-explain`     |
| Go / Gin             | `go-code-explain`       |
| Rust / Axum          | `rust-code-explain`     |
| .NET / ASP.NET Core  | `dotnet-code-explain`   |
| PHP / Laravel        | `laravel-code-explain`  |
| React                | `react-code-explain`    |
| Vue                  | `vue-code-explain`      |
| Angular              | `angular-code-explain`  |

Read the target code fully before producing any explanation.

### Step 3 - Purpose (all depths)

Two to four sentences: what it does from the caller's perspective, what responsibility it owns, and what it explicitly does NOT do.

### Step 4 - Flow Context (standard, deep)

- **Triggered by:** HTTP route, event, scheduled job, lifecycle hook, parent render. Trace upstream until a recognizable entry point.
- **Runs before / after this:** upstream that prepares state; downstream that consumes output or side effects.
- **Frequency:** hot path, background, edge case.
- **Inbound callers:** grep the symbol name. Cite concrete `file:line`. If callers cannot be enumerated (DI, dynamic dispatch, framework auto-wiring), record under Confidence Gaps.

### Step 5 - Why It Exists (standard, deep)

Domain reason (what business problem) and technical reason (what constraint forced this shape). If inferable only, mark under Confidence Gaps.

### Step 6 - Structure and Data Flow (standard, deep)

Entry points, key branches, external calls (DB/cache/queue/HTTP), return values, side effects. For complex flows, trace one representative path end-to-end.

Use skill: `architecture-guardrail` to spot layer-boundary violations. Fold any finding into Non-Obvious Behavior or Change Impact as a gotcha or check - do not emit its findings report.

### Step 7 - Non-Obvious Behavior (standard, deep)

Surface what will surprise a careful reader. Universal categories:

| Type                | Examples                                                              |
| ------------------- | --------------------------------------------------------------------- |
| Silent failures     | Returns null/empty instead of throwing; swallowed exceptions          |
| Hidden state        | Behavior changes with DB flags, feature toggles, request context      |
| Ordering            | Method A must precede B; init order matters                           |
| Thread safety       | Not thread-safe; requires external synchronization                    |
| Mutability          | Mutates input; returns shared mutable reference                       |
| Implicit retries    | Internal retry amplifies downstream load                              |
| Async traps         | Blocking in async context; unhandled rejection; fire-and-forget       |
| Lazy / caching      | Deferred computation; cached result; cache not invalidated on writes  |
| Framework magic     | Lifecycle injection, implicit invocation, convention-based wiring     |

Use skill: `architecture-concurrency` if concurrency gotchas are present. Fold its issues into this table as gotchas phrased as checks, not fixes.

### Step 8 - Key Invariants (standard, deep)

Assumptions NOT enforced by types or compiler. Format:

> **Invariant:** [statement]
> **If violated:** [what breaks]

### Step 9 - Change Impact Preview (standard, deep)

Frame as checks, not edits:

- **Logic change:** which callers from Step 4 to re-verify; which tests likely cover this path
- **Signature / return shape:** call sites to update; serialization or API boundary affected
- **Side effects:** DB tables, events, caches, logs, metrics affected
- **Timing / ordering:** async jobs, retries, sequenced operations at risk
- **Remove / rename:** features or flows that depend on it
- **Tests:** existing test files that exercise this code; coverage gaps

### Step 10 - Confidence Gaps (standard, deep)

State where the explanation is inferred rather than verified, and what specific check would confirm it.

### Step 11 - Design Intent (deep only)

Pattern in use and why; alternatives traded off; constraints that shaped the design (performance, backward compat, framework); what would force a redesign.

Use skill: `complexity-review` to judge whether complexity is essential or accidental.

## Output Format

### Quick depth

```markdown
## [Target]

**What it does:** [2-4 sentences]

**Key gotchas:**
- [Gotcha 1]
- [Gotcha 2]
```

### Standard depth (default)

```markdown
## [Target]

**What it does:** [2-4 sentences]
**Scope boundary:** [what it does NOT handle]
**Stack:** [language / framework, or "unknown"]

### Flow Context
- **Triggered by:** [route / event / job / hook / parent]
- **Runs before / after:** [upstream] / [downstream]
- **Frequency:** [hot path / background / edge]
- **Inbound callers:**
  - `path/to/file.ext:LINE` - [context]

### Why It Exists
[domain and/or technical reason]

### Data Flow
[entry points, branches, external calls, return/side effects]

### Non-Obvious Behavior
| Behavior | Detail |
| -------- | ------ |
| [Type]   | [What and when] |

### Key Invariants
- **Invariant:** [statement] - **If violated:** [consequence]

### Change Impact Preview
- **Logic:** re-verify [`caller.ext:LINE`]; run [test file]
- **Signature:** update [call sites]; affects [boundary]
- **Side effects:** affects [DB / event / cache / log]
- **Timing:** may break [async / retry / sequence]
- **Remove / rename:** depended on by [feature]
- **Tests:** [existing files], [coverage gaps]

### Confidence Gaps
- [Where inferred; how to confirm]
```

### Deep depth

Standard, plus:

```markdown
### Design Intent
[pattern, tradeoffs, constraints]

### Complexity Assessment
[essential vs accidental; what could be simplified without loss]
```

## Output Constraints

- Omit sections with nothing to say
- Match depth to request - do not over-explain at `quick`
- No code review findings, refactoring suggestions, or generated code

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran; stack atomic loaded if available and its signals injected into the four target sections; code read before explaining
- [ ] Step 3: Purpose from caller's perspective with scope boundary
- [ ] Step 4: Flow Context populated; inbound callers grepped or marked in Gaps
- [ ] Step 5: Why It Exists stated or marked in Gaps
- [ ] Step 6: Data flow covers entry points, branches, external calls, side effects; guardrail findings folded in, not reported
- [ ] Step 7: Non-obvious behavior flagged; concurrency issues folded in as checks
- [ ] Step 8: Invariants named with violation consequence
- [ ] Step 9: Change Impact lists concrete checks tied to real callers
- [ ] Step 10: Confidence Gaps present wherever inferred
- [ ] Step 11 (deep only): Design Intent and Complexity Assessment

## Avoid

- Reviewing for quality or suggesting refactors - list checks, not edits
- Explaining from signatures or names without reading the body
- Listing callers as "find in IDE" - grep and cite `file:line`
- Asserting a business reason unsupported by code, comments, or context
- Generic descriptions ("this is a service layer") without specifics
- Burying gotchas in prose where they get missed
