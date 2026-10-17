---
name: flutter-navigation-patterns
description: "Design go_router navigation: route trees, shell routes, auth redirects, typed routes, path and query params, deep links, web URL strategy."
metadata:
  category: mobile
  tags: [flutter, dart, go-router, navigation, deep-links, routing, web]
user-invocable: false
---

# Flutter Navigation Patterns

> go_router is the default. If the project uses `auto_route`, the concepts map (`@RoutePage()` pages, generated route classes, a hand-written `RootStackRouter` config, `AutoRouteGuard` in place of `redirect`) - keep the guidance, swap the API names. If it uses raw Navigator 2.0 (`RouterDelegate` + `RouteInformationParser`), the route-tree and guard patterns still apply but you own the plumbing; do not propose migrating routers as a side effect of an unrelated change.

## When to Use

- Declaring or restructuring an app's route tree, tabs, or nested navigation
- Adding an auth guard, onboarding gate, or any conditional redirect
- Wiring deep links / universal links, or debugging a link that opens the wrong screen
- Passing data between screens, or fixing a screen that breaks on browser refresh or process death

## Rules

- The `GoRouter` instance is created once at app scope and passed to `MaterialApp.router(routerConfig: ...)`. Rebuilding it inside a widget `build` discards navigation history
- Child `path` values are relative (no leading `/`); only top-level routes start with `/`, and routes directly under a `ShellRoute` or `StatefulShellBranch` take the shell's level (top-level under a top-level shell, relative under a shell nested in a `GoRoute`). Tabs that must keep their own stacks use `StatefulShellRoute`. A leading or trailing slash on a child fails go_router's route-configuration assertion
- Static segments are declared before parameterized siblings (`new` before `:id`) - go_router matches in declaration order
- `go` replaces the current location and its stack; `push` stacks a route on top and can be popped back off. Tabs and root-level moves use `go`; details and modals opened from the current screen use `push`
- One top-level `redirect` owns cross-cutting gates (auth, onboarding). Per-route `redirect` handles a single route's own condition. Returning `null` means "allow"
- `redirect` never awaits I/O, must be idempotent, and must never form a cycle (`A -> B -> A`) - go_router detects the loop and routes it to the error page as a `GoException`. Returning the current location counts as no redirect; `redirectLimit` separately caps the chain length
- `redirect` reads auth state from a synchronously readable source. To re-evaluate when that state changes, hand the router a `Listenable` via `refreshListenable`; do not `await` an auth check inside `redirect`
- Path segments carry resource identity (`/orders/:id`); query parameters carry optional, omittable modifiers (filters, pagination, search). Never encode a secret or a token in either
- Every value arriving from a route is untrusted input, whether it came from an in-app tap or an external link. Parse and validate it, and authorize the resource server-side - a route guard controls what renders, not what the user may access
- `state.extra` is not part of the URL. It is `null` after an external deep link; after a web reload or state restoration a model object is dropped (only JSON-encodable values survive without an `extraCodec`), so no screen may depend on it for correctness - it is an optimization over re-fetching by id
- Supply an error route (`errorBuilder` / `errorPageBuilder`). Without one an unmatched or malformed link lands on go_router's default error page, which shows the raw exception and the unmatched URI outside the app's chrome
- On web with the path URL strategy, the host rewrites unknown paths to `index.html`, or every non-root URL 404s on reload; the default hash strategy needs no rewrite

## Patterns

### Router declaration

```dart
// Bad - a fresh router per rebuild: history and current location reset
Widget build(BuildContext context) =>
    MaterialApp.router(routerConfig: GoRouter(routes: _routes));

// Good - constructed once (top-level final, or a keepAlive provider)
final appRouter = GoRouter(initialLocation: '/', routes: _routes, redirect: _guard);
```

### Route tree and relative paths

