---
name: flutter-widget-patterns
description: "Apply Flutter widget patterns: Stateless/Stateful, const constructors, Keys, BuildContext safety, lifecycle, constraints, rebuild scoping."
metadata:
  category: mobile
  tags: [flutter, dart, widgets, const, keys, buildcontext, lifecycle, layout, rebuilds]
user-invocable: false
---

# Flutter Widget Patterns

> Language-level Dart shape decisions live in `dart-language-patterns`. This skill owns the widget tree: what a widget is, when it rebuilds, and how it is laid out. Frame-budget measurement and profiling belong to the performance lens.

## When to Use

- Building or reviewing screens, widgets, and layout code
- Deciding between `StatelessWidget` and `StatefulWidget`, whether a `Key` is required, or where a rebuild boundary belongs
- Diagnosing state that jumps to the wrong list item, disappears on rebuild, or survives when it should not
- Diagnosing layout exceptions (unbounded constraints, overflow) and "works on my device only" sizing

## Rules

- `StatelessWidget` unless the widget owns mutable state or a lifecycle-bound resource (controller, subscription, ticker). State handed down from above is a constructor parameter, not a `State`
- Every constructor that can be `const` is declared `const`, and call sites actually write `const` - an omitted `const` at the call site discards the whole benefit
- Extract subtrees into widget classes, never `Widget _buildX()` methods or top-level functions returning a widget: the result has no `BuildContext` or rebuild boundary of its own, its call site cannot be `const`, and it always rebuilds with its parent
- Children whose *identity* can change position (reorder, insert, remove) need a `Key` when anything below them holds state - their own `State`, a descendant's, or element-held state like scroll offset or text selection. Place it on the root of the subtree whose state must survive, not on an inner node
- `GlobalKey` only for cross-subtree access or moving a subtree while preserving its state; hold it in a field, never construct one in `build`
- Never touch a `BuildContext` after an `await` without re-checking `mounted` first, and never store a `BuildContext` in a field or hand it to an object that outlives the frame
- Inherited lookups (`Theme.of`, `MediaQuery.of`, and equivalents) belong in `build` or `didChangeDependencies` - never `initState` or `dispose`
- Everything `initState` creates, `dispose` releases; everything derived from `widget.*` is re-derived in `didUpdateWidget` when its source field changed
- Compose by wrapping. Never subclass a concrete framework widget to change its behavior
- Size from the incoming constraints, not from the screen: a widget must render correctly under any constraints a parent may impose
- Push rebuilds down - put the changing part behind a builder and pass the unchanged subtree through the builder's `child` parameter

## Patterns

### Stateless vs Stateful

```dart
// Bad - State holds nothing mutable; all ceremony, no benefit
class Badge extends StatefulWidget { ... }
class _BadgeState extends State<Badge> {
  @override Widget build(BuildContext context) => Text('${widget.count}');
}

// Good
class Badge extends StatelessWidget {
  const Badge({required this.count, super.key});
  final int count;
  @override Widget build(BuildContext context) => Text('$count');
}
```

The test is ownership, not mutation: if the value changes but is *owned* by a parent or a provider, the widget stays stateless and simply receives the new value. `StatefulWidget` earns its place when the widget itself owns a controller, subscription, ticker, or focus node.

### `const` and rebuild cost

```dart
// Bad - a new instance every build; the framework must diff this subtree each time
child: Padding(padding: EdgeInsets.all(16), child: Text('Total')),

// Good - canonicalized: the identical instance arrives next build
child: const Padding(padding: EdgeInsets.all(16), child: Text('Total')),
```

Identical `const` expressions are canonicalized to one instance. When a rebuild hands the element the *same* widget instance it already has, the framework short-circuits and skips that subtree entirely. That is the mechanism - `const` does not stop the parent from rebuilding, it stops the const subtree from being recreated and re-diffed.

`const` is viral: a widget is const-constructible only if every argument is a constant, so a single non-const argument deep in a tree blocks it all the way up. Turn on `prefer_const_constructors` in `analysis_options.yaml` rather than auditing by eye.

### Keys

| Key | Use when |
|-----|----------|
| none | children are positionally stable, or carry no state |
| `ValueKey(id)` | identity is a value you already hold (an item id) |
| `ObjectKey(item)` | identity is the object instance itself, with no stable id field |
| `UniqueKey()` | you deliberately want a fresh element and discarded state |
| `GlobalKey` | you need the `State`/context from outside the subtree, or must move the subtree elsewhere in the tree with its state intact |

```dart
// Bad - reorder the list and state stays with the slot, not the item
ListView(children: [for (final t in todos) TodoTile(todo: t)]);

// Good - identity travels with the item
ListView(children: [for (final t in todos) TodoTile(key: ValueKey(t.id), todo: t)]);
```

