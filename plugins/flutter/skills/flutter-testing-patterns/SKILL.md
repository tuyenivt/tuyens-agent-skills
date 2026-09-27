---
name: flutter-testing-patterns
description: "Plan Flutter tests by layer: unit, widget, golden, integration_test; pump vs pumpAndSettle, golden stability, mocktail, Riverpod overrides."
metadata:
  category: mobile
  tags: [flutter, dart, testing, widget-test, golden-test, integration-test, mocktail, riverpod]
user-invocable: false
---

# Flutter Testing Patterns

> This skill owns test layering, doubles, and golden stability. Provider shapes belong to `flutter-riverpod-patterns`; what to assert about accessibility belongs to `flutter-accessibility`.

## When to Use

- Choosing which layer a behavior should be tested at
- Authoring or reviewing widget, golden, or `integration_test` suites
- Diagnosing a flaky test, or a golden that passes locally and fails in CI
- Wiring fakes into Riverpod and stubbing the network

## Rules

- Test at the cheapest layer that can observe the behavior: pure logic as unit, anything needing `BuildContext`/layout/gestures as widget, pixel appearance as golden, real engine and platform plugins as `integration_test`.
- Widget tests are the default layer for UI. Goldens supplement behavioral assertions; they never replace them.
- No live backend in unit, widget, or golden tests: stub at the HTTP client boundary, or inject a fake repository. Integration tests use a stubbed or seeded backend, never a shared environment.
- Doubles enter through the seam production uses - a Riverpod override or a constructor argument. Never a mutable global swapped in `setUp`.
- `pumpAndSettle` only when pending frames are finite. Continuous animation, or a timer that schedules a frame on each tick, requires `pump(Duration)`; a timer still pending when the test ends fails it, so cancel it or advance past it.
- Goldens are generated and verified on one pinned platform and Flutter version. A golden written on a developer machine and checked in a different CI image is a broken test, not a real diff.
- Fonts are loaded explicitly before any golden renders. The default test font draws every glyph as a box.
- Pin every source of nondeterminism a golden can see: surface size, device pixel ratio, text scale, clock, randomness, animation state, image sources.
- `--update-goldens` output is reviewed as an image diff. Regenerating to make CI green discards the signal the test exists for.
- One behavior per test, named for the behavior. Never `Future.delayed` to let things settle.

## Patterns

### Choosing a layer

| Behavior | Layer | Why |
|----------|-------|-----|
| Failure mapping, formatters, validators, notifier state transitions | Unit | no widget tree needed |
| Loading / empty / error states render correctly | Widget | needs a tree and finders |
| "tapping retry re-issues the request" | Widget | needs gesture plus rebuild |
| A themed component's appearance across breakpoints or themes | Golden | the contract is pixels |
| Login through to home with real plugins, permissions, deep links | Integration | needs a real engine and device |

Push down whenever possible. A widget test that only checks a formatted string should be a unit test on the formatter.

### `pump` vs `pumpAndSettle`

```dart
// Bad - settling skips past the in-flight state, and times out if the request never completes
await tester.tap(find.byType(SubmitButton));
await tester.pumpAndSettle();

// Good - advance exactly as far as each assertion needs
await tester.tap(find.byType(SubmitButton));
await tester.pump(); // one frame: the in-flight state is now on screen
expect(find.byType(CircularProgressIndicator), findsOneWidget);
await tester.pump(const Duration(seconds: 1)); // let timers fire, then rebuild
expect(find.text('Saved'), findsOneWidget);
```

`pump()` builds exactly one frame. `pumpAndSettle()` pumps repeatedly until no frame is scheduled, and fails on timeout if something keeps scheduling frames - a repeating indicator, a looping `AnimationController`, or a periodic timer that rebuilds on each tick. It does not wait for timers that schedule no frame.

`testWidgets` runs in a fake-async zone, so `pump(Duration)` advances timers rather than waiting in real time. Work that depends on real I/O will not complete this way; wrap that in `tester.runAsync`.

### Finders

