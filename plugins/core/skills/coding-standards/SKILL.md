---
name: coding-standards
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
- Prefer explicit over clever — readability over brevity
- One responsibility per file/class/module — no god objects

---

## Naming Conventions

Every language has established naming conventions. Apply the conventions of the detected stack:

- **Case style**: Use the naming convention standard for the detected language (e.g., camelCase, snake_case, PascalCase, kebab-case)
- **Consistency**: Do not mix naming styles from different languages within the same codebase
- **Descriptiveness**: Short names in small scopes; descriptive names in larger scopes

## Dependency Management

- Prefer the dependency injection pattern native to the detected framework
- Avoid tight coupling to concrete implementations — depend on abstractions where the framework supports it
- Follow the detected framework's conventions for organizing dependencies and configuration

## Layering and Structure

- Follow the layered architecture pattern established in the project
- Presentation layer should be thin — delegate business logic to service/domain layer
- Do not expose data layer entities directly in API responses — use response shaping appropriate to the framework (DTOs, serializers, response structs, etc.)

## Anti-Pattern Detection

After loading stack-detect, check for anti-patterns specific to the detected ecosystem. Common categories include:

- **Concurrency anti-patterns**: Using deprecated or unsafe concurrency primitives for the detected runtime
- **Testing anti-patterns**: Using deprecated test utilities or patterns that the framework has superseded
- **Performance anti-patterns**: Connection pool misconfiguration, missing query optimization, improper caching
- **Security anti-patterns**: Disabled security features, exposed internals, missing input validation

If the detected stack is unfamiliar, apply the universal rules above and recommend the user verify against their framework's documentation and linting tools.

---

## Avoid (All Stacks)

- Mixing naming conventions from different languages
- God classes / modules with > 300 lines
- Magic numbers without named constants
- Dead code left in "just in case" — delete it
- Comments that restate the code instead of explaining why
