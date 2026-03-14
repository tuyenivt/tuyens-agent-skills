---
name: complexity-review
description: Complexity assessment - cyclomatic complexity, cognitive load, abstraction depth. Auto-detects project stack and adapts thresholds to the detected ecosystem.
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
- Complexity must justify itself - simple problems deserve simple solutions
- Prefer flat control flow over deeply nested conditionals

---

## Complexity Signals

Common complexity signals across all ecosystems:

| Signal                                         | Threshold                                     | Fix                                                                                        |
| ---------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Long method/function                           | > 20-40 lines (varies by language convention) | Extract methods/functions by responsibility                                                |
| Deeply nested conditionals                     | > 3 levels                                    | Guard clauses, early returns, pattern matching                                             |
| Large file/class/module                        | > 200-300 lines                               | Split by responsibility                                                                    |
| Constructor/initializer with many dependencies | > 5 params                                    | Facade or reorganize responsibilities                                                      |
| Long switch/case or if-else chain              | > 10 branches                                 | Map lookup, strategy pattern, or polymorphism                                              |
| External service calls in one method           | > 3 calls                                     | Coordinator pattern - extract to orchestration layer with explicit error handling per call |

Note: Exact thresholds vary by ecosystem. Some languages are naturally more verbose than others. After loading stack-detect, calibrate thresholds to the norms of the detected language.

### Cognitive Complexity

Cyclomatic complexity counts decision points; cognitive complexity measures how hard the code is to read. Cognitive complexity increases with:

- Each nesting level: `+1` per level for conditionals and loops
- Structural complexity breaks (early `return`, `break`, `continue`, `goto`): `+1`
- Boolean operator sequences (`&&`, `||`): `+1` per unique sequence

Flag high cognitive complexity (estimated > 15) even when cyclomatic complexity is within threshold - deeply nested code with few branches is still hard to reason about.

### Refactoring Priority

When multiple complexity signals fire simultaneously, fix in this order:

1. **External service calls first** - extract into named wrapper methods with explicit timeout/error handling per call
2. **Guard clauses** - invert nested conditionals into early returns to flatten nesting
3. **Extract by responsibility** - split long methods into focused single-purpose functions

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

## Output Format

Consuming workflow skills depend on this structure to surface complexity issues consistently.

```
## Complexity Assessment

**Stack:** {detected language / framework}

### Issues

- [Severity: High | Medium | Low] {file:line or function/class name} - {description of complexity issue}
  - Signal: {which signal triggered - cyclomatic complexity | file size | nesting depth | abstraction depth}
  - Measured: {e.g., "cyclomatic complexity 18, threshold 10" or "347 lines, threshold 300"}
  - Simplification: {concrete pattern from the detected stack - guard clauses, extraction, etc.}

### No Issues Found

{State explicitly if complexity is within acceptable thresholds - do not omit this section silently}
```

**Severity guidance:**

- **High**: Cyclomatic complexity > 15, or file > 400 lines, or abstraction depth > 4 levels
- **Medium**: Cyclomatic complexity 10-15, or file 300-400 lines, or nesting > 3 levels
- **Low**: Approaching thresholds but not yet a maintenance burden

Omit "No Issues Found" if issues were listed.

## Avoid (All Stacks)

- Complexity metrics as absolute rules - context matters
- Refactoring stable, well-tested code solely to reduce metrics
- Premature abstraction to "reduce complexity" (adds indirection complexity)
- Ignoring cognitive complexity in favor of only cyclomatic complexity
