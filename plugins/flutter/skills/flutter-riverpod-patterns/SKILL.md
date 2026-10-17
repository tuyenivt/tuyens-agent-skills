---
name: flutter-riverpod-patterns
description: "Apply Riverpod state patterns: provider kinds, Notifier/AsyncNotifier, AsyncValue, ref lifecycle, family, autoDispose, DI and test overrides."
metadata:
  category: mobile
  tags: [flutter, dart, riverpod, state-management, asyncvalue, providers, testing]
user-invocable: false
---

# Flutter Riverpod Patterns

> **Riverpod 2 and 3 differ where noted; read the major from `pubspec.yaml`.** In 3, `AsyncValue.value` returns null on error (2 rethrows; use `valueOrNull` there), a failing provider retries automatically (configure `retry:`), a dependency's error arrives wrapped in `ProviderException`, and touching `ref` or `state` after dispose throws (guard with `ref.mounted`). Riverpod 3 also moved `StateProvider`, `StateNotifierProvider`, and `ChangeNotifierProvider` to `package:flutter_riverpod/legacy.dart` and removed the `AutoDispose*` and `Family*` notifier base classes: every notifier extends `Notifier`, `AsyncNotifier`, or `StreamNotifier`, and a family notifier receives its argument through its constructor (`AsyncNotifierProvider.family<TodoNotifier, Todo, String>(TodoNotifier.new)`) rather than as a `build` parameter.
>
> **This skill is Riverpod-only.** If the detected project uses Bloc, Provider, or GetX, open the response with `Detected <X>; Riverpod-specific guidance does not apply` and fall back to the state-management-agnostic subset: keep UI state out of widgets, model async work as explicit loading/error/data states, do side effects in event handlers rather than in build/render, release every subscription, timer, and controller on teardown and never emit after close, and inject dependencies so tests can substitute them. Do not rewrite a working Bloc/Provider/GetX codebase into Riverpod unless the user asks for a migration.

## When to Use

- Choosing which provider kind fits a piece of state, or whether state belongs in a provider at all
- Implementing or reviewing a `Notifier` / `AsyncNotifier` and its `AsyncValue` consumption in the UI
- Diagnosing rebuild storms, "ref used after dispose", providers that never dispose, or state that resets unexpectedly
- Wiring dependency injection and test doubles through provider overrides

## Rules

- Provider kind follows the shape of the value, not habit: synchronous derived value -> `Provider`; one-shot async read -> `FutureProvider`; continuous source -> `StreamProvider`; state with methods that mutate it -> `NotifierProvider` (sync) or `AsyncNotifierProvider` / `StreamNotifierProvider` (async)
- `StateProvider`, `StateNotifierProvider`, and `ChangeNotifierProvider` are legacy - do not use them in new code; `Notifier` / `AsyncNotifier` replace them
- `build()` of a Notifier is pure: it computes and returns initial state. No navigation, no analytics, no writes, no `state =` inside it. Side effects live in the notifier's own methods or in `ref.listen`
- `ref.watch` only in `build` (widget or notifier) - it subscribes. `ref.read` only in callbacks and notifier methods - it does not. `ref.listen` only in `build`, and it is the only correct place for reacting to state with a side effect (snackbar, navigation, dialog)
- Never `ref.watch` inside a callback, and never `ref.read` a provider you depend on for rendering - the first registers a dependency from outside `build` (and through `.notifier` subscribes the widget to notifier replacement), so the rebuild it schedules has nothing to do with the tap; the second silently stops rebuilding
- Async state surfaces as `AsyncValue`; the UI handles loading, error, and data in all three branches. An unhandled error branch is a defect, not a style choice
- Mutating methods that can fail, on an `AsyncNotifier` or a `StreamNotifier`, wrap the work in `AsyncValue.guard` so the failure lands in `AsyncError` instead of an unhandled zone error
- `family` arguments must have stable value equality (primitives, records, or a `freezed`/`==`-implementing class). An argument with identity equality creates a new provider instance on every rebuild
- `autoDispose` is the default posture for screen-scoped state; keep-alive is a deliberate, justified exception. On Riverpod 2 an `.autoDispose` notifier provider needs the `AutoDispose` notifier base class (`AutoDisposeAsyncNotifier`); Riverpod 3 and `@riverpod` code generation do not. Anything holding a subscription, timer, or controller releases it via `ref.onDispose`. State that must outlive a screen (a cart, the auth session) is keep-alive, and a provider owning a shared resource (database, HTTP client) is keep-alive and closes it in `ref.onDispose`; a provider holding one user's data watches the session provider so sign-out rebuilds it
- External dependencies (HTTP client, repository, storage, clock) are reached through providers, never constructed inline in a notifier - overriding them is the only supported seam for tests and flavors
- Tests use a `ProviderContainer` with overrides and dispose it in teardown; widget tests use `ProviderScope(overrides: [...])`. No global mutable singletons

