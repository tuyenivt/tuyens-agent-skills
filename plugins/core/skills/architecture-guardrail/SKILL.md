---
name: architecture-guardrail
description: Detect layer violations, coupling, boundary erosion, and structural drift in code changes or a whole-tree audit; adapt to the detected stack.
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
- Auditing a whole tree with no diff - every file is in scope and the codebase's own conventions are the baseline

## Rules

- Flag only violations that cross an established boundary; ignore style
- Distinguish intentional refactor from accidental drift - check the commit message and adjacent code; in an audit with no diff, the commit log of the module stands in for the commit message
- One structural violation outweighs many cosmetic issues
- Use the conventions already present in the codebase as the baseline, not a generic ideal. A convention is established when the project's instruction file documents it or, with no documented rule on the point, the majority of sites in the module follow it; a documented rule to the contrary makes the sites that break it violations, not a convention, however many there are
- When no baseline exists yet (greenfield, first files of a module), the Patterns sections *are* the baseline: flag against universal layering, coupling, and erosion, since the first files set the convention every later one inherits. `Drift:` reads "none observed - establishing the pattern"
- When the established convention itself matches a Layer Violations pattern (controllers routinely hitting the ORM, with no documented rule against it), code following it is not flagged per site: raise the convention once, `[Recommend]`, anchored on the module, naming the migration cost. A violation the code under review newly introduces - a boundary the codebase does respect elsewhere - still flags `[Must]`
- The unit under review is the diff when there is one and every file in scope in an audit; "the code under review" below means whichever applies
- In a monorepo, judge each file by the vocabulary of its own ecosystem, whatever stack-detect named primary

## Patterns

### Layer Violations

Most backend codebases follow some form of:

```
Presentation (Controller / Handler) -> Service / Domain -> Data Access (Repo / ORM / Query)
```

Frontend equivalent: Component (presentation) -> hook / store -> API client or server action (transport) -> server service -> data access. A server component or server action that calls a data-access module is the framework's idiom; it is flagged only when it inlines the query or the business rule.

Repository and ORM are one Data Access tier: a service calling the ORM directly is Drift when the module routes through repositories, not a layer violation.

Flag when the code under review:

- Calls data access directly from presentation, skipping the service layer - reads and writes alike
- Puts business logic in controllers, handlers, views, templates, or callbacks
- Encodes business rules in schema migrations or persistence hooks - domain logic below the service layer
- Returns domain or ORM entities directly in API responses
- Pushes presentation or transport concerns into the domain layer
- Pulls infrastructure (HTTP, broker, DB driver) into the domain layer

After `stack-detect`, translate these into the detected ecosystem's vocabulary - controllers, handlers, actions, resolvers, route functions, components. Framework-specific patterns (fat controllers, business logic in callbacks, queries in templates, a model class that carries both persistence and domain rules) are concrete instances of these violations.

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
- A server-only module exported from a shared package with nothing preventing a client import - the cross-runtime import is possible, not yet made

### Drift

- New code that contradicts the existing module structure
- Inconsistent package or directory layout within one module
- Mixed architectural styles - some modules use ports/adapters, the new code does not

Good - specific, localized, references the existing convention, in the Output Format's shape:

```
#### [Must] app/controllers/orders_controller.rb:45 -> app/models/payment.rb:12

- Issue: Controller calls Payment.find_by(...), bypassing PaymentService
- Impact: Hidden coupling from the orders controller to payment persistence
- Drift: Existing pattern routes payment access through PaymentService
```

Bad - vague:

```
[Recommend] The architecture could be improved.
```

## Output Format

A violation that is a property of a module or a pair of modules - utils accumulation, a circular dependency, mixed styles - anchors there (`common/utils/ (21 files)`, `orders -> billing -> orders`), not on whichever file happens to be under review. A coupling that runs from a call site to a definition in another file anchors as `caller:line -> callee:line`. The same pattern at several sites in one file or module that one fix resolves (route the calls through the service) is one finding anchored at the first site, listing the others in the Issue line. Order findings `[Must]` first.

```
## Architecture Guardrail Findings

**Stack:** {language / framework | unknown - universal layering applied}{ - unfamiliar stack, verify against framework docs}{; monorepo: <dir> = <language / framework>, ...}

### Violations                                  {when at least one violation}

#### [Must | Recommend] {file:line, caller:line -> callee:line, or the module/edge the violation belongs to}

- Issue: {what boundary or layer was violated}
- Impact: {coupling or drift consequence}
- Drift: {how this diverges from the established pattern | "none observed - establishing the pattern" when no baseline is visible | "n/a - violation independent of convention" for a circular dependency or cross-runtime import | "assumed: <assumption> - author to confirm" when intent is unclear | the stated rationale and its ADR when the divergence is declared}

### No Violations Found                         {instead, when none: one sentence stating no violations were detected}
```

The Stack suffix is appended, not substituted: the framework was detected but its layer vocabulary (what it calls controllers, services, repositories) is not one the review knows. `unknown` is no detection at all. In a monorepo the line lists every ecosystem judged with its directory; a finding's path says which vocabulary applied.

Intent:

- **[Must]**: any Layer Violations pattern, circular dependency, cross-runtime import - except a site following an established convention that is itself the violation, which falls under the raise-the-convention-once rule in Rules
- **[Recommend]**: Module Coupling and Boundary Erosion patterns other than the above, and Drift patterns
- **[Recommend]**: drift with unclear intent - the Drift line carries the `assumed:` variant, which is the question to the author

A finding matching patterns in multiple sections takes the highest intent (Must > Recommend).

Stated intent (commit message, ADR) downgrades only the `Drift:` line, never the violation: an intentional layer violation is still [Must] - record the stated rationale in the finding. Give it something to act on, since the code itself may be correct as written: the action is to make the exception explicit and bounded (name the ADR in the code, scope it to this path, state what would end it), not to undo the change.

Exactly one of `### Violations` and `### No Violations Found` is emitted - consuming skills use the presence of one of them to confirm the check ran.

## Avoid

- Flagging an intentional architectural decision as drift
- Enforcing a style the project has not adopted
- Treating all coupling as equally harmful
- Losing one structural finding under a pile of style nits
