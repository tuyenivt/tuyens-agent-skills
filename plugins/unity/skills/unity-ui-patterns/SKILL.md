---
name: unity-ui-patterns
description: Build Unity 2D game UI with UI Toolkit - UXML/USS structure, query caching, PanelSettings scaling, screen stack, safe area, aspect-ratio adaptivity.
metadata:
  category: mobile
  tags: [unity, ui-toolkit, uxml, uss, visualelement, panelsettings, safe-area, adaptivity]
user-invocable: false
---

# Unity UI Patterns

> This skill owns **UI Toolkit structure, layout, and navigation**. Repaint and layout cost budgets belong to `unity-performance`; sprites, atlases, and sorting belong to `unity-2d-rendering`; contrast, touch-target minimums, and screen readers belong to `unity-accessibility`; user-facing strings belong to `unity-i18n`.

## When to Use

- Building or reviewing any runtime UI screen, HUD, popup, or menu
- Deciding UXML/USS structure and where styling lives
- UI breaks on a different aspect ratio, notch, or orientation
- Navigation, back handling, or modal stacking is ad hoc

## Rules

- **UI Toolkit only.** uGUI (`Canvas`, `RectTransform`, `UnityEngine.UI`) is out of scope for this plugin. A project on uGUI is reported as out of scope, not reviewed against these rules and not rewritten
- Structure in UXML, styling in USS, behaviour in C#. Inline styles set from C# for anything a class could express are unreviewable and untraceable
- **Cache every `Q`/`Query` result at bind time.** A query is a tree walk; running one per frame or per event is the single most common UI Toolkit cost trap
- One `UIDocument` per logical screen or overlay, with a shared `PanelSettings` asset per resolution strategy. Do not scatter panel settings per document
- Layout adapts by rule, not by pixel constants: flexbox growth, percentage widths, and `min-width`/`max-width` breakpoints. Hardcoded pixel positions break on the next device
- Safe area is applied to a single root container per panel, sourced from `Screen.safeArea`, and re-applied on resolution or orientation change
- Never assume 16:9. Portrait phone, tall phone, tablet, and desktop windows must all be handled by the same USS, verified at the extremes
- UI Toolkit is a built-in engine module, so the editor version pins its API. USS transitions and runtime data binding are settled at the 6000.3 floor; cite the editor version only for an API newer than 6000.3 or marked experimental

## Patterns

### Query caching

```csharp
// Bad - a tree walk every frame
void Update() { root.Q<Label>("score").text = score.ToString(); }

// Good - resolved once, updated on change
Label _score;
void OnEnable() { _score = GetComponent<UIDocument>().rootVisualElement.Q<Label>("score"); }
public void SetScore(int v) => _score.text = v.ToString();
```

Resolve in `OnEnable` and not `Awake`: `rootVisualElement` is not reliably populated until the document is enabled. Re-resolve after any `visualTreeAsset` swap, since the old references point at a discarded tree.

For lists, `ListView` with `makeItem`/`bindItem` recycles elements. Building one element per row of a 500-question bank is both an allocation spike and a layout stall. Cache each row's own `Q` results once in `makeItem` (stash them on `userData`) rather than re-querying in `bindItem`, which runs on every scroll recycle.

Set `virtualizationMethod` deliberately: `FixedHeight` is cheaper and correct only when every row is genuinely the same height; a row holding localized text is not, so variable content needs `DynamicHeight`. Guessing `FixedHeight` clips the first long translation.

### Text that grows

Labels change size with locale, and with the player's system font scale. A box authored around one English string clips the first German or Japanese one that arrives.

```css
/* Bad - fixed box, so a longer translation clips instead of growing */
.stat-label { width: 220px; height: 44px; }

/* Good - content drives the box, bounded rather than fixed */
.stat-label { max-width: 320px; min-width: 0; white-space: normal; }
```

Three rules carry most of it: never set a fixed `width`/`height` on a text-bearing element, use `min-width`/`max-width` instead; put `min-width: 0` on flex text children so they can actually shrink and wrap rather than overflowing their row; and set `flex-shrink: 0` on the value side of a label/value pair so a long label never squeezes the number out. Raise the whole type ramp through one class on a root when the system font scale is large, so the screen scales coherently instead of one label outgrowing its row. Read the system value from `UnityEngine.Accessibility.AccessibilitySettings.fontScale` (Android and iOS; subscribe to `fontScaleChanged`), falling back to 1 or an in-game text-size setting elsewhere. Which strings need this, and their font assets and fallback chains, are `unity-i18n`.

