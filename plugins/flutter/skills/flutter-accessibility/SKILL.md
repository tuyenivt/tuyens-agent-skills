---
name: flutter-accessibility
description: "Review Flutter accessibility: Semantics labels, TalkBack/VoiceOver, colour contrast, touch-target size, text scaling, focus order, announcements."
metadata:
  category: mobile
  tags: [flutter, dart, accessibility, a11y, semantics, screen-reader, contrast, touch-target, text-scaling, focus]
user-invocable: false
---

# Flutter Accessibility

> Platform tiers are defined in `flutter-adaptive-responsive`; this skill states the tier each pattern applies to. Localized strings are `flutter-i18n`'s - a semantic label is user-facing text and follows the same no-hardcoding rule.

## When to Use

- Building or reviewing any interactive surface: buttons, icon buttons, form fields, list tiles, custom gesture targets, dialogs
- Adding a custom-painted or gesture-based control that has no built-in semantics
- Auditing an existing screen against screen reader, contrast, target size, or text-scale requirements
- A report that a control is unlabelled, unreachable by keyboard, invisible to TalkBack or VoiceOver, or overflows when the user raises the system font size

## Rules

- Every interactive element exposes a label that names its **action or destination**, not its icon. If a screen reader cannot say what the control does, it is broken
- Labels are localized strings, never literals in the widget tree. This skill files a literal only when it is a label, tooltip, hint, or `semanticLabel`; other literal text is `flutter-i18n`'s
- Decorative images and icons are hidden from the semantics tree; meaningful ones carry a text alternative. An image that carries information the surrounding text does not repeat is meaningful
- Minimum interactive target is 48x48 dp on Android and 44x44 pt on iOS. Small visuals are padded up to the target, not shrunk to fit
- Text contrast meets WCAG AA: 4.5:1 for body text, 3:1 for large text (>= 18pt, or >= 14pt bold - about 24 and 18.7 logical pixels) and for UI component boundaries and meaningful graphics. `textContrastGuideline` treats 18 and 14-bold logical pixels as large, so text between those sizes needs a manual 4.5:1 check
- No widget assigns a fixed height, width, or aspect ratio to a box whose only content is text. Text size is user-controlled and grows without bound
- Text scaling is supported to at least 200%. Clamping is a last resort, applied at the narrowest possible scope, never app-wide
- Focus order follows visual reading order, and every action reachable by pointer is reachable by keyboard on any tier where a keyboard exists
- A state change is announced when the user did not directly cause it, when its result is off-screen, or when it is a completion, removal, or error that leaves no persistent node. A silent success is a failure for a screen reader user
- Colour, or any other visual-only cue (opacity, position), is never the only carrier of meaning: pair it with text, an icon, or a shape

## Patterns

### Labelling interactive elements

*Tiers: All.*

```dart
// Bad - TalkBack announces "button"; VoiceOver announces nothing useful
IconButton(icon: const Icon(Icons.delete), onPressed: _delete)

// Good - tooltip feeds the semantics tree and gives sighted users a hover hint too
IconButton(
  icon: const Icon(Icons.delete),
  tooltip: l10n.deleteOrder,
  onPressed: _delete,
)
```

Icon-only controls are the single most common defect: the icon has no text, so the semantics node has no label. `tooltip:` on `IconButton` is the shortest correct fix. For controls with no tooltip parameter, wrap:

```dart
Semantics(button: true, label: l10n.playTrack, child: _customPlayControl())
```

A single-choice group (payment methods, a segmented filter) wraps each option in `Semantics(inMutuallyExclusiveGroup: true, checked: isSelected, label: ...)` - radio semantics, as `Radio` and `SegmentedButton` use; the checked state announces the change, so no extra announcement is needed. A `TextField` labelled only by `hintText` loses its accessible name once text is entered; give it `labelText` or a `Semantics` label.

Label the action, not the glyph. `"delete order"` is a label; `"trash can icon"` is not. Do not include the role in the label - the framework already announces "button", so `label: 'Delete button'` is read as "delete button, button".

A bare gesture handler exposes a tap action with no label and no button role, so the screen reader announces nothing useful:

