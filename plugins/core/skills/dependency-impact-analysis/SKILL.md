---
name: dependency-impact-analysis
description: Map consumers of a changed contract, classify breaking vs additive, derive deployment ordering for shared libraries and services.
metadata:
  category: ops
  tags: [deployment, dependencies, impact, ordering, compatibility]
user-invocable: false
---

# Dependency Impact Analysis

## When to Use

- Change affects shared libraries, APIs, events, or data contracts consumed elsewhere
- Planning deployment order for multi-service or multi-module changes
- Upgrading a dependency consumed by multiple services
- Adding an outbound dependency on another service, or deciding whether the change needs coordinated rollout

## Rules

- Map the dependency graph before classifying impact.
- Classify breaking vs additive per consumer, not in aggregate: the Impact column answers "will this break this consumer if deployed without the ordering below". When the producer code and the contract document disagree, the code is the current contract and the discrepancy is named in the row's Component Changed cell.
- Deployment order follows the direction the payload flows. A field added to what a provider returns or publishes: provider first when every consumer ignores unknown fields, consumer leniency first otherwise. A field a consumer adds to a request it sends: provider accepts it first, always. A removal: consumers stop reading first, then the provider removes; on a retained or replayable event log consumers must tolerate both shapes for the retention window (indefinitely on a compacted topic), and a schema registry's compatibility mode decides the order (`BACKWARD`: consumers first; `FORWARD`: producers first; `FULL`: either order; `NONE`: the change itself decides; `_TRANSITIVE` variants follow their base mode against every prior version).
- Breaking changes require an expand-contract migration plan (see `ops-backward-compatibility`).
- Treat minor version bumps as potentially breaking until release notes prove otherwise. Below 1.0.0 SemVer guarantees nothing: resolvers treat a `0.y` minor bump as a major (`^0.2` stops below `0.3`), and a `0.y.z` patch is unproven the way a 1.x minor is. Release notes that prove a break make it `breaking`, whatever the version number says.

## Patterns

### Dependency Mapping

For each changed component, identify:

