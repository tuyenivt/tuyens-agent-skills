---
name: backend-coding-standards
description: Review code for language-appropriate naming, layering, dependency injection, and anti-patterns. Adapts to the detected stack.
metadata:
  category: governance
  tags: [standards, conventions, style, multi-stack]
user-invocable: false
---

# Coding Standards

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Code review for naming, layering, and framework conventions
- Writing new code to match established project patterns
- Onboarding to understand a codebase's style expectations

## Rules

- Apply the detected language's naming convention (camelCase, snake_case, PascalCase, kebab-case). Do not mix styles within a codebase.
- Short names in small scopes; descriptive names in larger scopes.
- One responsibility per file/class/module. Functions/methods over 50 lines must be decomposed (up to 80 for verbose languages - calibrate to stack norms).
- Files live in directories matching their architectural role (no service classes in `controllers/`).
- Presentation layer stays thin - business logic belongs in the service or domain layer.
- Responses use DTOs / serializers / response structs, never data-layer entities.
- Use the framework's native dependency injection. Depend on abstractions where the framework supports it.
- No emojis in code, logs, comments, commit messages, or documentation.
- Idiomatic error handling for the language: no bare or blanket catches that swallow errors, no discarded error returns, no panic/abort/raise for recoverable failures in request paths.
- No magic numbers - extract named constants.
- No dead code - delete it.
- Comments explain why, not what.

## Patterns

### Naming finding (specific, fixable)

```
# Bad - vague style comment
[Recommend] The naming could be more consistent across the codebase.

# Good - specific finding with fix
[Recommend] src/handlers/user_handler.go:12 - Mixed naming styles:
camelCase `getUserById` in a Go codebase that uses MixedCaps elsewhere
  - Rule: Go convention is MixedCaps/mixedCaps; initialisms are upper-case (ID, not Id)
  - Fix: Rename to `GetUserByID` (exported) or `getUserByID` (unexported)
```

### Layering violation

```
# Bad - controller returns the ORM entity
return userRepository.findById(id)

# Good - controller returns a DTO via the service
return userService.getProfile(id)  // -> UserProfileDto
```

### Anti-pattern categories to scan

After stack-detect, check for ecosystem-appropriate instances of:

- **Concurrency**: deprecated or unsafe primitives for the detected runtime
- **Testing**: deprecated test utilities the framework has superseded
- **Performance**: connection pool misconfiguration, N+1 queries, missing query bounds
- **Security**: disabled framework safeguards, exposed internals, missing input validation
- **Structural**: circular imports, files in the wrong layer directory, package structure that contradicts the documented architecture

If stack-detect output is missing, infer the language from file extensions and syntax and report `**Stack:**` with an `(inferred)` marker. If the stack is unfamiliar, apply the language-agnostic rules (responsibility, layering, DTO boundaries, error handling, magic numbers, dead code) and recommend the user verify naming and DI conventions against the framework's docs and linters.

## Output Format

Consuming workflows parse this structure.

```
## Coding Standards Findings

**Stack:** {detected language / framework}

### Violations

- [Must | Recommend] {file:line} - {description}
  - Rule: {the naming/structure/anti-pattern rule violated}
  - Fix: {concrete correction}

### Anti-Patterns Detected

- {anti-pattern name}: {location and impact}

### No Issues Found

{State explicitly if no violations - do not omit this section silently}
```

**Intent:**

- **[Must]**: Breaks correctness, security, or layering - logic or data crossing layer boundaries (god class, entity exposed in API, business logic in the presentation layer, swallowed errors, disabled security feature)
- **[Recommend]**: Structural drift that compounds (mixed naming, magic numbers, file placed in the wrong layer directory)
- **[Recommend]**: Ambiguous case where the rule may or may not apply - state the assumption and ask the author to confirm in the same finding

Omit Anti-Patterns if none. Omit "No Issues Found" if violations were listed.

## Avoid

- Applying one language's naming or idioms to a different detected stack
- Modules / classes over ~300 lines without decomposition
- Circular imports (extract shared types, inject dependencies, or restructure module boundaries)
- Findings without `file:line`, the rule violated, and a concrete fix