## Patterns

### Provider kind selection

| State shape | Provider |
|-------------|----------|
| Dependency / derived pure value | `Provider` |
| One-shot async fetch, no mutation | `FutureProvider` |
| Continuous source (socket, DB watch, auth changes) | `StreamProvider` |
| Mutable sync state + methods | `NotifierProvider` |
| Mutable async state + methods | `AsyncNotifierProvider` |
| Mutable state backed by a stream + methods | `StreamNotifierProvider` |

If nothing outside one widget reads it and it dies with the widget, it is `setState` / a `StatefulWidget` field - not a provider.

### `Notifier` and `AsyncNotifier`

```dart
final counterProvider = NotifierProvider<Counter, int>(Counter.new);

class Counter extends Notifier<int> {
  @override
  int build() => 0;               // pure: initial state only
  void increment() => state = state + 1;
}
```

```dart
final todosProvider = AsyncNotifierProvider.autoDispose<Todos, List<Todo>>(Todos.new);

class Todos extends AsyncNotifier<List<Todo>> {   // Riverpod 3; on 2, extends AutoDisposeAsyncNotifier
  @override
  Future<List<Todo>> build() => ref.watch(todoRepoProvider).fetchAll();

  Future<void> add(Todo todo) async {
    final repo = ref.read(todoRepoProvider); // read before the await: no ref use until the mounted check
    state = const AsyncLoading();
    final next = await AsyncValue.guard(() async {
      await repo.add(todo);
      return repo.fetchAll();
    });
    if (!ref.mounted) return;     // Riverpod 3; in 2, check a flag set by ref.onDispose in build
    state = next;
  }
}
```

`build` re-runs when a watched dependency changes, so the notifier re-fetches for free. `AsyncValue.guard` converts a thrown exception into `AsyncError` instead of an uncaught async error.

### Side effects out of `build`

```dart
// Bad - fires on every rebuild, and rebuild count is not something you control
@override
Future<List<Todo>> build() async {
  analytics.log('todos_opened');
  return repo.fetchAll();
}

// Good - the event that caused it owns it
void onScreenOpened() => ref.read(analyticsProvider).log('todos_opened');
```

`build` can run many times (dependency change, invalidation, hot reload). Anything non-idempotent there fires many times.

### Code generation (`riverpod_generator`)

```dart
@riverpod
Future<User> user(Ref ref, String id) => ref.watch(apiProvider).fetchUser(id);
// generates userProvider; the extra parameter makes it a family: ref.watch(userProvider('42'))

@riverpod
class Todos extends _$Todos {
  @override
  Future<List<Todo>> build() => ref.watch(todoRepoProvider).fetchAll();
}
```

Generated providers are `autoDispose` by default; opt out with `@Riverpod(keepAlive: true)`. Requires the `part 'file.g.dart';` directive and a `build_runner` run. The `Ref` parameter type differs by generator major version (older versions generate a per-provider ref type such as `UserRef`) - match whatever the project's existing generated files use rather than assuming.

