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
- A user action that writes more than one row or table is one local transaction; a single-row write, or a single drift `batch` (already atomic), does not need another. Transactions here buy **atomicity across an interrupted app**, not concurrency control
- Anything persisted survives app updates. A shape change ships with a migration and a bumped schema version - delegate to `flutter-local-db-migration`
- Binary payloads go to the filesystem (IndexedDB on web); the row stores a path relative to the base directory
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
final rel = 'receipts/$id.jpg';                     // relative: the iOS container path changes across updates
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

When invoked from an implementation workflow, emit one row per persisted item. When the project targets desktop or web, open with the `Tiers:` line in `flutter-adaptive-responsive`'s form (`Tiers: Mobile, Web (source: platform directories)`) - and name the tier constraint in the Rationale of each row it changes (e.g. web: session secret in memory, not secure storage):

```
| Data | Store | Sensitivity | Rationale |
|------|-------|-------------|-----------|
| refresh token | secure storage | Secret | OS keystore, wiped on logout |
| order + items | Drift | Internal | queried, watched by UI, offline read |
| theme mode | shared_preferences | Public | scalar, no query |
```

Classify each item by its most sensitive use. `Sensitivity: {Secret | Personal | Internal | Public}`. Secret = grants access (tokens, keys, credentials) -> secure storage. Personal = user content or identifying/financial/health data -> SQL store, SQLCipher when the dataset is regulated or high-harm; a Personal binary goes to an encrypted file. Internal = app-produced operational data. Public = display-only or config.

Implement mode ends with `Pre-existing: <file:line> - <defect>` for each defect in code the plan edits or depends on but does not fix, or `Pre-existing: none`. Code not yet written is cited as `<path> (new)`. A file the plan depends on that is absent or could not be read is listed as `Not read: <path> - <reason>`. A defect the change cannot ship on top of is fixed in the plan, not listed as `Pre-existing`.

When invoked from a review workflow, emit one block per store the change touches, citing every file that touches it:

```
Store: {Drift | sqflite | Isar | Hive | shared_preferences | secure storage | filesystem | in-memory}
Access Path: {repository at file:line | direct store access from <widget|notifier> at file:line (defect) | second database instance at file:line (defect)} - list each path found
Sensitive Placement: {OK | VIOLATION: <what> in <store> at file:line}
Model Shape: {screen projection | server-DTO mirror or queried JSON blob at file:line (defect) | N/A} - typed columns the screens read are a projection even when their names match the server's
Blobs: {filesystem, relative path in row | BLOB column at file:line (defect) | absolute path stored at file:line (defect) | N/A}
Transaction Scope: {multi-row or multi-table writes wrapped | single drift batch (atomic) | unwrapped at file:line | N/A single-row write}
Schema Version: {<n> | unversioned | version key <name> (key-value store) | N/A (no persisted shape changed)}
Migration: {present - correctness reviewed by flutter-local-db-migration | MISSING for a shipped shape change | N/A no shape change}
Reactivity: {streamed | one-shot with manual refetch | one-shot, stale | one-shot, imperative flow | N/A}
Logout Wipe: {defined at file:line | partial: <what survives> | undefined | N/A no account scope}
Platform Tiers: {mobile | + desktop | + web: <constraint>}
```

A defect that depends on code outside the files read is still marked, with `(unconfirmed: depends on <path>)` appended to its slot; the consuming workflow assigns severity. A check whose subject does not appear in the files read is clean; a check the files read cannot exercise is listed once as `Not checked: <names> - <reason>` and gets no clean or zero-finding line. A file in scope that could not be read is named on that line.

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
