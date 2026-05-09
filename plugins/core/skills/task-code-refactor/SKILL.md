---
name: task-code-refactor
description: Refactor entry point: smell identification, test-coverage gate, phased step-by-step plan. Detects stack and dispatches refactor workflow.
metadata:
  category: review
  tags: [refactoring, code-quality, technical-debt, multi-stack, router]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Code Refactor (Router)

This skill is a thin dispatcher. It detects the project stack and delegates to the matching stack-specific skill (e.g., `task-spring-refactor`, `task-rails-refactor`, `task-react-refactor`). The stack workflow names framework-specific smells directly (Rails: fat controllers, callback abuse; Spring: business logic in controller; React: prop drilling, effect spaghetti) and applies framework-aware refactor recipes.

For unknown stacks, this skill falls back to a minimal generic refactoring protocol.

## When to Use

- Code smell identification and resolution
- Technical debt reduction targeting a specific file, class, module, or function
- Safe refactoring planning with a test gate

**Not for:** Deciding which debt to tackle first (use `task-debt-prioritize`), feature changes (use `task-implement` family), architecture-level restructuring (use the architecture plugin).

## Inputs

| Input                 | Required    | Description                                                              |
| --------------------- | ----------- | ------------------------------------------------------------------------ |
| Target scope          | Yes         | File, class, module, or path to refactor                                 |
| Goal                  | Yes         | What the refactoring should achieve                                      |
| Test coverage status  | Recommended | Whether tests exist and pass for the target area                         |
| Shared/public surface | Recommended | Whether the target is used across module or team boundaries              |

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect`.

### Step 2 - Dispatch to Stack Workflow

| Detected stack       | Delegate to             |
| -------------------- | ----------------------- |
| Java / Spring Boot   | `task-spring-refactor`  |
| Kotlin / Spring Boot | `task-kotlin-refactor`  |
| Python               | `task-python-refactor`  |
| Ruby / Rails         | `task-rails-refactor`   |
| Node.js / TypeScript | `task-node-refactor`    |
| Go / Gin             | `task-go-refactor`      |
| Rust / Axum          | `task-rust-refactor`    |
| .NET / ASP.NET Core  | `task-dotnet-refactor`  |
| PHP / Laravel        | `task-laravel-refactor` |
| React                | `task-react-refactor`   |
| Vue                  | `task-vue-refactor`     |
| Angular              | `task-angular-refactor` |

If matched, delegate and stop. Do not run Step 3.

### Step 3 - Generic Fallback (unknown stack only)

**Identify smells** (these are signals, not hard rules; judgment over checklist):

| Smell               | Signal                                                      | Risk   |
| ------------------- | ----------------------------------------------------------- | ------ |
| Long Method         | Difficult to name, test, or understand in one reading       | Medium |
| Large Class         | Multiple responsibilities; hard to mock                     | High   |
| Duplicate Code      | Same logic copy-pasted; diverges silently                   | Medium |
| Feature Envy        | Method more interested in another class's data than its own | Low    |
| Long Parameter List | >3-4 params; callers must look up meaning                   | Low    |
| Divergent Change    | One class changed for many unrelated reasons                | High   |
| Shotgun Surgery     | One change requires many small edits across classes         | High   |

**Cross-module assessment** before proposing any step:

- Is the target used outside its module? Treat signature/behavior changes as breaking; check callers explicitly.
- Is it part of a public API or published contract? Use skill: `ops-backward-compatibility`.
- Does any step touch a constructor, factory, or function signature? Always invoke `ops-backward-compatibility`. Add a deprecation alias before renaming public symbols.
- Use skill: `review-blast-radius` to estimate the scope of affected callers/tests/deployments.

**Test coverage gate:**

- If tests exist and pass: proceed to the refactoring sequence.
- If tests are absent or insufficient: do **not** propose refactoring steps. Output a "Test First" plan instead - characterization tests that pin current behavior, prioritized by risk. Only after those tests pass, return to plan refactor steps.

**Common refactorings:**

| Smell            | Refactoring            | Cross-Module Risk         |
| ---------------- | ---------------------- | ------------------------- |
| Long Method      | Extract Method         | Low (private scope)       |
| Large Class      | Extract Class          | Medium (new interface)    |
| Duplication      | Extract, Pull Up       | Medium-High (shared code) |
| Feature Envy     | Move Method            | Medium (changes callers)  |
| Divergent Change | Split into two classes | High (public boundary)    |
| Shotgun Surgery  | Inline and consolidate | High (many callers)       |

**Safe step protocol:** ensure tests pass -> commit -> apply ONE refactoring -> run tests -> commit -> repeat. Each step must be independently committable.

## Output Format

When dispatched (Step 2 matched): the stack-specific workflow owns the output.

When fallback runs (Step 3):

```markdown
## Refactoring Plan: [Target Name]

**Stack:** unknown (generic fallback applied)
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

1. [Test: what behavior to pin, suggested test name]
2. ...
```

## Self-Check

- [ ] `behavioral-principles` loaded before any other step
- [ ] `stack-detect` ran at Step 1
- [ ] If a stack matched, the dispatched workflow ran and Step 3 was skipped
- [ ] If no stack matched, fallback ran with smell identification, cross-module check, test gate, and committable steps
- [ ] Test coverage gate enforced - no refactor steps proposed when tests are insufficient
- [ ] `ops-backward-compatibility` invoked when any step touches public signatures
- [ ] Each step is independently committable

## Avoid

- Running both Step 2 dispatch and Step 3 fallback
- Producing your own plan when a stack workflow was dispatched
- Proposing refactoring steps before checking test coverage
- Renaming or removing public symbols without a deprecation alias step
- Combining multiple refactorings into one step (masks which change broke tests)
- Treating the fallback as a full equivalent of a stack workflow - install the matching language plugin when one exists