```dart
// Bad - GestureDetector exposes a tap action but no label and no role
GestureDetector(onTap: _openProfile, child: _avatar())

// Good - either use a real button widget, or declare the semantics
Semantics(button: true, label: l10n.openProfile, child: GestureDetector(onTap: _openProfile, child: _avatar()))
```

Prefer the real widget (`TextButton`, `IconButton`, `ListTile`) over declaring semantics by hand; those controls already carry role, state, and focus behaviour. `InkWell` supplies tap and focus but no button role, so pair it with `Semantics(button: true, label: ...)`.

### What the screen reader actually says

*Tiers: Mobile primary (TalkBack, VoiceOver); desktop uses the OS reader; web builds a separate DOM semantics tree and must be verified on the real web build.*

```dart
// Bad - each Text is its own stop (the unlabelled Icon adds none); two swipes to hear one row
Row(children: [Icon(Icons.check), Text(order.id), Text(order.total)])

// Good - one node, one coherent announcement
MergeSemantics(
  child: Row(children: [const Icon(Icons.check), Text(order.id), Text(order.total)]),
)
```

The semantics tree, not the widget tree, is what gets read. Two `Text` widgets in a row are two stops in swipe navigation unless merged. Conversely, one node holding a whole screen is unnavigable.

| Widget | Effect |
|--------|--------|
| `Semantics` | creates or annotates a node (label, hint, value, role flags) |
| `MergeSemantics` | collapses descendants into one node so the row is read as one item |
| `ExcludeSemantics` | drops the subtree from the tree entirely (decoration) |
| `BlockSemantics` | hides everything painted beneath, for a modal overlay |

Use `hint:` for what happens on activation when the label alone does not imply it (`label: order.id`, `hint: l10n.opensOrderDetail`). Use `value:` for a control's current setting, which is what makes a slider or toggle intelligible.

### Images and icons

*Tiers: All.*

```dart
// Bad - an unlabelled Image still contributes an image role, so the screen reader announces "image" with nothing to say
Image.asset('assets/divider.png')

// Good
Image.asset('assets/divider.png', excludeFromSemantics: true)
```

```dart
// Bad - the chart is the only place the trend appears, and it is silent
Image.asset('assets/revenue_chart.png')

// Good
Image.asset('assets/revenue_chart.png', semanticLabel: l10n.revenueUpPercent(12))
```

`Image` and `Icon` both take `semanticLabel`. `Icon` adds no semantics node unless given one, so an unlabelled decorative icon needs no wrapper; `Image` contributes an image role unless `excludeFromSemantics: true`, as its own stop or merged into its parent's, depending on the ancestors. The test is whether removing the image loses information: a divider or a chevron next to a labelled row loses nothing (exclude it); a chart, a status badge, or an avatar that identifies a person carries information (label it).

### Touch targets

*Tiers: Mobile primary; pointer tiers benefit but are less constrained.*

```dart
// Bad - a 20x20 tap target; usable only with a precise touch
GestureDetector(onTap: _close, child: const Icon(Icons.close, size: 20))

// Good - the icon stays 20dp, the target grows to the minimum, and the control is labelled
Semantics(
  button: true,
  label: l10n.close,
  child: InkWell(
    onTap: _close,
    child: const SizedBox(
      width: kMinInteractiveDimension,   // 48.0
      height: kMinInteractiveDimension,
      child: Icon(Icons.close, size: 20),
    ),
  ),
)
```

Visual size and target size are independent. `IconButton` already sizes to the minimum; the defect appears when a raw `GestureDetector`, a small `InkWell`, or `MaterialTapTargetSize.shrinkWrap` bypasses it. Adjacent targets also need separation - two 48dp targets touching each other still produce mistaps at the boundary.

Assert it rather than eyeballing it:

```dart
testWidgets('meets tap target guidelines', (tester) async {
  await tester.pumpWidget(const App());
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
});
```

### Text scaling

*Tiers: All.*

```dart
// Bad - at 200% font scale the text is clipped inside a box that cannot grow
SizedBox(height: 48, child: Text(l10n.orderTotal))

// Good - the box follows the text
ConstrainedBox(
  constraints: const BoxConstraints(minHeight: 48),
  child: Text(l10n.orderTotal),
)
```

