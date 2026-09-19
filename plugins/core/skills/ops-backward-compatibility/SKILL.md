---
name: ops-backward-compatibility
description: Assess API, event, and DB schema changes for consumer breakage and produce expand-contract migration plans.
metadata:
  category: ops
  tags: [compatibility, api, contracts, migration, deployment, multi-stack]
user-invocable: false
---

# Backward Compatibility Analysis

> Load `Use skill: stack-detect` first to determine the project stack (it names the serializer and migration tool the Action column speaks in).

## When to Use

- Before deploying changes to public APIs, event schemas, or database schemas
- When assessing consumer impact and coordinated-deploy requirements
- When planning expand-contract migrations or dual-write/dual-read transitions

## Rules

- Judge "additive" from the consumer's view, on the side of the wire the consumer reads: adding an optional field a producer emits is safe only for consumers that tolerate unknown fields; modifications, removals, tightened input constraints, and widened output domains (new enum value emitted, first null in a never-null field, longer or more precise values) are breaking until proven otherwise. Widening what a producer *accepts* breaks no consumer unless the accepted value is stored and echoed back, which makes it an output widening too.
- Confirm the changed code sits on the consumer-facing path before classifying: a change to a path no consumer reaches is `Yes`, with `unreachable by consumers` and the evidence in its Consumers (evidence) cell.
- Breaking changes require an expand-contract plan with an explicit transition window: one consumer release cycle for events; for APIs and schemas, until every named consumer confirms, with a review date, or one release cycle when every consumer is internal.
- Schema changes must be compatible with both current and previous code during rolling deploy; the previous release's own instances are a consumer class of every schema change, satisfied by the expand-contract plan rather than by a row of their own.
- "No external callers found" requires evidence, and the evidence must reach where the consumers actually are: a code search proves nothing about consumers outside the repository. For a shared library or DTO, search every repo that depends on it; for an HTTP field, read access logs or gateway analytics over a period long enough to include infrequent clients; for an event field, inspect the broker's consumer groups. A consumer named in the architecture docs counts as known for *who*; it proves nothing about *what they depend on*. A fact the requester states outranks a document's open item; the document's hedge is noted in the evidence source. When you cannot reach the evidence, the consumer list is `unknown - verify before deploy`, not "none".
- A type is internal-only when no other service binds to it *and* no serialized copy of it outlives a deploy: cache entries, queued jobs, JSONB columns, and session state make a "private" DTO a contract with the past.

## Patterns

### Compatibility Matrix

Direction column: `out` is what the producer emits and consumers read; `in` is what the producer accepts; `db` is a table read or written by more than one code version or client.

