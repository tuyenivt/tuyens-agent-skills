---
name: flutter-local-db-migration
description: "Migrate on-device Drift/SQLite schemas across app updates: stepped migrations, schema snapshots, migration tests, data preservation."
metadata:
  category: mobile
  tags: [flutter, dart, drift, sqlite, migration, schema-version, on-device]
user-invocable: false
---

# Flutter Local DB Migration

> Store selection lives in `flutter-data-persistence`; this skill owns schema versioning and the upgrade path. Old app versions stay installed on user devices for months, so the schema a shipped build understands is a compatibility surface: a newer build must read what an older one wrote, and an older build must refuse newer data rather than corrupt it.

**The user controls when they update.** That single fact separates this from server migration: there is no deploy window, no coordinated rollout, no operator on the other end. A device may sit on schema v3 for a year and jump straight to v9 on one launch, so every intermediate step must still compose. A migration that fails runs on a phone you cannot reach, leaves the app unable to open its database, and is cleared only by an uninstall - which destroys every row the user owned.

## When to Use

- Changing the shape of anything persisted: new or dropped table, added/removed/retyped column, changed constraint or index
- Writing or reviewing a migration step, or the `MigrationStrategy` as a whole
- Diagnosing crash-on-launch after an app update, or data missing once the user upgraded
- Deciding whether a change can preserve data at all, and what to do when it cannot

## Rules

- One released schema revision = one `schemaVersion` bump = one step; ops developed and shipped together belong in that one step. Never fold a new change into a version that has already shipped - that edits a frozen step. Emit one implementation-contract block per step
- **A step that has shipped is frozen.** Never edit, renumber, or reorder it - devices in the field have already run it, and their state is defined by what it did, not by what the file says now. A shipped step that is broken is repaired forward: the next step detects the state it left and fixes it. A step that throws on every device never completed anywhere, so it is not frozen: replace it
- Migration from **any shipped version** to current must work, not just from the previous one. Correctness is per-step and order-independent of the starting point
- A migration is offline, unattended, and forward-only. No network calls, no reads of app settings or other app state, no user prompts inside a step; writing the files a step moves data into is allowed. It completes on the device's own resources or the install is bricked
- Preserve data by default. Dropping user-authored rows is a product decision with a user-visible consequence, not an implementation shortcut
- Test every shipped version -> current against a committed schema snapshot, with data seeded at the old version. Schema equality is not data correctness
- Bundle SQLite with the app (`sqlite3_flutter_libs` on `package:sqlite3` 2.x; 3.x bundles it through build hooks) rather than relying on the system library - Android's system SQLite version varies by OS release and vendor, so feature availability (`DROP COLUMN`, `ALTER TABLE RENAME COLUMN`) is not uniform across the installed base
- `PRAGMA foreign_keys` has no effect inside a transaction: in drift turn it `OFF` at the top of `onUpgrade` before the step transaction, run `PRAGMA foreign_key_check` as the transaction's last statement so a violation rolls the steps back, and turn it `ON` in `beforeOpen`; `sqflite` runs its callbacks in a transaction, so there it goes in `onConfigure`. A table rebuild with foreign keys on cascades or blocks on the child rows
- Handle `from > to` explicitly: refuse to open with an update-required screen (default), or open read-only if the product needs it. Never auto-delete, and never continue silently - a user can end up on an older build over newer data (sideload, reinstall, TestFlight downgrade), and continuing corrupts

## Patterns

### Device migration is not server migration

| Server | Device |
| --- | --- |
| One database, you choose when it migrates | One database per install, the user chooses |
| Coordinated deploy window, staged rollout | No window; the store and the user decide |
| Failure -> restore backup, roll back the release | Failure -> app cannot open its DB; no backup, no rollback |
| Always version N-1 -> N | Any shipped version -> current, in one launch |
| Operator can intervene | Nobody can reach the device |
| Concurrency, locking, and downtime are the risks | Composition and data loss are the risks |

Nothing about locks, index build strategy, or downtime transfers. The device DB is single-user local storage; the app's background isolates (a sync worker, a push handler) must not open it until the upgrade completes.

### Steps must compose across skipped versions

```dart
// Bad - a v3 install upgrading to v9 never gets dueDate; the branch only fires from v8
onUpgrade: (m, from, to) async {
  if (from == 8) await m.addColumn(todos, todos.dueDate);
}
```

