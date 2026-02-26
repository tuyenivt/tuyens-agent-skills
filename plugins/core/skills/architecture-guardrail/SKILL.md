---
name: architecture-guardrail
description: Layer violation and boundary erosion detection for structural integrity. Auto-detects project stack and adapts guardrails to the detected ecosystem.
metadata:
  category: governance
  tags: [architecture, boundaries, coupling, layer-violations, multi-stack]
user-invocable: false
---

# Architecture Guardrail

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During code review to detect structural drift
- When changes introduce new dependencies between modules
- When code bypasses established abstractions or layers
- When reviewing changes to shared or core modules

## Rules

- Focus on structural integrity, not implementation style
- Flag violations only when they cross established boundaries
- Distinguish intentional refactoring from accidental drift
- One boundary violation is more important than ten style issues

## Pattern

### Layer Violations — Universal Principles

Common layer violations regardless of framework:

- Presentation → Data access (skipping business logic layer)
- Business logic → Presentation (reverse dependency)
- Domain objects in API responses (skipping response shaping)
- Business logic in presentation layer (responsibility leak)
- Infrastructure concerns in domain layer

Most backend frameworks follow a layered architecture pattern:

```
Presentation (Controllers/Handlers) → Service/Business Logic → Data Access (Repository/ORM)
```

**Violation detection**: When code in the presentation layer directly accesses the data layer, or when business logic appears in controllers/handlers instead of the service layer, flag it as a layer violation.

### Stack-Specific Guidance

After loading stack-detect, apply layer violation detection using the idioms of the detected stack. For example:

- In frameworks with annotation-based architectures (e.g., Spring), controllers should delegate to service classes, not access repositories directly
- In MVC frameworks (e.g., Rails, Django, Phoenix), controllers/actions should be thin — business logic belongs in service objects or model methods
- In handler-based architectures (e.g., Go HTTP frameworks, Express), handlers should delegate to service packages, not perform business logic or direct DB access
- Framework-specific violations (e.g., fat controllers, business logic in callbacks, circular package imports) should be detected based on the conventions of the detected ecosystem

If the detected stack is unfamiliar, apply the universal layering principles above and recommend the user verify against their framework's documentation.

### Module Coupling (All Stacks)

Detect new coupling between previously independent modules:

- Direct imports across module boundaries instead of through defined interfaces
- Shared mutable state between modules
- Circular dependencies (A → B → A)
- Feature module depending on another feature module's internals

### Boundary Erosion (All Stacks)

Detect gradual weakening of established abstractions:

- Adding "just one more" public method to an internal class/module
- Exposing implementation details through return types
- Domain logic leaking into infrastructure layer
- Configuration values used directly instead of through abstraction

### Drift Detection (All Stacks)

Compare change patterns against established conventions:

- New code that contradicts existing module structure
- Inconsistent package/directory organization within the same module
- Mixed architectural styles (some modules use ports/adapters, new code does not)

### Good: Specific guardrail finding

```
[High] order-service/app/controllers/orders_controller.rb:45
- Issue: Controller directly queries Payment model, bypassing PaymentService
- Impact: Creates hidden coupling between order and payment modules
- Drift: Existing pattern uses inter-service communication via PaymentClient
```

### Bad: Vague architectural concern

```
[Suggestion] The architecture could be improved.
```

## Avoid

- Flagging intentional architectural decisions as violations
- Enforcing a specific architecture style not established in the project
- Treating all coupling as equally harmful
- Missing the forest for the trees — one structural violation matters more than many style issues