```dart
// Bad - breaks when copy is edited or the locale changes
expect(find.text('Sign in'), findsOneWidget);

// Good - stable across copy and localization
expect(find.byKey(const Key('signInButton')), findsOneWidget);
```

Use `find.text` when the copy itself is the assertion, `find.bySemanticsLabel` when what a screen reader announces is the assertion, and `find.byKey`/`find.byType` for structure. `findsOneWidget` over `findsWidgets` - an unexpected duplicate is a real bug worth failing on. Navigation is asserted by pumping the screen inside a test router and checking which screen type is shown, not by mocking `context.go`.

### Golden stability

This is where Flutter test suites break most often. Address all four causes up front.

**1. Load fonts once for the whole suite.** A file named `flutter_test_config.dart` at the root of `test/` wraps every test in that directory tree:

```dart
// test/flutter_test_config.dart
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  final loader = FontLoader('Inter')
    ..addFont(rootBundle.load('assets/fonts/Inter-Regular.ttf'))
    ..addFont(rootBundle.load('assets/fonts/Inter-Bold.ttf'));
  await loader.load();
  await testMain();
}
```

Without this, goldens encode boxes instead of glyphs, so every later typography change passes unnoticed. For a font shipped by a package, *both* arguments take the `packages/<package_name>/` prefix - the `FontLoader` family name and the `rootBundle.load` path:

```dart
FontLoader('packages/acme_ui/AcmeSans')
  ..addFont(rootBundle.load('packages/acme_ui/assets/fonts/AcmeSans-Regular.ttf'));
```

Prefixing only the path loads the font under an unreachable family name: `rootBundle.load` succeeds, no error is raised, and the golden silently renders boxes. The widget under test must also request the loaded family (`fontFamily: 'Inter'`, or the package-prefixed name), usually via `ThemeData`, or the loaded font is never reached.

**2. Fix the surface.** Physical size and device pixel ratio set the logical surface the widget lays out in and which asset variants load; a finder-scoped golden is captured at logical size, a whole-screen one at the ratio:

```dart
tester.view.physicalSize = const Size(1080, 1920);
tester.view.devicePixelRatio = 3.0;
addTearDown(tester.view.reset);
```

Without the tear-down the override leaks into later tests in the same file, so failures depend on test order.

**3. Set a tolerance deliberately.** The default comparator is an exact pixel match, so a single antialiased pixel fails the test. Replace `goldenFileComparator` in `flutter_test_config.dart`, before `testMain()`:

```dart
class _Tolerant extends LocalFileComparator {
  _Tolerant(super.testFile, {required this.tolerance});
  final double tolerance; // fraction of differing pixels, e.g. 0.005

  @override
  Future<bool> compare(Uint8List bytes, Uri golden) async {
    final r = await GoldenFileComparator.compareLists(bytes, await getGoldenBytes(golden));
    if (r.passed || r.diffPercent <= tolerance) {
      r.dispose();   // omitting this leaks the diff images for the run
      return true;
    }
    final error = await generateFailureOutput(r, golden, basedir);
    r.dispose();
    throw FlutterError(error);
  }
}

// In testExecutable, before `await testMain()`. LocalFileComparator takes a test *file* and uses its
// directory, so hand it a file inside the current basedir; the directory itself resolves one level up.
final existing = goldenFileComparator as LocalFileComparator;
goldenFileComparator = _Tolerant(existing.basedir.resolve('placeholder_test.dart'), tolerance: 0.005);
```

Keep the threshold as low as CI tolerates - a generous tolerance silently accepts real regressions, which is worse than a brittle test.

A golden test, with the surface fixed and the capture scoped to the component rather than the whole app. `matchesGoldenFile` on a finder captures the nearest enclosing `RepaintBoundary`, so the component is wrapped in one, centred so the route's tight constraints do not stretch it to the screen, under a `Scaffold` so its text has a `Material` ancestor:

```dart
testWidgets('renders in dark theme', (tester) async {
  tester.view.physicalSize = const Size(1080, 1920);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(MediaQuery(
    data: const MediaQueryData(textScaler: TextScaler.linear(1.0)),
    child: MaterialApp(
      theme: darkTheme,
      home: const Scaffold(body: Center(child: RepaintBoundary(child: PriceTag(amount: 1299)))),
    ),
  ));

  // one file per variant: price_tag_dark_2x.png for text scale 2.0
  await expectLater(find.byType(PriceTag), matchesGoldenFile('goldens/price_tag_dark.png'));
});
```

