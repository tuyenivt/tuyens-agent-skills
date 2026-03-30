---
name: backend-coding-standards
description: Coding conventions adapted to the detected project stack. Enforces language-appropriate naming, structure, and anti-pattern detection.
metadata:
  category: governance
  tags: [standards, conventions, style, multi-stack]
user-invocable: false
---

# Coding Standards

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During code review to enforce language and framework conventions
- When writing new code to follow established project patterns
- When onboarding to a codebase to understand its style expectations

## Universal Rules (All Stacks)

- No emojis in code, logs, comments, commit messages, or documentation
- Follow the naming conventions of the detected language (do not mix styles)
- Prefer explicit over clever - readability over brevity
- One responsibility per file/class/module - no god objects
- No god functions: individual functions/methods exceeding 50-80 lines should be decomposed regardless of class size

---

## Naming Conventions

Every language has established naming conventions. Apply the conventions of the detected stack:

- **Case style**: Use the naming convention standard for the detected language (e.g., camelCase, snake_case, PascalCase, kebab-case)
- **Consistency**: Do not mix naming styles from different languages within the same codebase
- **Descriptiveness**: Short names in small scopes; descriptive names in larger scopes
- **PHP/Laravel**: PSR-12 coding style, camelCase for methods/variables, PascalCase for classes, snake_case for database columns and config keys. Laravel conventions: singular model names (`Order`), plural table names (`orders`), `{Model}Controller`, `{Model}Request`, `{Model}Resource`

## Dependency Management

- Prefer the dependency injection pattern native to the detected framework
- Avoid tight coupling to concrete implementations - depend on abstractions where the framework supports it
- Follow the detected framework's conventions for organizing dependencies and configuration

## Layering and Structure

- Follow the layered architecture pattern established in the project
- Presentation layer should be thin - delegate business logic to service/domain layer
- Do not expose data layer entities directly in API responses - use response shaping appropriate to the framework (DTOs, serializers, response structs, etc.)

## Anti-Pattern Detection

After loading stack-detect, check for anti-patterns specific to the detected ecosystem. Common categories include:

- **Concurrency anti-patterns**: Using deprecated or unsafe concurrency primitives for the detected runtime
- **Testing anti-patterns**: Using deprecated test utilities or patterns that the framework has superseded
- **Performance anti-patterns**: Connection pool misconfiguration, missing query optimization, improper caching
- **Security anti-patterns**: Disabled security features, exposed internals, missing input validation
- **Structural anti-patterns**: Circular imports/dependencies between modules, files placed in the wrong architectural layer directory (e.g., service classes in a controllers/ directory), package structure that contradicts the layered architecture

If the detected stack is unfamiliar, apply the universal rules above and recommend the user verify against their framework's documentation and linting tools.

### Good: Specific finding with fix

```
[Severity: Medium] src/handlers/user_handler.go:12 - Mixed naming styles: camelCase `getUserById` in a Go codebase that uses snake_case elsewhere
  - Rule: Go convention is MixedCaps/mixedCaps (exported/unexported), not snake_case or camelCase with lowercase prefix
  - Fix: Rename to `GetUserByID` (exported) or `getUserByID` (unexported). Note: `ID` not `Id` per Go conventions.
```

### Bad: Vague style comment

```
[Suggestion] The naming could be more consistent across the codebase.
```

---

## Output Format

This is the contract that consuming workflow skills depend on. Produce findings in this structure so that callers can integrate results consistently.

```
## Coding Standards Findings

**Stack:** {detected language / framework}

### Violations

- [Severity: High | Medium | Low] {file:line if available} - {description of violation}
  - Rule: {the naming/structure/anti-pattern rule violated}
  - Fix: {concrete correction}

### Anti-Patterns Detected

- {anti-pattern name}: {location and impact}

### No Issues Found

{State explicitly if no violations detected - do not omit this section silently}
```

**Severity guidance:**

- **High**: Breaks correctness, security, or layering (e.g., god class, exposed entity in API response)
- **Medium**: Structural issue that will compound over time (e.g., mixed naming styles, magic numbers)
- **Low**: Style drift with no structural consequence (e.g., inconsistent comment style)

Omit the Anti-Patterns section if none detected. Omit "No Issues Found" if violations were listed.

## Avoid (All Stacks)

- Mixing naming conventions from different languages
- God classes / modules with > 300 lines
- Magic numbers without named constants
- Dead code left in "just in case" - delete it
- Comments that restate the code instead of explaining why
- Circular imports between modules (refactor to extract shared types, use dependency injection, or restructure module boundaries)
- Placing files in directories that contradict their architectural role (e.g., service classes in a controllers/ directory)
