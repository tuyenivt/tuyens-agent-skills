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
- Report cognitive complexity alongside cyclomatic: a cyclomatic or cognitive Signal group's Measured line carries both numbers. Cyclomatic counts decision points; cognitive captures reading difficulty.
- Calibrate thresholds to the detected stack's norms (Ruby methods are shorter than Java). When the stack's standard linter ships a stricter default (RuboCop `Metrics/MethodLength` 10), that default is the calibrated threshold and overrides the range.
- Order rows by severity, High first; within one unit with multiple signals, order the Signal groups in Refactor Priority order.
- Ranged thresholds (e.g., 20-40 lines): pick the point in the range matching stack norms (Ruby and Python toward the lower end, Java, Go, and TypeScript toward the upper); use the upper bound when the stack is unknown.
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
| External calls per method         | > 3 call statements (network, IPC, or database; three DB statements are three), or one call inside a loop over an unbounded collection | Extract orchestration layer; batch the per-item call; explicit error handling per call |
| Error-handling complexity         | qualitative: broad catch-all, empty catch, try nested more than 2 deep | Specific exception types, Result/Either, error handler delegation |

Cyclomatic complexity: decision points plus one; each binary `&&` / `||` operator is a decision point (`if (a && b)` is 1 + 1 + 1 = 3). Cognitive complexity (SonarSource rules): +1 for each `if`, `else`/`else if`, ternary, `switch`/`match` (one increment for the whole statement, whatever the case count), loop, `catch`, labeled jump, and each method in a recursion cycle (once per method, not per call site); a further +1 per nesting level for `if`, ternary, `switch`, loops, and `catch` (none for `else`/`else if`; nested functions and lambdas raise the nesting level but receive no increment); +1 per sequence of like binary logical operators (`a && b && c` is one sequence; `a && b || c` is two).

Indirection depth: follow the call chain from the entry point until a hop does real work (a branch, a transform, an I/O call), counting only hops that forward arguments. More than 3 such hops is the finding; stop counting at 5 or at a repository/client boundary. Anchor the row at the chain's entry point and name the hops.

### Severity

- **High**: any numeric signal at or beyond ~1.5x its calibrated threshold (at the default upper bounds: cyclomatic >= 15, cognitive >= 23, file >= 450 lines, nesting >= 5) unless the downgrade rule below applies, or a qualitative signal (error handling) that blocks comprehension or correctness (a broad catch that swallows errors on a request path)
- **Medium**: over the threshold but below ~1.5x, or a qualitative signal that does not block comprehension
- **Low**: over the threshold where context justifies it - a flat exhaustive mapping, or stable and tested code the team has chosen not to touch

Downgrade rule: a flat exhaustive mapping (uniform one-line branches, no shared mutable state) caps the branch-chain and cyclomatic signals at Low regardless of branch count; suggest a data table only when branches duplicate logic. Drop those Signal lines when the downgrade leaves nothing to act on; the row survives only if another signal fires - a readable lookup table reported as Low is an invitation to a refactor that makes the code worse.

### Refactor Priority

When several signals fire together, address in order: (1) externalize service calls, (2) flatten nesting with guard clauses, (3) extract by responsibility, (4) any remaining signal in Signal Table order. Each step often removes downstream signals; a signal a preceding step resolves still gets its own Signal group, noting which step resolves it.

### Stack Calibration

After `stack-detect`, adjust thresholds to ecosystem norms and prefer the stack's standard linting/analysis tool for measured metrics. When `Language` is `unknown`, use universal thresholds at the upper bound and write the `Measured by` line's unknown-language value.

## Output Format

One row per unit, not per signal - a unit firing three signals is one row carrying three Signal groups, severity set by its worst signal, so the reader sees one place to fix rather than three reports of the same method. One block per stack: units sharing a stack are rows in one block; units from different stacks get one block each.

```
## Complexity Assessment

**Stack:** {language / framework | unknown}{ - <qualifiers, comma-joined: library or CLI with no framework, unfamiliar stack>}

**Measured by:** {tool and version | "manual count - <stack's tool> not run" | "manual count - no calibrated tool (language unknown)" | "design evaluation - counts from the proposal"}

### Issues                                    {when at least one issue}

- [Severity: High | Medium | Low] {file:line or symbol; in design mode the proposed construct} - {one-line description}
  - Signal: {signal name from table}
  - Measured: {value and threshold, e.g., "cyclomatic 18 / cognitive 24, thresholds 10 / 15" | "n/a - qualitative: <what was observed>"}
  - Simplification: {concrete fix from Patterns}
  - Signal: {next signal on the same unit, in Refactor Priority order}
  - Measured: {...}
  - Simplification: {...}

### No Issues Found                           {instead, when none: one sentence stating no actionable complexity was found - covers both clean code and downgraded rows that were dropped}
```

When evaluating a design rather than code, anchor each row at the proposed construct (layer, abstraction, interface) and `Measured` counts what the proposal declares - layers, branches, parameters, calls per item - against the same thresholds. Proposal items that map to no signal are not rows and are not listed.

## Avoid

- Treating thresholds as absolutes; well-tested stable code may exceed them
- Premature abstraction that trades branch complexity for indirection complexity
- Reporting cyclomatic complexity without cognitive complexity
- Refactoring solely to satisfy metrics