Manual declaration and codegen interoperate; pick one per project and stay consistent. Do not migrate an existing manual codebase to codegen as a side effect of an unrelated change.

### `ref.watch` vs `ref.read` vs `ref.listen`

```dart
// Bad - read in build: the widget never rebuilds when the count changes
Widget build(BuildContext context, WidgetRef ref) {
  final count = ref.read(counterProvider);
  return Text('$count');
}

// Good
final count = ref.watch(counterProvider);
```

```dart
// Bad - watch in a callback: a dependency registered outside build, unrelated to the tap
onPressed: () => ref.watch(counterProvider.notifier).increment(),

// Good
onPressed: () => ref.read(counterProvider.notifier).increment(),
```

```dart
// Bad - navigating from build, on every rebuild
if (ref.watch(authProvider).isLoggedOut) context.go('/login');

// Good - listen fires once per transition; call it in build, react outside it
ref.listen(authProvider, (previous, next) {
  if (next.isLoggedOut) context.go('/login');
});
```

Outside a `build` (for example in `initState`), use `ref.listenManual` and close the returned subscription. An action that spans providers is a notifier method that reads the others. Narrow rebuilds with `select` when a widget needs one field of a large object:

```dart
final locale = ref.watch(settingsProvider.select((s) => s.locale)); // rebuilds only when locale changes
```

### `AsyncValue`

```dart
// Bad - on error this renders an empty list (Riverpod 3) or throws in build (Riverpod 2)
final todos = ref.watch(todosProvider).value ?? [];
return TodoList(todos);

// Good - all three branches handled
return ref.watch(todosProvider).when(
  data: (todos) => TodoList(todos),
  loading: () => const LoadingView(),
  error: (err, stack) => ErrorView(err, onRetry: () => ref.invalidate(todosProvider)),
);
```

Dart 3 pattern matching is equivalent and often reads better (`AsyncValue` is `sealed` from Riverpod 2.4; below that the switch is not exhaustive, so use `.when`):

```dart
return switch (ref.watch(todosProvider)) {
  AsyncData(:final value) => TodoList(value),
  AsyncError(:final error) => ErrorView(error),
  AsyncLoading() => const LoadingView(),
};
```

Both forms behave the same: `ref.refresh`/`ref.invalidate` keep the previous `AsyncData` with `isLoading` set, so both keep showing data, and both show loading when a dependency change reloads the provider (`.when` via `skipLoadingOnReload: false`). To keep stale content on screen in every case, read the value before branching, and still surface a failed refresh:

```dart
final async = ref.watch(todosProvider);
final todos = async.value;                       // Riverpod 3; valueOrNull in 2
if (todos != null) {
  return TodoList(todos, refreshing: async.isLoading, refreshError: async.error);
}
return async.hasError ? ErrorView(async.error!) : const LoadingView();
```

A value derived from an async provider stays async: `ref.watch(cartProvider).whenData(total)` in a `Provider`, not a default of 0 that hides loading and errors.

`ref.invalidate` schedules a rebuild of the provider; `ref.refresh` does the same and returns the new value.

### `family` and `autoDispose`

```dart
// Bad - a new Filter instance each rebuild; identity equality means a fresh provider every time
ref.watch(itemsProvider(Filter(status: 'open')));

// Good - value equality: records, freezed, or a const instance (itemsProvider declared .family<List<Item>, ({String status, int page})>)
ref.watch(itemsProvider((status: 'open', page: 1)));
```

```dart
// Good - keep an expensive result alive only while it is worth caching
final catalogProvider = FutureProvider.autoDispose<Catalog>((ref) async {
  final catalog = await ref.watch(catalogRepoProvider).fetch();
  if (!ref.mounted) return catalog;  // Riverpod 3: disposed during the fetch
  final link = ref.keepAlive(); // after the await: a failed fetch is not cached
  final timer = Timer(const Duration(minutes: 5), link.close);
  ref.onDispose(timer.cancel);
  return catalog;
});
```