| Contract     | Change                       | Direction | Compatible | Action                                                  |
| ------------ | ---------------------------- | --------- | ---------- | ------------------------------------------------------- |
| REST API     | Add optional field, or a field the server always populates | out | Yes for consumers that tolerate unknown fields; No for strict readers | Verify each consumer's reader, then deploy provider first. A bare Jackson `ObjectMapper` rejects unknown fields (Spring Boot's auto-configured mapper, Jackson 3, Pydantic, and serde accept them); a JSON Schema or OpenAPI contract rejects them only where it sets `additionalProperties: false` |
| REST API     | Add required field           | in        | No         | Optional first, then enforce; or version                |
| REST API     | Remove / rename response field | out     | No         | Add new, deprecate old, verify zero reads, then remove  |
| REST API     | Remove, rename, or retype a request field | in | No   | Accept both shapes for the transition window, then reject the old with a clear error; or version |
| REST API     | Change response field type or path | out | No         | Version the API                                         |
| REST API     | Tighten request validation (stricter pattern, smaller max, optional -> required) | in | No | Announce, grace period, then enforce; or version |
| Any contract | Widen value domain (new enum value, newly nullable, longer or more precise values) | out | No | Verify consumers tolerate the new values, then emit |
| Any contract | Widen accepted domain        | in        | Yes        | Verify the echo path; a stored-and-echoed value also emits the row above as its own `out` row |
| Event schema | Add field with a default / optional field | out | Yes for consumers that tolerate unknown fields | Verify readers; under a schema registry the subject's compatibility level decides deploy order: `BACKWARD` (Confluent's and Glue's default; Apicurio ships with none) consumers first, `FORWARD` producer first, `FULL` either, `NONE` no evidence - verify by hand |
| Event schema | Add required field / field without a default | out | No | Add it with a default; under `BACKWARD` or `FULL` the default stays for good and the requirement is enforced in application validation, or the change goes to a new event type. proto3 syntax has no `required`: only `optional` scalars, message fields, and `oneof` members carry presence (editions can reinstate it with `LEGACY_REQUIRED`) |
| Event schema | Remove field / change meaning | out      | No         | Two-phase removal or new event type                     |
| DB schema    | Add nullable column          | db        | Yes for readers that project explicit columns; No for `SELECT *` into a strict row mapper (`sqlx.StructScan`, `Dataclass(**row)`) | Migration then code; verify raw-SQL readers |
| DB schema    | Add index                    | db        | Yes for non-unique; No for UNIQUE (old writers that insert duplicates start failing, and existing duplicates abort the build) | Online build (`CONCURRENTLY` outside a transaction; InnoDB `INPLACE` by default); a UNIQUE index is a tightened write constraint: dedupe, stop duplicate writers, then build; lock risk is `backend-db-migration`'s |
| DB schema    | Add column NOT NULL with a constant default | db | Same reader split as Add nullable column | Migration then code; old writers omit the column and take the default |
| DB schema    | Add NOT NULL without a default | db      | No         | Breaks writers: nullable + backfill + add constraint    |
| DB schema    | Drop column                  | db        | No         | Stop reads *and* writes in code (ORMs write every mapped column) + verify + migrate |
| DB schema    | Rename column                | db        | No         | Expand-contract: add new, dual-write, backfill, switch reads, drop old |
| DB schema    | Change column type           | db        | No         | Expand-contract migration                               |
| Any contract | Change behavior at a stable schema (ordering, pagination stability, default value, precision or timezone, error-code meaning) | in or out | No | Treat as a contract change: announce, verify consumers do not depend on the old behavior, version if they do |

When a change matches more than one row, the row whose Change cell names it explicitly wins. A column widening (`VARCHAR(50)` to `VARCHAR(255)`, more decimal places) is a widened value domain for its readers, not a column-type change: verify consumers tolerate the longer or more precise values. Its DDL cost is `backend-db-migration`'s - on PostgreSQL no rewrite for a longer varchar or a larger numeric precision at the same scale, but a brief `ACCESS EXCLUSIVE` lock that queues behind long transactions; a larger numeric scale rewrites the table; on InnoDB a rebuild when the widening crosses the 255-byte length-prefix boundary under a multibyte charset.

Schema-stable behavioral changes are the ones reviews miss: no diff of fields or types reveals them, so they must be found by reading what the code now does differently. Behavioral dependence is also invisible to traffic inspection - logs show that a consumer calls, never that it relies on ordering, a default, or precision - so verification means consumer-side confirmation (their tests, their ack) or an announced grace period; never claim logs as evidence here.

### Contract Scope

Identify the consumer surface before classifying severity:

- **HTTP-exposed**: backs a public endpoint. Renaming or removing is breaking for API consumers.
- **Shared library**: consumed by other services via compile-time or runtime binding. Treat like an HTTP contract.
- **Internal-only**: called only within the same service and never serialized past a deploy. Refactor freely after confirming no reflection, dynamic dispatch, external test coverage, or persisted copies.

### Stack Adaptation

After `stack-detect`, map changes to the ecosystem's serialization and migration mechanisms (DTOs/records/structs/schemas, framework validation, migration tool). Two universals hold regardless of stack:

- Making a previously optional input required is breaking at the validation layer.
- Entity/model changes must use the ecosystem's migration tool; never auto-schema-update in production.

When `Language`, the database engine, or the registry mode is unknown, apply the matrix and add `verify against the <framework | engine | registry> docs` to each Action that depends on the unknown.

### Dual-Write / Dual-Read Assessment

For storage or event-format changes, answer four questions in the Breaking Changes block:

