---
name: ops-backward-compatibility
description: Assess API, event, and DB schema changes for consumer breakage and produce expand-contract migration plans.
metadata:
  category: ops
  tags: [compatibility, api, contracts, migration, deployment, multi-stack]
user-invocable: false
---

# Backward Compatibility Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Before deploying changes to public APIs, event schemas, or database schemas
- When assessing consumer impact and coordinated-deploy requirements
- When planning expand-contract migrations or dual-write/dual-read transitions

## Rules

- Additive optional changes are safe; modifications and removals are breaking until proven otherwise.
- Breaking changes require an expand-contract plan with an explicit transition period.
- Schema changes must be compatible with both current and previous code during rolling deploy.
- Event schema changes must hold backward compatibility for at least one consumer release cycle.
- "No external callers found" requires evidence (a search); absence of search is not evidence.

## Patterns

### Compatibility Matrix

| Contract     | Change                       | Compatible | Action                                                  |
| ------------ | ---------------------------- | ---------- | ------------------------------------------------------- |
| REST API     | Add optional field           | Yes        | Deploy provider first                                   |
| REST API     | Add required field           | No         | Version or expand-contract (optional first, then enforce) |
| REST API     | Remove / rename field        | No         | Add new, deprecate old, verify zero reads, then remove  |
| REST API     | Change field type or path    | No         | Version the API                                         |
| Event schema | Add optional field           | Yes        | Consumers must tolerate unknown fields                  |
| Event schema | Add required field           | No         | Optional first, consumers update, then enforce required |
| Event schema | Remove field / change meaning | No         | Two-phase removal or new event type                     |
| DB schema    | Add nullable column / index  | Yes        | Migration then code                                     |
| DB schema    | Add NOT NULL column          | No         | Nullable + backfill + add constraint                    |
| DB schema    | Drop / rename column         | No         | Stop reads in code + verify + migrate                   |
| DB schema    | Change column type           | No         | Expand-contract migration                               |

### Contract Scope

Identify the consumer surface before classifying severity:

- **HTTP-exposed**: backs a public endpoint. Renaming or removing is breaking for API consumers.
- **Shared library**: consumed by other services via compile-time or runtime binding. Treat like an HTTP contract.
- **Internal-only**: called only within the same service. Refactor freely after confirming no reflection, dynamic dispatch, or external test coverage.

### Stack Adaptation

After `stack-detect`, map changes to the ecosystem's serialization and migration mechanisms (DTOs/records/structs/schemas, framework validation, migration tool). Two universals hold regardless of stack:

- Making a previously optional input required is breaking at the validation layer.
- Entity/model changes must use the ecosystem's migration tool; never auto-schema-update in production.

If the stack is unfamiliar, apply the matrix above and flag a recommendation to verify against the framework's docs.

### Dual-Write / Dual-Read Assessment

For storage or event-format changes, answer four questions:

1. Transition window: how long do old and new versions coexist?
2. Dual-write: does new code write both formats?
3. Dual-read: does new code read both formats?
4. Backfill + cleanup: is existing data migrated, and when is old-format support removed?

### Good

```
Change: Rename OrderDTO.total -> OrderDTO.totalAmount
Consumers: CustomerPortal, ReportingService, MobileAPI
Compatibility: Breaking (field rename)
Plan:
  1. Add totalAmount, keep total (dual-write) - deploy provider
  2. Migrate consumers to read totalAmount
  3. Stop populating total - verify no reads
  4. Remove total - next release cycle
```

### Bad

```
Renamed the field. It is just a rename, should be fine.
```

## Output Format

Consuming workflow skills parse this structure to surface breaks and migration plans.

```
## Backward Compatibility Assessment

### Changes Assessed

| Contract Type | Change | Compatible | Action Required |
| ------------- | ------ | ---------- | --------------- |
| {REST API / Event schema / DB schema} | {description} | Yes / No | {action or "None"} |

### Breaking Changes

{For each breaking change:}

**{Contract type}: {change description}**
- Consumers affected: {list or "unknown - verify before deploy"}
- Migration plan: {expand-contract phases}
- Dual-write needed: Yes / No
- Dual-read needed: Yes / No

### No Breaking Changes

{State explicitly if all changes are backward compatible - do not omit silently.}
```

Always produce the Changes Assessed table even when all changes are compatible. Omit "No Breaking Changes" if breaking changes were listed.

## Avoid

- Treating all field additions as safe (required fields break consumers).
- Removing fields without verifying zero consumer usage.
- Breaking changes without an expand-contract plan or dual-write/read assessment.
- Migrations that require simultaneous code deployment.