One golden file per variant, named `<component>_<variant>.png`. Variants of one component share a test file.

**4. Generate and verify on one platform.** Text rasterization and shader output differ across host operating systems and across Flutter versions, so the same widget yields different bytes on macOS and in a Linux CI container. Two workable setups:

| Approach | Cost | When |
|----------|------|------|
| Run goldens only in the pinned CI job; tag them and skip that tag elsewhere | Low | default choice |
| Commit per-platform golden directories and select by host platform | High | a team that genuinely reviews goldens on multiple hosts |

Tag with `@Tags(['golden'])` above `library;` at the top of the file, declare the tag under `tags:` in `dart_test.yaml` (or every run warns), then run `flutter test --tags golden` in the pinned job and `flutter test --exclude-tags golden` in the general one. Pin the Flutter version in CI: an engine upgrade legitimately rewrites every golden, and that should land as one reviewed commit rather than as scattered flakes.

Diagnosing a drift:

| Symptom | Cause |
|---------|-------|
| Text renders as boxes or blank | fonts never loaded |
| Layout shifted or reflowed, or a whole-screen golden scaled | different surface size or device pixel ratio |
| Faint edge and antialiasing differences only | golden generated on a different host OS |
| Every golden in the repo changes at once | Flutter or engine version bump |
| Passes locally, fails only in CI | golden was regenerated on a developer machine |

### mocktail

```dart
class MockUserRepo extends Mock implements UserRepo {}
class FakeUser extends Fake implements User {}

setUpAll(() => registerFallbackValue(FakeUser()));

test('save posts the edited user', () async {
  final repo = MockUserRepo();
  when(() => repo.save(any())).thenAnswer((_) async {});

  await EditUser(repo).call(user);

  verify(() => repo.save(user)).called(1);
});
```

mocktail needs no code generation: stubs are closures, which is why every `when`/`verify` is wrapped in `() =>`. `any()` on a non-primitive argument type requires a `registerFallbackValue` for that type first, or the `when`/`verify` that uses it throws.

```dart
// Bad - a mock with stubbed methods reimplementing a repository
when(() => repo.fetch(any())).thenAnswer(...);
when(() => repo.save(any())).thenAnswer(...);
// ...

// Good - a hand-written fake holds the behavior once and is reusable
class InMemoryUserRepo extends Fake implements UserRepo {
  InMemoryUserRepo([Iterable<User> seed = const []]) {
    for (final u in seed) _users[u.id] = u;
  }
  final _users = <String, User>{};
  @override Future<User> fetch(String id) async => _users[id] ?? (throw ServerFailure(404));
  @override Future<void> save(User u) async => _users[u.id] = u;
}
```

Mocks are for verifying interactions. When the double needs behavior, a fake is shorter; extending `Fake` keeps it compiling when the interface gains a method (an unimplemented member throws only if called).

### Riverpod overrides

```dart
// Notifier / provider tests
final container = ProviderContainer(
  overrides: [userRepoProvider.overrideWithValue(InMemoryUserRepo([const User(id: 'u1', name: 'Ada')]))],
);
addTearDown(container.dispose);

// listen keeps an autoDispose provider alive while the future resolves
final sub = container.listen(userProvider('u1').future, (_, __) {});
expect((await sub.read()).name, 'Ada');

// Widget tests - the same seam, one layer up
await tester.pumpWidget(
  ProviderScope(
    overrides: [userRepoProvider.overrideWithValue(InMemoryUserRepo())],
    child: const App(),
  ),
);
```

`overrideWithValue` fits a plain `Provider` holding a dependency; `overrideWith((ref) => ...)` covers `Provider`, `FutureProvider`, and `StreamProvider` (return the value, future, or stream); a Notifier-backed provider takes `overrideWith(() => FakeNotifier())`. Always `addTearDown(container.dispose)` - an undisposed container keeps listeners and timers alive into the next test.