### UXML structure and USS styling

```xml
<!-- Bad - identity, layout, and look all inline -->
<ui:Button name="play" style="width: 320px; height: 88px; background-color: #2A8;" />

<!-- Good - name for lookup, class for style -->
<ui:Button name="play" class="btn btn--primary" text="Play" />
```

Name attributes are for `Q` lookup and tests. Classes carry style. A USS class edited once restyles every button; an inline style must be hunted per file.

Keep the tree shallow. Each nesting level adds layout nodes and measure work, and a deeply wrapped hierarchy makes flexbox growth behaviour hard to predict.

### PanelSettings and scale mode

`PanelSettings` decides how the panel maps to the screen. The choice is the whole resolution-independence strategy:

| Scale mode | Behaviour | Use for |
| --- | --- | --- |
| Constant Pixel Size | 1 UI unit = 1 screen pixel | Desktop tools; wrong for mobile - UI shrinks on high-DPI |
| Scale With Screen Size | Scales against a reference resolution | Default for mobile 2D games |
| Constant Physical Size | Scales against DPI to a physical target | Touch-target-critical UI where physical size matters |

With Scale With Screen Size, the reference resolution plus the match-width-or-height factor determines what happens off-ratio. Match on width for portrait games so vertical extra space becomes headroom rather than shrinking everything; match on height for landscape. A game shipping both orientations ships Match 0.5 in its one asset and adapts with the root-class swap below, not by changing the match value at runtime. A single reference resolution with no breakpoints still produces a stretched tablet layout - scaling is not adaptivity.

### Screen and popup stack

```csharp
// Bad - screens hide each other by direct reference; back button guesses
menuDoc.SetActive(false); gameDoc.SetActive(true);

// Good - one owner, explicit stack, back pops
public interface INavigator {
    void Push(ScreenId id);   // hides the current screen, or overlays it when id is a modal
    bool Pop();               // false when the stack is empty -> quit prompt
}
```

One navigator owns the stack. Screens do not know each other. A modal overlays the screen beneath, which stays visible but receives no input. Android back arrives as `<Keyboard>/escape`, so one action bound to it serves both back and desktop Escape and calls `Pop`. A modal that captures input must be the top of the stack rather than an element that happens to render last.

Hiding a screen: `display: none` removes it from layout and skips its layout/paint work; `visibility: hidden` and zero opacity keep it in layout and keep costing. Use `display` for screens, opacity only for transitions.

### Safe area and notch

```csharp
// Bad - a magic top pad that is wrong on every other device
root.style.paddingTop = 48;

// Good - the runtime safe area converted to panel units, all four sides (screen origin is bottom-left)
var sa = Screen.safeArea; var panel = root.panel;
var min = RuntimePanelUtils.ScreenToPanel(panel, new Vector2(sa.xMin, Screen.height - sa.yMax));
var max = RuntimePanelUtils.ScreenToPanel(panel, new Vector2(sa.xMax, Screen.height - sa.yMin));
var size = panel.visualTree.layout.size;
root.style.paddingLeft = min.x;  root.style.paddingTop = min.y;
root.style.paddingRight = size.x - max.x;  root.style.paddingBottom = size.y - max.y;
```

`Screen.safeArea` is in screen pixels and every panel length is in panel units, so the conversion is not optional. Re-apply on orientation change and on desktop window resize - safe area is not constant for the process lifetime. `GeometryChangedEvent` on the root catches both, but not a 180-degree flip (landscape left to right), which keeps the panel size and moves the notch: also compare `Screen.safeArea` with the last applied rect, a cheap per-frame check. The same event drives the root class swap for a layout restructure. Gesture bars at the bottom matter as much as the notch at the top: a Play button under the home indicator is unreachable.

### Aspect-ratio adaptivity

| Form factor | Typical ratio | Layout rule |
| --- | --- | --- |
| Phone portrait | 9:19.5 to 9:16 | Single column; board centred; controls anchored to the bottom safe area |
| Phone landscape | 19.5:9 | Board centred; HUD moves to the side gutters, not above/below |
| Tablet | 4:3 to 3:2 | Cap board `max-width`; let gutters grow rather than the board |
| Desktop window | arbitrary, resizable | Same as tablet, plus a `min-width` floor and a resize re-layout |

