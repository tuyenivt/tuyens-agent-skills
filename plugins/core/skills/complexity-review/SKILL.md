---
name: complexity-review
description: Flag cyclomatic/cognitive complexity, long methods, deep nesting, oversized files, parameter bloat, over-abstraction. Stack-aware thresholds.
metadata:
  category: governance
  tags: [complexity, review, maintainability, multi-stack]
user-invocable: false
---

# Complexity Review

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Code review to flag overly complex methods, classes, or modules
- Refactoring planning to identify simplification targets
- Evaluating whether a design is over-engineered

## Rules

- Flag strictly above thresholds; a unit at or under every threshold is not a finding. Context can justify exceeding a threshold, which lowers severity, never the other way round.
- Cyclomatic and cognitive complexity report together: when either fires, the unit carries one Signal group, `Signal: Cyclomatic / cognitive complexity`, whose Measured line carries both numbers and whose Simplification is the Signal Table Fix of each of the two signals that exceeds its threshold, cyclomatic's first when both do.
- Calibrate thresholds to the detected stack's norms (Ruby methods are shorter than Java). A stricter limit the stack's standard linter enforces under the project's own linter config, or under the linter's defaults when the project sets none (plain RuboCop 1.x: `Metrics/MethodLength` 10, `Metrics/CyclomaticComplexity` 7, `Metrics/ClassLength` 100), is the calibrated threshold and overrides the Signal Table default, ranged or fixed; a looser project limit does not raise the default, and a rule the linter or its shipped preset disables (ESLint `max-params`; every `Metrics/*` cop under `rubocop-rails-omakase`, the Rails 7.2+ default) does not.
- Order rows by severity, High first; within a severity, rows with a numeric signal first by the worst metric-to-threshold ratio, then rows with only qualitative or loop-call signals, each group in file order; within one unit, order the Signal groups by Refactor Priority.
- Ranged thresholds (e.g., 20-40 lines): the lower bound for Ruby and Python, the upper bound for Java, Go, TypeScript, any other language, and an unknown stack.
- Only the Signal Table is in scope, in every mode: a dead variable, an unclosed client, or absent error handling is another skill's finding, not a row here.

## Patterns

### Signal Table

| Signal                            | Default Threshold      | Fix                                                        |
| --------------------------------- | ---------------------- | ---------------------------------------------------------- |
| Cyclomatic complexity             | > 10                   | Extract by responsibility; replace conditionals with table lookup or polymorphism |
| Cognitive complexity              | > 15                   | Flatten nesting; collapse boolean chains; split mixed concerns |
| Method/function length            | > 20-40 lines          | Extract methods by responsibility                          |
| File/class/module size            | > 200-300 lines        | Split by responsibility (likely SRP violation)             |
| Nesting depth                     | > 3 levels             | Guard clauses, early returns, pattern matching             |
| Parameter count                   | > 5 (the receiver `self` / `this` / `cls` not counted) | Parameter object, builder, or rebalance responsibilities   |
| Branch chain (switch / if-else)   | > 10 branches          | Map lookup, strategy, or polymorphism                      |
| Inheritance/mixin depth           | > 3-4 levels           | Composition over inheritance                               |
| Indirection depth                 | > 3 pass-through delegation hops | Collapse layers that add no logic; inline single-use wrappers |
| Speculative abstraction           | qualitative: an interface, factory, registry, or strategy layer with one implementation or one caller, stub implementations nothing calls, or in design mode a new service or module boundary with one caller | Inline into the single implementation; add the layer when a second implementation exists |
| External calls per method         | > 3 call statements (network, IPC, or database; three DB statements are three, commit and rollback included), or one call inside a loop over an unbounded collection (an ORM lazy load per item counts) | Extract orchestration layer; batch the per-item call; explicit error handling per call |
| Error-handling complexity         | qualitative: broad catch-all, empty catch, try nested more than 2 deep | Specific exception types, Result/Either, error handler delegation |

Cyclomatic complexity: decision points plus one, counted the way the stack's tool counts them - ESLint `complexity`, gocyclo, radon, ruff `C901`, and RuboCop add one per non-default arm of a `switch`, `select`, `case`, or `match` (a `default`, `else`, or Python `case _` arm adds none; RuboCop counts every `in` arm of a `case`/`in`, `in _` included); radon, ESLint, gocyclo, and RuboCop add one per `&&` / `||` (`if (a && b)` is 3), ruff `C901` adds none per boolean operator (`if a and b` is 2), and standalone mccabe counts neither boolean operators nor `match` cases; RuboCop also adds one per iterating block (`items.each { }`), per `&.` (repeated `&.` on the same local receiver adds one in total), and per `||=`; ESLint adds one per `??` (7.x and later), and 9+ also per `?.` and default parameter value. Cognitive complexity (SonarSource rules): +1 for each `if`, `else`/`else if`, ternary, `switch`/`match` (one increment for the whole statement, whatever the case count), loop, `catch`, labeled jump, and each method in a recursion cycle (once per method, not per call site); a further +1 per nesting level for `if`, ternary, `switch`, loops, and `catch` (none for `else`/`else if`; nested functions and lambdas raise the nesting level but receive no increment); +1 per sequence of like binary logical operators (`a && b && c` is one sequence; `a && b || c` is two).

