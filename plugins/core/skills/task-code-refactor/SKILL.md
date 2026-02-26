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

## Workflow

### Step 1 — Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 — Identify Smells (All Stacks)

| Smell                    | Risk   |
| ------------------------ | ------ |
| Long Method (>20 lines)  | Medium |
| Large Class (>200 lines) | High   |
| Duplicate Code           | Medium |
| Feature Envy             | Low    |
| Long Parameter List      | Low    |

### Step 3 — Framework-Specific Smells

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

### Step 4 — Safe Refactoring Steps

1. Ensure tests exist
2. Commit current state
3. Apply ONE refactoring
4. Run tests
5. Commit
6. Repeat

### Step 5 — Common Refactorings

| Smell        | Refactoring      |
| ------------ | ---------------- |
| Long Method  | Extract Method   |
| Large Class  | Extract Class    |
| Duplication  | Extract, Pull Up |
| Feature Envy | Move Method      |

## Key Skills Reference

- Use skill: `coding-standards` for style and structure guidelines
- Use skill: `concurrency-model` for thread-safety during refactoring
- Use skill: `architecture-guardrail` for layer violation detection

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
[Description of issues]

## Risk Assessment

| Factor        | Status         |
| ------------- | -------------- |
| Test Coverage | Safe/Warn/Risk |
| Complexity    | Safe/Warn/Risk |
| Dependencies  | Safe/Warn/Risk |

## Step-by-Step Plan

### Step 1: [Name]

- What: [change]
- Risk: Low/Medium/High
- Tests: [verify]

## Prerequisites

- [ ] Add tests for [area]
- [ ] Create branch

## Rollback

[How to revert]
```

## Avoid

- Refactoring without test coverage
- Combining refactoring with new features
- Large, multi-step changes in a single commit
- Refactoring code you don't understand
- Applying framework conventions from a different stack
