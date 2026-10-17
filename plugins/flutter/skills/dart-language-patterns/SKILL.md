---
name: dart-language-patterns
description: "Apply Dart 3 idioms: null safety, records, pattern matching, sealed classes, class modifiers, extension types, async/Stream, isolates."
metadata:
  category: mobile
  tags: [flutter, dart, null-safety, patterns, sealed-classes, records, async, isolates]
user-invocable: false
---

# Dart Language Patterns

> Confirm the project's target platforms first - they change the isolate guidance below. Widget-tree, rebuild, and lifecycle concerns live in `flutter-widget-patterns`. This skill owns language-level shape decisions.

## When to Use

- Writing or reviewing Dart that is not widget-tree code: models, repositories, mappers, controllers, pure logic
- Choosing between a record and a class, a sealed hierarchy and an enum, `late` and `?`, an extension type and a typedef
- Reviewing whether code reads as Dart 3 vs null-safety-retrofitted Dart 2 or Kotlin/TypeScript translated into Dart

## Rules

- Model absence with `?`, never a sentinel (`-1`, `''`, epoch). `!` only where a non-null invariant is locally proven; every other `!` is a scheduled crash, and so is `.first`, `.last`, or `[0]` on a possibly-empty collection (use `firstOrNull`)
- `late` only for a value guaranteed assigned before any read - in an earlier callback (`initState`) or by a lazy initializer (`late final x = expensive();`); prefer `late final`. Never `late` to silence the compiler on a genuinely optional value - that is `?`
- Sealed hierarchy + exhaustive `switch` for closed variant sets. No `default` or `_` arm on a sealed switch: it makes the switch trivially exhaustive and adding a variant stops being a compile error
- `switch` expressions and object patterns over if-else chains on type or shape; destructure and bind in one step
- Records for multi-value returns with no behavior; a class once the group has invariants, methods, or is part of a public API
- Class modifiers state the boundary contract explicitly (see the table below) - an unmodified `class` means "anyone may extend or implement this", which is rarely the intent
- `extension type` for zero-cost domain wrappers over primitives; it is compile-time only, so never depend on it for runtime type tests or polymorphism
- Every `StreamSubscription`, `StreamController`, `Timer`, and owned client or handle (`http.Client`, a database) has a matching `cancel`/`close` on the owner's teardown path (`dispose`, or `ref.onDispose` for a provider)
- Money is integer minor units or a decimal type, never `double`
- CPU-bound work (large JSON decode, parsing, crypto, image processing) goes off the UI isolate - `compute` when web is a target, `Isolate.run` otherwise; `async` alone does not free the UI thread
- `rethrow`, never `throw e` - `throw e` discards the original stack trace. Catch with `on <Type>`; bare `catch` only at a boundary that sends the error to the reporting service
- Build collections declaratively with collection-`if`/`for` and spreads, not `add` sequences

## Patterns

### Null safety and promotion

```dart
// Bad - a public field does not promote; `user.email` is still String? inside the if
if (user.email != null) send(user.email!);

// Good - a local promotes, and the `!` disappears
final email = user.email;
if (email != null) send(email);
```

Only **private final** fields promote (Dart 3.2+). Public or mutable fields never do, because a getter could return a different value on the second read - so the `!` a reviewer sees is often a promotion failure, not a real invariant.

Prefer the null-aware operators over branching: `user.address?.city ?? 'unknown'`, `_cache ??= compute()`.

### `late` discipline

```dart
// Bad - `late` used to dodge "field must be initialized"; read order is now a runtime bet
late String _token;

// Good - genuinely optional
String? _token;

// Good - guaranteed assigned in initState, never reassigned
late final AnimationController _controller;
```

`late` converts a compile-time error into a `LateInitializationError` at runtime. That trade is only worth it when the assignment is guaranteed by a framework-ordered callback, or made by a lazy initializer.

### Records vs classes

```dart
// Bad - a Map for a two-value return: no types, no checking
Map<String, Object?> parseRange(String s) => {'start': a, 'end': b};

// Good - a record: structural, immutable, value-equal
({DateTime start, DateTime end}) parseRange(String s) => (start: a, end: b);

final (:start, :end) = parseRange(input);
```

Records have value equality and no declaration cost, which makes them right for local plumbing and multi-value returns. Promote to a class (typically freezed) once the group needs a name in an API, an invariant, or a method.

Names on **positional** record fields are documentation only - `(int x, int y)` is still accessed as `$1` and `$2`. Use named fields when you want to read them by name.

An identity that changes over time (a client id later replaced by a server id) is one class with a nullable server-id field, never a mutable `String`; a money amount is `(int minor, String currency)` with the exponent taken from the currency, not the locale.

### Sealed classes and exhaustive `switch`

