---
name: flutter-adaptive-responsive
description: "Build adaptive Flutter UI: platform tiers, Material vs Cupertino, LayoutBuilder/MediaQuery breakpoints, safe areas, input modality, desktop and web."
metadata:
  category: mobile
  tags: [flutter, dart, adaptive, responsive, layout, mediaquery, cupertino, desktop, web, platform-tiers]
user-invocable: false
---

# Flutter Adaptive and Responsive UI

> This skill owns the **platform tier convention** (first pattern below). `flutter-accessibility` and `flutter-i18n` reference it rather than restating it. Constraint mechanics (`Expanded`, unbounded-constraint errors, `const`) belong to `flutter-widget-patterns`; route-level web URL strategy belongs to `flutter-navigation-patterns`.

## When to Use

- Building or reviewing a screen that must work on more than one form factor, orientation, or platform
- Choosing between Material, Cupertino, and `.adaptive` widgets, or deciding whether a platform difference is worth branching on
- Deciding where a layout switches between one-pane and multi-pane, and whether the switch reads a constraint or the screen
- A platform target directory is added to the project, or a bug reproduces only on tablet, desktop, web, split-screen, or a folded device

## Rules

- Every pattern and every finding declares its tiers. Mobile is assumed unless the project says otherwise; desktop and web are addressed only when their target directories exist
- Layout switches on the constraints the parent granted (`LayoutBuilder`), not on the physical screen (`MediaQuery.sizeOf`). Screen size is correct only for decisions that are genuinely about the window: system chrome, insets, orientation
- Breakpoints live in one named place and are referenced by name. A magic `600` inline in a widget is a defect
- Platform branching reads `Theme.of(context).platform`, never `Platform.isX` from `dart:io`. `dart:io` throws on web and ignores the theme override that tests and previews rely on
- Prefer an `.adaptive` constructor over a hand-rolled `if (isIOS)` branch. Branch by hand only when the two platforms need genuinely different interaction, not different paint
- Pick one design language per app (Material by default) and stay in it. A Cupertino control inside an otherwise Material screen is an inconsistency, not an adaptation
- Insets are read, never assumed: `SafeArea` or `MediaQuery.paddingOf` for cutouts and system bars, `MediaQuery.viewInsetsOf` for the keyboard. No hardcoded status-bar or notch heights
- Any surface that can receive text input or a scroll must survive a keyboard, a rotation, and a window resize without clipping or losing scroll position
- Every interactive element is reachable and operable by keyboard once desktop or web is a target; pointer affordances (hover, cursor, right-click) are additive, never the only path to an action
- Web removes capabilities rather than adding them: no `dart:io`, no `MethodChannel`, no secure-storage guarantee. Code paths that need them are behind a capability check with a defined web fallback

## Patterns

### Platform tiers

Coverage degrades predictably instead of expanding into a full platform matrix.

| Tier | Platforms | Detect | Coverage |
|------|-----------|--------|----------|
| **Primary** | Android, iOS | assumed unless stated otherwise | Full. Every pattern applies and is expected to be correct. |
| **Secondary** | Windows, macOS, Linux | `windows/` `macos/` `linux/` present | Covered as caveats. |
| **Tertiary** | Web | `web/` present | Covered as constraints. |

**Desktop caveats (secondary).** Window size and minimum size, mouse and keyboard input, focus traversal order, right-click and context menus, native file dialogs, `dart:io` available, packaging (MSIX / DMG / AppImage), and no app-store sandbox assumptions.

**Web constraints (tertiary).** No `dart:io`, no `MethodChannel` platform channels (JS interop instead), URL strategy and deep links, deferred loading and initial bundle size, renderer differences in text metrics and paint, PWA and service-worker caching, and **no secure-storage guarantee** - browser storage is not an OS keystore.

When the platform targets cannot be determined, assume Mobile only and say so once rather than silently reviewing against all three tiers.

### Material vs Cupertino and adaptive widgets

*Tiers: All.*

```dart
// Bad - dart:io throws on web, and ignores the ThemeData.platform override tests set
if (Platform.isIOS) return CupertinoSwitch(value: v, onChanged: onChanged);
return Switch(value: v, onChanged: onChanged);

// Good - one constructor, correct on every tier
Switch.adaptive(value: v, onChanged: onChanged);
```

The `.adaptive` family (`Switch.adaptive`, `Slider.adaptive`, `CircularProgressIndicator.adaptive`, `AlertDialog.adaptive`, `showAdaptiveDialog`) renders Cupertino on iOS and macOS and Material elsewhere, with no branch to maintain.

