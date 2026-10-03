---
name: unity-accessibility
description: Make Unity 2D games playable for all - colour-blind-safe signalling, touch targets, contrast, text scaling, reduced motion, remappable input.
metadata:
  category: mobile
  tags: [unity, accessibility, colour-blind, contrast, touch-target, reduced-motion, screen-reader]
user-invocable: false
---

# Unity Accessibility

> This skill owns **whether a player can perceive, reach, and act on the game**. UXML/USS structure and the screen stack belong to `unity-ui-patterns`; palette and sprite authoring belong to `unity-2d-rendering`; translated strings and text expansion belong to `unity-i18n`; input action maps belong to `unity-2d-physics-input`.

## When to Use

- Any UI screen, HUD, or board where state is communicated visually
- Gameplay distinguishes pieces, gems, tiles, or cells by colour
- Adding animation, screen shake, flashing, or timed pressure
- Reviewing a diff that adds an interactive element or a new signal
- Deciding what accessibility can actually be claimed for a store listing

## Rules

- **Colour is never the only carrier of information.** Every colour-coded distinction carries a redundant shape, symbol, pattern, label, or position. In a Match-3 or colour-matching game this is a correctness requirement, not a courtesy - roughly 8% of male players cannot reliably separate the hues a default gem palette uses, and for them the game is unplayable rather than merely uncomfortable
- Interactive touch targets are at least **48dp x 48dp** with at least 8dp between adjacent targets, regardless of the visual element's size (board cells sized by the board's geometry excepted - see Touch targets). A 24px icon gets a 48dp hit area
- Body and UI text meets **4.5:1** contrast against its background; large text (>= 18pt, or >= 14pt bold - 24px and ~19px at 1:1) and meaningful icons meet **3:1**. Contrast is measured against the actual background, including gameplay art behind a transparent panel
- Text scales without clipping or overlap. Layouts reflow; they do not truncate the sentence
- Every animation, shake, flash, and particle burst has a reduced-motion path that removes or dampens it while preserving the information the motion carried
- Every input binding is remappable, and no interaction requires multi-touch, a drag held for a duration, or a gesture with no tap equivalent
- **Do not claim screen-reader support that has not been verified on device.** Unity's accessibility surface is limited compared to native app frameworks; state what was tested, on which platform, at which engine version

## Patterns

### Colour-blind-safe signalling

The common types constrain the palette differently: red-green deficiency (mostly the milder deuteranomaly and protanomaly, plus full deuteranopia and protanopia - together the large majority) and tritanopia (blue/yellow, rare). Red-versus-green is the worst possible pairing; blue-versus-orange is the most robust.

```csharp
// Bad - the gem type IS the colour; two gems are identical to a deuteranope
gem.color = gemType switch { GemType.Red => Color.red, GemType.Green => Color.green, _ => Color.white };

// Good - colour plus an intrinsic shape; readable in greyscale
gem.sprite = gemSprites[gemType];   // circle, diamond, star, hexagon, teardrop
gem.color  = gemPalette[gemType];   // colour remains, as reinforcement
```

**The test: render the screen in greyscale.** If two game-relevant states become indistinguishable, the design is broken and a palette swap will not fix it. Shape or symbol redundancy is the fix; a "colour-blind palette" toggle alone is a partial mitigation that still fails at high gem counts, because five to seven hues that stay distinct for a deuteranope at similar lightness do not exist.

Beyond the board, the same rule applies to every signal: correct/incorrect answer feedback, valid/invalid move highlights, enemy team identity, health and cooldown states, and required-versus-optional form fields.

| Signal | Colour-only (bad) | Redundant (good) |
| --- | --- | --- |
| Quiz answer result | Green / red fill | Check / cross icon + fill + result text |
| Legal move | Green cell tint | Tinted cell + dot marker + outline |
| Chess piece side | Light / dark tint | Distinct silhouette or side marker in addition to tint |
| Low health | Bar turns red | Bar turns red + pulses + numeric value |

Where a palette toggle is offered, it changes the palette *in addition to* the shape redundancy, and it applies to gameplay art and UI together - a toggle that recolours the HUD but not the board is worse than none.

### Touch targets and spacing

