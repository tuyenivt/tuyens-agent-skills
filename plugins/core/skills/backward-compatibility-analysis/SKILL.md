---
name: backward-compatibility-analysis
description: API, event, and data contract backward compatibility assessment. Auto-detects project stack and adapts compatibility checks to the detected ecosystem.
metadata:
  category: ops
  tags: [compatibility, api, contracts, migration, deployment, multi-stack]
user-invocable: false
---

# Backward Compatibility Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Before deploying changes that modify public APIs, event schemas, or database schemas
- When assessing whether a change requires coordinated deployment across consumers
- When planning expand-and-contract migrations for breaking changes
- When evaluating dual-write or dual-read requirements during rollout

## Rules

- Every public contract change must be assessed for consumer impact before deployment
- Additive changes are safe; modifications and removals are breaking until proven otherwise
- Breaking changes require an expand-contract migration plan with explicit transition period
- Event schema changes must maintain backward compatibility for at least one consumer release cycle
- Database schema changes must be compatible with both current and previous code versions during rolling deployment
- Do not assume consumers deserialize leniently — verify

## Pattern

### Compatibility Assessment Matrix (All Stacks)

| Contract Type | Change Kind            | Compatible | Action Required                          |
| ------------- | ---------------------- | ---------- | ---------------------------------------- |
| REST API      | Add optional field     | Yes        | Deploy provider first                    |
| REST API      | Add required field     | No         | Version API or expand-contract           |
| REST API      | Remove field           | No         | Verify no consumers read it, then remove |
| REST API      | Rename field           | No         | Add new + deprecate old + remove later   |
| REST API      | Change field type      | No         | Version API                              |
| REST API      | Change endpoint path   | No         | Redirect old + deploy new                |
| Event schema  | Add optional field     | Yes        | Consumers must tolerate unknown fields   |
| Event schema  | Remove field           | No         | Verify no consumers, two-phase removal   |
| Event schema  | Change field semantics | No         | New event type or versioned schema       |
| DB schema     | Add nullable column    | Yes        | Migration then code                      |
| DB schema     | Add NOT NULL column    | No         | Add nullable + backfill + add constraint |
| DB schema     | Drop column            | No         | Remove code reads + verify + drop        |
| DB schema     | Rename column          | No         | Add new + migrate + drop old             |
| DB schema     | Change column type     | No         | Expand-contract migration                |

### Stack-Specific Guidance

After loading stack-detect, apply compatibility checks using the idioms of the detected ecosystem:

- **DTO/response changes**: Adding fields to response objects is generally safe; removing or renaming breaks clients. The specific mechanism varies by framework (records, serializers, structs, schemas).
- **Input validation changes**: Making a previously optional field required is a breaking change in any framework's validation layer.
- **Data layer changes**: Entity/model changes must be paired with the ecosystem's migration tool — never use auto-schema-update in production.
- **Internal event changes**: Event schema changes within the application affect all subscribers/listeners — assess impact within the detected framework's event system.
- **Module/package interface changes**: Renaming or removing public APIs (exported functions, public methods, interface methods) is breaking. In some ecosystems (e.g., Go modules), module path changes require major version bumps.

If the detected stack is unfamiliar, apply the universal compatibility matrix above and recommend the user verify against their framework's serialization and migration documentation.

### Dual-Write / Dual-Read Assessment

When a change modifies data storage or event format:

1. **Identify transition period** — time window where old and new versions coexist
2. **Dual-write needed?** — must the new code write both old and new format?
3. **Dual-read needed?** — must the new code read both old and new format?
4. **Backfill needed?** — must existing data be migrated to the new format?
5. **Cleanup needed?** — when and how to remove old format support?

### Good: Explicit compatibility assessment with migration plan

```
Change: Rename OrderDTO.total -> OrderDTO.totalAmount
Consumer impact: CustomerPortal, ReportingService, MobileAPI
Compatibility: Breaking -- field rename

Migration plan:
  Phase 1: Add totalAmount field, keep total (both populated) -- deploy provider
  Phase 2: Migrate consumers to read totalAmount -- deploy consumers
  Phase 3: Deprecate total field, stop populating -- verify no reads
  Phase 4: Remove total field -- next release cycle
```

### Bad: Compatibility assumption without consumer analysis

```
Renamed the field. It is just a rename, should be fine.
```

## Avoid

- Assuming field additions are always safe (required fields break consumers)
- Breaking changes without an expand-contract plan
- Removing fields without verifying zero consumer usage
- Event schema changes without backward compatibility window
- Database migrations that require simultaneous code deployment
- Skipping dual-write assessment for data format changes