On Riverpod 3, providers retry failures automatically: error-state tests pass `retry: (_, __) => null` to the `ProviderContainer` or `ProviderScope`, and a dependency's error reaches a dependent provider wrapped in `ProviderException`.

Override the dependency, not the thing under test. Overriding `userProvider` itself in a test about `userProvider` asserts only that the override works.

### Stubbing the network at the client boundary

```dart
// Bad - a real client: under the test binding every request gets HTTP 400, so the test asserts
// nothing real; without the binding it hits the live API
final repo = UserRepo(Dio());

// Good - swap the transport, keep the repository under test
final dio = Dio()..httpClientAdapter = stubAdapter; // e.g. http_mock_adapter
final repo = UserRepo(dio);
```

Swapping the adapter keeps interceptors, serialization, and error mapping inside the test - which is exactly the code most likely to be wrong. Substitute a fake repository only when the test is about the consumer rather than the repository.

`flutter_test` installs an `HttpClient` that fails every real request, so `Image.network` renders as an error in widget tests. Inject a fake `ImageProvider` or preloaded bytes rather than expecting network images to appear.

### `integration_test`

```dart
// integration_test/login_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('user logs in and reaches home', (tester) async {
    app.main();
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('email')), 'ada@example.com');
    await tester.tap(find.byKey(const Key('submit')));
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);
  });
}
```

Reserve this layer for a handful of flows that are worthless if broken: launch, auth, purchase. It needs a device, emulator, or desktop host and runs orders of magnitude slower than widget tests. Point it at a stubbed or seeded backend selected by `--dart-define`, not at a shared environment that other people are changing.

## Output Format