A fixed height is a promise about text size that the user is entitled to break. The same defect appears as a fixed-height `Container`, a `Row` of chips with a hardcoded height, a bottom bar sized in pixels, or an `AspectRatio` wrapping text. Use `minHeight`, intrinsic sizing, or let the content scroll.

Read the current scale through `MediaQuery.textScalerOf(context)` and scale non-text elements that must track it (an icon beside a label, a badge around a number) with `TextScaler.scale`. Do not multiply font sizes yourself - Flutter already applies the scale to `TextStyle.fontSize`.

Clamping is occasionally unavoidable for a control whose geometry genuinely cannot flex:

```dart
// Acceptable only at the narrowest scope, never around MaterialApp
MediaQuery.withClampedTextScaling(maxScaleFactor: 1.5, child: _fixedGeometryChip())
```

Clamping the whole app silently discards the user's system setting and is a defect, not a policy.

### Contrast

*Tiers: All.*

```dart
// Bad - grey on white measures roughly 2.7:1
Text(l10n.caption, style: const TextStyle(color: Color(0xFF9E9E9E)))

// Good - the theme's text colour is contrast-checked once, centrally
Text(l10n.caption, style: Theme.of(context).textTheme.bodySmall)
```

Contrast is a property of the colour pair, so it belongs in the theme where the pair is defined, not at each call site. Per-widget colour literals are how a design system silently loses contrast.

Check both `Brightness.light` and `Brightness.dark`, and check placeholder and hint text - that is where palettes usually fall below 4.5:1. Disabled controls are exempt from WCAG contrast. Non-text elements are not exempt: an icon that conveys status, a focus ring, and an input border need 3:1 against their background.

```dart
await expectLater(tester, meetsGuideline(textContrastGuideline));
await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
```

`meetsGuideline` catches the systematic cases in CI; a gradient or image background still needs a manual check because the effective background varies per pixel.

### Focus order and keyboard traversal

*Tiers: Desktop and Web required; Mobile whenever a hardware keyboard or switch-access device is attached.*

```dart
// Bad - submit is pinned top-right, so geometric reading order visits it before the fields
Stack(children: [
  Positioned(top: 0, right: 0, child: _submitButton()),
  Positioned(top: 48, left: 0, right: 0, child: _titleField()),
  Positioned(top: 120, left: 0, right: 0, child: _bodyField()),
])

// Good - keep the layout, state the traversal order explicitly
FocusTraversalGroup(
  policy: OrderedTraversalPolicy(),
  child: Stack(children: [
    Positioned(top: 0, right: 0,
        child: FocusTraversalOrder(order: const NumericFocusOrder(3), child: _submitButton())),
    Positioned(top: 48, left: 0, right: 0,
        child: FocusTraversalOrder(order: const NumericFocusOrder(1), child: _titleField())),
    Positioned(top: 120, left: 0, right: 0,
        child: FocusTraversalOrder(order: const NumericFocusOrder(2), child: _bodyField())),
  ]),
)
```

Default traversal (`ReadingOrderTraversalPolicy`) follows on-screen geometry, which diverges from the intended order when a control is positioned out of reading sequence or a layout is reordered. `FocusTraversalGroup` orders focus; it does not contain it. Modal routes (dialogs, bottom sheets) already scope focus with their own `FocusScope`; a custom overlay built from a `Stack` or `Overlay` needs its own `FocusScope` to keep focus off the page behind it.

Verify by tabbing the screen end to end: focus must be visible at every stop, must never land on a non-interactive element, and must never leave a modal.

### Announcing dynamic state

*Tiers: All.*

```dart
// Bad - the item is removed and the screen reader says nothing
setState(() => _items.remove(item));

// Good
setState(() => _items.remove(item));
SemanticsService.announce(l10n.itemRemoved(item.name), Directionality.of(context)); // or SemanticsService.sendAnnouncement(View.of(context), ...) on SDKs that deprecate announce
```

For a region whose content updates in place (a validation message, a live count, a status line), mark it instead of announcing manually:

```dart
Semantics(liveRegion: true, child: Text(_errorText))
```

