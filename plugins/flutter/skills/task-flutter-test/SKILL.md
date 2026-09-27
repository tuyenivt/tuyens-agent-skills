---
name: task-flutter-test
description: Flutter test plan and scaffolding - unit, widget, golden, and integration_test layering, mocktail, provider overrides, golden stability in CI.
agent: flutter-test-engineer
metadata:
  category: mobile
  tags: [flutter, dart, testing, widget-test, golden, integration-test, mocktail, riverpod, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Flutter Test

Flutter-aware test strategy and scaffolding across unit, widget, golden, and `integration_test` layers, using mocktail and provider overrides, with golden stability treated as a first-class concern.

## When to Use

- Test strategy for a new Flutter app or feature
- Test-coverage gap assessment across layers
- Scaffolding tests for under-covered screens, state holders, or repositories
- Test pyramid review
- Adding failure-path tests to happy-path-only tests
- Diagnosing goldens that pass locally and fail in CI

**Not for:** debugging a failing test whose production code is wrong (`flutter-engineer`), general review (`task-flutter-review`).

## Workflow

### Step 1 - Principles, Stack, and Project Shape

Use skill: `behavioral-principles` first (accept the parent's confirmation when invoked as a subagent). Accept the project shape from a parent workflow when invoked as a subagent. Otherwise read `pubspec.yaml`; if it is absent or declares no `flutter` dependency, stop - this workflow tests Flutter projects only. Record state management (and the Riverpod major, 2 or 3, when Riverpod is used), navigation, networking client, persistence store, mocking library (mocktail / mockito / hand-written), and whether the project uses code generation.

The project's own tooling wins over this skill's defaults. Where the project differs, say so once and follow the project:

| Default here | If the project differs | What changes |
|--------------|------------------------|--------------|
| Riverpod | Bloc / Provider / GetX | Test seam is that library's own - `BlocProvider.value` and `blocTest` for Bloc - not provider overrides |
| mocktail | mockito | `@GenerateNiceMocks` (or legacy `@GenerateMocks`) codegen and bare `when(...)`; `registerFallbackValue` does not exist and its checks are N/A |
| mocktail | hand-written fakes | No matcher registration at all; assert on the fake's recorded calls |

`bloc_test` is built on mocktail, so a Bloc project on mockito ends up with both. Keep each library to its own file, or alias one import - importing both unaliased makes `when`, `verify`, and `any` ambiguous and the file does not compile.

### Step 1b - Route the Request

Decide the deliverable before reading code, because it decides what to read:

| Request | Deliverable | Steps that run |
|---------|-------------|----------------|
| "Why does this golden/test fail in CI?" | Diagnosis finding blocks | 1, 2 (the failing test's whole file, its setup, and the CI configuration that runs it), 4, 8 |
| "Write tests for X" / "scaffold" | Test Scaffolds | all (7 only when test files are sparse against source files; it orders the files written and adds no section) |
| "What tests are missing?" | Coverage Assessment | all |
| "Test strategy" / "test plan", or low coverage with no scaffolds requested | Strategy Doc | all |
| Unclear | Strategy Doc | all |

For a strategy or coverage request, Step 7 selects the targets and Step 2 then reads them; run Step 7 first and treat its output as Step 2's reading list.

### Step 2 - Read Code Under Test + Existing Tests

Ground output in project conventions, not generic templates.

- Read each target top-to-bottom: the screen's widget tree, its state holder, the repository it depends on, and the failure types it can surface
- Glob `test/**/*_test.dart` and read one existing widget test, one unit test, one golden test, and any shared setup file - learn the project's finders, pump conventions, fake construction, and override style
- Read every `test/**/flutter_test_config.dart`; the nearest one above a test applies, and it is where golden and font setup usually lives
- Read CI configuration for how tests run, whether goldens run in a separate job, and how failures surface
- Read `integration_test/` for existing driver setup

If no existing tests: say so and propose conventions on the `Conventions:` line rather than inventing them silently. A setup file this step names that does not exist is a `Not read: <path> - absent` line, not a gap, unless the deliverable needs it.

### Step 3 - Flutter Test Pyramid

| Layer | Tooling | What belongs |
|-------|---------|--------------|
| Unit | `test` / `flutter_test` + mocktail | State-holder logic, failure mapping, validators, formatters, pure functions |
| Widget | `testWidgets` + finders | A screen or component in isolation: renders, responds to input, shows each state |
| Golden | `matchesGoldenFile` | Pixel-level appearance of visually complex or regression-prone UI only |
| Integration | `integration_test` on a device, emulator, or desktop host | Critical end-to-end journeys only |

**Many** unit, **some** widget, **few** golden and integration. Goldens are a deliberate minority: they are the most expensive layer to keep stable and the least specific about what broke.

### Step 4 - Apply Flutter Test Patterns

Use skill: `flutter-testing-patterns` - diagnose mode for a Diagnosis, implement mode otherwise - for canonical finders, pump semantics, golden stability, mocktail usage, and provider overrides. Notes below cover layer-specific items.

**Unit tests:**

- Test the state holder directly, without building a widget tree. If a unit test needs a widget, it is misclassified
- One group per public method; cover success, each failure type, and the edges between them
- Failure mapping deserves its own tests: assert that a transport error becomes the intended domain failure, not just that "an error happened"
- Inject fakes through the same seam production uses, so the test proves the wiring too

**Widget tests:**

- Build the widget under a test harness that supplies its dependencies via overrides, not a real network client or database
- Assert on every state the screen can render: loading, error, empty, and populated. A screen tested only in its populated state is half-tested
- Prefer pumping a bounded number of frames over settling when the widget has an indefinite animation or a frame-scheduling timer - settling on those times out and throws instead of failing on the assertion
- Find by semantics or key where possible; finding by literal text couples the test to copy and breaks under localization
- Test user interaction, not just initial render: tap, scroll, enter text, then assert the resulting state

**Golden tests:**

Golden instability is the dominant failure mode, and it is almost always environmental rather than a real regression.

- Load fonts deterministically in test setup; without it, text renders as boxes on every host and typography changes go unseen
- Pin the surface size and device pixel ratio rather than inheriting the host's
- Expect platform-dependent rendering differences: a golden generated on one OS is not reliably pixel-identical on another. Either generate per platform or run goldens on one designated platform in CI
- Pin the generating platform first; a tolerance, kept as low as CI allows, covers only the antialiasing residue
- Tag goldens so the main test job can exclude them and a dedicated job can run them
- Regenerating a golden must be a deliberate act with the diff reviewed, never a reflex when CI goes red

**Integration tests:**

- Reserve for journeys that cross screens, persistence, and the network together: sign-in through to first meaningful screen, purchase, offline-then-reconnect
- Stub the network at the client boundary, or point at a seeded backend selected by `--dart-define`, never at a live shared one, so the test is deterministic
- Avoid for anything a widget test could cover; they are slow and fail for environmental reasons

### Step 5 - Test Boundaries

**Unit:** state holders, failure mapping, validators, formatters, domain rules, calculations, and any pure transformation

**Widget:** every screen - each of loading, error, empty, populated; user interaction paths; navigation triggers; form validation feedback; accessibility labels present on interactive elements

**Golden:** visually complex components, custom painters, theming across light and dark, and layout at representative breakpoints. Not simple layouts whose correctness a widget test already asserts

**Integration:** critical journeys only; on-device persistence surviving a restart; permission-gated flows

**Does NOT need a test:** framework-provided behavior, generated code (`*.g.dart`, `*.freezed.dart`, and siblings), and trivial pass-through delegation with no logic. A hand-written migration callback is not generated code; it is P2

### Step 6 - Test Data and Fakes

- Factory functions with sensible defaults and named overrides, rather than hand-rolled literals repeated per test
- Fakes over mocks where the collaborator has real behavior worth simulating; mocks where you only need to assert an interaction happened
- Keep test data minimal - a 100-item fixture for a test asserting one row signals the wrong layer
- Satisfy the mocking library's own matcher requirement once in shared setup, not per test: mocktail needs `registerFallbackValue` for any custom type used with `any()`; mockito needs no matcher registration, but a return type it cannot fake needs `provideDummy` once in shared setup

### Step 7 - Prioritization

Runs for every Strategy Doc and Coverage Assessment, and **before** scaffolding when test files are sparse against source files - it determines which tests come first.

Measure, do not guess: run the project's coverage command when the suite runs locally (`flutter test --coverage` writes `coverage/lcov.info`; the percentage comes from summarizing it, and files no test imports are missing from it, so say so); when it cannot run, estimate from test-file density and label the number an estimate.

Band from structure, not implementations: the route table, feature directory names, and pubspec dependencies (a purchase plugin implies P3 surface) are enough to place targets. Step 2 then reads only the selected targets.

| Priority | Targets |
|----------|---------|
| P1 - Auth and session | Sign-in, token refresh, expiry and forced sign-out, permission-gated screens |
| P2 - Data integrity | Failure mapping, on-device persistence and its migrations, sync and conflict resolution, optimistic-update rollback |
| P3 - Business-critical | Purchase and billing flows, anything irreversible from the user's side, state machines |
| P4 - High-churn | Files with frequent recent commits (read-only `git log --since="3 months ago"`) or bug-fix history |
| P5 - Presentational | Simple stateless components with no logic - lower risk, can wait |

**Multi-band rule.** When a target qualifies for multiple bands, file it under the highest (lowest number) and note the secondary so the plan covers both axes.

### Step 8 - Test Infrastructure Hygiene

Run this against the project. Items that fail or cannot be verified fill the `## Infrastructure Gaps` slot in the Strategy Doc and Coverage Assessment, once, and are not repeated as coverage gaps; items that hold need no line. On a Diagnosis, a failing item that causes the failure files as a finding block, and one that only costs (no Defect value names it) becomes an `Infrastructure:` line; on Scaffolds, apply it silently and raise only what blocks the deliverable.

- [ ] Fonts loaded deterministically before golden tests
- [ ] Goldens tagged and run in a job that can be excluded from the fast feedback loop
- [ ] Goldens pin surface size, pixel ratio, and tolerance
- [ ] Golden platform expectations documented, so a cross-platform diff is not mistaken for a regression
- [ ] Network stubbed at the client boundary or a seeded backend; no live shared backend in CI
- [ ] Test setup overrides only what differs from production - never silently disables auth
- [ ] mocktail: fallback values registered once in shared setup for custom matcher types
- [ ] Generated code regenerated and committed state verified when models change
- [ ] Coverage command documented; thresholds, if any, stated per area rather than as one global number
- [ ] Integration tests segregated so they do not gate every pull request

## Output Format

Step 1b routes the request to one deliverable, or to each deliverable the request names; two or more are emitted in this order, separated by `---`: Coverage Assessment -> Strategy Doc -> Test Scaffolds. Diagnosis stands alone.

`Stack` carries the `pubspec.yaml` constraints (`environment.flutter`, `environment.sdk`) as written; a missing constraint is `unconfirmed`. Implement-mode atomics end with `Pre-existing:` and `Not read:` lines, a `Not read:` line naming any file the plan needed but could not read, absent or denied. The report carries them once, merged across atomics and deduplicated by cited location, under `## Pre-existing and Not read`; `Pre-existing: none` is written when no atomic found one.

**Diagnosis:** in this order - the finding blocks from `flutter-testing-patterns`' diagnose mode in that skill's order (blocks for the reported failure first, then every other defect seen in the files read, sibling tests in the failing test's file included), or `No testing findings.` when there are none; its `Production:` lines; `Infrastructure: <file:line> - <defect>` lines for cost defects no Defect value names (goldens gating the fast job, a suite too slow to run per PR); its `Not checked:` line; any `Not read:` line from Step 2; and a `Verify:` line naming the command that re-runs the failing surface (one per finding when no single command exercises every fix). Nothing else: no strategy doc, no pyramid, no coverage table. A defect in shared setup (`flutter_test_config.dart`, a `test/support/` helper, CI configuration) anchors to the file that carries it, or to `<path> (missing)` when the file the fix needs does not exist, and its Test slot names the setup function or CI job. `Not checked:` names checks the files read cannot exercise, not files outside the Diagnosis reading scope.

**Coverage Assessment:**

```markdown
## Flutter Test Coverage Assessment

**Stack:** Flutter <constraint> / Dart <constraint>
**State Management:** Riverpod | Bloc | Provider | GetX | none
**Mocking:** mocktail | mockito | hand-written
**Coverage:** <N>% measured via <command> | <N>% estimated from test-file density (test files per source file under `lib/`, not line coverage)
**Conventions:** [only when the project has no tests: the conventions proposed]
**Recommended pyramid balance:** Unit [target] / Widget [target] / Golden + integration [target - keep small] (share of test files)

## Test Plan by Target

[the per-target table and `### Coverage Gaps` block from `flutter-testing-patterns`; a screen missing loading, error, or empty coverage is a `Missing Layer: Widget` entry naming the missing states]

## Pre-existing and Not read

[the merged `Pre-existing:` and `Not read:` lines]

## Infrastructure Gaps

[the Step 8 items that failed or could not be verified, unstable goldens among them, each naming the priority band it blocks. Omit when all hold.]

## Prioritization

1. **P1 - Auth and session:** [sign-in, refresh, expiry, forced sign-out]
2. **P2 - Data integrity:** [failure mapping, migrations, sync, rollback]
3. **P3 - Business-critical:** [purchase, billing, irreversible actions]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Presentational:** [simple stateless components]

[a band whose signal is unavailable reads `P<n> - unmeasurable: <reason>`]
```

**Test Scaffolds:** ready-to-run files using project conventions, delivered with the per-target table and `### Coverage Gaps` block from `flutter-testing-patterns`, the `## Pre-existing and Not read` lines, and a `Conventions:` line when the project had no tests:

- Right test layer for the behaviour
- Grouped cases with descriptive names, not copy-pasted bodies
- Factories over raw literals
- Widget tests covering loading, error, empty, and populated
- Fakes injected through the project's own dependency seam
- Goldens only where a widget test cannot express the concern, with font and size setup included
- An existing test the scaffold supersedes is rewritten in place and named in the file list with what it got wrong; `Pre-existing:` stays for defects the scaffolds do not fix
- **Verified before delivery:** run `flutter analyze` and the generated tests, and fix what they surface. When the environment cannot run them (no Flutter toolchain, no device for integration tests), deliver the scaffolds with an explicit `Not verified:` line naming the subset that did not run and the specific things analysis would have caught - symbol names, generated-type accessors, and API shapes taken from simulated reads. A scaffold that failed a check you did run is never delivered.

**Strategy Doc:**

```markdown
## Flutter Test Strategy

**Objective:** [what this strategy achieves]
**Coverage:** <N>% measured via <command> | <N>% estimated from test-file density (test files per source file under `lib/`, not line coverage)
**Conventions:** [only when the project has no tests: the conventions proposed]
**Pyramid balance:** Unit {x}% / Widget {y}% / Golden + integration {z}% (share of planned test files)
**Tooling:** flutter_test, <the project's mocking library>, <the project's DI seam>, integration_test
**Golden policy:** [generating platform, font loading, tolerance, how they are regenerated]
**Network isolation:** [where the client boundary is stubbed]

## Test Plan by Target

[the per-target table and `### Coverage Gaps` block from `flutter-testing-patterns`]

## Pre-existing and Not read

[the merged `Pre-existing:` and `Not read:` lines]

## Gaps to Close (prioritized)

1. **P<n> - <band>:** [highest risk first; a band whose signal is unavailable reads `P<n> - unmeasurable: <reason>`]
2. ...

## Infrastructure Gaps

[the Step 8 items that failed or could not be verified, each naming the priority band it blocks. Omit when all hold.]
```

## Self-Check

**Always:**

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Stack confirmed; state management, mocking library, and codegen usage recorded
- [ ] Request routed at Step 1b
- [ ] Code under test + existing tests + shared setup read directly (Diagnosis: the failing test's whole file, its setup, and its CI configuration)
- [ ] `flutter-testing-patterns` consulted
- [ ] Project's own state-management and mocking tooling followed over this skill's defaults

**Strategy / Coverage:**

- [ ] Pyramid mapped to Flutter layers (unit -> state holders; widget -> screens; golden -> visual regression; integration -> journeys)
- [ ] Boundaries defined: each layer covers what it does best; no duplicated assertions
- [ ] Risk-based prioritization (P1 auth, P2 integrity, P3 business, P4 churn, P5 presentational); Coverage Gaps keep the atomic's Risk, the bands order the targets
- [ ] Coverage number stated and labelled measured or estimated; unmeasurable bands named rather than guessed
- [ ] Strategy Doc: golden policy stated - platform, fonts, tolerance, regeneration discipline
- [ ] `Pre-existing:` and `Not read:` lines carried
- [ ] Screens missing loading, error, or empty coverage flagged explicitly
- [ ] Step 8 failures reported as `## Infrastructure Gaps`, sequenced against the P1-P5 content it blocks

**Diagnosis:**

- [ ] Diagnosis in order: finding blocks (or `No testing findings.`), `Production:`, `Infrastructure:`, `Not checked:`, `Not read:`, `Verify:`; no strategy doc or pyramid
- [ ] Shared-setup and CI defects anchored to the file that carries them, or to `<path> (missing)`
- [ ] Cost defects no Defect value names filed as `Infrastructure:` lines
- [ ] Verification step named for the author to confirm the fix

**Scaffolds:**

- [ ] Per-target table, `### Coverage Gaps`, and `Pre-existing:` / `Not read:` lines delivered with the files
- [ ] Grouped and descriptive, not copy-pasted
- [ ] Factories over raw literals
- [ ] Widget tests cover loading, error, empty, and populated
- [ ] Finders prefer key or semantics over literal copy
- [ ] Fakes injected through the production dependency seam
- [ ] Golden scaffolds include font and surface-size setup
- [ ] mocktail: fallback values registered for custom matcher types
- [ ] Scaffolds analyzed and run before delivery; any subset not run is named

## Avoid

- Scaffolding without reading existing tests and shared setup
- Chasing a coverage number instead of prioritizing by risk
- Testing only the populated state of a screen that also has loading, error, and empty
- Golden tests as a substitute for asserting the logic that produced the pixels
- Regenerating a failing golden without reading the diff
- Exact golden comparison across platforms
- Running goldens in the same job as fast unit tests
- Finding widgets by literal user-facing text in a localized app
- Settling a widget test that contains an indefinite animation or a frame-scheduling timer
- Pointing tests at a live shared backend
- Full integration tests for what a widget test could cover
- Testing framework internals or generated code
- Disabling auth in test setup to make unrelated tests pass
- Delivering scaffolds that were never analyzed or run
