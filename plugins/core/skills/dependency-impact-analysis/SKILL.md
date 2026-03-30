---
name: dependency-impact-analysis
description: Library and service dependency graph analysis - deployment ordering, breaking change detection, and compatibility impact. Focused on dependency graph and sequencing, not code-level blast radius (use review-blast-radius for that).
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
- Breaking changes require a compatibility migration plan -- use skill: `ops-backward-compatibility` for expand-contract mechanics
- Do not assume consumers will update immediately

## Pattern

### Dependency Mapping

For each changed component, identify:

1. **Direct consumers** -- services that call or import this component
2. **Transitive consumers** -- services that depend on direct consumers
3. **Contract type** -- API, event schema, shared library, database view
4. **Coupling strength** -- compile-time (strong) vs runtime (weak) vs event (loose)

### Impact Classification

| Change Type             | Consumer Impact     | Deployment Constraint                                                                                  |
| ----------------------- | ------------------- | ------------------------------------------------------------------------------------------------------ |
| Additive (new field)    | None if optional    | Deploy provider first                                                                                  |
| Modification (rename)   | Breaking            | Use skill: `ops-backward-compatibility`                                                                |
| Removal (drop field)    | Breaking            | Verify no consumers, then remove                                                                       |
| Behavioral (logic)      | Depends on contract | Canary with consumer monitoring                                                                        |
| Performance (latency)   | Cascading risk      | Load test with consumer traffic                                                                        |
| Version upgrade (minor) | Possibly breaking   | Check release notes for deprecations/removals; minor versions can contain breaking changes in practice |
| Version upgrade (major) | Breaking            | Compatibility matrix review + upgrade one module/service first before rolling to all                   |

### Dependency Version Upgrade Impact

When the change is a version upgrade rather than a code change, the standard consumer-mapping approach still applies, but the impact surface is different:

1. **Transitive dependency conflicts**: The new version may require different transitive dependencies (e.g., Spring Boot 3.5 requires Java 21 minimum). Check the upgraded library's requirements against each module's runtime.
2. **Minor version breaking changes**: Treat minor version bumps as potentially breaking - check the official migration guide and release notes for deprecated APIs, removed defaults, or behavior changes.
3. **Phased rollout for shared parent dependencies**: In a monorepo with a shared parent POM or root build file, upgrade one module first and run its full test suite before propagating to other modules.
4. **Deprecated API removal window**: If consumers use APIs that are deprecated in the new version, flag them - they may be removed in the next major version.

**Upgrade blockers:** When a transitive dependency has no version compatible with the target upgrade:
- **Wait**: Monitor the dependency's release timeline; defer the upgrade if a compatible release is imminent
- **Find alternative**: Replace the incompatible dependency with a compatible alternative that provides equivalent functionality
- **Shim/bridge**: Use a compatibility adapter if the incompatible API surface is small
- **Fork (last resort)**: Maintain a patched fork temporarily; track the upstream for when a compatible version is released

Document the blocker, the chosen strategy, and the conditions under which the workaround can be removed.

### Deployment Ordering

- **Provider before consumer** for additive changes
- **Consumer before provider** for removal changes
- **Simultaneous** only when feature-flagged on both sides
- **Expand-contract** for breaking changes -- see skill: `ops-backward-compatibility` for detailed migration plan

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

## Output Format

Consuming workflow skills depend on this structure to determine deployment ordering and consumer impact.

```
## Dependency Impact Assessment

### Consumers Affected

| Component Changed | Direct Consumers | Transitive Consumers | Contract Type | Coupling |
| ----------------- | ---------------- | -------------------- | ------------- | -------- |
| {name} | {list or "none"} | {list or "none"} | {API / event / library / DB view} | {compile-time / runtime / event} |

### Deployment Order

{ordered list, e.g.:}
1. Deploy {provider} first - additive change, consumers update at own pace
2. Notify {consumer list} of upcoming breaking change
3. Deploy {consumer} after {provider} has been running for {N} days

### Breaking Changes Requiring Migration

{For each breaking change: reference `ops-backward-compatibility` for expand-contract plan}

### No Impact

{State explicitly if the change has no consumer impact - do not omit this section silently}
```

Always produce the Consumers Affected table. Omit "No Impact" if impact was found.

## Avoid

- Deploying provider changes without mapping consumers
- Assuming all consumers handle new fields gracefully
- Breaking changes without a migration plan (see skill: `ops-backward-compatibility`)
- Deploying consumer before provider for additive changes
- Ignoring transitive dependency impact
