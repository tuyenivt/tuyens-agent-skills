---
name: dependency-impact-analysis
description: Deployment ordering and dependency change impact assessment
metadata:
  category: ops
  tags: [deployment, dependencies, impact, ordering, compatibility]
user-invocable: false
---

# Dependency Impact Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- When a change affects shared libraries, APIs, or data contracts consumed by other services
- When planning deployment order for multi-service changes
- When upgrading a dependency that multiple services consume
- When assessing whether a change requires coordinated deployment

## Rules

- Map the dependency graph before assessing impact
- Changes to shared contracts require consumer impact assessment
- Deployment order must respect the dependency direction
- Breaking changes require a compatibility migration plan -- use skill: `backward-compatibility-analysis` for expand-contract mechanics
- Do not assume consumers will update immediately

## Pattern

### Dependency Mapping

For each changed component, identify:

1. **Direct consumers** -- services that call or import this component
2. **Transitive consumers** -- services that depend on direct consumers
3. **Contract type** -- API, event schema, shared library, database view
4. **Coupling strength** -- compile-time (strong) vs runtime (weak) vs event (loose)

### Impact Classification

| Change Type           | Consumer Impact     | Deployment Constraint                        |
| --------------------- | ------------------- | -------------------------------------------- |
| Additive (new field)  | None if optional    | Deploy provider first                        |
| Modification (rename) | Breaking            | Use skill: `backward-compatibility-analysis` |
| Removal (drop field)  | Breaking            | Verify no consumers, then remove             |
| Behavioral (logic)    | Depends on contract | Canary with consumer monitoring              |
| Performance (latency) | Cascading risk      | Load test with consumer traffic              |

### Deployment Ordering

- **Provider before consumer** for additive changes
- **Consumer before provider** for removal changes
- **Simultaneous** only when feature-flagged on both sides
- **Expand-contract** for breaking changes -- see skill: `backward-compatibility-analysis` for detailed migration plan

### Good: Specific impact with deployment order

```
Changed: OrderService API - added shippingEstimate field to GET /orders/{id}
Direct consumers: FulfillmentService, CustomerPortal, AdminDashboard
Impact: Additive (new optional field) - no breaking change
Deployment order: OrderService first, consumers update at their own pace
Risk: FulfillmentService strict deserialization may reject unknown fields
Mitigation: Verify FulfillmentService uses lenient JSON parsing before deploy
```

### Bad: Impact without consumer analysis

```
Changed the Order API. Should be fine for everyone.
```

## Avoid

- Deploying provider changes without mapping consumers
- Assuming all consumers handle new fields gracefully
- Breaking changes without a migration plan (see skill: `backward-compatibility-analysis`)
- Deploying consumer before provider for additive changes
- Ignoring transitive dependency impact