When you must branch, read the theme:

```dart
// Good - respects ThemeData.platform, so previews and widget tests can force either
final isApple = switch (Theme.of(context).platform) {
  TargetPlatform.iOS || TargetPlatform.macOS => true,
  _ => false,
};
```

`defaultTargetPlatform` is the fallback for code with no `BuildContext`; it does not see the theme override. Branch on *interaction* (a swipe-to-dismiss gesture iOS users expect, a menu bar desktop users expect), not on paint that `.adaptive` already handles.

### Breakpoints and where the number comes from

*Tiers: All.*

Material 3 window size classes give a default set. Name them once, in the app's own constants class (below it is `WindowSize`; `flutter_adaptive_scaffold` ships an unrelated `Breakpoints` class), and never inline the number.

| Class | Width (dp) | Typical layout |
|-------|-----------|----------------|
| Compact | < 600 | one pane, bottom `NavigationBar` |
| Medium | 600 - 839 | one pane wider, `NavigationRail` collapsed |
| Expanded | 840 - 1199 | two panes, `NavigationRail` |
| Large / Extra-large | >= 1200 | two or three panes, standard `NavigationDrawer` |

```dart
// Bad - reads the whole screen; wrong in split-screen, in a dialog, in a resized desktop window
if (MediaQuery.sizeOf(context).width > 840) return TwoPane();

// Good - the Expanded class boundary (inclusive, per Material 3), named, read from what this widget was actually granted
abstract final class WindowSize { static const medium = 600.0; static const expanded = 840.0; }

LayoutBuilder(
  builder: (context, c) =>
      c.maxWidth >= WindowSize.expanded ? const TwoPane() : const OnePane(),
);
```

`MediaQuery.sizeOf` describes the window, so it is right for system-level decisions and wrong for widget-level ones. A widget that reads the screen renders correctly full-screen and incorrectly inside a split view, a side sheet, or a desktop window at half width.

Use the scoped accessors (`MediaQuery.sizeOf`, `paddingOf`, `viewInsetsOf`, `orientationOf`) rather than `MediaQuery.of(context)`: the latter subscribes the widget to *every* media-query change, so a keyboard opening rebuilds widgets that only cared about width.

### Safe areas, cutouts, and the keyboard

*Tiers: Mobile primary; desktop and web have padding of zero but the code is identical.*

```dart
// Bad - invented constant; wrong on every device with a cutout or a gesture bar
Padding(padding: const EdgeInsets.only(top: 24), child: content)

// Good
SafeArea(child: content)
```