1. Transition window: how long do old and new versions coexist?
2. Dual-write: does new code write both formats?
3. Dual-read: does new code read both formats?
4. Backfill + cleanup: is existing data migrated, and when is old-format support removed?

For events, dual-write means the producer emits both old and new shapes (both field names in one payload, or both event versions); dual-read means consumers accept both shapes during the transition. A validation break, a widened value domain, or a behavioral break has no format transition: its dual-write and dual-read answers are `n/a - no format transition`.

### Good

```
## Backward Compatibility Assessment

**Stack:** Java 21 / Spring Boot 3.5 (Jackson) / PostgreSQL 16 / no schema registry

### Changes Assessed

| Contract Type | Change | Direction | Consumers (evidence) | Compatible | Action Required |
| ------------- | ------ | --------- | -------------------- | ---------- | --------------- |
| Shared library | Rename OrderDTO.total -> OrderDTO.totalAmount | out | CustomerPortal, ReportingService, MobileAPI (registry dependents - who); field usage unknown - verify before deploy | No | Add totalAmount to the Jackson-serialized record, keep total, deprecate with `@Deprecated`, verify zero reads, then remove |

### Breaking Changes

**Shared library: rename OrderDTO.total -> OrderDTO.totalAmount**
- Consumers affected: CustomerPortal, ReportingService, MobileAPI (dependents of orderflow-common by registry search; MobileAPI pins `>=2,<3`, verify before publishing 3.0); field-level usage unknown - verify before deploy
- Transition window: until CustomerPortal, ReportingService, and MobileAPI each confirm they read totalAmount; review date six weeks after the provider deploy
- Migration plan: 1. add totalAmount, keep total (dual-write) - deploy provider; 2. migrate consumers to read totalAmount; 3. stop populating total - verify no reads; 4. remove total next release cycle
- Dual-write needed: Yes
- Dual-read needed: Yes
- Backfill + cleanup: no stored copies; remove `total` at step 4
```

### Bad

```
Renamed the field. It is just a rename, should be fine.
```

## Output Format

Consuming workflow skills parse this structure to surface breaks and migration plans.

```
## Backward Compatibility Assessment

**Stack:** {language / framework and serializer / database engine / registry, from stack-detect; each unknown part written as `unknown`}

### Changes Assessed

| Contract Type | Change | Direction | Consumers (evidence) | Compatible | Action Required |
| ------------- | ------ | --------- | -------------------- | ---------- | --------------- |
| {REST API / Event schema / DB schema / Shared library / other named surface} | {description} | {out / in / db} | {list with the evidence source, or "unknown - verify before deploy"} | {Yes / No / No (unverified)} | {action from the matrix, plus the stack's mechanism} |

### Breaking Changes                             {when at least one row is No or No (unverified)}

**{Contract type}: {change description}**
- Consumers affected: {list with the evidence source, or "unknown - verify before deploy"}
- Transition window: {duration old and new coexist, and what ends it}
- Migration plan: {phases from the matrix row's action}
- Dual-write needed: {Yes / No / n/a - no format transition}
- Dual-read needed: {Yes / No / n/a - no format transition}
- Backfill + cleanup: {what is migrated and when old-format support is removed, or "n/a"}

### No Breaking Changes                          {instead, when every row is Yes: one sentence}
```

Always produce the Changes Assessed table, one row per discrete change: two constraints tightened on one field in one release are one row; two mechanisms changed on one surface (an ordering and a default), or two fields changed on one event, are one row each; a change that alters both what is accepted and what is emitted is one row per direction; a change that is compatible for one consumer class and breaking for another (raw-DB readers vs HTTP clients) is one row per class. A matrix `Yes` that depends on a reader property you could not verify is `No (unverified)`: a break the evidence rule could not confirm either way, treated as `No` for planning, naming what would clear it. Contract Type names the actual surface - the four listed are the common cases, not a closed set (GraphQL schema, gRPC proto, exported file format are all valid values).

## Avoid

- Treating all field additions as safe (required input fields and strict readers break consumers).
- Removing fields without verifying zero consumer usage.
- Breaking changes without an expand-contract plan or dual-write/read assessment.
- Migrations that require simultaneous code deployment.