Without a key, the framework matches new widgets to existing elements by position and runtime type. That is correct for stable lists and wrong the moment items are reordered or removed: a checkbox, scroll offset, or text field keeps the old element's state and appears to jump to a neighboring row. Key on the identity that outlives every change the item undergoes - a client-generated id when a server id later replaces it.

```dart
// Bad - a new GlobalKey each build; the subtree is remounted and state is lost
Widget build(BuildContext context) => Form(key: GlobalKey<FormState>(), child: ...);

// Good - created once, held by the State
final _formKey = GlobalKey<FormState>();
```

A `GlobalKey` must be unique across the whole tree and is more expensive than a local key. Reach for it only when nothing else can express the need.

### `BuildContext` across async gaps

```dart
// Bad - the widget may already be gone; this context is dead
Future<void> _save() async {
  await repo.save(draft);
  Navigator.of(context).pop();
}

// Good - re-check after every await that precedes a context use
Future<void> _save() async {
  await repo.save(draft);
  if (!mounted) return;
  Navigator.of(context).pop();
}
```

Better still, resolve what you need *before* the gap, so no context survives it:

```dart
final messenger = ScaffoldMessenger.of(context);
await repo.save(draft);
messenger.showSnackBar(const SnackBar(content: Text('Saved')));
```

Inside a `State`, check `mounted`; elsewhere, `context.mounted`. The `use_build_context_synchronously` lint flags these, so keep it enabled instead of relying on review to catch them. A bottom sheet or dialog is its own route: its `State` owns its controllers, it returns its result through `Navigator.pop(result)`, and the caller re-checks `mounted` after awaiting it.

A `BuildContext` is a handle on a position in the element tree, valid for as long as that element is mounted. Storing one in a field, a controller, or a singleton outlives that guarantee and leaks the element.

### Lifecycle

| Hook | Runs | Responsibility |
|------|------|----------------|
| `initState` | once, before first build | create controllers, subscriptions, tickers; no inherited lookups |
| `didChangeDependencies` | after `initState`, then whenever an inherited dependency changes | first inherited reads; react to theme/locale/media changes. An inherited lookup in `initState` asserts in debug, and a value copied there never refreshes because `initState` never re-runs |
| `didUpdateWidget(old)` | parent rebuilt with a new config of the same type and key | diff `old.x` against `widget.x` and re-wire whatever depended on it |
| `dispose` | once, on removal | cancel, close, and dispose everything `initState` created |

```dart
// Bad - the subscription stays bound to the first id forever
@override
void initState() {
  super.initState();
  _sub = repo.watch(widget.id).listen(_onData);
}

// Good - follow the config when it changes
@override
void didUpdateWidget(covariant ItemView oldWidget) {
  super.didUpdateWidget(oldWidget);
  if (oldWidget.id != widget.id) {
    _sub.cancel();
    _sub = repo.watch(widget.id).listen(_onData);
  }
}
```

A `StatefulWidget`'s `State` outlives the widget object. The parent rebuilding gives the same `State` a new `widget`, so anything captured from `widget.*` in `initState` silently goes stale unless `didUpdateWidget` refreshes it. Call `super` in every hook, and `super.dispose()` last.

`setState` after `dispose` throws. Cancel subscriptions and timers in `dispose`; a `Future` cannot be cancelled, so after an `await` check `mounted` before touching state.

### Composition over inheritance

```dart
// Bad - subclassing a concrete widget to bolt on behavior
class LoggingButton extends ElevatedButton { ... }

// Good - wrap it
class LoggingButton extends StatelessWidget {
  const LoggingButton({required this.onPressed, required this.child, super.key});
  final VoidCallback onPressed;
  final Widget child;

  @override
  Widget build(BuildContext context) => ElevatedButton(
        onPressed: () { log('tap'); onPressed(); },
        child: child,
      );
}
```

Framework widgets are configuration objects with private state contracts; subclassing binds you to internals that change between releases. Wrapping composes the same behavior with no coupling. In a reorderable list whose rows hold text fields, set `buildDefaultDragHandles: false` and give each row an explicit drag handle (`ReorderableDragStartListener`) so a long-press in a field edits text instead of starting a drag.

```dart
// Bad - not a widget of its own: no context or rebuild boundary, no const call site, rebuilds with the entire parent
Widget _buildHeader() => Row(children: [...]);

// Good - its own element, its own rebuild boundary, const-able
class _Header extends StatelessWidget {
  const _Header();
  @override Widget build(BuildContext context) => const Row(children: [...]);
}
```

### Constraints and sizing

Constraints go down, sizes go up, the parent sets the position. A widget cannot know its size before layout; it chooses one within the constraints it was handed.