```dart
GoRoute(
  path: '/orders',
  builder: (context, state) => const OrdersScreen(),
  routes: [
    GoRoute(                              // resolves to /orders/:id
      path: ':id',                        // Bad: '/:id' fails the sub-route path assertion
      builder: (context, state) => OrderScreen(id: state.pathParameters['id']!), // present by route match; OrderScreen validates it
    ),
  ],
)
```

Nesting a route under a parent means the parent participates in the stack, so back from `/orders/42` lands on `/orders`.

### `go` vs `push`

```dart
// Bad - push from a bottom-nav tab: taps accumulate an unbounded stack
onTap: () => context.push('/settings'),

// Good - tab switch replaces, detail pushes
onTap: () => context.go('/settings'),
onOrderTap: (id) => context.push('/orders/$id'),
```

### Shell routes

`ShellRoute` wraps its children in persistent chrome (an app bar, a nav bar) while the child area swaps:

```dart
ShellRoute(
  builder: (context, state, child) => Scaffold(body: child, bottomNavigationBar: const NavBar()),
  routes: [ /* children render into `child` */ ],
)
```

`StatefulShellRoute.indexedStack` is the one to use for bottom-nav tabs that must each keep their own navigation stack and scroll position across switches - it builds from a list of `StatefulShellBranch`, and the builder receives a navigation shell object used to switch branches by index. Plain `ShellRoute` resets the child stack on every switch, which is the usual cause of "my tab forgets where I was".

A route that must cover the shell (a full-screen modal, a capture flow) declares `parentNavigatorKey: rootNavigatorKey` so it renders above the shell's chrome. A screen that is read-only on one tier is one route whose builder branches on `kIsWeb`, not a second route tree.

### Redirect guards

```dart
String? _guard(BuildContext context, GoRouterState state) {
  final loggedIn = authNotifier.isLoggedIn;          // synchronously readable
  final atLogin = state.matchedLocation == '/login';

  if (!loggedIn && !atLogin) return '/login?from=${Uri.encodeComponent(state.uri.toString())}'; // keeps the query
  if (loggedIn && atLogin) return '/';
  return null;                                        // allow
}
```

The `!atLogin` term stops `/login` redirecting to itself: without it each pass wraps the previous URI in a new `from`, the location never repeats, and the chain runs until `redirectLimit` routes it to the error page as a `GoException`. Pass `refreshListenable: authNotifier` so login and logout re-run the guard instead of leaving the user on a stale screen. If auth state lives in a stream, bridge it to a `Listenable` (a `ChangeNotifier` that calls `notifyListeners` on each event) - go_router's docs show this bridge as a small class you own, not a package export.

### Path vs query parameters

```dart
// Bad - identity in the query, filter in the path, and no validation
'/order?id=$id'
final id = state.pathParameters['status'];

// Good
'/orders/$id?status=open&page=2'
final id = state.pathParameters['id']!;                          // identity; present by route match, validate its shape
final page = int.tryParse(state.uri.queryParameters['page'] ?? '') ?? 1;  // optional, validated
```

Path parameters come from `state.pathParameters`; query parameters from `state.uri.queryParameters`. Both are strings and both can be attacker-supplied.

### `extra` is not deep-linkable

```dart
// Bad - throws when reached by link, reload, or restoration
context.push('/orders/42', extra: order);
final order = state.extra! as Order;

// Good - extra is a fast path, id is the source of truth
final cached = state.extra as Order?;
return OrderScreen(id: id, preloaded: cached);   // fetches by id when preloaded == null
```

### Typed routes

`go_router_builder` generates typed navigation from route classes annotated with `@TypedGoRoute<T>`, where each class extends `GoRouteData` and implements the screen build. Navigation then goes through a constructed object (`OrderRoute(id: '42').go(context)`) instead of a hand-built string, so a renamed parameter is a compile error rather than a runtime null. The exact class boilerplate (mixin requirement, generated route-list symbol) changed across `go_router_builder` versions - copy the shape from the project's existing generated routes rather than writing it from memory.