```xml
<!-- Bad - the hit area is the 24px glyph -->
<ui:Button class="icon-close" style="width: 24px; height: 24px;" />

<!-- Good - the glyph sits inside a target sized by USS: .icon-close { min-width: ...; min-height: ...; } -->
<ui:Button class="icon-close" />
```

Express minimums in USS as `min-width`/`min-height` so they survive scaling, then verify the physical size on the physically narrowest screen supported (`unity-ui-patterns`).

**Reference px are not dp.** The rules above are in dp (1dp = 1/160 inch); USS is authored in reference px. On device, physical px = reference px x panel scale, and dp = physical px x 160 / dpi (`Screen.dpi`, which can read 0 - state the fallback used). Under Scale With Screen Size the panel scale is `screen width / reference width` at Match 0, `screen height / reference height` at Match 1, and interpolated between. A 48px target on a 1080-wide reference, shown on a 1080-wide phone at ~420dpi, is about 18dp. Convert before judging a target compliant, and when the reference resolution, match, or device dpi is not stated, say what you assumed (default: ~420 dpi for a 1080-wide phone) rather than reporting a bare pass or fail.

Board cells are exempt from the 48dp minimum only where the board's own geometry sets the size (a 9x9 Sudoku grid on a phone) - but then the input handling must tolerate imprecision: snap to the nearest cell, and confirm destructive actions rather than committing on the first ambiguous tap.

Adjacent targets need spacing. Two 48dp buttons flush against each other still produce mistaps at the seam.

### Contrast

Measure against what is actually behind the text. The frequent failure is a HUD label that passes on the design mock's flat background and fails over the bright gameplay art it ships against. Fixes, in order of robustness: an opaque or heavily tinted backing plate, then a text outline or shadow, then a colour change. A pure alpha reduction on the backing plate reintroduces the problem on the brightest levels.

Disabled states are commonly authored at very low opacity and fall below 3:1. A disabled control still has to be readable, or the player cannot tell what is unavailable versus what is absent.

### Text scaling and reflow

```css
/* Bad - fixed height clips the second line the moment text grows */
.answer-btn { height: 56px; overflow: hidden; }

/* Good - grows with content, floor preserved */
.answer-btn { min-height: 56px; white-space: normal; }
```

Support at least 200% text scale. A quiz game is text; a fixed-height answer button that clips at 130% makes questions ungradeable.

Where the platform exposes a system font-scale preference (`AccessibilitySettings.fontScale` on Android and iOS), honouring it is the correct default; where it does not, ship an in-game text-size setting. Interaction with translation is real: German and Russian run roughly 30% longer than English before any scaling is applied, so the worst case is longest-locale plus maximum scale, and that is the case to verify (`unity-i18n`).

### Screen readers - what is actually available

Be precise here rather than optimistic:

- Unity's runtime accessibility exposure to platform screen readers is provided by the **Accessibility module** (`com.unity.modules.accessibility`, a built-in engine module enabled by default, not an external package) via the `UnityEngine.Accessibility` `AccessibilityHierarchy` / `AssistiveSupport` API. At 6000.3 it covers TalkBack (Android) and VoiceOver (iOS), and - new in 6.3 - Narrator (Windows) and VoiceOver (macOS). It remains narrower than native UIKit or Android View accessibility, and it does not make an arbitrary rendered game board readable
- **UI Toolkit runtime elements are not automatically exposed to platform screen readers** the way native controls are. The hierarchy is a separate node tree that you build and keep in sync with your visual elements in your own code; nothing is exposed that you did not add a node for. Verify on device before claiming it
- The dependable path for a casual 2D game is **in-game accessibility**: a self-voicing option using platform TTS for quiz prompts and answers, high-contrast and large-text modes, and full keyboard/gamepad navigability with a visible focus indicator. These are under the game's control and testable
- Focus order and a visible focus ring are worth getting right regardless: they serve switch access, keyboard, and gamepad players, and they are pure UI Toolkit work

Statements about screen-reader behaviour must name the Unity version and the platform they were verified on - the module ships with the engine, so the editor version is what pins its surface. An unverified claim in a store listing is a compliance problem, not just a docs problem.

### Reduced motion