`liveRegion` re-announces the node when its content changes; a one-off announcement is for events with no persistent node, or whose node unmounts because navigation follows. Newer Flutter SDKs deprecate `announce` in favour of the view-scoped `SemanticsService.sendAnnouncement`, and Android 16 deprecates the underlying announcement event, so prefer a `liveRegion` node where one exists and otherwise use the announcement API the project's SDK provides. Announce meaningful transitions only - loading started and finished, save succeeded, validation failed - not every rebuild or progress tick; a progress indicator carries `semanticsLabel`. When the focused control becomes disabled mid-flow, move focus to the status it reports, never to the page root. A snackbar carrying an action stays until dismissed, or at least 10 s, when `MediaQuery.accessibleNavigationOf(context)` is true; a sheet's first focus lands on its title or first field, never on the page behind.

### Gesture-only actions need a semantic alternative

*Tiers: All.*

A swipe, drag, or long-press is invisible to a screen-reader user - swipe gestures are captured for navigation. Every gesture-only action gets an equivalent on the node:

```dart
// Swipe-to-delete row: expose the action to assistive tech
Semantics(
  customSemanticsActions: {CustomSemanticsAction(label: l10n.deleteOrder): _delete},
  child: Dismissible(...),
)
```

Widgets like `Dismissible` announce nothing about the hidden action by themselves. The same applies to a custom drag-to-reorder (expose move up/down actions - `ReorderableListView` already does) and long-press menus (expose the menu as an action or a visible affordance).

## Output Format

When invoked from an implementation workflow, emit the accessibility plan:

```
| Element | Semantics | Target | Contrast pair | Focus order | Announces |
|---------|-----------|--------|---------------|-------------|-----------|
| Delete icon button | tooltip: l10n.deleteOrder | 48dp (IconButton) | onSurface / surface | page 4 | itemRemoved |
| Order row | MergeSemantics, hint: opensDetail | 56dp | onSurface / surface | page 2 | - |
| Status dot | ExcludeSemantics (label on row) | n/a | statusColor / surface, 3:1 | - | - |
```

Record text-scaling decisions (minHeight vs fixed, clamp scope) and gesture-alternative actions in the Semantics column of the affected row, not as rows of their own. One row per element a user can perceive or operate; a container or a purely visual background gets no row. Focus order numbers each scope (page, sheet, snackbar) separately as `<scope> <n>`; Target is `n/a` for an element with no tap target; Announces holds the l10n key announced, `liveRegion`, or `-` when nothing is announced. A tier-specific difference (web read-only) goes in the Semantics cell as `<tier>: ...`. On a keyboard tier a `customSemanticsActions` entry is reachable through the screen reader's actions menu, not the keyboard: pair it with a visible button or a `Shortcuts` binding. A control whose label or announcement changes by state (idle, loading, done) keeps one row and lists each state in the Semantics and Announces cells. A contrast pair names both colours by theme role, for text and non-text boundaries alike; a selection indicator is a UI component boundary (3:1). A row with no tab stop writes `-` for Focus order.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one block per finding:

```
### [{Blocker | High | Medium | Low}] {file:line}

- Area: Accessibility
- Check: {Semantic-Label | Screen-Reader-Output | Image-Alternative | Touch-Target | Text-Scaling | Contrast | Colour-Only | Focus-Order | State-Announcement | Gesture-Alternative}
- Tier: {Mobile | Desktop | Web | All}
- Code: {one-line citation}
- Impact: {what a user relying on the affected assistive path cannot do}
- Fix: {concrete edit}
```

Tier is comma-separated when more than one applies.

**Severity calibration.** A required flow is one the app's main task cannot complete without (sign-in, checkout, primary navigation); when the product does not state it, the list -> detail -> primary action path is required. `Blocker` = an action is impossible via an assistive path (unlabelled control on a required flow, content clipped at the supported text scale, focus trap, keyboard-unreachable action on a keyboard tier). `High` = the action is possible but the assistive experience is wrong or lossy: a wrong, misleading, or missing announcement (including a silent completion, error, or removal; a silent loading start is Medium), an unlabelled control or a gesture-only action off a required flow, a meaningful image with no text alternative, a hardcoded label in an app that ships more than one locale, contrast below AA (4.5:1 body, 3:1 large text and non-text), colour as the only carrier of meaning, an app-wide text-scale clamp, a target below the minimum on a required flow, focus order diverging from reading order across interactive elements on a keyboard tier, an invisible focus indicator, or focus escaping a custom overlay with no `FocusScope`. `Medium` = extra friction (unmerged rows, decorative nodes in traversal, a redundant cue placed away from the coloured element, a target below the minimum elsewhere, a screen-scoped text clamp or manual `fontSize` multiplication, a fixed-height text box that still fits at the supported scale, over-announcement such as a `liveRegion` on a node that changes every frame). `Low` = wording of a label or hint, or a hardcoded label in a single-locale app. When a finding matches two bands, the higher band wins.

