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

- Flag at thresholds; do not enforce them as absolutes. Context can justify exceeding any threshold.
- Report cognitive complexity alongside cyclomatic. Cyclomatic counts branches; cognitive captures reading difficulty.
- Calibrate thresholds to the detected stack's norms (Ruby methods are shorter than Java).
- When multiple signals fire on the same unit, fix the highest-severity signal first.

## Patterns

### Signal Table

| Signal                            | Default Threshold      | Fix                                                        |
| --------------------------------- | ---------------------- | ---------------------------------------------------------- |
| Cyclomatic complexity             | > 10                   | Extract by responsibility; replace conditionals with table lookup or polymorphism |
| Cognitive complexity              | > 15                   | Flatten nesting; collapse boolean chains; split mixed concerns |
| Method/function length            | > 20-40 lines          | Extract methods by responsibility                          |
| File/class/module size            | > 200-300 lines        | Split by responsibility (likely SRP violation)             |
| Nesting depth                     | > 3 levels             | Guard clauses, early returns, pattern matching             |
| Parameter count                   | > 5                    | Parameter object, builder, or rebalance responsibilities   |
| Branch chain (switch / if-else)   | > 10 branches          | Map lookup, strategy, or polymorphism                      |
| Inheritance/mixin depth           | > 3-4 levels           | Composition over inheritance                               |
| Indirection depth                 | > 3 pass-through delegation hops | Collapse layers that add no logic; inline single-use wrappers |
| External calls per method         | > 3                    | Extract orchestration layer; explicit error handling per call |
| Error-handling complexity         | Broad catch-all, empty catch, nested try > 2 | Specific exception types, Result/Either, error handler delegation |

Cognitive complexity: +1 per control-flow structure, +1 extra per nesting level it sits under, +1 per sequence of mixed boolean operators. A flat switch/match or top-level guard-clause sequence counts +1 total - branch count does not multiply the score.

### Severity

- **High**: any signal at or beyond ~1.5x its threshold (cyclomatic > 15, cognitive > 22, file > 400 lines, nesting > 4), or any signal blocking comprehension
- **Medium**: over threshold but below ~1.5x
- **Low**: approaching threshold but not yet a maintenance burden

Downgrade rule: a flat exhaustive mapping (uniform one-line branches, no shared mutable state) is at most Low regardless of branch count; suggest a data table only when branches duplicate logic.

### Refactor Priority

When several signals fire together, address in order: (1) externalize service calls, (2) flatten nesting with guard clauses, (3) extract by responsibility. Each step often removes downstream signals.

### Stack Calibration

After `stack-detect`, adjust thresholds to ecosystem norms and prefer the stack's standard linting/analysis tool for measured metrics. Use universal thresholds if the stack is unknown and recommend a calibrated tool.

## Output Format

```
## Complexity Assessment

**Stack:** {language / framework}

### Issues

- [Severity: High | Medium | Low] {file:line or symbol} - {one-line description}
  - Signal: {signal name from table}
  - Measured: {e.g., "cyclomatic 18, threshold 10"}
  - Simplification: {concrete fix from Patterns}

### No Issues Found

{Include only when no issues were listed. State that complexity is within thresholds.}
```

Omit "No Issues Found" when issues are listed.

## Avoid

- Treating thresholds as absolutes; well-tested stable code may exceed them
- Premature abstraction that trades branch complexity for indirection complexity
- Reporting cyclomatic complexity without cognitive complexity
- Refactoring solely to satisfy metrics