```dart
// Bad - sizes off the screen; breaks in split-screen, on desktop, and on rotation
width: MediaQuery.of(context).size.width * 0.8,

// Good - relative to whatever the parent actually granted
FractionallySizedBox(widthFactor: 0.8, child: ...)

// Good - when the number is needed explicitly
LayoutBuilder(
  builder: (context, constraints) => SizedBox(width: constraints.maxWidth * 0.8, child: ...),
)
```

```dart
// Bad - Column hands its child unbounded height; the ListView cannot lay out and throws
Column(children: [Header(), ListView(...)])

// Good - Expanded bounds it to the leftover space
Column(children: [Header(), Expanded(child: ListView(...))])
```

Unbounded-constraint errors nearly always mean a scrollable or flexible child sits inside a parent that imposes no limit on that axis. `Expanded`/`Flexible` fix it and must sit under a `Row`, `Column`, or `Flex` with only plain widget wrappers (no other render object) between. `shrinkWrap: true` (for a scrollable) and `IntrinsicHeight`/`IntrinsicWidth` (for a flexible child; a scrollable's viewport throws on intrinsics) also silence the error but force extra layout work over the children - use them only when the bounded alternative genuinely does not fit.

Prefer `SizedBox` over `Container` when only sizing or spacing is needed: it is const-constructible and cheaper. Keyboard and safe-area insets belong to `flutter-adaptive-responsive`.

### Scoping rebuilds with builders

```dart
// Bad - one changing value rebuilds the whole screen
setState(() => _count++);   // in a State whose build() returns the entire page

// Good - only the Text rebuilds; the header is built once and passed through
ValueListenableBuilder<int>(
  valueListenable: _counter,
  child: const ExpensiveHeader(),
  builder: (context, value, child) => Column(children: [child!, Text('$value')]),
)
```

The `child` parameter is the point of these builders: it is built once outside the builder callback and handed back on every invocation, keeping an expensive subtree out of the rebuild. `AnimatedBuilder` takes the same `child` for the same reason, which matters most there because it rebuilds every frame.

```dart
// Bad - a new Future every rebuild; the builder restarts and the UI flickers
FutureBuilder(future: repo.load(widget.id), builder: ...)

// Good - created in initState, re-created only when its source changes
late Future<Item> _item;
@override
void initState() { super.initState(); _item = repo.load(widget.id); }
@override
void didUpdateWidget(ItemView old) {
  super.didUpdateWidget(old);
  if (old.id != widget.id) _item = repo.load(widget.id);
}
FutureBuilder(future: _item, builder: (context, snapshot) => ...)
```

The rule generalizes: a builder rebuilds whenever its source changes, so the source must not be *created* during build. Handle every branch a snapshot can present - waiting, error, and data - rather than assuming data. `MediaQuery.of(context)` subscribes the widget to every media-query change; the scoped accessors (`MediaQuery.sizeOf`, `paddingOf`, `viewInsetsOf`) subscribe to one field.

## Output Format

When invoked from an implementation workflow, emit the tree decisions:

```
| Widget | Type | Key | Rebuild Scope | Notes |
|--------|------|-----|---------------|-------|
| OrderScreen | Stateless | none | full | reads state from above |
| OrderList | Stateless | none | full | builds a ListView.builder; items keyed by id |
| OrderTile | Stateful | ValueKey(order.id) | self | owns expansion controller |
| TotalBar | Stateless | none | ValueListenableBuilder | isolates the total |
| EmptyCartHint | Stateless (const) | none | const | no runtime inputs |
```

One row per widget where a decision was made; skip widgets with nothing to decide. Tier variants (web read-only) and `Semantics` are not tree decisions; they belong to `flutter-adaptive-responsive` and `flutter-accessibility`.

- `Type: {Stateless | Stateless (const) | Stateful | Consumer Stateless | Consumer Stateful}` - `Consumer` when the widget reads providers; write `(const)` only when every call site can pass `const`
- `Rebuild Scope` names what limits this widget's own rebuild: `self` when it rebuilds alone (including a widget driven only by a controller it listens to, whoever owns it, or by its own state), `full` when it rebuilds with its direct parent, `const` when every call site passes `const` so the parent's rebuild hands the element the identical instance and skips it, or the name of the builder, scoped-list widget, `Consumer`, or `select`ed provider that bounds it

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one block per finding:

```
### [{Must | Recommend}] {file:line}

- Category: {Widget Type | Const Usage | Key Correctness | Context Safety | Lifecycle | Composition | Constraints | Rebuild Scope}
- Code: {one-line citation}
- Issue: {the rule broken and the user-visible symptom it causes}
- Recommendation: {concrete edit}
```

The label follows the failure, not the category. `[Must]` when the violation crashes, leaks, loses user-visible state, or breaks what the user sees (dead context, missing dispose, missing key on stateful items of a list that reorders, inserts, or removes, a `GlobalKey` built in `build`, an inherited lookup in `initState`, unbounded constraints, overflow that clips content, stale `initState` capture, a `Future` or `Stream` created in `build` - filed as `Rebuild Scope`). `[Recommend]` for cost and clarity: an empty `State` or `ConsumerState` (one that exists only to reach `ref` is a `ConsumerWidget`), omitted `const`, `Container` where `SizedBox`, `Padding`, or `ColoredBox` fits (a `Container` carrying a decoration is not a finding), `_buildX` helpers, the reorderable drag-handle rule (`Composition`), `MediaQuery.of(context)` where a scoped accessor exists (`Rebuild Scope`), `MediaQuery...size` driving layout a constraint could (`Constraints`), a `Positioned` with both `left` and `right` overriding its child's width (`Constraints`), and `shrinkWrap` or `IntrinsicHeight` used to silence an unbounded-constraint error. A disabled `use_build_context_synchronously` or `prefer_const_constructors` lint is one `[Recommend]` finding anchored on its `analysis_options.yaml` line, or on the `linter:` line when the lint is simply absent, under `Context Safety` or `Const Usage`. Provider and plain-Dart defects next to widget code are `Also seen` lines.

Diagnose mode adds `- Confidence: {Confirmed | Likely | Needs-Source}` to every block - `Needs-Source` when two or more causes fit equally, code read or not; otherwise `Confirmed` when the cited code was read and `Likely` when it was not (with no source, never `Confirmed`); a weaker alternative cause is its own block at the label it would carry if confirmed, after the stronger one within its symptom group. With no source file supplied, the heading is `### [{Must | Recommend}] <pattern section>` (the `## Patterns` heading that explains the cause), `Code:` names the suspected shape (`unkeyed stateful rows in a ListView`), and `Issue:` and `Recommendation:` describe the shape and the edit in that section's terms; a `Future` or `Stream` created in `build` cites `Scoping rebuilds with builders`. No `Not checked` line is emitted when no source was read; the `Symptom <n>:` lines are plain lines, blank-separated.

In diagnose mode with no source read, emit `Diagnosed from symptom only; no category sweep performed.` in place of the omitted lines.

Generated widget code (`*.g.dart`, `*.freezed.dart`, and other build_runner output) is out of scope - report against the source that generates it.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Category` values, or the path of a file that could not be read) when any check could not be exercised, then the `No <category> findings.` lines. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean and gets its `No <category> findings.` line; a check on the `Not checked` line does not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Issue:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape, a request to review or audit takes the review shape, and a supplied symptom or bug report takes diagnose mode.

The closing lines - `Also seen` and `Not checked` only when they have content, then one `No <category> findings.` line per clean check (no block, not on the `Not checked` line), blank-separated:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

{No <category> findings.}
```

Diagnose mode opens with one line per reported symptom, `Symptom <n>: <the report's title or first sentence>`, a title that lists two symptoms is two lines, naming on each any premise the files read contradict (a flag the report says is on, a version it names) - the diagnosis then proceeds on what the code shows - and stating when the files read cannot cause the symptom. Blocks for the causes of the reported symptoms come first, grouped by symptom in reported order and within a group by severity, each such block's `Issue:` line opening with `Symptom <n>:`; a cause shared by two symptoms is one block opening `Symptom 1, 2:`, placed with the lower-numbered symptom; every other defect seen in the files read follows, ordered as in review mode. The zero-finding lines named above are omitted in diagnose mode; `Also seen` and `Not checked` lines are kept.

## Avoid

- `StatefulWidget` whose `State` has no fields and overrides no lifecycle method - it is a `StatelessWidget`
- Omitting `const` at the call site of a const constructor
- `Widget _buildSection()` helper methods in place of widget classes
- Unkeyed stateful children in a reorderable or filterable list
- A `Key` on an inner node when the state to preserve lives above it
- `GlobalKey` constructed inside `build`, or used where a `ValueKey` would do
- `context` after `await` with no `mounted` check, and `BuildContext` stored in a field or passed to a repository, controller, or singleton
- `Theme.of(context)` / `MediaQuery.of(context)` in `initState`, and any inherited lookup in `dispose`
- `initState` reading `widget.*` into a field with no matching `didUpdateWidget`
- Controllers, subscriptions, tickers, and focus nodes created without a `dispose`
- `setState` inside `build`, inside `dispose`, or wrapping work that changes nothing observable
- Subclassing `ElevatedButton`, `Scaffold`, or any concrete framework widget to alter behavior
- `MediaQuery.of(context).size` for layout that a constraint could drive
- `shrinkWrap: true` or `IntrinsicHeight` used to silence an unbounded-constraint error that `Expanded` should fix
- `Container` where `SizedBox`, `Padding`, or `ColoredBox` says it more precisely and can be const
- A `Future` or `Stream` constructed inside `build` and fed to a builder