```dart
sealed class LoadState { const LoadState(); }
final class Loading extends LoadState { const Loading(); }
final class Loaded extends LoadState { const Loaded(this.items); final List<Item> items; }
final class Failed extends LoadState { const Failed(this.error); final Object error; }

final label = switch (state) {
  Loading()            => 'Loading...',
  Loaded(:final items) => '${items.length} items',
  Failed(:final error) => 'Failed: $error',
};
```

`sealed` is implicitly abstract and confines subtypes to the same library, which is what lets the compiler check exhaustiveness. Adding a `Refreshing` variant then breaks every `switch` that must handle it - the whole point. Guards refine an arm without breaking that: `Loaded(:final items) when items.isEmpty => 'Nothing here'`.

Use an `enum` (with fields and methods if needed) when variants carry no distinct data; use `sealed` when they do.

### Class modifiers

| Modifier | Outside the declaring library | Use for |
|----------|-------------------------------|---------|
| `final` | neither extend nor implement | leaf and value types; closes the hierarchy |
| `base` | extend, not implement | invariants that live in the base and must be inherited, not re-declared |
| `interface` | implement, not extend | pure contracts: repository ports, service boundaries |
| `sealed` | neither; implicitly abstract | closed variant sets driving exhaustive `switch` |

Codegen-annotated classes (freezed, json_serializable) take the form their generator requires; their modifiers are not findings. Test doubles are the common tension: `interface`/unmodified classes can be implemented by a fake, `final` cannot. Choose `final` for types you own end-to-end, `interface` for seams you expect callers to stub.

### Extension types

```dart
// Bad - every id is a String; swapping the arguments compiles fine
void link(String userId, String orderId) { ... }

// Good - distinct types at compile time, no wrapper object at runtime
extension type UserId(String value) {}
extension type OrderId(String value) {}
void link(UserId userId, OrderId orderId) { ... }
```

An extension type is erased to its representation type at runtime, so runtime type tests and dynamic dispatch cannot tell it apart from the underlying value - it is a static-checking tool, not a runtime one. Adding `implements String` makes the wrapper assignable wherever a `String` is accepted and exposes every `String` member on it; the two ids still cannot be swapped for each other, but the wrapper now flows into raw-string APIs unchecked - add it only deliberately.

### Async: start concurrently, await once

```dart
// Bad - independent calls serialized; latencies add
final user = await fetchUser();
final prefs = await fetchPrefs();

// Good - both in flight; typed results, one error surface (.wait on records needs import 'dart:async')
final (user, prefs) = await (fetchUser(), fetchPrefs()).wait;
```

A `Future` starts when it is created, not when it is awaited. Starting two futures and awaiting them one by one is not a fix: if the first throws, the second's error goes unhandled. The record `.wait` (Dart 3) awaits all of them and throws one `ParallelWaitError`; `Future.wait([...])` covers a homogeneous list and throws the first error.

Fire-and-forget needs to be explicit - wrap it in `unawaited(...)` from `dart:async` so an intentional gap is distinguishable from a forgotten `await`, and attach error handling: a failed future nobody awaits reaches only the zone's uncaught-error handler, detached from the caller's control flow and from any `try`/`catch`.

### Streams

```dart
// Bad - subscription outlives its owner: leaks, and fires after teardown
repo.watch(id).listen(_onData);

// Good - own it, then cancel it
_sub = repo.watch(id).listen(_onData);   // created in initState
_sub.cancel();                           // in dispose
```

A plain stream is single-subscription: a second `listen` throws. Use a broadcast controller or `asBroadcastStream()` only when there really are multiple listeners - and note broadcast streams drop events emitted while nobody is listening.

`async*` with `yield` is the readable way to produce a stream; it stops when the listener cancels, so no manual controller bookkeeping is needed.

### Isolates

```dart
// Bad - async does not yield the UI thread; a 40ms decode still drops frames
final data = await Future(() => jsonDecode(hugeJson));

// Good - real parallelism, off the UI isolate
final data = await Isolate.run(() => jsonDecode(hugeJson) as Map<String, Object?>);
```

The closure and everything it captures are copied to the new isolate, so captured state must be sendable - no `BuildContext`, no open subscriptions, no platform-channel handles. Startup and copying cost real time, so small payloads finish faster inline; move work off-isolate because it is measurably long, not on principle.

`compute` is Flutter's wrapper: on native it runs `Isolate.run` and accepts closures; on web it runs the callback inline on the main thread, while `Isolate.run` throws `UnsupportedError`. Code that also targets web calls `compute`, and since the jank remains there, reduces the work instead of relocating it.

### Declarative collections

```dart
// Bad - imperative assembly by mutation
final actions = <Widget>[];
actions.add(const SaveAction());
if (canDelete) actions.add(const DeleteAction());

// Good
final actions = <Widget>[
  const SaveAction(),
  if (canDelete) const DeleteAction(),
  for (final tag in tags) TagChip(tag),
  ...?extraActions,
];
```

`...?` spreads a possibly-null list without a branch. The same syntax works in map and set literals.

## Output Format