`SafeArea` consumes the intrusions; `MediaQuery.paddingOf(context)` reports them when you need the number (for example to pad a scroll view's content while letting it paint under the status bar). Flutter draws behind the system bars by default, and Android 15 enforces edge-to-edge for apps targeting SDK 35, so reading the padding is never optional.

```dart
// Bad - a field pinned to the bottom of a full-screen Stack; the keyboard covers it
Stack(children: [content, Positioned(left: 0, right: 0, bottom: 0, child: TextField(controller: c))])

// Good - the sheet lifts by exactly the keyboard height
Padding(
  padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
  child: TextField(controller: c),
)
```

`viewInsets` is the keyboard (and other system overlays that obscure content); `padding` is the notch, status bar, and gesture area. `Scaffold` handles the common case via `resizeToAvoidBottomInset`, so a plain `Scaffold(body: Column(...))` with a field is not this defect; it breaks in a custom bottom sheet, a full-screen `Stack`, or a `Scaffold` with `resizeToAvoidBottomInset: false`.

### Input modality

*Tiers: touch on all; hover, cursor, and right-click on Desktop and Web; keyboard on Desktop and Web, and on Mobile whenever a hardware keyboard is attached.*

```dart
// Bad - the only way to delete is a long-press; a mouse user cannot discover or perform it
GestureDetector(onLongPress: _delete, child: tile)

// Good - long-press, secondary click, and a focusable overflow button reach one intent
InkWell(
  onTap: _open,
  onLongPress: _showActions,
  onSecondaryTap: _showActions,
  child: Row(children: [
    Expanded(child: tile),
    IconButton(icon: const Icon(Icons.more_vert), tooltip: l10n.moreActions, onPressed: _showActions),
  ]),
)
```

Treat modalities as additive paths to the same intent. A hover-only affordance is invisible on touch; a long-press-only affordance is undiscoverable with a mouse; a gesture-only affordance is unreachable by keyboard. `InkWell` gives focus, Enter/Space activation, and a click cursor; the overflow button gives keyboard users the menu.

Keyboard shortcuts are declared, not hand-detected in a raw key listener:

```dart
Shortcuts(
  shortcuts: {
    const SingleActivator(LogicalKeyboardKey.keyS, control: true): const SaveIntent(), // Windows, Linux, web
    const SingleActivator(LogicalKeyboardKey.keyS, meta: true): const SaveIntent(),    // macOS
  },
  child: Actions(
    actions: {SaveIntent: CallbackAction<SaveIntent>(onInvoke: (_) => _save())},
    child: child,
  ),
)
```

`MenuAnchor` supplies desktop-style context and dropdown menus. Focus traversal order is shared with accessibility - see `flutter-accessibility`.

### Orientation, foldables, and large screens

*Tiers: Mobile primary; desktop resizing exercises the same code paths.*

```dart
// Bad - loses scroll position, controller state, and any in-progress input on rotate
if (MediaQuery.orientationOf(context) == Orientation.portrait) {
  return PortraitScreen(items: items);
}
return LandscapeScreen(items: items);

// Good - one tree, different arrangement; element identity and state survive the change
return Flex(
  direction: isWide ? Axis.horizontal : Axis.vertical,
  children: const [Pane(), Detail()],
);
```

Rotation and resize rebuild with new constraints; two disjoint trees mean the framework tears down one subtree and builds the other, discarding its state. Reuse the same widgets and change their arrangement.

Locking orientation with `SystemChrome.setPreferredOrientations` is a product decision, not a fix for a layout that overflows in landscape; it does nothing on desktop, on web it applies only where the browser supports orientation lock, and Android 16 (apps targeting API 36) and iPad multitasking ignore it on large screens.

Foldables and hinged devices report `MediaQuery.displayFeaturesOf(context)`. Content must not be placed across a hinge or fold; treat each feature as an obstruction that splits the available area. A hinge splits the panes at the hinge even when width alone would choose one pane. Width alone is not enough to detect this, because an unfolded device is simply wide.

### Desktop windowing

*Tiers: Desktop only.*

Flutter has no stable Dart API for window sizing. The initial and minimum window size is set in the native runner sources (`windows/runner/`, `macos/Runner/MainFlutterWindow.swift`, `linux/runner/`), or through a window-management package. Two consequences:

- A desktop target with no minimum size ships a window the user can drag to 200px wide. Every layout must either survive that or the runner must set a floor.
- Layout that assumes a phone aspect ratio produces enormous line lengths at 2560px. Constrain reading-width content with `ConstrainedBox(constraints: const BoxConstraints(maxWidth: 720))` rather than letting text stretch the full window.

Desktop also expects: real focus traversal, context menus on right-click, native file pickers rather than an in-app browser, and no assumption that the process is sandboxed the way an app-store mobile build is.

### Web constraints

*Tiers: Web only.*

```dart
// Bad - compiles for mobile, throws at runtime on web
final dir = await getApplicationDocumentsDirectory(); // dart:io path

// Good - the branch is explicit and the web path is defined, not accidental
if (kIsWeb) return _webCache.read(key);
return _fileCache.read(key);
```

| Constraint | Consequence |
|------------|-------------|
| No `dart:io` | file, socket, and `Platform.isX` code needs a web branch or a conditional import |
| No `MethodChannel` | native integrations need JS interop; a plugin without web support fails at runtime, not compile time |
| Initial bundle size | large screens or heavy dependencies belong behind `deferred as` imports and `loadLibrary()` |
| Renderer differences | text metrics and paint differ from mobile; verify layout on the web build, not on a mobile emulator |
| URL strategy and deep links | see `flutter-navigation-patterns` |
| PWA and service worker | a cached shell can serve a stale build after deploy |
| **No secure storage** | tokens in browser storage are readable; treat web as unable to hold a long-lived secret |

## Output Format

When invoked from an implementation workflow, emit the adaptive plan:

```
Tiers: {comma-separated from Mobile, Desktop, Web} (source: {platform directories | project CLAUDE.md | assumed})
Design language: {Material | Cupertino}
Breakpoints: {file:line of the named constants | <path> (new) | none defined}
Window floor (only when Desktop in Tiers): {size set in runner | window-management package | none - set one}

| Surface | Tiers | Layout switch | Adaptive widgets | Insets | Input paths |
|---------|-------|---------------|------------------|--------|-------------|
| OrderList | All | LayoutBuilder @ expanded -> two pane | NavigationBar / NavigationRail | SafeArea | tap, keyboard |
| FilterSheet | Mobile | compact -> bottom sheet, expanded -> dialog | showAdaptiveDialog | viewInsets bottom | tap, keyboard |
```

The `Tiers` cell is `All` or a comma-separated subset of the header's tiers; a tier may name its present platforms, as in `Desktop (macOS)`. A row may name a form factor (tablet, foldable) inside a tier.

Implement mode ends with `Pre-existing: <file:line> - <defect>` for each defect in code the plan edits or depends on but does not fix, or `Pre-existing: none`. Code not yet written is cited as `<path> (new)`. A file the plan depends on that is absent or could not be read is listed as `Not read: <path> - <reason>`. A defect the change cannot ship on top of is fixed in the plan, not listed as `Pre-existing`.

When invoked from a review workflow or directly to diagnose a form-factor bug, emit one block per finding:

```
### [Blocker | High | Medium | Low] file:line

- Area: Adaptive
- Check: {Platform-Tier | Adaptive-Widget | Breakpoint | Safe-Area | Input-Modality | Orientation | Desktop-Window | Web-Constraint}
- Tier: {Mobile | Desktop | Web | All}, comma-separated when more than one applies
- Code: {one-line citation}
- Impact: {what the user cannot see, reach, or do}
- Fix: {concrete edit}
```

Close with one coverage line: `Checks clean: {comma-separated Check values with zero findings | none}`.

**Severity calibration.** `Blocker` = content unreachable or an action impossible on a declared target tier (clipped behind the keyboard, off-screen past a cutout, a runtime throw on web from `dart:io` or an unguarded platform channel). `High` = a declared tier is visibly broken but usable (including screen-size branching that renders the wrong layout in split-screen, a fold, or a resized window), or in-progress user state is discarded by a rotation, fold, or resize, or a long-lived secret is held in browser storage on a declared web tier. `Medium` = correct output in every declared layout produced by fragile means (screen-size branching that happens to hold, inline breakpoint), or a hand-picked control from the other design language in an otherwise consistent screen (`.adaptive` output is not one). `Low` = naming and organization, or a `MediaQuery.of` read where a scoped accessor exists (extra rebuilds only). When a finding matches two bands, the higher band wins.

When one line fits two Checks, file it under the Check naming the failure on the worst affected tier: a `Platform.isX` read that throws on web is `Web-Constraint`. A Check whose violation was filed under another Check is not listed as clean.

**Label mapping for the umbrella review:** `Blocker`, `High` -> `[Must]`; `Medium`, `Low` -> `[Recommend]`.

Findings are raised only for tiers the project actually targets. Review and diagnose output opens with the same `Tiers:` line as implement mode; when the tier set is unknown it reads `Tiers: Mobile (source: assumed)` and findings stay on mobile.

Blocks are one per defect, ordered by severity, then file and line, then enum order. Each site of a repeated rule is its own defect; a single defect that needs edits in several places anchors on the line to edit and names the others as `also <file:line>` on its citation line.

A finding that depends on code outside the files read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to the line describing its effect. A check whose subject does not appear in the files read is clean; a check the files read cannot exercise is listed once as `Not checked: <names> - <reason>` and gets no clean or zero-finding line. A file in scope that could not be read is named on that line.

In diagnose mode, blocks for defects that cause the reported symptoms come first, in the order the symptoms were reported; every other defect seen in the files read follows at its own severity.

## Avoid

- `Platform.isAndroid` / `Platform.isIOS` from `dart:io` for UI branching - throws on web and ignores `ThemeData.platform`
- `MediaQuery.sizeOf(context).width` as the input to a widget-level layout decision - use `LayoutBuilder`
- `MediaQuery.of(context)` where a scoped accessor exists - it subscribes to every media-query change
- Inline breakpoint numbers scattered across widgets instead of one named set
- Two separate widget trees for portrait and landscape - state does not survive the swap
- Hardcoded status-bar, notch, or keyboard heights
- A Cupertino control dropped into an otherwise Material screen for the sake of looking native
- Hover-only or long-press-only affordances as the sole path to an action
- Locking orientation to hide a landscape overflow
- Width alone as a foldable check - read `displayFeatures`
- Shipping a desktop target with no minimum window size and no layout floor
- Assuming secure storage, `dart:io`, or platform channels on web
- Reviewing or building for a tier the project does not target
