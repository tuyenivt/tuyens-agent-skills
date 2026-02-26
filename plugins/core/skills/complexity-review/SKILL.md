---
name: complexity-review
description: Complexity assessment — cyclomatic complexity, cognitive load, abstraction depth. Auto-detects project stack and adapts thresholds to the detected ecosystem.
metadata:
  category: governance
  tags: [complexity, review, maintainability, multi-stack]
user-invocable: false
---

# Complexity Review

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During code review to flag overly complex methods or modules
- When refactoring to identify simplification targets
- When evaluating whether a design is over-engineered

## Universal Rules (All Stacks)

- Flag methods/functions with cyclomatic complexity > 10
- Flag files/classes with > 300 lines (indicates SRP violation)
- Flag call chains deeper than 3 levels of abstraction
- Complexity must justify itself — simple problems deserve simple solutions
- Prefer flat control flow over deeply nested conditionals

---

## Complexity Signals

Common complexity signals across all ecosystems:

| Signal                                         | Threshold                                     | Fix                                            |
| ---------------------------------------------- | --------------------------------------------- | ---------------------------------------------- |
| Long method/function                           | > 20-40 lines (varies by language convention) | Extract methods/functions by responsibility    |
| Deeply nested conditionals                     | > 3 levels                                    | Guard clauses, early returns, pattern matching |
| Large file/class/module                        | > 200-300 lines                               | Split by responsibility                        |
| Constructor/initializer with many dependencies | > 5 params                                    | Facade or reorganize responsibilities          |
| Long switch/case or if-else chain              | > 10 branches                                 | Map lookup, strategy pattern, or polymorphism  |

Note: Exact thresholds vary by ecosystem. Some languages are naturally more verbose than others. After loading stack-detect, calibrate thresholds to the norms of the detected language.

## Simplification Patterns

Universal simplification strategies:

- **Guard clauses and early returns**: Eliminate nesting by returning early on error conditions
- **Pattern matching**: Use the language's pattern matching feature (if available) instead of nested if/else
- **Validation delegation**: Move input validation to the framework's validation layer instead of manual checks
- **Centralized error handling**: Use the framework's global error handling instead of per-endpoint try/catch
- **Extraction**: Extract complex logic into focused, named functions/methods with single responsibilities
- **Callback/hook simplification**: If the framework uses callback patterns, prefer explicit orchestration over long callback chains

## Stack-Specific Guidance

After loading stack-detect, apply complexity review using the conventions of the detected ecosystem:

- Calibrate method/function length thresholds to the language's norm (e.g., methods tend to be shorter in Ruby than in Java)
- Use the ecosystem's standard linting/analysis tools for complexity metrics
- Apply the framework's recommended patterns for reducing controller/handler complexity (service extraction, middleware, etc.)
- Identify framework-specific complexity signals (e.g., callback chains, middleware stacking, overly wide interfaces)

If the detected stack is unfamiliar, apply the universal thresholds above and recommend the user consult their ecosystem's linting tools for calibrated thresholds.

---

## Avoid (All Stacks)

- Complexity metrics as absolute rules — context matters
- Refactoring stable, well-tested code solely to reduce metrics
- Premature abstraction to "reduce complexity" (adds indirection complexity)
- Ignoring cognitive complexity in favor of only cyclomatic complexity