Worth it when there are more than a handful of parameterized routes. For a small app, `name`d routes plus `context.goNamed('order', pathParameters: {'id': id})` gets most of the safety with no codegen.

### Deep links and app links

Registration is platform-side, not Dart-side: Android needs an `intent-filter` with `android:autoVerify="true"` plus a hosted `assetlinks.json`; iOS needs the Associated Domains capability plus a hosted `apple-app-site-association`. Without the hosted file the link opens a browser instead of the app. Once registered, go_router matches the incoming URI against the route tree like any other location.

Treat the arriving URI as hostile:

```dart
// Bad - a link controls what the app opens next
final next = state.uri.queryParameters['next'];
if (next != null) context.go(next);           // open redirect: any external link can drive navigation

// Good - allowlist, then navigate
const allowed = {'orders', 'profile'};
final next = state.uri.queryParameters['next'];
if (next != null && allowed.contains(next)) context.go('/$next');
```

The same applies to ids in the path: a link can name any resource, so the guard is server-side authorization on fetch, not the route match. go_router matches `uri.path`, and in a custom-scheme link `fieldly://orders/42` the first segment is the host: register such links with three slashes (`fieldly:///orders/42`) or rewrite host plus path in the top-level `redirect`. A notification tap is a deep link resolved like any other, cold start included: through `initialLocation` resolution and the top-level `redirect`.

### Web URL strategy

```dart
import 'package:flutter_web_plugins/url_strategy.dart';

void main() {
  usePathUrlStrategy();   // /orders/42 instead of /#/orders/42
  runApp(const App());
}
```

This requires the host to rewrite unknown paths to `index.html`; without that rewrite, a direct load of `/orders/42` returns 404 while in-app navigation works, which is why it usually surfaces only after deploy.

## Output Format

When invoked from an implementation workflow, emit the route table:

```
| Route | Path | Params | Guard | Deep link | Notes |
|-------|------|--------|-------|-----------|-------|
| Orders | /orders | - | auth | https | inside StatefulShellBranch |
| Order detail | /orders/:id | id (path) | auth | both | validate id, fetch by id |
| Search | /search | q, page (query) | none | https | page defaults to 1 |
| Login | /login | from (query) | none | no | redirect target |
```

The table is followed by these lines, then the `Fixed in plan` / `Pre-existing` / `Not read` lines:

```
Shell: {none | ShellRoute | StatefulShellRoute}

Guard source: {provider | listenable | static | none}

Error route: {declared | missing}

Web URL strategy: {path | hash | n/a}

Gate order: {<gate> -> <gate> | single gate}
```

`Gate order` names the evaluation order when the top-level redirect owns more than one gate; the Guard column then lists the gates in that order, and `Guard source` is `;`-separated, one value per gate in that order, when they differ. Platform registration files the plan adds (an intent-filter, `Runner.entitlements`, the hosted association files) appear as `<path> (new)` in Notes. `Deep link: {https | scheme | both | no}` names the link forms the product registers for the route (`scheme` = a custom scheme is registered, whether or not its host is rewritten). `Guard source` names what the guard reads: `provider` = DI/provider state (bridged to `refreshListenable`; a token read from secure storage is `provider` when sign-in or sign-out must re-run the guard), `listenable` = a raw `Listenable`/`ChangeNotifier`, `static` = a value loaded before `runApp` that never changes while the app runs, `none` = no guard. Chained gates carry the original target through both in one `from` parameter; a deep link into a non-default tab selects its `StatefulShellBranch` by location.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one finding block per issue:

```
### [{Critical | High | Medium | Low}] {file:line}

- Rule: {router-lifetime | relative-path | route-order | shell-choice | go-vs-push | redirect-contract | guard-source | param-placement | untrusted-param | extra-dependency | error-route | web-strategy | deep-link-registration | naming}
- Code: {one-line citation}
- Problem: {what breaks at runtime, not what looks unusual}
- Recommendation: {concrete edit}
```