When invoked from a test-strategy or implementation workflow (this skill's implement mode), emit the plan as one row per target:

```
| Target | Layer | Doubles | Determinism | Rationale |
|--------|-------|---------|-------------|-----------|
| `FailureMapper.fromDio` | Unit | None | Deterministic | pure mapping, no tree |
| `LoginScreen` error state | Widget | Fake | Deterministic | needs tree + tap |
| `PrimaryButton` variants | Golden | None | Needs-Pinning | fonts + 1080x1920 @3.0, Linux CI only |
| login -> home | Integration | Stubbed-Transport | At-Risk | real plugins, device-dependent |
```

- `Target` is one row per test file you would write, not per assertion; success and failure of one unit share its row. Variants that share a file collapse into one row (`PriceTag variants`, `PaymentSheet light/dark @1.0/1.3/2.0`); a behavior needing its own file gets its own row.
- `Layer: {Unit | Widget | Golden | Integration}`
- `Doubles: {None | Fake | Mock | Stubbed-Transport}`
- `Determinism: {Deterministic | Needs-Pinning | At-Risk}` - `Needs-Pinning` means it is stable once fonts, surface, tolerance, and platform are fixed; `At-Risk` means a residual source of flake remains and is named in the rationale.

Follow the table with gaps, omitting the section when there are none:

```
### Coverage Gaps

- {target} - Missing Layer: {Unit | Widget | Golden | Integration} - Risk: {High | Medium | Low} - {why it matters}
```

Implement mode ends with `Pre-existing: <file:line> - <defect>` for each defect in code the plan edits or depends on but does not fix, or `Pre-existing: none`. Code not yet written is cited as `<path> (new)`. A file the plan depends on that is absent or could not be read is listed as `Not read: <path> - <reason>`. A defect the change cannot ship on top of is fixed in the plan, not listed as `Pre-existing`. A production defect that blocks a planned test (a state the code can never reach) goes on a `Pre-existing` line, not in Coverage Gaps; the test plan does not fix production code.

When invoked from a review workflow or directly to diagnose a flaky test, emit one finding block per defect:

```
### [Blocker | High | Medium | Low] test/path/file_test.dart:LINE

- Test: {test name}
- Defect: {Wrong-Layer | Flaky-Pump | Sleep-Wait | Unstable-Golden | Unreviewed-Golden | Golden-Only | Live-Dependency | Leaky-Double | Self-Override | Weak-Assertion | Multi-Behavior | Fragile-Finder}
- Impact: {what breaks, or what the test fails to catch}
- Fix: {concrete edit}
```

| Defect | Meaning |
|--------|---------|
| `Wrong-Layer` | tested at a slower layer than the behavior requires |
| `Flaky-Pump` | `pumpAndSettle` on unbounded animation, or a missing pump before an assertion |
| `Sleep-Wait` | `Future.delayed` or `sleep` used to wait for a rebuild |
| `Unstable-Golden` | a nondeterminism source the pinning rules name (fonts, surface, pixel ratio, text scale, clock, randomness, animation state, image sources, tolerance, platform) left unpinned |
| `Unreviewed-Golden` | golden regenerated, or tolerance raised, to turn CI green without an image review |
| `Golden-Only` | goldens are a screen's only coverage |
| `Live-Dependency` | real network, real clock, real filesystem, or shared backend |
| `Leaky-Double` | global or static swapped in `setUp` (including one no test wires in), or an undisposed `ProviderContainer` |
| `Self-Override` | the provider whose logic the test asserts is overridden instead of its dependency; in a test of a screen, overriding the provider the screen reads is the correct seam |
| `Weak-Assertion` | asserts the double was configured, only that the widget tree built, or a state the code under test never produces |
| `Multi-Behavior` | one test asserts several behaviors |
| `Fragile-Finder` | finder coupled to editable copy or incidental structure (`find.text` on copy localization will change) |

`Blocker` = the test lies or cannot catch the break it exists for (Weak-Assertion on the only coverage, whether it passes or fails today, Unreviewed-Golden). `High` = flaky, environment-dependent, or testing the wrong thing (Flaky-Pump, Sleep-Wait, Unstable-Golden, Live-Dependency, Self-Override). `Medium` = order-dependence or maintenance drag (Leaky-Double, Wrong-Layer, Fragile-Finder, Golden-Only, Weak-Assertion where other coverage exists). `Low` = style (Multi-Behavior). When a finding matches two bands, the higher band wins. If there are no findings, emit exactly `No testing findings.` so the workflow knows the check ran.

One block per defect, not per test - a test with three defects emits three blocks, and a defect in `setUp` that affects every test emits one block naming `setUp` as the Test. A defect in shared setup or CI configuration anchors to that file instead of a test file, or to `<path> (missing)` when the file the fix needs does not exist, and its Test names the setup function or CI job. A production defect a test exposes (a timer never cancelled that fails teardown) follows the blocks as `Production: <file:line> - <defect>`; its fix belongs to the production code's owner.

Blocks are one per defect, ordered by severity, then file and line, then enum order. Each site of a repeated rule is its own defect; a single defect that needs edits in several places anchors on the line to edit and names the others as `also <file:line>` on its citation line.

A finding that depends on code outside the files read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to the line describing its effect. A check whose subject does not appear in the files read is clean; a check the files read cannot exercise is listed once as `Not checked: <names> - <reason>` and gets no clean or zero-finding line. A file in scope that could not be read is named on that line.

In diagnose mode, blocks for defects that cause the reported symptoms come first, in the order the symptoms were reported; every other defect seen in the files read follows at its own severity.

## Avoid

- `pumpAndSettle` after triggering anything that animates continuously
- `Future.delayed` or `sleep` inside a test to wait for a rebuild
- Goldens as the only coverage for a screen - they assert appearance, not behavior
- Regenerating goldens with `--update-goldens` to clear a red build without inspecting the diff
- Golden tests without loaded fonts, a fixed surface size, or a pinned platform
- Golden generation on developer machines when CI verifies on a different OS
- Tolerance raised until the suite passes - fix the nondeterminism instead
- A live backend, real clock, or real filesystem in unit, widget, or golden tests
- `any()` on a custom type without `registerFallbackValue` for it
- Overriding the provider under test rather than its dependencies
- A `ProviderContainer` created without `addTearDown(container.dispose)`
- `find.text` on user-facing copy that localization or product will change
- `integration_test` for logic a widget test can already observe
- Asserting only `findsOneWidget` on a screen while never checking its rendered state
