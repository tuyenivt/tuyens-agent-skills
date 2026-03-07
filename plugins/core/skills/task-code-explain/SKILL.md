---
name: task-code-explain
description: Explain a single file, function, class, or module - what it does, why it is structured this way, non-obvious gotchas, and key invariants. Not for broken code (use task-debug) and not for whole-codebase mapping (use task-onboard-codebase).
metadata:
  category: code
  tags: [explanation, code-understanding, onboarding, review, debugging]
  type: workflow
user-invocable: true
---

# Code Explain

## Purpose

Targeted code explanation for a specific file, function, class, or module:

- **What it does** -- the observable behavior from the caller's perspective
- **Why it is structured this way** -- the design decisions visible in the code, including non-obvious ones
- **Non-obvious gotchas** -- behavior that will surprise a developer unfamiliar with this code
- **Key invariants** -- assumptions the code depends on that are not enforced by the type system
- **Entry points and data flow** -- where control enters and how data moves through

This skill explains existing code. It does not review it for quality, suggest refactoring, or generate new code.

## When to Use

- Understanding unfamiliar code during a code review
- Debugging a module you did not write
- Onboarding to a specific feature or component (not the whole codebase - use `task-onboard-codebase` for that)
- Preparing to modify or extend a piece of code you need to understand first
- Explaining code to a teammate or in documentation

## Inputs

| Input             | Required | Description                                                               |
| ----------------- | -------- | ------------------------------------------------------------------------- |
| Code target       | Yes      | File path, function name, class name, or pasted code block to explain     |
| Explanation depth | No       | `quick` (what it does), `standard` (default), or `deep` (design intent)   |
| Caller context    | No       | What the caller is trying to do with this code (shapes what to emphasize) |
| Known confusion   | No       | Specific aspect that is unclear (focus explanation there)                 |

Default depth: `standard`.

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

Use skill: `stack-detect` to identify the language and framework. This shapes:

- Naming convention interpretation
- Framework lifecycle awareness (e.g., Spring beans, Rails callbacks, NestJS decorators)
- Common patterns the code may be implementing (middleware, interceptors, repository pattern)

Read the target code fully before proceeding.

### Step 2 - Purpose Summary (all depths)

State in two to four sentences:

- What this code does from the perspective of its caller or user
- What problem it solves or what responsibility it owns
- What it explicitly does NOT do (scope boundary)

Example framing:

> "This class is the entry point for all payment processing. It validates the payment request, delegates to the appropriate payment provider, and persists the result. It does not handle refunds - those go through `RefundService`."

### Step 3 - Structure and Data Flow (standard and deep)

Explain how the code is organized internally:

- **Entry points**: Where does control enter? (public methods, event handlers, HTTP handlers, constructors)
- **Data flow**: How does data move through the code? What transforms it, what validates it, what persists it?
- **Key branches**: What are the main conditional paths? What triggers each?
- **External calls**: What does this code call outside itself? (databases, caches, queues, HTTP, other services)
- **Return values / side effects**: What does the caller get back? What state does this code change?

For complex flows, trace one representative path end-to-end.

Use skill: `architecture-guardrail` to identify whether the code respects expected layer boundaries.

### Step 4 - Non-Obvious Behavior and Gotchas (standard and deep)

Surface behavior that will surprise a developer who has not read this code carefully:

| Gotcha Type               | Examples                                                                                           |
| ------------------------- | -------------------------------------------------------------------------------------------------- |
| Silent failures           | Returns null/empty instead of throwing; swallows exceptions                                        |
| Hidden state dependencies | Behavior changes based on external state (DB flags, feature toggles, request context)              |
| Ordering requirements     | Method A must be called before method B; initialization order matters                              |
| Thread safety assumptions | Not thread-safe; requires external synchronization; assumes single-threaded access                 |
| Mutability surprises      | Modifies the input parameter; returns a shared mutable reference                                   |
| Implicit retries          | Retries internally without the caller knowing; can amplify downstream load                         |
| Async traps               | Blocking call inside async context; unhandled promise rejection path; fire-and-forget side effects |
| Lazy evaluation           | Computation deferred; result differs depending on when it is accessed                              |
| Caching behavior          | Result is cached; stale data may be returned; cache is not invalidated on writes                   |
| Framework magic           | Behavior injected by framework lifecycle (Spring `@Transactional`, Rails `before_action`, etc.)    |

List only the gotchas that actually apply to this code.

Use skill: `concurrency-model` if concurrency gotchas are present.

### Step 5 - Key Invariants (standard and deep)

State the assumptions the code depends on that are NOT enforced by the type system or compiler:

- Preconditions the caller must satisfy
- Postconditions the caller can rely on
- Environmental assumptions (specific DB state, config values, initialization order)
- Data shape assumptions not captured in types (e.g., "this list is never empty", "this map always has key X")

Format each invariant as:

> **Invariant**: [statement of what must be true]
> **If violated**: [what breaks]

### Step 6 - Design Intent (deep only)

Explain why the code is structured the way it is - the design decisions embedded in the implementation:

- What pattern is being implemented and why (repository, strategy, decorator, etc.)
- What alternatives were likely considered and what this approach trades off
- What constraints shaped the design (performance, backward compatibility, framework requirements)
- What would need to change if a key assumption changed

Use skill: `complexity-review` to assess whether complexity is accidental or essential.

### Step 7 - Relationships (standard and deep)

Name what this code connects to:

- **Depends on**: What this code calls or imports (key dependencies, not exhaustive list)
- **Used by**: Known callers or consumers (if discoverable from the codebase)
- **Shared state**: What mutable state this code shares with other components

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

### Data Flow

[Entry points, key branches, external calls, return/side effects]

### Non-Obvious Behavior

| Behavior | Detail                  |
| -------- | ----------------------- |
| [Type]   | [What happens and when] |

### Key Invariants

- **Invariant**: [statement] -- **If violated**: [consequence]

### Relationships

- **Depends on**: [key dependencies]
- **Used by**: [known callers, if discoverable]
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

## Success Criteria

A well-executed explanation passes all of these.

### Completeness

- [ ] The code was read before explaining - no explanation from names alone
- [ ] The purpose is stated from the caller's perspective, not the implementation's perspective
- [ ] Non-obvious behavior is explicitly flagged, not buried in prose
- [ ] Key invariants are named with their violation consequence

### Clarity

- [ ] A developer unfamiliar with this code could use it correctly after reading the explanation
- [ ] A developer debugging this code would know where to look for the root cause of common failures
- [ ] Gotchas that have caused or could cause production bugs are prioritized

### Proportionality

- [ ] Explanation depth matches the requested level
- [ ] Obvious detail is omitted - no explaining common patterns or language syntax
- [ ] The explanation is specific to this code, not a generic description of the pattern it uses

## Avoid

- Reviewing the code for quality or suggesting improvements (use `task-code-review` for that)
- Explaining from function signatures or names without reading the implementation
- Generic descriptions ("this is a service layer") without concrete specifics
- Burying gotchas in prose where they will be missed
- Explaining language syntax or well-known patterns in detail
- Generating new code or proposing refactoring

## Key Skills Reference

- Use skill: `stack-detect` for framework-aware interpretation
- Use skill: `architecture-guardrail` for layer boundary context
- Use skill: `concurrency-model` for concurrency gotcha analysis
- Use skill: `complexity-review` for design intent assessment (deep only)