**Label mapping for the umbrella review:** `Blocker`, `High` -> `[Must]`; `Medium`, `Low` -> `[Recommend]`; a finding whose Impact reads `unverifiable from source` -> `[Recommend]` at any severity.

A bare `GestureDetector` acting as a button is one `Semantic-Label` block; its size is a separate `Touch-Target` block only when below the minimum. A widget on a `Platform.isX` branch takes that platform's tier. `ListTile` does not merge its slots (only `CheckboxListTile`, `SwitchListTile`, and `RadioListTile` wrap themselves in `MergeSemantics`); wrap it when it must read as one item, and verify with `tester.getSemantics`. A keyboard-unreachable control on a keyboard tier is `Focus-Order`. A finding whose inputs are not in source at all (runtime data, a server-driven theme) takes the unverifiable form; one whose deciding file was not read takes `(unconfirmed: ...)`. The visible text of a button or body copy is `flutter-i18n`'s (`Also seen`); this skill files a literal only as a label, tooltip, hint, or `semanticLabel`.

A check that cannot be verified from source is reported, not dropped or guessed: emit the block at the severity it would have if confirmed, with `Impact: unverifiable from source - <verification needed>`. Any check whose inputs are not in the source takes this form; the recurring cases are contrast over image, gradient, or runtime-derived backgrounds (manual check), screen-reader output on the Web tier (observable only on the real web build), whether a framework widget already merges its children (check with `tester.getSemantics` in a widget test), and focus order that depends on runtime layout.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Check` values, or the path of a file that could not be read) when any check could not be exercised, then the `Checks clean:` line. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean and is listed on `Checks clean:`; a check on the `Not checked` line is not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Impact:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape, a request to review or audit takes the review shape, and a supplied symptom or bug report takes diagnose mode.

The closing lines - `Also seen` and `Not checked` only when they have content, `Checks clean:` in review mode:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

Checks clean: {comma-separated Check values with zero findings | none}
```

Diagnose mode opens with one line per reported symptom, `Symptom <n>: <the report's title or first sentence>`, a title that lists two symptoms is two lines, naming on each any premise the files read contradict (a flag the report says is on, a version it names) - the diagnosis then proceeds on what the code shows - and stating when the files read cannot cause the symptom. Blocks for the causes of the reported symptoms come first, grouped by symptom in reported order and within a group by severity, each such block's `Impact:` line opening with `Symptom <n>:`; a cause shared by two symptoms is one block opening `Symptom 1, 2:`, placed with the lower-numbered symptom; every other defect seen in the files read follows, ordered as in review mode. The `Checks clean:` line is omitted in diagnose mode; `Also seen` and `Not checked` lines are kept.

## Avoid

- `IconButton` with no `tooltip`, and any `GestureDetector` acting as a button with no `Semantics`
- Labels that name the icon, restate the role ("Delete button"), or are hardcoded English literals
- Decorative images left in the semantics tree; meaningful images and icons left without `semanticLabel`
- Tap targets under 48x48 dp / 44x44 pt, and `MaterialTapTargetSize.shrinkWrap` used to tighten a layout
- Fixed `height`, `width`, or `AspectRatio` on a box containing text
- `MediaQuery.withClampedTextScaling` above a screen, and manual multiplication of `fontSize` by the text scale
- Colour literals at widget call sites instead of contrast-checked theme roles
- Contrast checked in light mode only, or with placeholder and hint text skipped
- Colour as the sole indicator of state, error, or selection
- Focus order left to the default policy where controls are positioned out of reading sequence; a custom overlay with no `FocusScope`
- Silent success and silent removal - announce the outcome
- `liveRegion: true` on a node that changes every frame
- Treating a `meetsGuideline` pass as full coverage - it does not test screen reader phrasing or focus order
