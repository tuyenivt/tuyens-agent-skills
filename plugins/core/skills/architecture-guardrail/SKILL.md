---
name: architecture-guardrail
description: Detect layer violations, coupling, boundary erosion, and structural drift in code changes; adapt findings to the detected stack.
metadata:
  category: governance
  tags: [architecture, boundaries, coupling, layer-violations, multi-stack]
user-invocable: false
---

# Architecture Guardrail

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing changes for structural drift, not style
- New dependencies between modules, packages, or layers
- Code that bypasses an established abstraction
- Changes to shared, core, or cross-cutting modules

## Rules

- Flag only violations that cross an established boundary; ignore style
- Distinguish intentional refactor from accidental drift - check commit message and adjacent code
- One structural violation outweighs many cosmetic issues
- Use the conventions already present in the codebase as the baseline, not a generic ideal

## Patterns

### Layer Violations

Most backend codebases follow some form of:

```
Presentation (Controller / Handler) -> Service / Domain -> Data Access (Repo / ORM / Query)
```

Frontend equivalent: Component (presentation) -> hook / store / service -> API client or server action (data access).

Flag when the change:

- Calls data access directly from presentation, skipping the service layer
- Puts business logic in controllers, handlers, views, templates, or callbacks
- Returns domain or ORM entities directly in API responses
- Pushes presentation or transport concerns into the domain layer
- Pulls infrastructure (HTTP, broker, DB driver) into the domain layer

After `stack-detect`, translate these into the detected ecosystem's vocabulary - controllers, handlers, actions, resolvers, route functions, components. Framework-specific patterns (fat controllers, fat models, business logic in callbacks or migrations, queries in templates) are concrete instances of these violations.

If the stack is unfamiliar, apply the universal layering above and recommend the user verify against the framework's documentation.

### Module Coupling

- Direct cross-module imports that bypass a defined interface
- Shared mutable state between modules
- Circular dependencies (A -> B -> A)
- Feature module reaching into another feature module's internals
- Cross-runtime imports in a monorepo - server code in a client bundle or vice versa

### Boundary Erosion

- "Just one more" public method added to an internal class
- Implementation types leaking through return values
- Configuration read directly instead of through an abstraction
- Shared "utils" or "common" module growing past ~20 files or mixing domains - signals a missing domain boundary; split or extract

### Drift

- New code that contradicts the existing module structure
- Inconsistent package or directory layout within one module
- Mixed architectural styles - some modules use ports/adapters, the new code does not

Good - specific, localized, references the existing convention:

```
[Must] orders/controllers/orders.rb:45
- Issue: Controller calls Payment.find_by(...), bypassing PaymentService
- Impact: Hidden coupling between orders and payments modules
- Drift: Existing pattern routes payment access through PaymentClient
```

Bad - vague:

```
[Recommend] The architecture could be improved.
```

## Output Format

```
## Architecture Guardrail Findings

**Stack:** {detected language / framework, or "unknown - universal layering applied" when detection fails}

### Violations

#### [Must | Recommend | Question] {file:line}

- Issue: {what boundary or layer was violated}
- Impact: {coupling or drift consequence}
- Drift: {how this diverges from the established pattern; "none observed" when no baseline is visible}

### No Violations Found

{State explicitly if no violations detected - do not omit this section silently}
```

Intent:

- **[Must]**: any Layer Violations pattern, circular dependency, cross-runtime import
- **[Recommend]**: other Module Coupling and Boundary Erosion patterns
- **[Question]**: drift with unclear intent - ask before flagging as a violation

A finding matching patterns in multiple sections takes the highest intent (Must > Recommend > Question).

Omit "No Violations Found" only when violations were listed. Never omit the section entirely - consuming skills use its presence to confirm the check ran.

## Avoid

- Flagging an intentional architectural decision as drift
- Enforcing a style the project has not adopted
- Treating all coupling as equally harmful
- Losing one structural finding under a pile of style nits