1. **Direct consumers** - services/modules that import or call it. The publishing repo's own adoption is a consumer row like any other. For a new outbound call, the callee is a row of its own with Impact `behavioral`: it receives new load and coupling, and must be live and capacity-verified before the caller ships
2. **Transitive consumers** - those that depend on direct consumers
3. **Contract type** - API, event, library, DB view
4. **Coupling** - compile-time (linked at build or installed as a package, dynamic languages included), runtime (a network call), event (a broker in between)
5. **Ownership** - owning team per consumer, from an ownership file, a service catalogue, or a document naming the team; circumstantial evidence (a ticket's assignee) is written `<team> (inferred from <source>)`; nothing is written `owner unknown - find before deploy`, never guessed. Cross-team consumers need notification before any step that requires action from them

### Impact Classification

| Change                                             | Impact               | Deployment Constraint                                          |
| -------------------------------------------------- | -------------------- | -------------------------------------------------------------- |
| Add optional field to a response or event          | additive for consumers that tolerate unknown fields; breaking for consumers that reject them, resolved by their leniency change | Provider first when every consumer tolerates unknown fields; otherwise consumer leniency first |
| Add a field to a request the consumer sends        | additive             | Provider accepts it first                                      |
| Add required field                                 | breaking             | Expand-contract via `ops-backward-compatibility`               |
| Add an enum value                                  | breaking for closed-enum or strict-validating consumers (proto2, Avro readers below 1.9 or without an enum `default`, JSON schema validators); additive for open-enum consumers (proto3, Avro 1.9+ readers with a `default`, lenient JSON) | Per consumer row |
| Make a field nullable                              | breaking for consumers whose type or reader schema has no null (an Avro reader on the bare type, a non-null typed client); additive for consumers that already handle null | Per consumer row |
| Rename a field                                     | breaking for compile-time consumers and name-keyed encodings (JSON, Avro - which resolves by name and needs the alias in each reader's schema first); additive when the wire key is unchanged (Protobuf binary field number) | Per consumer row; Avro: readers adopt the alias first |
| Change type, precision, or semantics of a field    | breaking             | Expand-contract via `ops-backward-compatibility`               |
| Remove a field or surface                          | breaking             | Consumers stop reading first, verified, then remove; retained event logs: tolerate both shapes for the retention window |
| Behavioral change at a stable schema (logic, ordering, defaults) | behavioral | Canary with consumer monitoring                             |
| Latency or throughput change                       | behavioral           | Load test with the consumer traffic profile; check consumer timeouts and retries |
| New outbound dependency (the callee's row)         | behavioral           | Callee live and capacity-verified before the caller ships      |
| Change confined to a surface no consumer reads     | none                 | Single deploy                                                  |
| Version upgrade (patch, 1.x and above)            | additive             | Release notes override                                          |
| Version upgrade (minor, or `0.y.z` patch)          | breaking (unproven)  | Check release notes for deprecations and behavior changes; proven additive downgrades the row, proven breaking hardens it |
| Version upgrade (major, or `0.y` minor)            | breaking (one row for consumers on a changed surface), additive (one row for the rest) | Compatibility matrix; upgrade one module first |
| Consumer uses an API the new version deprecates    | behavioral           | Migrate off it before the next major                            |

### Version Upgrade Specifics

- **Transitive conflicts**: new version may require updated transitives (e.g., framework requiring newer runtime). Check against each module.
- **Publish vs adopt**: publishing a library version deploys nothing to pinned consumers - each consumer's rebuild is its deploy. A consumer adopts at its next *resolution*, which happens one of three ways: a manifest edit or explicit upgrade (Maven exact pins, pip pins and `--upgrade`, Go's minimum-version selection - a Go major from v2 on is a separate module path `/vN`, never adopted by resolution, while v0 to v1 stays on the base path), a lock refresh (npm, Bundler, Cargo, uv, and poetry lockfiles), or a cache refresh for dynamic versions (Gradle caches `2.+` for 24 hours). Unbounded specifiers (npm `latest` / `*`, Gradle `+` / `latest.release`; Maven `LATEST` is deprecated since Maven 3) take a new major on resolve; bounded ranges (`^2`, `~> 2.0`, `2.+`, and `^0.2` which stops below `0.3`) take minors and patches only. Publish a break under a new major and have unbounded-range consumers bound their specifier first; the publisher's own levers are the major, an npm dist-tag (`--tag next`), or a Go `/vN` path.
- **Phased rollout**: upgrade one consumer first and run its tests before propagating (monorepo: one module under the shared parent; polyrepo: one low-risk service).
- **Deprecated APIs**: flag consumer usage of newly deprecated APIs; they may be removed in the next major.
- **Blocker strategies** when no compatible transitive exists: **wait** (imminent release), **swap** to a compatible alternative, **shim** if surface is small, **fork** as last resort. Document the strategy and removal condition.

### Deployment Ordering Rules

- Provider before consumer for additive response or event changes consumers tolerate; consumer leniency before provider otherwise; provider before consumer for a request field, always
- Consumer before provider for removals
- Simultaneous only when feature-flagged on both sides
- Expand-contract for breaking changes
- Cyclic dependencies have no valid order while breaking both ways: make both sides tolerate old and new (additive), deploy in any order, then tighten behind a flag

### Good

```
## Dependency Impact Assessment

### Consumers Affected

| Component Changed | Direct Consumers | Transitive Consumers | Contract Type | Coupling | Owner | Impact |
| ----------------- | ---------------- | -------------------- | ------------- | -------- | ----- | ------ |
| OrderService GET /orders/{id} (optional shippingEstimate added) | FulfillmentService (rejects unknown fields) | none | API | runtime | fulfilment team | breaking |
| OrderService GET /orders/{id} (optional shippingEstimate added) | CustomerPortal, AdminDashboard | none | API | runtime | web team | additive |

### Deployment Order

1. FulfillmentService enables lenient JSON parsing - it rejects unknown fields today
2. OrderService deploys the field
3. CustomerPortal and AdminDashboard update at their own pace

### Breaking Changes Requiring Migration

- FulfillmentService: resolved by its leniency change in step 1; no expand-contract needed

### Cross-Team Notifications

- FulfillmentService (fulfilment team): enable lenient parsing; before step 2
- CustomerPortal, AdminDashboard (web team): none required - informational
```

### Bad

```
Changed the Order API. Should be fine for everyone.
```

## Output Format

```
## Dependency Impact Assessment

### Consumers Affected

| Component Changed | Direct Consumers | Transitive Consumers | Contract Type | Coupling | Owner | Impact |
| ----------------- | ---------------- | -------------------- | ------------- | -------- | ----- | ------ |
| {name (change; code-vs-document discrepancy when any)} | {list, each optionally `(rejects unknown fields)` or `(unconfirmed - <why>)`, "none", or "unenumerable: <where they live>"} | {same} | {API \| event \| library \| DB view} | {compile-time \| runtime \| event} | {team \| team (inferred from <source>) \| owner unknown - find before deploy} | {breaking \| breaking (unproven) \| additive \| behavioral \| none} |

### Deployment Order

{numbered steps with reasons, or the single line `Single deploy; ordering is not the risk - <the verification that is>`}

### Breaking Changes Requiring Migration

{For each breaking row: the expand-contract plan via `ops-backward-compatibility`, or the consumer change that resolves it before the provider ships; "none" when no row is breaking}

### Cross-Team Notifications                     {when any consumer is owned by another team or its owner is unknown}

- {consumer (owner)}: {required action, "identify the owner", or "none required - informational"}; {deadline relative to deploy}

### No Impact                                    {instead of the three sections above, when every row is `none`: one sentence}
```

Fill rules:

- One row per component-change and consumer group whose impact, owner, or deployment constraint differs; a change touching two contract surfaces (an event schema and the library that types it) is one row per surface; several changes to one surface in one release are one row whose Impact is the worst of them, listing the changes.
- Write `none` only when you have checked and there are no consumers. A named consumer whose use of this surface cannot be confirmed (a service listed per-service, not per-endpoint) stays in the list as `(unconfirmed - <why>)` and is planned for. When the consumer set cannot be enumerated - a library published to a registry, callers in repos you cannot read - write `unenumerable: <where they live>` and plan for the worst case: `none` claims a coordinated rollout is unnecessary, which is the opposite of what an unenumerable set implies.
- A change that is additive during expand and breaking at contract takes the classification of its **end state**, with the per-phase safety shown in Deployment Order - the column answers "will this break this consumer without the ordering," not "is every step safe."
- A version bump whose release notes cannot prove it additive fills `breaking (unproven)` - the treat-as-breaking rule decides the plan, and the qualifier tells the reader what evidence would downgrade it. A re-tag under a new major, when the notes prove a break, is Deployment Order step 1.
- A behavioral or performance change deployable in one step uses the `Single deploy` line and names the verification that is the risk (load test with the tight-loop consumer's profile, canary with consumer monitoring); a numbered list of one step hides that.
- A blocker strategy (wait / swap / shim / fork) is a numbered Deployment Order step, carrying its removal condition.

## Avoid

- Deploying provider changes without mapping consumers
- Assuming consumers handle new fields gracefully
- Breaking changes without a migration plan
- Deploying consumer before provider for additive changes the consumers already tolerate
- Ignoring transitive consumers