```csharp
// Bad - unconditional shake; a vestibular trigger with no opt-out
StartCoroutine(ShakeCamera(0.4f, 30f));

// Good - the signal survives; the motion does not
if (!Settings.ReduceMotion) StartCoroutine(ShakeCamera(0.4f, 30f));
else FlashBorderOnce();
```

Ship reduced motion as an in-game toggle; where the project can read the platform's reduce-motion setting, default the toggle from it. Reduced motion removes the motion, not the feedback. A match that was communicated only by a particle burst still needs a communicated result - a static highlight, a score tick, a sound.

Cover screen shake, parallax, full-screen particle bursts, rapid flashing, spinning or looping backgrounds, and large transition animations. Anything flashing faster than roughly 3 Hz across a large area is a seizure risk and should not be present at all, not merely gated behind a toggle.

Where a UI transition is skipped, the end state must still be reached - a screen that only becomes visible via a transition disappears entirely under reduced motion.

### Remappable input and timing

Every action rebindable, with a reset-to-default. The Input System supports interactive rebinding and persisted overrides; expose it rather than hardcoding a scheme (`unity-2d-physics-input`).

No interaction may *require* a gesture: every drag, swipe, long-press, and pinch has a tap or button equivalent. A Match-3 swap works by tapping two adjacent gems as well as by dragging.

Timing accommodations, which for puzzle games are the accessibility feature that actually changes who can play:

| Pressure source | Accommodation |
| --- | --- |
| Countdown timer | Extend, or a no-timer / relaxed mode |
| Auto-advancing question | Advance on input, not on a timer |
| Cascade or resolution animation | Skippable, and never input-blocking beyond its duration |
| Toast or feedback that vanishes | Persist until dismissed, or long enough to read at slow reading speed |
| Double-tap or hold-to-confirm | Tap plus explicit confirm as an alternative |

Never gate progression or story on reaction speed in a casual puzzle game unless a relaxed mode reaches the same content.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design, including what accessibility a store listing may claim. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line. A claim recommendation is: the verdict, the exact wording that may ship, and what must be verified (feature, platform, Unity version) before a broader claim.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {ColourOnly | TouchTarget | Contrast | TextScaling | ScreenReader | ReducedMotion | InputRemapping | GestureOnly | Timing | FocusOrder}
- Evidence: {source | inferred (what was not seen)}
- Affects: {who is blocked - "red-green deficiency, ~8% of male players", "200% text scale", "switch access"}
- Verified: {Unity version and platform exercised on device | not tested}
- Code: {one-line citation | not supplied}
- Impact: {what the player cannot do - "cannot distinguish red and green gems, game unplayable"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

`GestureOnly` covers an action with no tap or button equivalent. A `ScreenReader` block carries the `Verified` line; other blocks omit it. `Evidence` records whether the source was read; `Verified` records whether the behaviour was exercised on a device.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = a player group cannot play or cannot complete a core loop (colour-only board signalling, flashing above ~3 Hz across a large area, an action with no non-gesture path, progression gated on reaction speed with no relaxed mode). High = a core interaction or core content is unreliable or unreadable for a known group (sub-48dp target on a primary control, body text below 4.5:1, text clipped at 200% scale, feedback that vanishes faster than slow reading speed, unconditional screen shake). Medium = a secondary or cosmetic surface with the same defect, or a missing remap for a non-essential action. Low = focus-order or labelling nit with a working alternative path. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: settings persistence -> unity-save-persistence`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No accessibility findings.` |
| A review was requested with nothing to judge | `Accessibility check not run: no source supplied.` |

## Avoid

- Hue as the sole distinguishing feature of a game piece, tile, cell, or answer state
- A colour-blind palette toggle offered as a substitute for shape or symbol redundancy
- A palette toggle that recolours the HUD but not the gameplay board
- Hit areas sized to the visual glyph
- Contrast measured against a design mock rather than the shipped background
- Fixed-height text containers with `overflow: hidden`
- Screen-reader support claimed without on-device verification, or without naming the Unity version and platform tested
- Screen shake, flashing, or particle bursts with no reduced-motion path
- Reduced motion that removes the feedback along with the motion
- Flashing faster than ~3 Hz across a large area, toggle or not
- A gesture with no tap or button equivalent
- Countdown pressure with no extended or relaxed mode
