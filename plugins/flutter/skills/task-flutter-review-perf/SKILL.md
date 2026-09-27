---
name: task-flutter-review-perf
description: Flutter / Dart perf review - jank and frame budget, rebuild scoping, list virtualization, image decode, isolates, startup, app size, leaks.
agent: flutter-performance-engineer
metadata:
  category: mobile
  tags: [flutter, dart, performance, jank, rebuild, isolate, app-size, memory-leak, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Flutter Performance Review

Client-side perf review naming the Flutter idiom: work inside `build`, unscoped rebuilds, non-lazy list constructors, full-resolution image decode, UI-isolate blocking, startup work before first frame, installed size growth, and undisposed controllers or subscriptions. Every finding states user-visible impact and labels its evidence.

## When to Use

- Flutter perf regression review of a change set
- Jank, dropped frames, or stutter on a specific screen
- Slow cold start or slow time to first meaningful frame
- Memory that climbs across a session or never returns after a route pops
- Installed app size growth
- Pre-release perf pass on scroll paths, image-heavy screens, or a new isolate

**Not for:** general review (`task-flutter-review`), security (`task-flutter-review-security`), pre-implementation design (`task-flutter-implement`).

Perceived slowness that is actually a missing loading state or an unhandled offline path is not a perf finding. When the request reports a symptom, the findings that explain it lead their impact section, after any `Critical`-origin finding.

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Profiling data supplied (DevTools timeline, startup trace, size analysis, heap snapshot), or a perf-critical release | All + a `### Device & Measurement Plan` subsection under Recommendations |

## Measurement Discipline

- **Profile mode on a physical device is the only valid timing source.** Debug mode runs unoptimized with asserts enabled; its numbers overstate cost and are not evidence. Simulator and emulator timings are not device timings.
- **State the frame budget the target device actually runs at** - roughly 16ms at 60Hz, 8ms at 120Hz.
- **Separate UI-thread jank from raster-thread jank.** They have different fixes: UI thread points at build, layout, and paint recording, raster points at `saveLayer`, layer complexity, and first-run shader compilation, which depends on the rendering engine (`flutter-performance`'s engine caveat).
- **Impact, not adjective.** "Rebuilds the full 200-row list on every keystroke" is a finding. "This is slow" is not.

## Out of Scope

Generated files are build output, not review surface. Exclude from findings: `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, and generated localization output. When a generated file carries the cost, review the source that produces it and cite that source's `file:line`.

Test files carry no user-visible cost, so they produce no perf finding. A slow suite is a testing concern, not this review's. A new binary asset is still size surface: without a size analysis it is an `unverified` Size finding naming `--analyze-size`.

## Invocation

`/task-flutter-review-perf [<branch>|pr-<N>] [--base <branch>]`

Defaults to the current branch vs its base; `pr-<N>` reviews a locally fetched PR ref. `review-precondition-check` fails fast on a dirty working tree and on a trunk head - review compares committed code only.

**Never modify the working tree.** Git is read-only here (`status`, `diff`, `log`, `show`).

When invoked as a subagent (e.g. by `task-flutter-review`), the parent supplies the resolved `base_ref` / `head_ref`, the pre-read diff and name-status, the depth level, the detected project shape, and the generated-file exclusion list: Step 3 is skipped, no git is re-run, and Step 12 returns the Output Format body instead of writing - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation if invoked as a subagent.

### Step 2 - Stack and Project Shape

Accept the project shape from the parent when invoked as a subagent. Otherwise read `pubspec.yaml`; if it is absent or declares no `flutter` dependency, stop - this workflow reviews Flutter projects only.

Record: state management (Riverpod / Bloc / Provider / GetX / none), navigation, networking client, persistence store, image loading approach, and the platform targets present. Navigation, networking, persistence, and image approach are working context; the Summary fields are reported, and any the change set and project files do not establish is written `unconfirmed` rather than inferred - a wrong stack claim misroutes every finding under it.

If state management is not Riverpod, record it and note in the Summary: `Detected <X>; Riverpod-specific guidance does not apply.` Review rebuild scoping against that library's own selector or listener mechanism.

### Step 3 - Resolve the Change Set

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-perf`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). **Skip entirely** when the parent supplied the refs plus the pre-read diff. Surface any fail-fast verbatim.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` equals the captured `head_sha` and whose `depth` covers this run's (`deep` covers `standard`) -> print `No new commits since prior perf review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (Step 12 overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then resolve the review set - the paths in `git diff --name-status <base_ref>...<head_ref>`, minus the generated-file list - and read once and reuse, limited to it: `git diff <base_ref>...<head_ref> -- <paths>` for the change body and the name-status for per-file status; a renamed path adds its old path to `<paths>`. The handle's `notes` go to Coverage Notes.

### Step 4 - Read the Performance Surface

Cite real `file:line`. When the source available carries no line anchors, cite the file and name the construct - never invent a number. Open:

- Every changed widget with a `build` method, plus the `State` classes around them
- Every changed state holder (notifier, bloc, controller) and its provider or dependency wiring
- Scrollable constructors and their `itemBuilder` bodies
- Image call sites and any caching layer around them
- `main()`, `runApp`, bootstrap, and anything initialized before the first frame
- `pubspec.yaml` for added dependencies and assets
- Isolate entry points (`compute`, `Isolate.run`, `Isolate.spawn`) and what crosses the port

If the diff is small but ripples into unchanged code - a new screen mounting an existing widget that rebuilds the world, or a new call site into an existing unbounded cache - read the unchanged file. The regression lives there. Anchor the finding's `Location:` at the changed call site that introduced the cost and name the unchanged construct as `also <file:line>`. The unchanged construct is named there, not filed at its own line.

### Step 5 - Build-Path Cost and Rebuild Scoping

Use skill: `flutter-performance` for the pattern bank. Use skill: `flutter-widget-patterns` for `const`, keys, and lifecycle. Use skill: `flutter-riverpod-patterns` for provider scope and rebuild blast radius.

- [ ] **No work in `build`:** no I/O, parsing, sorting, `RegExp` compilation, or list construction. `build` runs whenever an ancestor rebuilds, not when the data changes
- [ ] **`const` on invariant subtrees** - a `const` widget is canonicalized and its subtree is skipped rather than rebuilt
- [ ] **State pushed down:** `setState` on a route-level `State` rebuilds the route. Hold state at the smallest widget that needs it
- [ ] **Selector-scoped watches:** `ref.watch(provider.select((s) => s.field))` over watching the whole object; `ref.read` in callbacks, never `ref.watch`
- [ ] **Builder scope:** a `Consumer`, `BlocBuilder`, or `ValueListenableBuilder` wrapping the whole screen rebuilds the whole screen. Wrap only the reactive part
- [ ] **`MediaQuery.of(context)` in `build`** subscribes to every `MediaQuery` change - keyboard, orientation, text scale, padding. When only one property is read, use the property-scoped accessor (`MediaQuery.sizeOf(context)` and siblings)
- [ ] **`child:` on `AnimatedBuilder`, `ListenableBuilder`, `ValueListenableBuilder`, and `TweenAnimationBuilder`** so the invariant subtree is built once instead of every tick
- [ ] **`RepaintBoundary` around an independently-animating subtree** so its repaints do not propagate to ancestors
- [ ] **`saveLayer` effects:** `Opacity` between 0 and 1, `ShaderMask`, `BackdropFilter`, and a clip with `Clip.antiAliasWithSaveLayer` render offscreen. Prefer alpha applied directly to a color or image and a `borderRadius` on the decoration; animate opacity with `FadeTransition` / `AnimatedOpacity`, which update the layer without rebuilding the subtree

**Bad / good.**

```dart
// Bad - sorts the whole list on every frame an ancestor rebuilds
Widget build(BuildContext context) {
  final sorted = items.toList()..sort((a, b) => a.name.compareTo(b.name));
  return Column(children: sorted.map(ItemRow.new).toList());
}

// Good - sorting belongs to the state holder; build only renders
Widget build(BuildContext context, WidgetRef ref) {
  final sorted = ref.watch(sortedItemsProvider);
  return Column(children: sorted.map(ItemRow.new).toList());
}
```

### Step 6 - List and Scroll Virtualization

- [ ] **Lazy constructors for any list or grid that can exceed one screen:** `ListView.builder` / `.separated`, `GridView.builder`, or `SliverChildBuilderDelegate`. The default `ListView(children: [...])` constructor constructs every child widget up front, on every build of the enclosing widget (elements and layout stay lazy)
- [ ] **`itemExtent` or `prototypeItem`** when rows are uniform, so the viewport does not measure children to lay out the scroll extent
- [ ] **No `shrinkWrap: true` + `NeverScrollableScrollPhysics` nested lists** - that lays out every child regardless of visibility. Compose with slivers in one `CustomScrollView` instead
- [ ] **Bounded per-item work:** no date formatting, `RegExp` compile, sort, or `firstWhere` scan over another collection inside `itemBuilder`
- [ ] **Windowed or paginated loading** for server-backed lists; an in-memory list that only grows is a leak with a scroll bar
- [ ] **Stable keys** (`ValueKey(item.id)`) so element and `State` are reused across reorder rather than rebuilt
- [ ] **`addAutomaticKeepAlives` / `AutomaticKeepAliveClientMixin` used deliberately** - keeping offscreen items alive defeats virtualization's memory benefit
- [ ] List children already get repaint boundaries by default (`addRepaintBoundaries`); adding another per row is noise, not a fix

### Step 7 - Images, Assets, and Decode Cost

- [ ] **Decode resolution bounded** via `cacheWidth` / `cacheHeight` or `ResizeImage`, sized in device pixels (logical size x device pixel ratio) to the box the image renders into. A decoded bitmap costs roughly `width * height * 4` bytes regardless of display size - a 4000x3000 photo in a 96px avatar is about 48 MB of pixels held for one thumbnail
- [ ] **Remote images that recur across launches go through a disk cache**; `ImageCache` reuses a decode only while its entry stays cached, per provider key
- [ ] **`ImageCache` limits are a decision, not a default** - raising `maximumSize` / `maximumSizeBytes` trades memory for fewer decodes and needs a stated reason
- [ ] **No re-decode per build:** `Image.memory` fed a freshly computed `Uint8List` inside `build` decodes again on every rebuild. Hoist the bytes, or cache the decoded image
- [ ] **`precacheImage`** for images that would otherwise pop in on first paint
- [ ] **Resolution variants shipped** (1x / 2x / 3x) rather than one oversized asset scaled at runtime; each variant adds to installed size, so ship only the densities the targets use

### Step 8 - Off-Thread Work and Isolates

Use skill: `dart-language-patterns` for isolate and async mechanics.

- [ ] **CPU-bound work moved off the UI isolate** via `compute` or `Isolate.run`: large JSON parse, crypto, image transform, big sort or filter. On web `Isolate.run` throws and `compute` runs on the UI thread, so a web target needs the work reduced or chunked instead
- [ ] **`async` does not move work off the isolate.** A synchronous loop blocks the UI whether or not the enclosing function is `async` - only an isolate or a genuine `await` on I/O yields
- [ ] **Threshold reasoning:** spawning an isolate and copying its message is not free. Recommend one when the work exceeds a few milliseconds - a real share of an 8-16ms frame - not microseconds
- [ ] **Large binary inputs, and payloads over a long-lived port,** use `TransferableTypedData`; an `Isolate.run` result already returns without a copy
- [ ] **Repeated background work uses a long-lived isolate with ports**, not one spawn per item
- [ ] **Platform-channel calls are already asynchronous** and the native work does not run on the Dart isolate - do not wrap one in `compute`. A background isolate that needs channels requires its binary messenger to be initialized explicitly for that isolate

### Step 9 - Startup Time and App Size

- [ ] **`main()` before `runApp` does the minimum:** no blocking network call, no full database open and migrate, no large parse. Defer past the first frame or behind an explicit splash state
- [ ] **Initialization is lazy** - a provider or service never read should never be constructed
- [ ] **Startup measured from a profile-mode startup trace** (`flutter run --profile --trace-startup`), not from stopwatch feel
- [ ] **Size measured from a build-size analysis** (`flutter build <target> --analyze-size`, Android with one `--target-platform`, reviewed in the DevTools app-size tool; web is measured by the built `main.dart.js`). Report the delta this change introduces, not the absolute total
- [ ] **New dependency justified against its size contribution** - a package pulled in for one helper is a size finding; with no size analysis supplied it is `unverified`, naming `--analyze-size` as its measurement
- [ ] **Asset hygiene:** uncompressed images, unused fonts, whole icon sets, and bundled test fixtures shipping to production
- [ ] **Android ships an app bundle or split-per-ABI builds** rather than one universal APK
- [ ] **Icon-font tree-shaking left enabled in release** - a non-constant `IconData` fails the release build unless `--no-tree-shake-icons` is passed, which ships the whole icon font

### Step 10 - Memory, Disposal, and Leaks

- [ ] **Everything created in a `State` is released in `dispose`:** `AnimationController`, `Ticker`, `TextEditingController`, `ScrollController`, `PageController`, `TabController`, `FocusNode`, `StreamSubscription`, `StreamController`, `Timer`, and any platform-channel or `EventChannel` subscription
- [ ] **Every `addListener` has a matching `removeListener`** - a listener closure captures its `State` and pins the element tree it belongs to
- [ ] **Riverpod:** screen-scoped providers are `autoDispose` or explicitly invalidated; `ref.onDispose` closes whatever the provider opened; a `keepAlive` is a deliberate cache with a stated eviction path
- [ ] **Global caches, static maps, and singletons are bounded and evicted** - unbounded growth reads as a slow leak
- [ ] **Large retained objects released when the route pops** (decoded images, full result sets, buffered streams)
- [ ] **Leak suspicion is confirmed, not asserted:** navigate away, force a GC, and check the retaining path in the DevTools memory view before filing a leak as measured

**Impact heuristic.** A leaked controller survives navigation, so the symptom is never the first leak - it is the tenth. Phrase impact as accumulation across a session ("about 40 MB retained per visit to this screen, never released"), ending in an OS kill the user experiences as the app closing itself.

### Step 11 - Evidence and Impact

Label every finding's evidence. Never present an estimate as a measurement, and never cite a debug-mode number at all.

Evidence and impact are independent axes. Evidence records how well the cost is established; impact records what the user feels. A finding can be `estimated` and High Impact, or `measured` and Low.

| Evidence | Use when | Example phrasing |
|----------|----------|------------------|
| `measured` | A trace, size analysis, or heap snapshot covering **this code path** was supplied | `raster thread 24ms/frame on the feed scroll, Pixel 6, profile mode` |
| `estimated` | The pattern's cost is unambiguous from the code alone | `rebuilds all 200 rows on every keystroke` |
| `unverified` | The cost turns on data only the author has (collection size, image dimensions, device tier) | Name the measurement that would settle it |

`flutter-performance`'s `measured (...)` and `estimated (no profile)` map onto this table, its `estimated` becoming `estimated` or `unverified` by the tiebreak below; blocks from the other atomics carry no Evidence and take one by the same rules. Data the user states (collection size, device) counts as known for the tiebreak. A trace supplied for part of the change set makes `measured` only the costs it isolates - a cost inside a measured window that the trace does not separate stays `estimated`; label the rest by the same rules and say where the trace's coverage ends in the Measurement Basis line; an uncovered path is not a `Not checked:` item. When both `estimated` and `unverified` fit, the tiebreak is whether a reasonable worst case is still a finding: if yes, `estimated`; if the finding evaporates under a plausible small input, `unverified`.

**Impact mapping.** This report groups by impact and grades only in-lens costs: build and rebuild work, lists, images, isolates, startup and size, disposal and leaks. An atomic finding outside those (key correctness, null safety, an unhandled error branch) is an `Outside this lens:` line. `Critical`, `High`, and `[Must]` map to **High Impact**, `Medium` to Medium, `Low` and `[Recommend]` to Low. One defect raised by two atomics - or two checklist items one edit fixes - is one finding at the higher impact, its Issue opening with the grading atomic's Category or Rule, `flutter-performance`'s when it raised the defect. When one defect multiplies another's cost (a per-tick rebuild re-running a non-lazy list), each is its own finding at the impact it has with the other present, and each names the other in its Issue. A `Critical`-origin finding - `flutter-performance` grades Critical only where profile data covers the path and caps at High without it; another atomic's Critical carries its own rationale - leads the High Impact section and opens its User-Visible Impact line with `Critical:` and the grading atomic's rationale; do not silently flatten it into an ordinary High, and never add the prefix to a finding the atomic did not grade Critical.

`unverified` does not lower impact: an unbounded cache on a primary path is High Impact whether or not its size is known. It sets intent instead - every `unverified` finding's Next Steps item is `[Recommend]` and the finding names its measurement, including at High Impact, which is the one case where a High Impact finding is not `[Must]`.

A cost the user cannot perceive on any supported device (well under a frame, off the startup path) is Low, whatever label the atomic gave it.

**Atomic output lines.** Findings keep the atomics' unit: one per defect, further sites of that one defect named as `also <file:line>` on the Location line (each site of a repeated rule is its own defect), and an atomic's `(unconfirmed: depends on <path>)` is resolved by reading that path before the finding is filed, and when the path cannot be read the finding stays `(unconfirmed: ...)` and the path joins the `Not checked:` line. `No performance findings.` and the other atomics' `No <category> findings.` and `No <rule> findings.` lines are working notes: they confirm a check ran and stay out of the report. Every atomic's `Not checked:` line, and any in-scope file that could not be read, is carried into Coverage Notes. There is no cap on findings; order carries priority. An atomic block's heading gives Location's `file:line` and its Code line the `also` sites, its Cost, Problem, or Issue line the User-Visible Impact, and its fix the Fix; the other atomics' blocks take a Thread by the same Category logic (disposal and leaks Memory, build work UI); `Dart SDK inferred:` and `Dart 3 patterns unavailable:` lines go to Coverage Notes.

**Pre-existing defects.** A defect on a line the change set does not touch is a finding only when the change makes it reachable or worse - a new caller, a new route into it, a new composition such as a new call site into an unbounded cache, or an omission the change needs filled in an untouched file; anchor it at the changed line and name the old line as `also`. Any other defect seen while reading goes on a `Pre-existing: <file:line> - <defect>` line in Coverage Notes and does not affect the Overall count. A defect outside this lens - a correctness or compile error, a risk the security lens owns - goes on an `Outside this lens: <file:line> - <defect>` line there; in a subagent run the parent routes it to its owning phase.

### Step 12 - Write Report

Standalone only. A subagent run writes no file and prints no confirmation line: it returns the Output Format body - Summary, Findings, Recommendations including any deep-only subsection, Next Steps, and Coverage Notes - to the parent, which merges it and owns the report. The checkpoint write is standalone-only.

**Round 2+ reconcile (standalone).** Project the prior report (the file at the handle's `report_path`, every impact section) into reconcile's parse shape: one `## High-Impact Findings` section with one `### [Label] file:line` heading per finding - the intent its Next Steps item carried (High -> `[Must]`; Medium, Low, or `unverified` -> `[Recommend]`), the bare `file:line` prefix of its `Location` line, and a trailing `_(carried from round <N>)_` group re-emitted on the heading as its own group - followed by its `Issue` line written as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line, and tally render as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this run did not re-derive publishes in its prior impact section with `_(carried from round <N>)_` (`<N>` = the prior report's `round`) appended to its `Location` line; one this run re-derived publishes once, at this run's impact. Both get a Next Steps entry. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table; `[Praise]` rows are never carried.

Use skill: `review-report-writer` with `report_type: review-perf`, `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `mode: full`, `round` and `prior_head_sha` from the round gate, `scope: +perf`, `depth` as resolved from the Depth table, `stack: flutter`, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Print the writer's confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit the report body as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

Every Next Steps item carries exactly one intent label, `[Must]` or `[Recommend]`, beside its `[Implement]` or `[Delegate]` tag. No other label is written.

```markdown
## Flutter Performance Review Summary

- **Stack Detected:** Flutter <constraint> / Dart <constraint>
- **State Management:** Riverpod | Bloc | Provider | GetX | none | unconfirmed _(non-Riverpod: `Detected <X>; Riverpod-specific guidance does not apply.`)_
- **Platform Targets:** <list>
- **Measurement Basis:** <profile-mode trace | startup trace | size analysis | heap snapshot> on <device or build> (covering: <paths>; estimated or unverified elsewhere) | estimated from code (no trace supplied) | estimated from code (supplied <debug-mode | emulator> timing not used as evidence)
- **Scope:** Client (Flutter)
- **Round:** <N> _(round 2+ standalone runs only)_
- **Overall:** Clean (no findings) | Issues Found - [count by impact, however few]
- **Checks with no findings:** [the Step 5-10 areas whose subject the diff touches that ran clean, named - build path, lists, images, isolates, startup and size, disposal]

## Findings

### High Impact

- **Location:** [file:line, further sites as `also <file:line>`; file plus construct when the source has no line anchors] _(a carried finding appends `_(carried from round <N>)_`)_
- **Issue:** [the grading atomic's Category or Rule, then the Flutter idiom: sort inside `build`, non-lazy `ListView` over a dynamic collection, full-resolution decode into a thumbnail, sync parse on the UI isolate, undisposed `AnimationController`]
- **User-Visible Impact:** [`Critical: <rationale> - ` first on a Critical-origin finding; then what the user experiences: "dropped frames while typing", "adds ~1.2s to cold start", "+3.1 MB installed size", "about 40 MB retained per visit, never released"]
- **Evidence:** measured (<source>) | estimated | unverified
- **Thread:** UI | Raster | Both | Startup | Memory | Size _(the atomic's Thread, except by Category: `Startup` is Startup, `Leak` and a non-blocking `ImageDecode` are Memory, `AppSize` is Size, a non-blocking `PlatformCall` is UI)_
- **Fix:** [concrete Dart change with code]
- **Verify:** [the measurement that settles an `unverified` finding, or shows the fix worked]

### Medium Impact / Low Impact

[Same structure]

_Omit empty sections._

## Prior Round Reconciliation _(round 2+ standalone runs only)_

[table, note line, and tally from `review-prior-findings-reconcile`]

## Recommendations

[Structural improvements not tied to a single finding]

### Device & Measurement Plan _(deep depth only)_

[Which device tiers to measure on, which trace to capture, and the number that decides whether the fix worked]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.
Impact maps to intent: High -> [Must]; Medium / Low -> [Recommend]. An `unverified` finding is `[Recommend]` at any impact; when its fix is cheap and safe regardless of the measurement, the action names the fix and the measurement together rather than the measurement alone. Order `[Recommend]` items by impact, so an unverified High Impact finding leads its band.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: server contract] - [one-line action]

_Omit if no actionable findings._

## Coverage Notes

[One line each, omitted when empty: the handle's notes (standalone runs), atomic header lines, `Not checked:`, `Pre-existing:`, `Outside this lens:`]
```

`Stack Detected` carries the `pubspec.yaml` constraints (`environment.flutter`, `environment.sdk`) as written; a missing constraint is `unconfirmed`.

## Self-Check

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; state management, image approach, and platform targets recorded; non-Riverpod state management surfaced rather than flagged
- [ ] `review-precondition-check` ran with `report_type: review-perf` (or parent-supplied refs and diff reused); round decided before any surface was read (or the stop line printed); diff and name-status read once and reused
- [ ] Performance surface read directly (widgets and `State`, state holders, scrollables, image call sites, bootstrap, `pubspec.yaml`, isolate entry points)
- [ ] `flutter-performance`, `flutter-widget-patterns`, `flutter-riverpod-patterns` consulted; work in `build`, `const`, rebuild scope, `MediaQuery` subscription, builder `child:`, `RepaintBoundary`, and `saveLayer` effects checked
- [ ] List virtualization checked: lazy constructor, extent hint, no `shrinkWrap` nesting, bounded `itemBuilder`, stable keys, pagination, deliberate keep-alive
- [ ] Image decode bounds, caching layer, `ImageCache` limits, and per-build re-decode checked when the diff touches images
- [ ] `dart-language-patterns` consulted; UI-isolate blocking, isolate threshold, and payload transfer assessed when the diff adds computation
- [ ] Startup path and size delta assessed when the diff touches bootstrap, dependencies, or assets
- [ ] Disposal completeness audited for every controller, subscription, timer, ticker, and listener introduced; provider disposal scope checked
- [ ] Every finding labelled `measured` / `estimated` / `unverified`; no debug-mode timing cited as evidence; a partial trace labelled `measured` only for the costs it isolates
- [ ] `unverified` findings kept at their true impact and tagged `[Recommend]` with the measurement named
- [ ] Every finding states user-visible impact, not an adjective
- [ ] Areas that ran clean named in the Summary; unresolvable stack fields written `unconfirmed`
- [ ] Generated and test files excluded from findings; the producing source cited instead
- [ ] Findings ordered by impact; Coverage Notes carry handle notes, atomic header lines, `Not checked:`, `Pre-existing:`, and `Outside this lens:` lines
- [ ] Depth honored: `standard` ran all steps; `deep` added the Device & Measurement Plan
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered Must > Recommend
- [ ] On round 2+ standalone runs, prior findings projected and reconciled, unresolved rows carried; report written via `review-report-writer` with every required field (`stack: flutter`, `mode: full`, round, both SHAs), confirmation line printed (standalone only; subagent runs return the Output Format body to the parent)

## Avoid

- State-changing git from this workflow (fetch/checkout/merge/pull/rebase/stash) - the review reads history only
- Writing a report when invoked as a subagent - the parent owns it
- Citing a debug-mode timing, an emulator timing, or a hot-reload observation as evidence
- Reporting cost without user-visible impact ("this rebuilds a lot" vs "rebuilds all 200 rows on every keystroke, dropping frames while typing")
- Generic frontend advice where a Flutter idiom exists ("scope the rebuild with `select`", not "reduce re-renders")
- Raising findings against `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, or generated localization output
- Prescribing `const` on a widget whose subtree actually varies
- Recommending an isolate for work too small to pay back its spawn and copy cost
- Recommending `RepaintBoundary` per list row where the framework already inserts one
- Treating `async` as a way to move CPU work off the UI isolate
- Blaming the client for latency that belongs to the server - route it to the owning service
- Filing a missing loading state or unhandled offline path as a perf finding
- Optimizing without a measurement plan that would show the fix worked