When invoked from an implementation workflow, emit decisions per concern:

```
| Concern | Decision | Rationale |
|---------|----------|-----------|
| Load state | sealed class + exhaustive switch | 4 variants carrying distinct data |
| Ids | extension type UserId(String) | compile-time swap detection, no runtime cost |
| Parse result | record ({DateTime start, DateTime end}) | two values, no behavior |
| Feed decode | Isolate.run | 30-50ms payloads on the UI isolate |
```

One row per shape decision the task actually forced; do not pad with concerns the task never raised.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one block per finding:

```
### [{Must | Recommend}] {file:line}

- Category: {Null Safety | Exhaustiveness | Type Modeling | Async | Concurrency | Error Handling | Resource Lifecycle | Collection Style}
- Code: {one-line citation}
- Issue: {the Dart 3 rule broken and the failure it produces}
- Recommendation: {concrete edit}
```

`[Must]` when the violation produces a runtime failure or leak (a scheduled-crash `!` or `late`, disabled exhaustiveness, missing `cancel`/`close`, swallowed or unobserved errors, UI-thread jank filed as `Concurrency`, money as `double` filed as `Type Modeling`, `Future.delayed` used to wait for another async step filed as `Async`). A misused `late` is `Null Safety`. `[Recommend]` for shape and readability (type modeling including sentinels, collection style, serialized independent awaits, an isolate spawned for trivial work, an unmodified public class, `implements <representation>` on an extension type) and for degraded diagnostics (`throw e` discarding a stack trace, a bare `catch` that logs or shows the error but never reports it). A `dynamic` value or unchecked `as` cast flowing past a decode boundary, and a type used as a map key or `family` argument without `==`/`hashCode`, are `Type Modeling` - the cast `[Must]` (it throws at runtime), the key type `[Recommend]`; writing to a closed sink or notifier is `Resource Lifecycle`, `[Must]`; a `Future` exposed through `asStream()` where callers expect re-emission is `Async`, `[Recommend]`. Language-level defects inside widget files are this skill's. The label follows the violation, not mitigation elsewhere in the call chain.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Category` values, or the path of a file that could not be read) when any check could not be exercised, then the `No <category> findings.` lines. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean and gets its `No <category> findings.` line; a check on the `Not checked` line does not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Issue:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape and a request to review, audit, or explain a failure takes the review shape.

The closing lines - `Also seen` and `Not checked` only when they have content, then one `No <category> findings.` line per clean check (no block, not on the `Not checked` line), blank-separated:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

{No <category> findings.}
```

Both modes open with two lines:

```
Dart SDK: {<version> (pubspec) | <version> (inferred from <feature>)}{ - Dart 3 patterns unavailable}

Targets: {<platforms>} (source: {platform directories | project CLAUDE.md | brief | assumed mobile})
```

The version is the lower bound of pubspec.yaml's `environment: sdk:` constraint or, when that is unavailable, inferred from features already in the code (records and patterns imply 3.0+, `extension type` 3.3+). `Targets` keys the `compute` vs `Isolate.run` guidance: web present -> `compute`, also for a feature that is native-only at runtime but compiles for web; `Isolate.run` only in code a `kIsWeb` guard keeps off the web build; below Dart 2.19 `Isolate.run` does not exist, so `compute` there too. Below 3.0 the first line ends ` - Dart 3 patterns unavailable`: `Exhaustiveness` is listed as `Not checked`, record, sealed, class-modifier, and extension-type recommendations are skipped, and fixes use pre-3.0 forms (`Future.wait`, `package:collection`'s `firstOrNull`); `Type Modeling` (money as `double`, sentinels) and `Collection Style` (collection-`if`/`for`, Dart 2.3+) stay in force. Below 2.12 `Null Safety` is also `Not checked`. On 3.0-3.2, skip `extension type` recommendations (3.3+); below 3.2, treat private-final field promotion as unavailable.

## Avoid

- `!` to clear an analyzer error - find why promotion failed; usually the field needs to be private and final, or copied to a local
- `late` on anything genuinely optional - use `?`
- `default` or `_` on a switch over a sealed type - it silently disables exhaustiveness checking
- `dynamic` to escape a type error; `Object?` plus a pattern match keeps the check
- Records where a named domain type belongs, or a class where a two-value return would do
- Plain `class` for public types with no modifier considered - state `final`, `base`, `interface`, or `sealed`
- `implements <representation>` on an extension type unless substitutability is the goal
- `throw e` inside `catch` - use `rethrow`
- Bare `catch (e)` outside a reporting boundary, and `catch` blocks that swallow without logging
- Un-awaited futures with no `unawaited()` and no error handler - the failure bypasses every local handler
- `listen` without a stored subscription, or a `StreamController` with no `close`
- `Isolate.run` for work measured in microseconds - the copy costs more than the work - or on a web target, where it throws
- `Future.delayed` to wait for another async step to finish (a deliberate backoff delay is fine)