`redirect-contract` covers loops (including a target that grows on every pass, such as appending its own location), awaited I/O inside `redirect`, and non-idempotence; a missing `refreshListenable` is `guard-source`, its own block. `shell-choice` is a plain `ShellRoute` under a bottom nav (tabs are assumed to keep their stacks unless the product says otherwise), Medium. `route-order` is a parameterized route declared before a static sibling it shadows. `naming` is a route or parameter name that misstates the resource (`/order?id=`) or a `goNamed` name that diverges from its path. A navigation target, a resource id, or a WebView URL taken from a route parameter is `untrusted-param`. `deep-link-registration` covers the platform side - intent-filter, Associated Domains (declared in `ios/Runner/Runner.entitlements`, which `Info.plist` cannot confirm), hosted assetlinks / site-association files - and a custom URL scheme where the product needs a verified link; it applies only to platforms the product links into. Review mode emits no route table or trailing route lines; those are implement mode's.

The heading severity is one of Critical, High, Medium, Low. Critical = open redirect, an unvalidated link parameter reaching navigation or a sink such as a WebView, a secret or token carried in a route, or a redirect loop. High = navigation that breaks under realistic use (router rebuilt in `build`, `extra`-dependent screens, a child path with a leading or trailing slash or a top-level path without one, route order that shadows a more specific path, guard source that never notifies, awaited I/O or non-idempotence inside `redirect`, a query parameter force-unwrapped or a route parameter used unparsed (a matched path parameter is present by construction), unregistered or unverifiable deep links on a platform the product links into). Medium = works but fragile or misplaced (go/push misuse, param placement, missing error route, the path URL strategy without a host rewrite on a web target). Low = naming. When a finding matches two bands, the higher band wins.

In diagnose mode each symptom block's `Recommendation:` ends with `(pattern: <section heading>)`.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Rule` values, or the path of a file that could not be read) when any check could not be exercised, then the `No <rule> findings.` lines. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean and gets its `No <rule> findings.` line; a check on the `Not checked` line does not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Problem:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape, a request to review or audit takes the review shape, and a supplied symptom or bug report takes diagnose mode.

The closing lines - `Also seen` and `Not checked` only when they have content, then one `No <rule> findings.` line per clean check (no block, not on the `Not checked` line), blank-separated:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

{No <rule> findings.}
```

Diagnose mode opens with one line per reported symptom, `Symptom <n>: <the report's title or first sentence>`, a title that lists two symptoms is two lines, naming on each any premise the files read contradict (a flag the report says is on, a version it names) - the diagnosis then proceeds on what the code shows - and stating when the files read cannot cause the symptom. Blocks for the causes of the reported symptoms come first, grouped by symptom in reported order and within a group by severity, each such block's `Problem:` line opening with `Symptom <n>:`; a cause shared by two symptoms is one block opening `Symptom 1, 2:`, placed with the lower-numbered symptom; every other defect seen in the files read follows, ordered as in review mode. The zero-finding lines named above are omitted in diagnose mode; `Also seen` and `Not checked` lines are kept.

## Avoid

- Constructing `GoRouter` inside a widget `build`
- A leading `/` on a child route `path`
- `push` for tab switches, `go` for a detail that should be poppable
- `redirect` that awaits a network or storage call, or that can redirect in a cycle
- Auth guards reading a value that never notifies the router - pair the source with `refreshListenable`
- Reading route parameters without parsing or validating them
- Screens whose correctness depends on `state.extra`
- Passing tokens, secrets, or full objects through the URL
- Navigating to a location taken verbatim from a link parameter - allowlist it
- Shipping without an error route, so a bad link lands on the default error page that shows the raw exception
- Treating a route guard as authorization - it hides UI, it does not protect data
- Mixing `Navigator.push` with go_router for routes that should be linkable; the raw Navigator route has no URL and no deep-link entry point
