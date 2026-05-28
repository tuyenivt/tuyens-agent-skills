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
- One responsibility per file/class/module. Functions/methods over 50-80 lines must be decomposed.
- Files live in directories matching their architectural role (no service classes in `controllers/`).
- Presentation layer stays thin - business logic belongs in the service or domain layer.
- Responses use DTOs / serializers / response structs, never data-layer entities.
- Use the framework's native dependency injection. Depend on abstractions where the framework supports it.
- No emojis in code, logs, comments, commit messages, or documentation.
- No magic numbers - extract named constants.
- No dead code - delete it.
- Comments explain why, not what.

## Patterns

### Naming finding (specific, fixable)

```
# Bad - vague style comment
[Suggestion] The naming could be more consistent across the codebase.

# Good - specific finding with fix
[Severity: Medium] src/handlers/user_handler.go:12 - Mixed naming styles:
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

If the stack is unfamiliar, apply the universal rules and recommend the user verify against the framework's docs and linters.

## Output Format

Consuming workflows parse this structure.

```
## Coding Standards Findings

**Stack:** {detected language / framework}

### Violations

- [Severity: High | Medium | Low] {file:line} - {description}
  - Rule: {the naming/structure/anti-pattern rule violated}
  - Fix: {concrete correction}

### Anti-Patterns Detected

- {anti-pattern name}: {location and impact}

### No Issues Found

{State explicitly if no violations - do not omit this section silently}
```

**Severity:**

- **High**: Breaks correctness, security, or layering (god class, entity exposed in API, disabled security feature)
- **Medium**: Structural drift that compounds (mixed naming, magic numbers, wrong-layer placement)
- **Low**: Cosmetic drift with no structural impact (inconsistent comment style)

Omit Anti-Patterns if none. Omit "No Issues Found" if violations were listed.

## Avoid

- Mixing naming conventions from different languages
- Modules / classes over ~300 lines without decomposition
- Dead code kept "just in case"
- Circular imports (extract shared types, inject dependencies, or restructure module boundaries)
- Files placed contrary to their architectural role