```dart
// Good - stepByStep and the versioned schemas come from `dart run drift_dev schema steps`;
// every fromNToM callback is required, and 3 -> 9 replays 4, 5, ... 9 in order
static final _steps = stepByStep(
  from3To4: (m, schema) => m.addColumn(schema.todos, schema.todos.dueDate),
  from4To5: (m, schema) => m.createTable(schema.tags),
  // ... from5To6 through from8To9
);

onUpgrade: (m, from, to) async {
  if (from > to) throw StateError('database v$from is newer than this build'); // -> update-required screen
  await customStatement('PRAGMA foreign_keys = OFF');
  await transaction(() async {
    await _steps(m, from, to);
    final broken = await customSelect('PRAGMA foreign_key_check').get();
    if (broken.isNotEmpty) throw StateError('foreign key violations after upgrade');
  }); // a failed step or check rolls back to the old version
},
```

Each step receives the schema **as it existed at that version**, so `schema.todos` keeps meaning v4's shape even after v7 rebuilds the table. A hand-written `onUpgrade` that references the current table classes silently changes behavior for old installs every time the table is edited again.

### Adding a column

```dart
// Bad - non-nullable with no default; existing rows have no value and the migration fails
IntColumn get priority => integer()();
await m.addColumn(todos, todos.priority);
```

```dart
// Good - existing rows get a stored default
IntColumn get priority => integer().withDefault(const Constant(0))();
```

Nullable, or defaulted, or backfilled inside the step. `clientDefault` is applied by Dart on insert and does nothing for rows already on disk.

### Changes SQLite cannot do in place

SQLite has no general `ALTER COLUMN`. Retyping, adding a constraint, or removing a column on an old SQLite requires rebuilding the table: create the new shape, copy rows through a transformation, drop the old, rename. Drift wraps this:

```dart
// inside the fromNToM step that rebuilds the table to add the column: (m, schema) async { ... }
await m.alterTable(TableMigration(
  schema.todos,
  newColumns: [schema.todos.priority],
  columnTransformer: {schema.todos.priority: const Constant(0)},
));
```

The rebuild rewrites the whole table. On a large table on a cold device this is the slowest thing the app will ever do at launch - size it against real user data, not a test fixture with 20 rows.

### When data must go

| Situation | Option | Cost |
| --- | --- | --- |
| Column no longer read | Leave it, stop reading it | Zero risk; a dead column forever |
| Column must be removed | Table rebuild without it | Rewrites the table; that column's data is gone |
| Data is a rebuildable cache | Drop and refetch on next sync | User sees a loading state, and it needs network |
| Data is user-authored | Migrate it to a preserved form, or export it before dropping | The only acceptable path |

```dart
// Bad - the reset that "fixes" any migration problem, and deletes everything the user made
await m.drop(todos);
await m.createAll();
```

Silent loss of user-authored data is a defect, not a tradeoff. If a shape genuinely cannot be migrated, write the old rows to an archive table or a file first, and treat surfacing that to the user as part of the change.

### Test against real old versions

```dart
// Commit a snapshot per version: dart run drift_dev schema dump lib/database.dart drift_schemas/
// Generate helpers:      dart run drift_dev schema generate --data-classes --companions drift_schemas/ test/generated/
final verifier = SchemaVerifier(GeneratedHelper());
for (final from in [1, 2, 3, 4]) {
  final connection = await verifier.startAt(from);
  final db = AppDatabase(connection);
  await verifier.migrateAndValidate(db, 5);
  await db.close();
}
```

Without committed snapshots there is nothing left to test against once the code moves on - the old schema exists only on user devices. Beyond shape verification, insert rows through the generated old-version classes before migrating and assert their values afterwards; a migration can produce a structurally perfect table full of nulls. Where a real database file from an old install is obtainable, run against it too.

### Non-Drift stores

`sqflite` uses `openDatabase(version:, onCreate:, onUpgrade:, onDowngrade:)` - same discipline, raw SQL, no snapshot tooling, so the version ladder and its tests are hand-written. Key-value and object stores are still versioned data: a changed key meaning, a changed Hive `typeId`, or a changed serialized shape is a migration. Store a schema-version key alongside the data and convert on read - which requires the old form to stay readable: keep the old adapter registered and never reuse a `typeId`.

## Output Format

When invoked from an implementation workflow:

```
Schema Version: {<old> -> <new>}
Step: {from<N>To<M>}
Change Type: {additive | rebuild | destructive | index-only} - the most severe operation in the step
Data Impact: {preserved | backfilled: <rule> | LOST: <what>}, comma-separated when the step mixes them
Oldest Shipped Version: {<n> | unknown}
SQLite Feature Floor: {none | requires SQLite >= <x>, bundled | system SQLite (risk)}
Snapshot Committed: {yes - <path> | NO | N/A (sqflite)}
Migration Test: {every shipped version -> current (<a>..<b>), with seeded data | shape only | newest version only | none}
Rebuild Cost: {N/A | rewrites <table> - measured on <n> rows | unmeasured}
Downgrade Path: {explicit at file:line | unhandled}
Rollback: {none - forward-only by construction}
```

