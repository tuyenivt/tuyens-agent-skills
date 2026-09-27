---
name: flutter-riverpod-patterns
description: "Apply Riverpod state patterns: provider kinds, Notifier/AsyncNotifier, AsyncValue, ref lifecycle, family, autoDispose, DI and test overrides."
metadata:
  category: mobile
  tags: [flutter, dart, riverpod, state-management, asyncvalue, providers, testing]
user-invocable: false
---

# Flutter Riverpod Patterns

> **Riverpod 2 and 3 differ where noted; read the major from `pubspec.yaml`.** In 3, `AsyncValue.value` returns null on error (2 rethrows; use `valueOrNull` there), a failing provider retries automatically (configure `retry:`), a dependency's error arrives wrapped in `ProviderException`, and touching `ref` or `state` after dispose throws (guard with `ref.mounted`).
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
- Never `ref.watch` inside a callback, and never `ref.read` a provider you depend on for rendering - the first adds a subscription per tap until the next rebuild, the second silently stops rebuilding
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
final todosProvider = AsyncNotifierProvider<Todos, List<Todo>>(Todos.new);

class Todos extends AsyncNotifier<List<Todo>> {
  @override
  Future<List<Todo>> build() => ref.watch(todoRepoProvider).fetchAll();

  Future<void> add(Todo todo) async {
    state = const AsyncLoading();
    final next = await AsyncValue.guard(() async {
      await ref.read(todoRepoProvider).add(todo);
      return ref.read(todoRepoProvider).fetchAll();
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
// Bad - watch in a callback: a new subscription every tap
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

Dart 3 pattern matching is equivalent and often reads better:

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

// Good - value equality: records, freezed, or a const instance
ref.watch(itemsProvider((status: 'open', page: 1)));
```

```dart
// Good - keep an expensive result alive only while it is worth caching
final catalogProvider = FutureProvider.autoDispose<Catalog>((ref) async {
  final catalog = await ref.watch(catalogRepoProvider).fetch();
  final link = ref.keepAlive(); // after the await: a failed fetch is not cached
  final timer = Timer(const Duration(minutes: 5), link.close);
  ref.onDispose(timer.cancel);
  return catalog;
});
```

Every subscription, timer, controller, or listener created in a provider is released in `ref.onDispose`. A provider that opens a stream and never disposes it is the most common Riverpod leak.

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

  expect(await container.read(todosProvider.future), hasLength(2));
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

`Scope: {autoDispose | keepAlive}` - lifetime only, matching the declared kind. A provider bound by a root override records that in Notes, not in Scope.

Implement mode ends with `Pre-existing: <file:line> - <defect>` for each defect in code the plan edits or depends on but does not fix, or `Pre-existing: none`. Code not yet written is cited as `<path> (new)`. A file the plan depends on that is absent or could not be read is listed as `Not read: <path> - <reason>`. A defect the change cannot ship on top of is fixed in the plan, not listed as `Pre-existing`.

When invoked from a review workflow, emit one finding block per issue:

```
### [Severity] file:line

- Rule: {ref-lifecycle | provider-kind | async-value | disposal | family-equality | side-effect-in-build | di-override | test-override | state-in-widget}
- Code: {one-line citation}
- Problem: {what breaks at runtime, not what looks unusual}
- Recommendation: {concrete edit}
```

`Severity: {Critical | High | Medium | Low}`. Critical = code that does not compile, leaked subscription, unhandled error branch on a user-facing path, or state that silently stops updating. High = misuse that misbehaves under realistic use (duplicate side effects from `build`, family arg without value equality, watch-in-callback, `ref` or `state` used after an await without `ref.mounted` on Riverpod 3). Medium = works today but fragile (legacy provider kinds, missing DI seam, keep-alive without justification, undisposed test containers, state a widget should own held in a provider or business logic in a widget). Low = style or naming. When a finding matches two bands, the higher band wins.

One block per defect, not per code site - a constructor that both leaks a subscription and logs analytics emits two. When a single defect satisfies two rules, file it under the one naming the runtime failure: a subscription that is never released is `disposal`, not `side-effect-in-build`. Missing `autoDispose` files under `disposal`. A `family-equality` defect anchors on the argument class declaration, with its call sites as `also`. A legacy `StateNotifier` releases in its `dispose` override.

Blocks are one per defect, ordered by severity, then file and line, then enum order. Each site of a repeated rule is its own defect; a single defect that needs edits in several places anchors on the line to edit and names the others as `also <file:line>` on its citation line.

A finding that depends on code outside the files read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to the line describing its effect. A check whose subject does not appear in the files read is clean; a check the files read cannot exercise is listed once as `Not checked: <names> - <reason>` and gets no clean or zero-finding line. A file in scope that could not be read is named on that line.

For each rule in the enum with zero findings, emit exactly `No <rule> findings.` so the workflow knows the check ran; omit that line for rules with findings.

In fallback mode (non-Riverpod project), emit the same structures using the detected framework's terms (e.g., Bloc/Cubit kinds in the graph table), with `Scope` becoming that framework's lifetime vocabulary and DI through its own seam (`RepositoryProvider`, `BlocProvider`, get_it); constructing the repository at the composition root is that seam, not a defect. Findings use only `async-value`, `disposal`, `side-effect-in-build`, `di-override`, `test-override`, and `state-in-widget`, at the band of the analogous Riverpod defect; a Cubit or Bloc constructor runs once per creation, so side effects there file under `side-effect-in-build`. The Riverpod-only rules - `ref-lifecycle`, `provider-kind`, `family-equality` - are neither reported nor enumerated as zero-finding lines.

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
