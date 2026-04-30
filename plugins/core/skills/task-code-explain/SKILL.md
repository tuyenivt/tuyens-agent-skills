---
name: task-code-explain
description: Explain a single file, function, class, or module - what it does, where it sits in the flow, why it exists, non-obvious gotchas, key invariants, and what to double-check before modifying it. Use when reading inherited or unfamiliar code, picking up a ticket in unfamiliar territory, or preparing to modify code you didn't write.
metadata:
  category: code
  tags: [explanation, code-understanding, onboarding, review, debugging]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Code Explain

## Purpose

Targeted code explanation for a specific file, function, class, or module:

- **What it does** -- the observable behavior from the caller's perspective
- **Where it sits in the flow** -- what triggers it, what runs before and after, how it fits into the larger story
- **Why it exists** -- the business or technical reason this code is here
- **Non-obvious gotchas** -- behavior that will surprise a developer unfamiliar with this code
- **Key invariants** -- assumptions the code depends on that are not enforced by the type system
- **Change impact preview** -- what the engineer must double-check before modifying this code

This skill explains existing code so an engineer picking up a ticket can modify it safely. It does not review the code for quality, suggest refactoring, or generate new code.

## When to Use

- Understanding unfamiliar code during a code review
- Debugging a module you did not write
- Preparing to modify or extend a piece of code you need to understand first
- Explaining code to a teammate or in documentation

## Not For

- Mapping a whole codebase or large subsystem - use `task-onboard-codebase` for that (it covers architecture, patterns, tech debt hotspots, and conventions across the whole repo)
- Code quality review or suggesting improvements - use `task-code-review` for that
- Broken or crashing code diagnosis - use `task-debug` for that

## Inputs

| Input             | Required | Description                                                               |
| ----------------- | -------- | ------------------------------------------------------------------------- |
| Code target       | Yes      | File path, function name, class name, or pasted code block to explain     |
| Explanation depth | No       | `quick` (what it does), `standard` (default), or `deep` (design intent)   |
| Caller context    | No       | What the caller is trying to do with this code (shapes what to emphasize) |
| Known confusion   | No       | Specific aspect that is unclear (focus explanation there)                 |

Default depth: `standard`.

Infer depth from caller context when not explicit: onboarding or documentation context suggests `deep`; quick question or debugging triage suggests `quick`.

Handle partial inputs gracefully. If only a file path is given, read the file and determine scope.

## Rules

- Read the code before explaining it - never explain from names or signatures alone
- State what the code does from the caller's perspective first, before internal detail
- Surface non-obvious behavior explicitly - do not bury it in prose
- Distinguish between what the code does and why it is written that way (intent vs mechanism)
- Flag invariants that are not type-enforced - these are the gotchas that cause bugs
- If the code is part of a larger system, name what it depends on and what depends on it
- Omit obvious detail - do not explain language syntax or common patterns that any engineer knows
- Keep explanation proportional to depth requested - `quick` is one paragraph, `deep` is full analysis

## Explanation Model

### Step 1 - Stack and Context Detection

Use skill: `stack-detect` to identify the language, framework, and `Stack Type`. This shapes:

- Naming convention interpretation
- Framework lifecycle awareness (e.g., Spring beans, Rails callbacks, NestJS decorators, React hooks, Vue composables, Angular signals, Laravel service providers / middleware / Eloquent observers)
- Common patterns the code may be implementing (middleware, interceptors, repository pattern, component composition, state management, data fetching hooks)

Read the target code fully before proceeding.

### Step 2 - Purpose Summary (all depths)

State in two to four sentences:

- What this code does from the perspective of its caller or user
- What problem it solves or what responsibility it owns
- What it explicitly does NOT do (scope boundary)

Example framing:

> "This class is the entry point for all payment processing. It validates the payment request, delegates to the appropriate payment provider, and persists the result. It does not handle refunds - those go through `RefundService`."

### Step 3 - Flow Context (standard and deep)

Reconstruct where this code sits in the larger story. The engineer needs to know what they are interfering with.

- **Triggered by**: What initiates execution? (HTTP route, event handler, scheduled job, CLI entry, framework lifecycle, parent component render). Trace upstream until you reach a recognizable entry point.
- **Runs before this**: What upstream code prepares state, validates, or authorizes before control reaches here?
- **Runs after this**: What downstream code consumes the output or side effects?
- **Frequency / criticality**: Hot path (every request), background job, edge case, one-time bootstrap? Affects blast radius of changes.
- **Inbound callers (grep)**: Run a grep for the function/class/module name across the codebase. List concrete callers (file:line). If callers are in many places, summarize the shape (e.g., "called from 8 controllers in `payments/`").