Every subscription, timer, controller, or listener created in a provider is released in `ref.onDispose`. A provider that opens a stream and never disposes it is the most common Riverpod leak.

State that must outlive the screen that started it - an undo window, an upload queue - is a keep-alive provider the app shell reads once at startup (`ref.read` in the root widget, or `ref.listen` from a keep-alive bootstrap provider) so it exists before any screen; its timers are cancelled in `ref.onDispose`.

### Dependency injection via overrides

```dart
// Declared without an implementation; the composition root supplies it
final todoRepoProvider = Provider<TodoRepo>((ref) => throw UnimplementedError());

void main() => runApp(ProviderScope(
      overrides: [todoRepoProvider.overrideWithValue(HttpTodoRepo(dio))],
      child: const App(),
    ));
```

This makes a missing binding fail loudly on its first read instead of a silent default, and gives flavors, previews, and tests one place to substitute.

### Test overrides

```dart
test('loads todos', () async {
  final container = ProviderContainer(
    overrides: [todoRepoProvider.overrideWithValue(FakeTodoRepo())],
  );
  addTearDown(container.dispose);

  final sub = container.listen(todosProvider.future, (_, __) {}); // keeps the autoDispose provider alive
  expect(await sub.read(), hasLength(2));
});
```

For widget tests, wrap the widget under test in `ProviderScope(overrides: [...])`. Notifier-backed providers are substituted with `overrideWith(() => FakeTodos())` rather than `overrideWithValue`, since the provider builds the notifier. Never leave a container undisposed - leaked containers keep subscriptions alive across tests and produce order-dependent failures.

## Output Format

When invoked from an implementation workflow, emit the provider graph:

```
| State | Provider kind | Scope | Dependencies | Notes |
|-------|---------------|-------|--------------|-------|
| Todo list | AsyncNotifierProvider.autoDispose<Todos, List<Todo>> | autoDispose | todoRepoProvider | mutations via guard |
| Auth session | NotifierProvider<Auth, AuthState> | keepAlive | secureStorageProvider | app-lifetime; has sign-in/out methods, else StreamProvider |
| User by id | FutureProvider.autoDispose.family<User, String> | autoDispose | apiProvider | String arg |
| TodoRepo | Provider<TodoRepo> | keepAlive | - | DI seam, overridden at root |
```

`Scope: {autoDispose | keepAlive}` - lifetime only, matching the declared kind. `Provider kind` is the declaration as written, class names included. Every provider the plan declares is a row, bootstrap providers included; a new package goes in Notes. A provider bound by a root override records that in Notes, not in Scope.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one finding block per issue:

```
### [{Critical | High | Medium | Low}] {file:line}

- Rule: {ref-lifecycle | provider-kind | async-value | disposal | family-equality | side-effect-in-build | di-override | test-override | state-in-widget}
- Code: {one-line citation}
- Problem: {what breaks at runtime, not what looks unusual}
- Recommendation: {concrete edit}
```

The heading severity is one of Critical, High, Medium, Low. Critical = code that does not compile on the pinned major (a legacy kind imported from its pre-3 path, a removed base class), a subscription, timer, or controller never released, an unhandled error branch on a user-facing path, or state that silently stops updating (including a mutable handle exposed through a `Provider` whose changes rebuild nothing - `provider-kind`). High = misuse that misbehaves under realistic use (duplicate side effects from `build`, family arg without value equality, watch-in-callback, `ref` or `state` used after an await without `ref.mounted` on Riverpod 3, a mutator that sets `AsyncLoading` then awaits without `guard`). Medium = works today but fragile (a legacy kind that still compiles, a kind that does not fit the state shape, missing DI seam, screen state without `autoDispose` or keep-alive without justification, an undisposed test container, state a widget should own held in a provider or business logic in a widget). Low = style or naming. When a finding matches two bands, the higher band wins.

