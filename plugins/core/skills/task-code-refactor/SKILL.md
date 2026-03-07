---
name: task-code-refactor
description: Safe refactoring plan with risk assessment. Auto-detects project stack from CLAUDE.md and adapts refactoring patterns to the detected language and framework.
metadata:
  category: review
  tags: [refactoring, code-quality, technical-debt, multi-stack]
  type: workflow
user-invocable: true
---

# Code Refactor

## When to Use

- Code smell identification and resolution
- Technical debt reduction
- Safe refactoring planning
- Code quality improvement

## Inputs

| Input                 | Required    | Description                                                                                               |
| --------------------- | ----------- | --------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, class, module, or path to refactor                                                                  |
| Goal                  | Yes         | What the refactoring should achieve (e.g., reduce complexity, extract service layer, improve testability) |
| Test coverage status  | Recommended | Whether tests exist and pass for the target area                                                          |
| Shared/public surface | Recommended | Whether the target is used across module or team boundaries                                               |

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Identify Smells (All Stacks)

Use judgment - these are signals, not hard rules. A 25-line method with a clear single responsibility is fine; a 10-line method doing three things is not.

| Smell               | Signal                                                      | Risk   |
| ------------------- | ----------------------------------------------------------- | ------ |
| Long Method         | Difficult to name, test, or understand in one reading       | Medium |
| Large Class         | Multiple responsibilities, hard to mock in tests            | High   |
| Duplicate Code      | Same logic copy-pasted; diverges silently under change      | Medium |
| Feature Envy        | Method more interested in another class's data than its own | Low    |
| Long Parameter List | >3-4 params; callers must look up meaning of each           | Low    |
| Divergent Change    | One class changed for many unrelated reasons                | High   |
| Shotgun Surgery     | One change requires many small edits across classes         | High   |

### Step 3 - Framework-Specific Smells

After loading stack-detect, identify smells specific to the detected ecosystem. Common categories include:

**Controller/Handler Bloat:**

- Presentation layer contains business logic that should be in a service layer
- Input validation done manually instead of using the framework's validation mechanism

**Data Layer Leaks:**

- ORM entities exposed directly in API responses instead of using DTOs/serializers/response structs
- Query logic scattered across layers instead of being encapsulated in repositories

**Dependency Anti-Patterns:**

- Using deprecated dependency injection patterns when the framework provides better alternatives
- Tight coupling to concrete implementations instead of abstractions

**Concurrency Anti-Patterns:**

- Using deprecated or unsafe concurrency primitives for the detected runtime
- Incorrect pool sizing for the runtime's threading model

**Test Anti-Patterns:**

- Using deprecated test utilities or annotations
- Missing test isolation (shared state between tests)

If the detected stack is unfamiliar, apply the universal smells from Step 2.

### Step 4 - Cross-Module and Shared-Code Assessment

Before proposing any refactoring step, assess boundary impact:

**Is the target used across module boundaries?**

- If yes, treat any signature or behavior change as a breaking change requiring coordination
- Check for callers outside the current package/module/namespace
- Flag shared utilities, base classes, or interfaces - changes cascade silently

**Is the target part of a public API or published contract?**

- HTTP endpoints, SDK methods, events, and database schemas are public contracts
- Refactoring these requires backward-compatibility analysis - use skill: `backward-compatibility-analysis`

**What is the blast radius?**

- Use skill: `blast-radius-analysis` to estimate how many callers, tests, and deployments are affected
- A refactoring touching shared infrastructure (logging, auth, caching) has higher blast radius than a leaf class

**Rules for cross-module refactoring:**

- Propose an interface/facade before removing or renaming shared code
- Never rename public symbols without a deprecation alias step first
- Add tests at the boundary before moving code across module lines

### Step 5 - Safe Refactoring Steps

1. Ensure tests exist
2. Commit current state
3. Apply ONE refactoring
4. Run tests
5. Commit
6. Repeat

### Step 6 - Common Refactorings

| Smell            | Refactoring            | Cross-Module Risk         |
| ---------------- | ---------------------- | ------------------------- |
| Long Method      | Extract Method         | Low (private scope)       |
| Large Class      | Extract Class          | Medium (new interface)    |
| Duplication      | Extract, Pull Up       | Medium-High (shared code) |
| Feature Envy     | Move Method            | Medium (changes callers)  |
| Divergent Change | Split into two classes | High (public boundary)    |
| Shotgun Surgery  | Inline and consolidate | High (many callers)       |