If callers cannot be determined from the codebase (dynamic dispatch, framework auto-wiring, external API entry), say so explicitly under Confidence Gaps below.

### Step 4 - Why It Exists (standard and deep)

State the business or technical reason this code is here, in two to three sentences. Distinguish:

- **Domain reason**: What product or business problem this solves (e.g., "deduplicates webhook deliveries because Stripe retries on timeout").
- **Technical reason**: What architectural constraint forced this shape (e.g., "extracted from controller because three endpoints share validation").

If the reason is not inferable from the code, comments, or surrounding context, mark it under Confidence Gaps rather than guessing.

### Step 5 - Structure and Data Flow (standard and deep)

Explain how the code is organized internally:

- **Entry points**: Where does control enter this unit? (public methods, event handlers, HTTP handlers, constructors)
- **Data flow**: How does data move through the code? What transforms it, what validates it, what persists it?
- **Key branches**: What are the main conditional paths? What triggers each?
- **External calls**: What does this code call outside itself? (databases, caches, queues, HTTP, other services)
- **Return values / side effects**: What does the caller get back? What state does this code change?

For complex flows, trace one representative path end-to-end.

Use skill: `architecture-guardrail` to identify whether the code respects expected layer boundaries.

### Step 6 - Non-Obvious Behavior and Gotchas (standard and deep)

Surface behavior that will surprise a developer who has not read this code carefully:

| Gotcha Type               | Examples                                                                                                                      |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Silent failures           | Returns null/empty instead of throwing; swallows exceptions                                                                   |
| Hidden state dependencies | Behavior changes based on external state (DB flags, feature toggles, request context)                                         |
| Ordering requirements     | Method A must be called before method B; initialization order matters                                                         |
| Thread safety assumptions | Not thread-safe; requires external synchronization; assumes single-threaded access                                            |
| Mutability surprises      | Modifies the input parameter; returns a shared mutable reference                                                              |
| Implicit retries          | Retries internally without the caller knowing; can amplify downstream load                                                    |
| Async traps               | Blocking call inside async context; unhandled promise rejection path; fire-and-forget side effects                            |
| Lazy evaluation           | Computation deferred; result differs depending on when it is accessed                                                         |
| Caching behavior          | Result is cached; stale data may be returned; cache is not invalidated on writes                                              |
| Framework magic           | Behavior injected by framework lifecycle (Spring `@Transactional`, Rails `before_action`, Laravel `$casts` / observers, etc.) |

List only the gotchas that actually apply to this code.

Use skill: `architecture-concurrency` if concurrency gotchas are present.

### Step 7 - Key Invariants (standard and deep)

State the assumptions the code depends on that are NOT enforced by the type system or compiler:

- Preconditions the caller must satisfy
- Postconditions the caller can rely on
- Environmental assumptions (specific DB state, config values, initialization order)
- Data shape assumptions not captured in types (e.g., "this list is never empty", "this map always has key X")

Format each invariant as:

> **Invariant**: [statement of what must be true]
> **If violated**: [what breaks]

### Step 8 - Change Impact Preview (standard and deep)

Answer the engineer's most pressing ticket question: "If I modify this, what should I double-check?" Frame as checks to perform, not changes to make. Do not propose refactors.

Use the Inbound callers list from Step 3 and the External calls list from Step 5 to ground each item in concrete files and call sites - generic warnings have low value.

Produce a specific list using the categories below. Include only categories that apply; cite file:line where possible.

- **If you change the logic / behavior**: which callers from Step 3 must be re-verified, which tests likely cover this path
- **If you change the return shape or signature**: which call sites must be updated, which serialization or API boundary is affected
- **If you change the side effects**: which downstream consumers (DB tables written, events published, caches invalidated, logs/metrics emitted) are affected
- **If you change timing or ordering**: which async jobs, retries, or sequenced operations may break
- **If you remove or rename this**: which features or flows depend on it
- **Tests to run / add**: existing test files that exercise this code, gaps that should be covered

### Step 9 - Confidence Gaps (standard and deep)

State explicitly where the explanation is inferred rather than verified. Examples:

- "Callers cannot be enumerated - invoked via reflection / DI auto-wiring / dynamic dispatch. Verify by [specific check]."
- "Likely part of the authentication flow based on naming and imports, but the entry point was not located. Confirm by tracing from `AuthController`."
- "Business reason inferred from method name; no comments or ticket reference found."

Surfacing uncertainty prevents false confidence, which is more dangerous than no explanation.

