---
name: dependency-impact-analysis
description: Map consumers of a changed contract, classify breaking vs additive, derive deployment ordering for shared libraries and services.
metadata:
  category: ops
  tags: [deployment, dependencies, impact, ordering, compatibility]
user-invocable: false
---

# Dependency Impact Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Change affects shared libraries, APIs, events, or data contracts consumed elsewhere
- Planning deployment order for multi-service or multi-module changes
- Upgrading a dependency consumed by multiple services
- Deciding whether the change needs coordinated rollout

## Rules

- Map the dependency graph before classifying impact.
- Classify breaking vs additive per consumer, not in aggregate.
- Deployment order respects dependency direction: additive provider-first, removal consumer-first.
- Breaking changes require an expand-contract migration plan (see `ops-backward-compatibility`).
- Treat minor version bumps as potentially breaking until release notes prove otherwise.

## Patterns

### Dependency Mapping

For each changed component, identify:

1. **Direct consumers** - services/modules that import or call it
2. **Transitive consumers** - those that depend on direct consumers
3. **Contract type** - API, event schema, shared library, DB view
4. **Coupling** - compile-time (strong), runtime (weak), event (loose)

### Impact Classification

| Change Type             | Consumer Impact     | Deployment Constraint                                          |
| ----------------------- | ------------------- | -------------------------------------------------------------- |
| Additive (new field)    | None if optional    | Provider first; consumers update at their pace                 |
| Modification (rename)   | Breaking            | Expand-contract via `ops-backward-compatibility`               |
| Removal (drop field)    | Breaking            | Verify no consumers, then remove                               |
| Behavioral (logic)      | Contract-dependent  | Canary with consumer monitoring                                |
| Performance (latency)   | Cascading risk      | Load test with consumer traffic profile                        |
| Version upgrade (minor) | Possibly breaking   | Check release notes for deprecations and behavior changes      |
| Version upgrade (major) | Breaking            | Compatibility matrix; upgrade one module first                 |

### Version Upgrade Specifics

- **Transitive conflicts**: new version may require updated transitives (e.g., framework requiring newer runtime). Check against each module.
- **Phased rollout**: in monorepos with a shared parent, upgrade one module and run its tests before propagating.
- **Deprecated APIs**: flag consumer usage of newly deprecated APIs; they may be removed in the next major.
- **Blocker strategies** when no compatible transitive exists: **wait** (imminent release), **swap** to a compatible alternative, **shim** if surface is small, **fork** as last resort. Document the strategy and removal condition.

### Deployment Ordering Rules

- Provider before consumer for additive changes
- Consumer before provider for removals
- Simultaneous only when feature-flagged on both sides
- Expand-contract for breaking changes

### Good

```
Changed: OrderService GET /orders/{id} - added optional shippingEstimate
Direct consumers: FulfillmentService, CustomerPortal, AdminDashboard
Impact: Additive - no breaking change
Order: Deploy OrderService first; consumers update at own pace
Risk: FulfillmentService strict deserialization may reject unknown fields
Mitigation: Confirm lenient JSON parsing before deploy
```

### Bad

```
Changed the Order API. Should be fine for everyone.
```

## Output Format

```
## Dependency Impact Assessment

### Consumers Affected

| Component Changed | Direct Consumers | Transitive Consumers | Contract Type | Coupling |
| ----------------- | ---------------- | -------------------- | ------------- | -------- |
| {name} | {list or "none"} | {list or "none"} | {API / event / library / DB view} | {compile-time / runtime / event} |

### Deployment Order

1. {step with reason}
2. {step with reason}

### Breaking Changes Requiring Migration

{For each: reference `ops-backward-compatibility` for the expand-contract plan, or "none"}

### No Impact

{Include only when the change has no consumer impact}
```

Always produce the Consumers Affected table. Omit "No Impact" when impact was found.

## Avoid

- Deploying provider changes without mapping consumers
- Assuming consumers handle new fields gracefully
- Breaking changes without a migration plan
- Deploying consumer before provider for additive changes
- Ignoring transitive consumers
