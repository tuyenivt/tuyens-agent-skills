---
name: task-code-refactor
description: Refactor entry point: smell identification, test-coverage gate, phased step-by-step plan. Detects stack and dispatches refactor workflow.
metadata:
  category: review
  tags: [refactoring, code-quality, technical-debt, multi-stack, router]
  type: workflow
user-invocable: true
---

# Code Refactor (Router)

Detects stack and delegates to the matching refactor workflow. Stack workflows name framework-specific smells (Rails fat controllers, Spring business logic in controller, Node callback nesting, etc.) and apply framework-aware recipes. Falls back to a generic protocol for unknown stacks.

## When to Use

- Code smell resolution targeting a specific file, class, module, or function
- Technical debt reduction with a test-coverage gate
- Safe refactoring planning

**Not for:** feature changes (`task-implement`), architecture-level restructuring (architecture plugin).

## Inputs

| Input                 | Required    | Notes                                                    |
| --------------------- | ----------- | -------------------------------------------------------- |
| Target scope          | Yes         | File, class, module, or path                             |
| Goal                  | Yes         | What the refactor should achieve                         |
| Test coverage status  | Recommended | Whether tests exist and pass                             |
| Public surface        | Recommended | Whether the target is used across module/team boundaries |

If a required input is missing, ask for it before proceeding. Determine missing recommended inputs from the codebase (run the tests, grep for callers) rather than assuming.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to             |
| -------------------- | ----------------------- |
| Java / Spring Boot   | `task-spring-refactor`  |
| Kotlin / Spring Boot | `task-kotlin-refactor`  |
| Python               | `task-python-refactor`  |
| Ruby / Rails         | `task-rails-refactor`   |
| Node.js / TypeScript | `task-node-refactor`    |
| Go / Gin             | `task-go-refactor`      |

On match: delegate, forwarding the Inputs table values (target scope, goal, coverage status, public surface). Stop; skip Step 4.

If the matched workflow is not installed: run Step 4 and recommend installing the matching plugin in the output.

### Step 4 - Generic Fallback (unknown stack or plugin not installed)

**Identify smells** (signals, not hard rules):

| Smell               | Signal                                                  | Refactoring             | Cross-Module Risk         |
| ------------------- | ------------------------------------------------------- | ----------------------- | ------------------------- |
| Long Method         | Hard to name, test, or read in one pass                 | Extract Method          | Low (private)             |
| Large Class         | Multiple responsibilities; hard to mock                 | Extract Class           | Medium (new interface)    |
| Duplicate Code      | Same logic copy-pasted; diverges silently               | Extract / Pull Up       | Medium-High               |
| Feature Envy        | Method more interested in another class's data          | Move Method             | Medium (callers change)   |
| Long Parameter List | >3-4 params; callers must look up meaning               | Introduce Parameter Obj | Low                       |
| Divergent Change    | One class changed for many unrelated reasons            | Split into two classes  | High (public boundary)    |
| Shotgun Surgery    | One change requires many small edits across classes     | Inline and consolidate  | High (many callers)       |

**Cross-module check** before any step:

- If the target is used outside its module, treat signature/behavior changes as breaking; verify callers.
- If any step touches a public symbol, constructor, factory, or signature: use skill: `ops-backward-compatibility` and add a deprecation alias before renaming.
- Use skill: `review-blast-radius` to estimate affected callers/tests/deployments.

**Test coverage gate:**

- Tests exist, pass, and exercise the behavior being refactored: proceed to the refactoring sequence.
- Tests exist but fail: stop. Report the failing tests and emit no plan - fix or quarantine first; never refactor on red.
- Tests absent or not exercising the target behavior: do **not** propose refactor steps. Output Smells Found plus a Test First plan (omit Refactoring Sequence) - characterization tests pinning current behavior, prioritized by risk. Resume only after those tests pass.

**Safe step protocol:** tests pass -> commit -> apply ONE refactoring -> tests pass -> commit -> repeat. Each step independently committable.

## Output Format

When dispatched (Step 3): the stack workflow owns the output.

When fallback runs (Step 4):

```markdown
## Refactoring Plan: [Target]

**Stack:** [unknown / <stack> - plugin not installed, install <plugin>] (generic fallback)
**Goal:** [what this achieves]
**Test coverage:** [sufficient / insufficient - see Test First if insufficient]
**Blast radius:** [Narrow / Moderate / Wide / Critical] - [callers / modules] (from `review-blast-radius`)

## Smells Found

| Smell   | Location    | Risk              |
| ------- | ----------- | ----------------- |
| [smell] | [file:line] | [Low/Medium/High] |

## Refactoring Sequence

Each step independently committable; run tests after each.

1. **[Refactoring]** - [file:line] - [what and why]
2. ...

## Breaking Change Risk

[None / Low / High] - [explanation if any public interface changes]

## Test First Plan (only if coverage insufficient)

1. [Test name and behavior to pin]
2. ...
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: stack matched and workflow installed -> dispatched with inputs forwarded, stopped; Step 4 skipped
- [ ] Step 4: stack unmatched or workflow missing -> smells identified, cross-module check ran, test gate enforced, steps committable
- [ ] `ops-backward-compatibility` invoked when any step touches public signatures
- [ ] No refactor steps proposed when tests are insufficient

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Producing a plan yourself when a stack workflow was dispatched
- Proposing steps before checking test coverage
- Renaming or removing public symbols without a deprecation alias
- Combining multiple refactorings into one step (masks which change broke tests)
- Treating the fallback as equivalent to a stack workflow - install the matching language plugin when one exists