Nesting depth counts control structures nested inside one another (`if`, loop, `switch`/`match`, `try`); `else`/`else if` stay at their `if`'s level; a ternary adds none in a manual count, while RuboCop `Metrics/BlockNesting` counts it as a level and a RuboCop-measured value keeps that count.

Indirection depth: follow the call chain from the entry point until a hop does real work (a branch, a transform, an I/O call), counting only hops that forward arguments. More than 3 such hops is the finding; stop counting at 5 or at a repository/client boundary. Anchor the row at the chain's entry point and name the hops.

### Severity

- **High**: any numeric signal at or beyond ~1.5x its calibrated threshold (at the default upper bounds: cyclomatic >= 15, cognitive >= 23, file >= 450 lines, nesting >= 5) unless the downgrade rule below applies, or a qualitative signal (error handling) that blocks comprehension or correctness (a broad catch that swallows errors on a request path)
- **Medium**: over the threshold but below ~1.5x, one or more calls inside a loop over an unbounded collection, or a qualitative signal that does not block comprehension (a speculative abstraction)
- **Low**: over the threshold where context justifies it - stable and tested code the team has chosen not to touch, or a flat exhaustive mapping whose branches duplicate logic (see the downgrade rule)

Downgrade rule: a flat exhaustive mapping (uniform one-line branches, no shared mutable state) caps the `Branch chain (switch / if-else)` and `Cyclomatic / cognitive complexity` Signal groups at Low regardless of branch count; suggest a data table only when branches duplicate logic. Drop those Signal groups when the downgrade leaves nothing to act on; the row survives only if another signal fires.

### Refactor Priority

When several signals fire on one unit, address them in order: (1) External calls per method, (2) Nesting depth, then Cyclomatic / cognitive complexity, (3) Method/function length, File/class/module size, Branch chain (switch / if-else), (4) any remaining signal in Signal Table order. Each step often removes later signals; a signal an earlier step resolves still gets its own Signal group, noting which step resolves it.

### Stack Calibration

After `stack-detect`, prefer the stack's standard linting/analysis tool for measured metrics (Python: radon or ruff `C901`; TypeScript/JavaScript: ESLint `complexity`; Go: gocyclo; Java: PMD or Checkstyle; Ruby: RuboCop `Metrics/*`). `Measured by` is `<tool> <version>` (its `--version` output; gocyclo has none, so its module version from `go version -m $(which gocyclo)`) when the counts come from running the tool, with ` + manual count (cognitive)` appended when that tool reports no cognitive complexity (radon, ruff, ESLint core, gocyclo, and RuboCop report cyclomatic only), `manual count - <tool> not run` when counted by hand, naming the project's configured tool when its config names one (ruff `C901` with a `max-complexity`), else the first tool listed for the stack; in design mode it is `design evaluation - counts from the proposal`. The Stack line is stack-detect's `<Language> / <Framework>` rendering verbatim, versions as it reports them (`Python 3.12 / FastAPI 0.115`); a secondary block's Stack line comes from stack-detect's `Additional` entry for that stack (`Frontend: TypeScript (React)` -> `TypeScript / React`). Write `<language> (no framework detected)` when stack-detect reports a known `Language` and `Framework: unknown`. When `Language` is `unknown`, use universal thresholds at the upper bound and write `Measured by: manual count - no calibrated tool (language unknown)`. When the language is known but has no standard complexity tool, append ` - unfamiliar stack` to the Stack line, use the upper bounds, and write `manual count - no calibrated tool (<language>)`.

## Output Format

One row per unit, not per signal - a unit firing three signals is one row carrying three Signal groups, severity set by its worst signal. One block per stack: units sharing a stack are rows in one block; units from different stacks get one block each. Stack and Measured by are always emitted; units checked and under every threshold are not listed.

```
## Complexity Assessment

**Stack:** {language / framework | <language> (no framework detected) | unknown}{ - unfamiliar stack}

**Measured by:** {tool and version{ + manual count (cognitive)} | "manual count - <stack's tool> not run" | "manual count - no calibrated tool (<language> or language unknown)" | "design evaluation - counts from the proposal"}

### Issues                                    {when at least one issue}

- [Severity: High | Medium | Low] {file:line of the unit's declaration, the first when the row spans several, or symbol; in design mode the proposed construct} - {one-line description}
  - Signal: {Signal Table name; `Cyclomatic complexity` and `Cognitive complexity` are always written as the pair `Cyclomatic / cognitive complexity`}
  - Measured: {value and threshold, e.g., "cyclomatic 18 / cognitive 24, thresholds 10 / 15" | "n/a - qualitative: <what was observed>"}
  - Simplification: {concrete fix from Patterns}
  - Signal: {next signal on the same unit, in Refactor Priority order}
  - Measured: {...}
  - Simplification: {...}

### No Issues Found                           {instead, when none: one sentence stating no actionable complexity was found - covers both clean code and downgraded rows that were dropped}
```

When evaluating a design rather than code, anchor each row at the proposed construct (layer, abstraction, interface) and `Measured` counts what the proposal declares - layers, branches, parameters, calls per item - against the same thresholds. Proposal items that map to no signal are not rows and are not listed.

## Avoid

- Recommending a refactor whose only effect is moving a number below its threshold
