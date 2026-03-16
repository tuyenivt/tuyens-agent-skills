---
name: task-code-refactor
description: Safe refactoring plan for a specific target - file, class, module, or function. Identifies code smells, assesses cross-module risk, requires a test coverage gate, and produces a step-by-step sequence of independently committable changes.
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

**Not for:** Deciding which debt to tackle first (use `task-debt-prioritize`), feature changes (use `task-feature-implement`), architecture-level restructuring (use `task-design-architecture`).

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

Use skill: `coding-standards` to enforce naming, structure, and anti-pattern rules for the detected stack.
Use skill: `concurrency-model` if concurrency patterns are present in the target scope.

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

**Does the refactoring change a constructor, `__init__`, factory method, or function signature?**

- Any parameter addition, removal, or reorder is a breaking change for callers outside the module
- Always invoke skill: `backward-compatibility-analysis` before finalizing refactoring steps that touch signatures
- Propose a deprecation alias or keyword-only parameters to soften the break where the language permits

**What is the blast radius?**

- Use skill: `blast-radius-analysis` to estimate how many callers, tests, and deployments are affected
- A refactoring touching shared infrastructure (logging, auth, caching) has higher blast radius than a leaf class

**Rules for cross-module refactoring:**

- Propose an interface/facade before removing or renaming shared code
- Never rename public symbols without a deprecation alias step first
- Add tests at the boundary before moving code across module lines

### Step 5 - Test Coverage Gate

Before proposing any refactoring sequence, assess test coverage on the target:

**If tests exist and pass:**

- Proceed to Step 6. The tests are the safety net.

**If tests are absent or insufficient:**

- Do not propose refactoring steps yet. Refactoring without tests is high-risk - a passing CI after the change proves nothing.
- Instead, output a "Test First" plan:
  - Identify the minimum test surface needed to safely refactor (the key behaviors to pin)
  - Write characterization tests that capture current behavior without asserting correctness
  - Only after those tests pass, proceed with the refactoring plan
- State this clearly: "Target has insufficient test coverage. Recommend writing characterization tests first before refactoring."

### Step 6 - Safe Refactoring Steps

1. Ensure tests exist and pass (see Step 5)
2. Commit current state
3. Apply ONE refactoring
4. Run tests
5. Commit
6. Repeat

### Step 7 - Common Refactorings

| Smell            | Refactoring            | Cross-Module Risk         |
| ---------------- | ---------------------- | ------------------------- |
| Long Method      | Extract Method         | Low (private scope)       |
| Large Class      | Extract Class          | Medium (new interface)    |
| Duplication      | Extract, Pull Up       | Medium-High (shared code) |
| Feature Envy     | Move Method            | Medium (changes callers)  |
| Divergent Change | Split into two classes | High (public boundary)    |
| Shotgun Surgery  | Inline and consolidate | High (many callers)       |

## Output Format

```markdown
## Refactoring Plan: [Target Name]

**Stack:** [language / framework]
**Goal:** [what the refactoring achieves]
**Test coverage status:** [sufficient / insufficient - if insufficient, see Test First plan below]
**Blast radius:** [Low / Medium / High] - [number of callers / affected modules]

## Smells Found

| Smell   | Location    | Risk              |
| ------- | ----------- | ----------------- |
| [smell] | [file:line] | [Low/Medium/High] |

## Refactoring Sequence

Each step is independently committable. Run tests after each.

1. **[Refactoring name]** - [file:line] - [what to do and why]
2. ...

## Breaking Change Risk

[None / Low / High] - [explanation if any public interfaces change]

## Test First Plan (if coverage insufficient)

Characterization tests to write before starting:

1. [Test: what behavior to pin, suggested test name]
2. ...
```

## Self-Check

- [ ] stack-detect invoked before any smell identification or refactoring steps
- [ ] Test coverage gate checked before proposing any refactoring steps; if insufficient, Test First plan output instead
- [ ] Cross-module usage checked; blast-radius-analysis invoked if callers exist outside the target module
- [ ] backward-compatibility-analysis invoked if refactoring touches constructors, `__init__`, factory methods, or public function signatures
- [ ] Every refactoring step is independently committable with a test run between steps
- [ ] Breaking Change Risk section present; empty only if no public symbols change

## Avoid

- Proposing refactoring steps before checking test coverage
- Renaming or removing public symbols without a deprecation alias step
- Treating constructor/signature changes as low-risk - always check callers first
- Combining multiple refactorings into one step (masks which change caused a test failure)
- Generating implementation code for the refactoring - describe what to do, not every line of code