### Step 10 - Design Intent (deep only)

Explain why the code is structured the way it is - the design decisions embedded in the implementation:

- What pattern is being implemented and why (repository, strategy, decorator, etc.)
- What alternatives were likely considered and what this approach trades off
- What constraints shaped the design (performance, backward compatibility, framework requirements)
- What would need to change if a key assumption changed

Use skill: `complexity-review` to assess whether complexity is accidental or essential.

### Step 11 - Relationships (standard and deep)

Name what this code connects to. Inbound callers are already enumerated in Step 3 (Flow Context); this step covers the remaining edges.

- **Depends on**: What this code calls or imports (key dependencies, not an exhaustive list)
- **Shared state**: What mutable state this code shares with other components (singletons, request context, caches, static fields)
- **Reuse signal**: Whether this is a shared utility, a critical-path component, or single-use - shapes whether to modify in place or extend

## Output

### Quick Depth

```markdown
## [Target Name]

**What it does**: [2-4 sentence summary]

**Key gotchas**:

- [Gotcha 1]
- [Gotcha 2]
```

### Standard Depth (default)

```markdown
## [Target Name]

**What it does**: [2-4 sentence summary from caller's perspective]

**Scope boundary**: [What it explicitly does NOT handle]

### Flow Context

- **Triggered by**: [HTTP route / event / job / lifecycle hook / parent caller]
- **Runs before this**: [upstream preparation, validation, auth]
- **Runs after this**: [downstream consumers of output or side effects]
- **Frequency**: [hot path / background / edge case]
- **Inbound callers**:
  - `path/to/file.ext:LINE` - [brief caller context]
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

- **Invariant**: [statement] -- **If violated**: [consequence]

### Change Impact Preview

- **If you change the logic**: re-verify [`caller.ext:LINE`], run [test file]
- **If you change the return shape**: update [call sites], affects [API/serialization boundary]
- **If you change the side effects**: affects [DB table / event / cache / log]
- **If you change timing or ordering**: may break [async job / retry / sequence]
- **If you remove or rename this**: depended on by [feature / flow]
- **Tests to run / add**: [existing test files], [coverage gaps]

### Relationships

- **Depends on**: [key dependencies]
- **Shared state**: [singletons, request context, caches]
- **Reuse signal**: [shared utility / critical path / single-use]

### Confidence Gaps

- [Where the explanation is inferred rather than verified, and how to confirm]
```

### Deep Depth

```markdown
## [Target Name]

[All standard sections plus:]

### Design Intent

[Pattern used, trade-offs, constraints that shaped the design, what would change if assumptions changed]

### Complexity Assessment

[Whether complexity is essential or accidental; what could be simplified without loss]
```

### Output Constraints

- No code review findings or refactoring suggestions unless the user explicitly asks
- No generated code
- Omit sections with nothing to say (no gotchas = omit gotchas section)
- Match depth to the requested level - do not over-explain for `quick`
- Omit obvious observations ("this method returns a value") - only high-signal content

## Self-Check

- [ ] Code was read before explaining - no explanation from names alone
- [ ] Purpose stated from the caller's perspective with scope boundary
- [ ] Flow Context populated: trigger, upstream, downstream, frequency, and inbound callers grepped (or marked under Confidence Gaps)
- [ ] Why It Exists stated (domain or technical reason), or marked under Confidence Gaps if not inferable
- [ ] Data flow covers entry points, key branches, external calls, and side effects
- [ ] Non-obvious behavior explicitly flagged; gotchas that could cause production bugs prioritized
- [ ] Key invariants named with violation consequence
- [ ] Change Impact Preview lists concrete checks tied to the callers and side effects above (not generic warnings)
- [ ] Confidence Gaps section present where any item was inferred rather than verified
- [ ] Explanation depth matches requested level; obvious detail omitted
- [ ] Explanation is specific to this code, not a generic description of the pattern

## Avoid

- Reviewing the code for quality or suggesting improvements (use `task-code-review` for that)
- Prescribing refactors in Change Impact ("prefer adding a new function instead") - list checks to perform, not edits to make
- Explaining from function signatures or names without reading the implementation
- Listing inbound callers as "discoverable in IDE" - actually grep and cite file:line, or mark under Confidence Gaps
- Stating a business reason that is not supported by the code, comments, or surrounding context - put it under Confidence Gaps instead
- Generic descriptions ("this is a service layer") without concrete specifics
- Burying gotchas in prose where they will be missed
- Explaining language syntax or well-known patterns in detail
- Generating new code or proposing refactoring
