---
name: task-code-refactor
description: Safe refactoring plan with risk assessment. Auto-detects project stack from CLAUDE.md and adapts refactoring patterns to the detected language and framework.
metadata:
  category: review
  tags: [refactoring, code-quality, technical-debt, multi-stack]
  type: workflow
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

## Key Skills Reference

- Use skill: `coding-standards` for style and structure guidelines
- Use skill: `concurrency-model` for thread-safety during refactoring
- Use skill: `architecture-guardrail` for layer violation detection
- Use skill: `blast-radius-analysis` for shared-code scope assessment
- Use skill: `backward-compatibility-analysis` for public API or contract changes

## Rules

- Never refactor without tests
- Never combine refactoring with feature changes
- One refactoring per commit
- Verify behavior preservation after each step
- Assess risks and prerequisites before starting
- Do not apply refactoring patterns from one framework to another

## Output

```markdown
## Current State

**Stack Detected:** [language / framework]
**Refactoring Goal:** [what this achieves]
[Description of issues and smells identified]

## Risk Assessment

| Factor          | Status         | Notes                            |
| --------------- | -------------- | -------------------------------- |
| Test Coverage   | Safe/Warn/Risk | [coverage in target area]        |
| Complexity      | Safe/Warn/Risk | [cognitive complexity of target] |
| Dependencies    | Safe/Warn/Risk | [internal vs. cross-module]      |
| Blast Radius    | Safe/Warn/Risk | [number of callers affected]     |
| Public Contract | Safe/Warn/Risk | [API/interface exposure]         |

## Cross-Module Impact

[Which modules or teams are affected. "None" if scope is fully internal.]

## Step-by-Step Plan

### Step 1: [Name]

- What: [change]
- Risk: Low/Medium/High
- Cross-module: Yes/No - [impact if yes]
- Tests: [how to verify behavior is preserved]

## Prerequisites

- [ ] Add tests for [area]
- [ ] Create branch
- [ ] Notify [team/owner] if cross-module changes are planned

## Rollback

[How to revert each step]
```

## Success Criteria

A well-executed refactoring plan passes all of these. Use as a self-check before starting the refactoring.

### Safety

- [ ] Test coverage for the target area is assessed before any refactoring step is proposed
- [ ] Each step is independently committable and verifiable - no multi-step atomic changes
- [ ] A rollback path exists for each step (git revert is sufficient if steps are small and isolated)
- [ ] No behavior change is mixed with structural change in any single step

### Completeness

- [ ] Smells are identified from both the universal list and framework-specific patterns for the detected stack
- [ ] Risk assessment covers test coverage, complexity, and dependency scope
- [ ] Cross-module or shared-code impact is explicitly assessed before proposing any step that touches boundaries
- [ ] Prerequisites (tests to add, branch to create) are listed before the step-by-step plan

### Staff-Level Signal (for tech lead review)

- [ ] The plan is ordered by risk reduction - highest-risk smells addressed after safety is established
- [ ] Any step touching shared code or public APIs is flagged as requiring review before execution
- [ ] The refactoring scope is bounded - no scope creep into unrelated areas
- [ ] A senior engineer could hand this plan to a junior and expect safe execution

## Avoid

- Refactoring without test coverage
- Combining refactoring with new features
- Large, multi-step changes in a single commit
- Refactoring code you don't understand
- Applying framework conventions from a different stack
