---
name: flutter-data-persistence
description: "Pick and use on-device Flutter storage: Drift, sqflite, Isar, Hive, shared_preferences, secure storage; repository pattern, local transactions."
metadata:
  category: mobile
  tags: [flutter, dart, drift, sqflite, hive, isar, shared-preferences, secure-storage]
user-invocable: false
---


Owns **where each piece of data lives on the device and how it is accessed**. On-device storage is single-user and local to one install. It is not a shared database: no other app writes it, there is no pool to size, no replica, and the app does not own the server's schema. The app's own background isolates (a sync worker, a push handler) are the one second writer. Schema versioning and upgrade paths live in `flutter-local-db-migration`; encryption-at-rest and platform hardening in `flutter-security-patterns`.

## When to Use

- Deciding where a new piece of data is persisted, or reviewing an existing choice
- Introducing a local database, cache, or key-value store
- Reviewing whether secrets are in the right store and whether widgets reach past the repository
- Wiring offline reads, local writes, or logout data wipe

## Rules

- Choose the store by **sensitivity first, then shape, then query needs** (table below). Familiarity is not a reason
- Secrets - access and refresh tokens, API keys, credentials, encryption keys - live only in platform secure storage. Never `shared_preferences`, never a plain SQLite column, never a file
- One repository owns each store. Widgets and notifiers depend on the repository interface, never on a DAO, `SharedPreferences`, or a secure-storage handle
- Local tables model the screens that read them, not the server's schema. They are a projection of remote state that the app is free to reshape
- A user action, or one sync batch, that writes more than one row or table is one local transaction; a single-row write, or a single drift or sqflite `batch` (already atomic), does not need another. Transactions here buy **atomicity across an interrupted app**, not concurrency control
- Anything persisted survives app updates. A shape change ships with a migration and a bumped schema version - delegate to `flutter-local-db-migration`
- Binary payloads go to the filesystem (IndexedDB on web); the row stores a path relative to the base directory, or the IndexedDB key
- Reads the UI must react to are streams; one-shot reads are for imperative flows
- Logout and account-switch define explicitly what is wiped and what survives; iOS Keychain entries outlive an uninstall unless deleted
- Heavy local work stays off the UI isolate (drift's background-isolate support, or `compute` for parse and transform)

## Patterns

### Store selection

| Data | Store | Why |
| --- | --- | --- |
| Access/refresh tokens, API keys, credentials, encryption keys | `flutter_secure_storage` (Keychain / Keystore) | only store with OS-backed encryption and no plaintext backup |
| Small non-sensitive scalars: theme, locale, onboarding-seen, a last tab or filter the user expects restored after a restart | `shared_preferences` | plaintext key-value, no schema, no queries, no migration cost |
| Relational domain data, offline cache, anything filtered, sorted, joined, or watched by the UI | **Drift** (default) | typed SQL, compile-checked queries, reactive streams, first-class migrations |
| Same, but the team wants raw SQL and no codegen | `sqflite` | thin SQLite wrapper; no type safety and no streams, so you hand-roll both |
| Object or key-value collections read by key, no joins | Isar / Hive | the original packages are unmaintained; adopt the community forks (`isar_community`, `hive_ce`) after checking their status. A regular Hive box loads every entry into memory |
| Images, downloads, exports, anything past a few hundred KB | filesystem via `path_provider`, path stored in the DB | keeps the DB small and its queries fast |
| Session-only state: in-flight form, scroll offset, a filter the user does not expect to survive a restart | in-memory (a provider) | persisting it buys a migration obligation for data nobody misses |

Sensitive **datasets** (health, financial records) rather than individual secrets: keep them in their own SQL database file, encrypted with SQLCipher (`sqlcipher_flutter_libs` on `package:sqlite3` 2.x; 3.x selects SQLCipher through its build hooks), so the main database stays plain and the regulated file can be wiped on its own. Its key lives in secure storage. Sensitive binary files (a medical receipt photo) are encrypted with a key from secure storage, since SQLCipher does not cover files on disk.

### Secrets are never in `shared_preferences`

```dart
// Bad - plaintext (an XML file or DataStore on Android, NSUserDefaults on iOS), readable on a rooted device, may land in backups
await prefs.setString('refresh_token', token);

// Good - Keychain / Keystore backed
await storage.write(key: 'refresh_token', value: token);
```

`shared_preferences` makes no confidentiality claim at all. Note the reverse failure too: secure storage is comparatively slow and size-limited, so it is the wrong home for a 5 MB cached response.

### Repository over the store

```dart
// Bad - notifier binds to drift; the store is now in the widget layer's dependency graph
class CartNotifier extends AsyncNotifier<Cart> {
  Future<Cart> build() => ref.read(appDatabaseProvider).select(...).get();
}

// Good - repository owns the store and returns domain models
abstract interface class CartRepository { Stream<Cart> watch(); Future<void> add(Item i); }
```

The repository is also the only place remote and local sources are reconciled, so cache policy stays in one file instead of leaking into every screen.

### One transaction per user action

```dart
// Bad - app killed between the two writes leaves an order with no items
await db.into(db.orders).insert(order);
await db.batch((b) => b.insertAll(db.orderItems, items));

// Good - both or neither
await db.transaction(() async {
  await db.into(db.orders).insert(order);
  await db.batch((b) => b.insertAll(db.orderItems, items));
});
```

The failure mode being defended against is process death, not contention: the OS can kill a backgrounded app between any two statements.

### Reactive reads

```dart
// Bad - one-shot read; the list goes stale after a background sync writes
Future<List<Todo>> load() => db.select(db.todos).get();

// Good - re-emits whenever a write touches todos
Stream<List<Todo>> watchAll() => db.select(db.todos).watch();
```

Drift streams re-run on writes through the same database instance, which removes the manual invalidate-and-refetch plumbing after every mutation. Any second construction of the database class is a second instance, and so is a background isolate that opens its own connection: share the database through a drift isolate so the UI stream sees its writes. `sqflite` has no equivalent; with it, you own invalidation.

### Local model is not the server DTO

```dart
// Bad - server JSON stored verbatim, then queried by digging into a blob
TextColumn get payload => text()();          // '{"status":"shipped", ...}'

// Good - the fields the app filters on are columns
TextColumn get status => text()();
DateTimeColumn get placedAt => dateTime()();
```

Any field you filter, sort, or index on is a column. Storing the raw response as a blob also couples the local schema to the server's wire format, so a harmless server rename becomes an on-device migration.

### Blobs on disk, path in the row

```dart
final dir = await getApplicationSupportDirectory();
final rel = 'receipts/$id.jpg';                     // relative: the iOS container path changes across updates; regulated or high-harm bytes are encrypted first (key in secure storage)
final file = await File(p.join(dir.path, rel)).create(recursive: true);
await file.writeAsBytes(bytes);
await db.into(db.receipts).insert(ReceiptsCompanion.insert(path: rel));
```

Large BLOB columns inflate every read that touches the row. Choose the directory by intent: application support for app-owned data the OS should preserve (on desktop the documents directory is the user's own Documents folder), the temporary or cache directory for regenerable data the OS is allowed to purge. Rebuild the absolute path at read time from the stored relative one. Handle the missing-file case on read - the OS can delete cache files without telling the app.

### Logout wipe

Enumerate it once, in the repository layer: secure storage keys deleted, user-scoped tables cleared or the database file deleted, cached files removed, non-sensitive preferences (theme, locale) deliberately kept. Deleting the account's rows while leaving its tokens in the Keychain is the common half-done version.

### Platform tiers

Mobile is the default assumption. On **desktop**, `dart:io` and the same stores are available, but files sit in user-accessible locations and secure storage maps to less uniform OS facilities. On **web**, `dart:io` is unavailable, SQLite requires drift's WASM setup (plain `sqflite` does not work), storage is browser-quota-bound and clearable by the user at any moment, binary payloads go to IndexedDB, and **no browser store offers secure-storage guarantees** - do not persist secrets on web; keep session secrets in memory and re-authenticate, or have the server manage the session via HttpOnly cookies.

## Output Format

Both modes open with `Tiers: {Mobile[, Desktop (<platforms>)][, Web]} (source: {platform directories | project CLAUDE.md | assumed})` - platform directories win when both sources exist; with neither, `Tiers: Mobile (source: assumed)`. Implement mode then emits one row per persisted item plus one `logout wipe` row. A stored thumbnail, a queue row, and an outbox entry are items; a derived value nobody persists is not. Name the tier constraint in the Rationale of each row it changes (web: session secret in memory, not secure storage):

```
| Data | Store | Sensitivity | Rationale |
|------|-------|-------------|-----------|
| refresh token | secure storage | Secret | OS keystore, wiped on logout |
| order + items | Drift | Personal | the user's purchases: queried, watched by UI, offline read |
| sync cursor | shared_preferences | Internal | app-produced, no query |
| logout wipe | secure storage, Drift, filesystem | Secret; Personal | tokens deleted, user tables cleared, receipts removed; pending uploads sent first, theme kept |
| theme mode | shared_preferences | Public | scalar, no query |
```

Classify each item by its most sensitive use. `Sensitivity: {Secret | Personal | Internal | Public}`. Secret = grants access (tokens, keys, credentials) -> secure storage, or memory only on web. Personal = user content or identifying/financial/health data -> a SQL or object store, encrypted (SQLCipher for rows, a per-file key from secure storage for binaries) when the dataset is regulated or high-harm, plain otherwise. Internal = app-produced operational data (sync cursors, queue state). Public = display-only or config. A client-generated id is a row's key for life; a server id is a nullable column filled on acknowledgement. Logout names what happens to rows not yet synced: upload first, or wipe after a warning, never silent loss.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one block per store the files read touch, citing every file that touches it:

```
Store: {Drift | sqflite | Isar | Hive | shared_preferences | secure storage | filesystem | IndexedDB (web) | in-memory}

Access Path: {repository at file:line | direct store access from <class> at file:line (defect) | second database instance at file:line (defect) | not in evidence - <file:line> stores the path}

Sensitive Placement: {OK | OK (in memory, session only) | VIOLATION: <what> in <store> at file:line}

Model Shape: {screen projection | server-DTO mirror or queried JSON blob at file:line (defect) | N/A}

Blobs: {filesystem, relative path in row | IndexedDB key in row | BLOB column at file:line (defect) | absolute path stored at file:line (defect) | N/A}

Transaction Scope: {multi-row or multi-table writes wrapped | single drift or sqflite batch (atomic) | unwrapped at file:line (defect) | N/A single-row write}

Schema Version: {<n> | unversioned (defect) | version key <name> (key-value store) | N/A (no persisted shape changed)}

Migration: {present - correctness reviewed by flutter-local-db-migration | MISSING for a shipped shape change (defect) | N/A no shape change}

Reactivity: {streamed | one-shot with manual refetch (sqflite) | one-shot, stale (defect) | one-shot, imperative flow | N/A}

Logout Wipe: {defined at file:line, pending uploads <sent first | wiped after warning | lost (defect)> | partial: <what survives> (defect) | undefined (defect) | N/A no account scope}

Platform Tiers: {Mobile | Mobile, Desktop | Mobile, Web | Mobile, Desktop, Web} - {<constraint per non-mobile tier> | none}
```

Access Path lists every path found. Typed columns the screens read are a projection even when their names match the server's. One block per store the files read touch; a dependency present but unused gets no block; a datum held in two stores appears in both blocks, each citing the other. For an in-memory store, Model Shape, Blobs, Schema Version, and Migration are `N/A`; Logout Wipe follows the rule below like any store. `openDatabase` on one path with sqflite's default `singleInstance: true` returns the shared instance and is not a second instance. A `Future` exposed through `asStream()` is `one-shot, stale (defect)`. `Logout Wipe: undefined` when the app has sign-in and the files read define no wipe; `N/A no account scope` only when the app has no sign-in. A store whose migration step looks wrong keeps `Migration: present - ...`; the step's defect is an `Also seen` line for `flutter-local-db-migration`. Several values in one slot are `;`-separated. A sync loop of upserts is one action: wrapped, or a batch. A value marked `(defect)` is a finding; the consuming workflow assigns severity.

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's slot names, or the path of a file that could not be read) when any check could not be exercised. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its slot, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape and a request to review, audit, or explain a failure takes the review shape.

The closing lines, each only when it has content:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}
```

## Avoid

- Tokens, credentials, or keys in `shared_preferences`, a plain SQLite column, or a file
- Bulk data in secure storage - it is for small values
- Widgets or notifiers holding a DAO, `SharedPreferences`, or secure-storage handle directly
- Mirroring the server's schema on-device, or storing raw response JSON in a column you then query
- Multi-table writes for one user action outside a transaction
- Changing a persisted shape without a migration and a version bump - old installs carry old data forever
- Large binaries as BLOB columns, or absolute file paths stored in a row
- One-shot reads for screens that must reflect background writes
- Assuming cache-directory files still exist on the next launch
- A logout path that clears rows but leaves tokens, or leaves the Keychain populated across an uninstall
- Adopting an object store without checking it is still maintained
- Persisting secrets on web, or assuming `sqflite` runs there
