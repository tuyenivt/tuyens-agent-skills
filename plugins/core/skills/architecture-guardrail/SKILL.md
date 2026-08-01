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
- When no baseline exists yet (greenfield, first files of a module), the Layer Violations list *is* the baseline: flag against universal layering, since the first files set the convention every later one inherits. `Drift:` reads "none observed - establishing the pattern."

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

If the stack is unfamiliar, apply the universal layering above and append `- unfamiliar stack, verify against framework docs` to the **Stack:** line.

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

#### [Must | Recommend] {file:line, or the module/edge the violation belongs to}

- Issue: {what boundary or layer was violated}
- Impact: {coupling or drift consequence}
- Drift: {how this diverges from the established pattern; "none observed" when no baseline is visible}

A violation that is a property of a module or a pair of modules - utils accumulation, a circular dependency, mixed styles - anchors there (`common/utils/ (21 files)`, `orders -> billing -> orders`), not on whichever file the diff happened to touch. The file that crossed the threshold is not the defect.

### No Violations Found

{State explicitly if no violations detected - do not omit this section silently}
```

Intent:

- **[Must]**: any Layer Violations pattern, circular dependency, cross-runtime import
- **[Recommend]**: other Module Coupling and Boundary Erosion patterns
- **[Recommend]**: drift with unclear intent - state the assumption being checked and ask the author to confirm in the same finding

A finding matching patterns in multiple sections takes the highest intent (Must > Recommend).

Stated intent (commit message, ADR) downgrades only the `Drift:` line, never the violation: an intentional layer violation is still [Must] - record the stated rationale in the finding. Give it something to act on, since the code itself may be correct as written: the action is to make the exception explicit and bounded (name the ADR in the code, scope it to this path, state what would end it), not to undo the change.

Emit exactly one of `### Violations` and `### No Violations Found` - consuming skills use the presence of one of them to confirm the check ran.

## Avoid

- Flagging an intentional architectural decision as drift
- Enforcing a style the project has not adopted
- Treating all coupling as equally harmful
- Losing one structural finding under a pile of style nits