A requested column that already exists is reported, not re-added: the step backfills or retypes it, and the plan says which. A shipped step found broken while planning is repaired forward in the new step and listed on the `Pre-existing` line; a repair that must reach every install runs at the new version after all shipped steps, never inside them. When snapshots were never committed, dump the current schema now and rebuild older ones from each release tag. Without production data, size a rebuild on a synthetic table at the largest realistic row count.

Implement mode ends with `Pre-existing: <file:line> - <defect>` for each defect in code the plan edits or depends on but does not fix, or `Pre-existing: none`. Code not yet written is cited as `<path> (new)`. A file the plan depends on that is absent or could not be read is listed as `Not read: <path> - <reason>`. A defect the change cannot ship on top of is fixed in the plan, not listed as `Pre-existing`.

When invoked from a review workflow, emit one finding block per issue:

```
### [Severity] file:line

- Rule: {version-bump | step-composition | shipped-step-mutated | non-nullable-add | in-place-alter | system-sqlite | rebuild-cost | data-loss | test-coverage | snapshot-missing | downgrade-unhandled | foreign-keys | offline-safety | dead-column}
- Code: {one-line citation}
- Problem: {what happens on a user device on the next launch}
- Recommendation: {concrete edit}
```

`Severity: {Critical | High | Medium | Low}`. Critical = crash on launch after update, a step that needs the network or app state (`offline-safety`), a step unreachable from a shipped version, a shipped step edited (device state diverges by when each install migrated), or silent loss of user-authored data. High = will fail on part of the installed base or on realistic data (a shape change without a version bump that has not yet crashed, missing snapshot/tests, system-SQLite feature use, unhandled downgrade, unmeasured rebuild of a large table), or a column of unknown provenance dropped without an archive. Medium = fragile but currently working (newest-version-only tests, shape-only verification). Low = a column still written but never read (`dead-column`; a column deliberately left and no longer read is not a finding), naming. When a finding matches two bands, the higher band wins.

Review scope is the whole migration strategy of the file the change touches, not only the added lines: defects in its shipped steps are reported (and fixed forward, never by editing the step). A missing guard or file anchors on the call that should carry it: `openDatabase` for a missing `onDowngrade` in `sqflite`, the `MigrationStrategy` for a missing `from > to` check, snapshot directory, or migration test in drift. A new op folded into a shipped step is `shipped-step-mutated`, not `version-bump`. A defect that predates the change opens its Problem line with `Pre-existing:`. An ineffective `PRAGMA foreign_keys` toggle is Medium. For `sqflite`, `snapshot-missing` is `Not checked` (no snapshot tooling); tests go under `test-coverage`.

For each rule in the enum with zero findings, emit exactly `No <rule> findings.` so the workflow knows the check ran; omit that line for rules with findings.

Blocks are one per defect, ordered by severity, then file and line, then enum order. Each site of a repeated rule is its own defect; a single defect that needs edits in several places anchors on the line to edit and names the others as `also <file:line>` on its citation line.

A finding that depends on code outside the files read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to the line describing its effect. A check whose subject does not appear in the files read is clean; a check the files read cannot exercise is listed once as `Not checked: <names> - <reason>` and gets no clean or zero-finding line. A file in scope that could not be read is named on that line.

## Avoid

- Assuming the previous version is the starting version - v3 -> v9 in one launch is normal
- Editing, renumbering, or reordering a step that has shipped
- Splitting one released revision's ops across several version bumps, or folding new ops into a step that already shipped
- Adding a non-nullable column with no stored default
- Reaching for `ALTER COLUMN` (SQLite has none) instead of a table rebuild
- Wiping and recreating the database as a migration strategy
- Dropping user-authored data without an archive or an explicit product decision
- Network calls, app-state reads, or user prompts inside a migration step
- Shipping without committed schema snapshots, or testing only the newest shipped version
- Verifying schema shape while never asserting that seeded rows survived with correct values
- Relying on the device's system SQLite for features that vary by OS version
- Toggling `PRAGMA foreign_keys` inside a step's transaction instead of around the whole upgrade
- Server framing: there is no deploy window, no rollback, no concurrent writer, and no operator on the device