When one line breaks two rules with one fix, file it under the rule naming the runtime failure: a subscription that is never released is `disposal`, not `side-effect-in-build`. Missing `autoDispose` files under `disposal`. A `family-equality` defect anchors on the argument class declaration, with its call sites as `also`; when that file was not read it anchors on the first call site in path order with `(unconfirmed: depends on <path>)`. A removed base class or a legacy kind that no longer compiles is `provider-kind`. A mutable handle exposed through a `Provider` anchors on the declaration. `ref.read` inside `build` is `ref-lifecycle`, Critical when the value is rendered and Medium otherwise. A shared resource (database, HTTP client) a keep-alive provider never closes is `disposal`, Medium. A legacy `StateNotifier` releases in its `dispose` override.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Rule` values, or the path of a file that could not be read) when any check could not be exercised, then the `No <rule> findings.` lines. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean and gets its `No <rule> findings.` line; a check on the `Not checked` line does not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Problem:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape, a request to review or audit takes the review shape, and a supplied symptom or bug report takes diagnose mode.

The closing lines - `Also seen` and `Not checked` only when they have content, then one `No <rule> findings.` line per clean check (no block, not on the `Not checked` line), blank-separated:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

{No <rule> findings.}
```

Diagnose mode opens with one line per reported symptom, `Symptom <n>: <the report's title or first sentence>`, a title that lists two symptoms is two lines, naming on each any premise the files read contradict (a flag the report says is on, a version it names) - the diagnosis then proceeds on what the code shows - and stating when the files read cannot cause the symptom. Blocks for the causes of the reported symptoms come first, grouped by symptom in reported order and within a group by severity, each such block's `Problem:` line opening with `Symptom <n>:`; a cause shared by two symptoms is one block opening `Symptom 1, 2:`, placed with the lower-numbered symptom; every other defect seen in the files read follows, ordered as in review mode. The zero-finding lines named above are omitted in diagnose mode; `Also seen` and `Not checked` lines are kept.

In fallback mode (non-Riverpod project), emit the same structures using the detected framework's terms (e.g., Bloc/Cubit kinds in the graph table), with `Scope` becoming that framework's lifetime vocabulary and DI through its own seam (`RepositoryProvider`, `BlocProvider`, get_it); constructing the repository at the composition root is that seam, not a defect. Findings use only `async-value`, `disposal`, `side-effect-in-build`, `di-override`, `test-override`, and `state-in-widget`, at the band of the analogous Riverpod defect; a Cubit or Bloc constructor runs once per creation, so side effects there file under `side-effect-in-build`. The Riverpod-only rules - `ref-lifecycle`, `provider-kind`, `family-equality` - are neither reported nor enumerated as zero-finding lines. Under Bloc, a subscription a Cubit or Bloc holds is released in its `close()` override and `emit` after close is guarded by `isClosed` (`disposal`); a repository that swallows failures into an empty result is `async-value`; a test asserting only `isA<State>()` is `test-override`.

## Avoid

- `StateProvider` / `StateNotifierProvider` / `ChangeNotifierProvider` in new code - use `Notifier` / `AsyncNotifier`
- Side effects in `build()` - navigation, analytics, writes, snackbars belong in methods or `ref.listen`
- `ref.read` for a value the UI renders, or `ref.watch` inside a callback
- `.value!` or `?? fallback` on an `AsyncValue` as a way to skip the error branch
- Constructing a repository, `Dio`, or storage client inside a notifier - it removes the only test seam
- `family` arguments without value equality (freshly constructed non-`freezed` objects, closures, lists)
- Global keep-alive by default - `autoDispose` unless the state is genuinely app-lifetime
- Providers that open streams, timers, or controllers without a matching `ref.onDispose`
- `ProviderContainer` without `addTearDown(container.dispose)`
- Business logic in widgets - the widget reads state and dispatches intent, nothing else
- Rewriting a Bloc/Provider/GetX project to Riverpod as an unrequested side effect