Drive these with USS `max-width`/`min-width` and flex growth on the gutters, so one stylesheet covers the range. Where a genuine restructure is needed (HUD above versus beside the board), swap a root class on an orientation change rather than maintaining two UXML trees; treat a short-to-long side ratio above ~0.7 as tablet.

For a fixed-aspect board (Sudoku, Chess, 2048, Match-3), constrain the board container by the smaller dimension and let surrounding space absorb the difference. Stretching a square board to fill an arbitrary ratio is a correctness bug, not a cosmetic one.

### Events and pointer input

```csharp
// Bad - polling a click flag from Update
void Update() { if (_btn.focusController.focusedElement == _btn && Mouse.current.leftButton.wasPressedThisFrame) Play(); }

// Good - registered callback, unregistered with the screen
_btn.RegisterCallback<ClickEvent>(OnPlay);
void OnDisable() => _btn.UnregisterCallback<ClickEvent>(OnPlay);
```

Unregister on disable. Callbacks captured against a screen that is pushed and popped repeatedly leak both delegates and their captured state.

Events propagate through the tree (trickle down, bubble up), along the picked element's ancestors only. A modal backdrop blocks taps by being pickable (the UXML attribute `picking-mode="Position"`, or `pickingMode` in C# - not a USS property) and covering what is behind it; `evt.StopPropagation()` only keeps the event from the backdrop's own ancestors. For drag interactions (Match-3 swaps, tile drags), use `PointerDownEvent`/`PointerMoveEvent`/`PointerUpEvent` with pointer capture rather than reconstructing drags from mouse polling - pointer events carry touch identity, mouse events do not.

Gameplay input that is not UI stays in the Input System (`unity-2d-physics-input`). Routing board taps through UI elements couples the board to the panel's hit-testing and scale mode.

### Transitions and juice

USS transitions animate style properties during the panel update, without per-frame C#:

```css
.btn { transition: scale 120ms ease-out; }
.btn:hover, .btn:active { scale: 1.06; }
```

Animate `translate`, `scale`, `rotate`, and `opacity`. USS has no `transform` shorthand - the transform is split into the four standalone properties `translate`, `scale`, `rotate`, and `transform-origin`, each animated by name. Animating `width`, `height`, `margin`, or `padding` forces a layout pass on every frame of the transition; on a full screen that is a measurable stall.

Every transition needs a reduced-motion path - see `unity-accessibility`.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {Structure | QueryCost | Scaling | Navigation | SafeArea | Adaptivity | TextGrowth | Events | Transitions | OutOfScopeUI}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {what breaks and where - "board stretches on 4:3 tablet", "query runs 60x/sec"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

In a mixed project, review the UI Toolkit surfaces normally and file each uGUI surface as one `[Low]` `OutOfScopeUI` block whose `Impact` states it was not reviewed.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = UI unreachable or unusable on a supported form factor (a control under the notch or gesture bar, the board clipped off-screen). High = a per-frame query or layout-animating transition on a hot screen, a navigation stack that cannot return to a previous screen, or a fixed-aspect board rendered distorted on a supported form factor. Medium = inline styling, an uncached query on a cold path, a hardcoded pixel constant with a working fallback, or a fixed text box that clips. Low = a structural nit with no current cost, or an out-of-scope uGUI surface. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: touch-target minimums -> unity-accessibility`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| The project's runtime UI is uGUI only, with no UI Toolkit surface | `uGUI project - UI Toolkit review out of scope.` and nothing else - no blocks, no `Deferred:` lines |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No UI findings.` |
| A review was requested with nothing to judge | `UI check not run: no source supplied.` |

## Avoid

- `Q`/`Query` called from `Update`, `OnGUI`, or an event handler that fires per frame
- Inline `style` assignments from C# for anything a USS class expresses
- Hardcoded pixel positions, sizes, or safe-area pads
- A single reference resolution treated as adaptivity
- Screens toggling each other directly with no navigation owner
- Callbacks registered without a matching unregister
- Transitions animating `width`, `height`, `margin`, or `padding`
- Board or gameplay input routed through UI elements
- An API newer than 6000.3, or experimental, cited without naming the editor version
