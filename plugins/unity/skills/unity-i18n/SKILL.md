---
name: unity-i18n
description: Localize Unity 2D games with the Localization package - string tables, smart strings, plurals, CJK font atlases, text expansion, RTL, formatting.
metadata:
  category: mobile
  tags: [unity, localization, i18n, string-tables, textcore, font-atlas, rtl, pluralization]
user-invocable: false
---

# Unity i18n

> This skill owns **translation, locale behaviour, and text rendering across scripts**. Content bank structure and identifiers belong to `unity-content-data`; layout containers and USS belong to `unity-ui-patterns`; text scaling and contrast belong to `unity-accessibility`; font atlas memory budgets belong to `unity-performance`.

## When to Use

- The game ships, or may ship, in more than one language
- Any user-facing string is being added
- Targeting a non-Latin script (CJK, Cyrillic, Arabic, Hebrew, Thai, Devanagari)
- Text overflows or clips in a non-English locale
- Reviewing a diff for hardcoded strings or locale-dependent formatting

## Rules

- **No hardcoded user-facing string.** Every string a player reads resolves through a string table entry keyed by a stable id. Applies to UI labels, buttons, tutorial text, error messages, store copy, and notification text
- Keys are stable and semantic (`quiz.result.correct`), never the English text and never derived from a position
- **Never build a sentence by concatenating translated fragments.** Word order differs by language; a fragment has no grammatical context. Use one parameterized entry per sentence
- Plural forms come from the localization system's plural rules, not from `count == 1`. Several target languages have three or more plural categories
- Numbers, dates, times, currency, and percentages format through a culture, never through a hardcoded pattern or the invariant culture
- Fonts must cover every glyph in every shipped locale. A shipped locale whose glyphs are absent from the atlas renders as blank boxes - a build-blocking defect, not a polish item
- Layouts are verified against the **longest** shipped locale, not English. German and Russian typically run 20-35% longer than English, and short UI strings expand far more
- Locale is auto-detected on first run and overridable in settings, with the override persisted

## Patterns

### String tables and keys

```csharp
// Bad - unlocalizable, and the string is duplicated across three screens
scoreLabel.text = "Score: " + score;

// Good - one entry, one parameter, translatable word order, re-resolved on locale change
var scoreVar = new IntVariable();                       // entry "hud.score" is Smart: "Score: {score}"
var hudScore = new LocalizedString("UI", "hud.score") { { "score", scoreVar } };
scoreLabel.SetBinding("text", hudScore);
// on change: scoreVar.Value = score;   - the bound text re-resolves
```

Split tables by load unit, not by screen: a UI table, a gameplay table, and one table per content bank slice. Loading a single monolithic table means every locale's worst case is one large resident asset.

Bind UI Toolkit text through the Localization package's data binding (`SetBinding("text", localizedString)`, Localization 1.5 on 2023.2+) rather than manual lookups: the binding waits for the table and re-resolves on every locale change.

Localization tables load asynchronously. A manual lookup made before its table resolves shows the key or a blank, and one made once at startup never follows a locale change.

### Smart strings and pluralization

```csharp
// Bad - two plural categories assumed; wrong in Russian, Polish, Arabic, Welsh
label.text = $"{n} " + (n == 1 ? "move left" : "moves left");

// Good - smart string; each locale's table supplies its own plural forms
// entry "hud.moves" (marked Smart in the table) = "{0:plural:{} move left|{} moves left}"
```

Smart strings also carry gender and conditional selection. Keep the branching inside the entry where a translator can restructure it; branching in C# forces every locale into English's grammar.

Ordering: use indexed or named placeholders (`{0}`, `{name}` - named ones need a Smart entry), never positional-only concatenation, so a translator can reorder them.

### Fonts and glyph coverage

This is the dominant mobile memory problem in localization. A full CJK font covers 20,000+ glyphs; rasterizing all of them into a static atlas produces a texture measured in tens of megabytes.

| Atlas mode | Behaviour | Use for |
| --- | --- | --- |
| Static | All glyphs pre-rasterized into the asset in the editor; fixed cost, no runtime work | Latin/Cyrillic sets, and any fixed known string set - outside any Advanced Text Generator subtree |
| Dynamic | Glyphs rasterized on demand into a growing atlas; small baseline, runtime cost on first use | CJK and any large or open-ended character set |

For CJK, use a **dynamic atlas plus a static pre-warm of the frequent set** (the characters the UI and the most common content actually use), with a dynamic fallback for the tail (no static pre-warm under the Advanced Text Generator). That keeps the baseline small and avoids a visible hitch the first time an uncommon character appears.

Font fallback chains resolve missing glyphs from a secondary font. Chains are searched in order on a miss, so a long chain costs on every uncached glyph - keep it short and ordered by likelihood. A glyph missing from the whole chain renders as a blank box or a replacement square.

```
// Bad - one 40MB static CJK atlas shipped in every build, every locale
// Good - Latin static atlas; CJK dynamic atlas + pre-warmed frequent set, loaded per locale
```

Ship font assets per locale through Addressables so a Latin-only install does not carry the CJK atlas. Verify glyph coverage at build time by scanning every shipped table entry against the locale's font - this is the same class of import-time validation `unity-content-data` applies to banks, and it must fail the build.

Arabic, Hebrew, Thai, and Devanagari need more than glyph presence: shaping (Arabic joining, Indic conjuncts, Thai mark stacking) or bidi and line breaking (Hebrew). UI Toolkit's Standard text generator, the 6000.3 runtime default, does neither and only reverses RTL text. The Advanced Text Generator (the runtime default from 6.5) does both through HarfBuzz and ICU; through 6.4 it takes two switches - Enable Advanced Text Generator in Project Settings > UI Toolkit, and `-unity-text-generator: advanced` on the elements. It supports only dynamic font assets, and it applies per element, so set it on the subtrees that render those scripts, or migrate every static font asset under it.

### Text expansion

```css
/* Bad - sized to fit the English string exactly */
.answer-btn { width: 280px; height: 48px; overflow: hidden; }

/* Good - grows with content, floors preserved, wraps */
.answer-btn { min-width: 280px; min-height: 48px; white-space: normal; }
```

Rule of thumb for expansion versus English: short UI strings (under 10 chars) can double; medium strings expand 30-40%; long paragraphs expand 15-20%. German compounds and Russian produce the worst cases; CJK is usually shorter in character count but taller in line height.

Verify the worst case as **longest locale at maximum text scale** (`unity-accessibility`), not each in isolation.

Auto-shrink-to-fit is a last resort, not a strategy: it silently produces unreadable text in exactly the locales that need the most room, and it hides the layout defect instead of surfacing it. Prefer wrapping and container growth; where truncation is unavoidable, truncate with an ellipsis and make the full string reachable.

Pseudo-localization (expand every string ~40% and bracket it) catches both hardcoded strings and fixed-width containers before any translation exists. Ship it as a debug locale.

### Complex scripts: shaping applies to LTR too

**Shaping is a separate axis from direction.** Devanagari and Thai are left-to-right and need no mirroring or bidi reordering, but they do need shaping - Devanagari forms conjuncts and repositions vowel signs (including pre-base matras), Thai stacks marks above and below the base. Every glyph can be present in the atlas and the text still render as broken, unreadable clusters.

In-engine shaping means the Advanced Text Generator (Fonts and glyph coverage, above). For an LTR complex script, apply the shaping and glyph-coverage requirements below and skip the mirroring and bidi ones. The do-not-ship rule applies on the same terms: if shaping cannot be verified to a shippable standard by someone who reads the script, do not ship the locale. Devanagari also runs taller than Latin because of stacked matras and conjuncts, so vertical clipping is its characteristic layout failure - a pseudo-locale that only widens strings will not catch it.

### RTL and its limits

Arabic and Hebrew need three separate things, and they fail independently:

1. **Text shaping** - Arabic letters change form by position and join; unshaped Arabic is legible-adjacent nonsense to a reader
2. **Bidirectional reordering** - mixed RTL text with embedded numbers or Latin names must be reordered per the Unicode bidi algorithm
3. **Layout mirroring** - the UI direction flips: navigation, back arrows, progress direction, and horizontal flex order

Shaping, bidi, and RTL line breaking need the Advanced Text Generator plus `language-direction="RTL"` on the text elements; the Standard generator only reverses the string. Verify rendering with native-speaker review either way. Layout mirroring is not automatic - flip flex direction and start/end padding on a root RTL class in USS.

Do not mirror everything: numerals, clocks, progress-toward-a-goal in some contexts, and game boards with intrinsic orientation (a chessboard) stay unmirrored. Mirror chrome and reading flow, not the play space.

If RTL cannot be verified to a shippable standard, **do not ship the locale**. A half-mirrored, unshaped Arabic build is worse than an English-only one.

### Locale-aware formatting

```csharp
// Bad - invariant or implicit culture; "1,234.5" is wrong in most of Europe
label.text = avgScore.ToString("N1");          // thread culture, not the player's locale
dateLabel.text = when.ToString("MM/dd/yyyy");

// Good - formatted against the selected locale's culture
var ci = LocalizationSettings.SelectedLocale.Identifier.CultureInfo;
label.text = avgScore.ToString("N1", ci);
dateLabel.text = when.ToString("d", ci);
```

`Identifier.CultureInfo` is null for a locale .NET does not know (a pseudo-locale), and formatting then silently falls back to the thread culture; format through an explicit fallback culture (`Locale.Formatter` falls back to the same null unless the locale sets a custom formatter).

The inverse also matters: data written to a save file, sent to a server, or used as a dictionary key formats with `CultureInfo.InvariantCulture`. A score serialized under a German culture and parsed under a US one is a real save-corruption path (`unity-save-persistence`).

Durations (an mm:ss countdown) have no culture pattern in .NET: the separator pattern is yours, and a literal mm:ss timer is not a hardcoded-pattern finding. .NET formatting always emits ASCII digits (`NativeDigits` is never applied), so a locale that wants native numerals maps them itself.

Large numbers in idle games need locale-aware abbreviation - "1.2K" and "1.2M" are not universal. CJK locales group by 10,000 (man/wan) rather than 1,000, and Indic locales group by lakh (100,000) and crore (10,000,000) with a different digit-separator pattern entirely. The **threshold** at which an abbreviation kicks in is therefore locale data too, not just the suffix. Route both through table entries rather than hardcoding a divisor.

### Locale detection and override

Detect from the platform locale on first run, fall back to a default locale when the detected one is not shipped, and persist any user override. Do not re-detect over an explicit override on later launches.

Locale changes at runtime must re-resolve every visible string, re-bind content bank text, and reload the locale's font assets. A locale switch that only takes effect after a restart is a defect.

### Content bank interaction

`unity-content-data` owns bank shape and identifiers; this skill owns their translated text. The boundary:

| Concern | Owner |
| --- | --- |
| Question id, `correctAnswerId`, tags, bank grouping | `unity-content-data` |
| Prompt and answer display strings per locale | this skill |
| Validating that every shipped locale has an entry per key | validation lives in the bank importer, rules stated here |

Correctness never keys off translated text: grade by answer id, not by comparing the displayed string. Only the active locale's text is resident; a bank that loads all locales multiplies memory by locale count for no benefit.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the single-locale scope header when it applies, the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {HardcodedString | KeyStability | Concatenation | Pluralization | GlyphCoverage | FontMemory | TextExpansion | RTL | Shaping | Formatting | LocaleDetection | TableResolution | ContentBankLocale}
- Evidence: {source | inferred (what was not seen)}
- Locales affected: {list, or "all non-English", or "all"}
- Code: {one-line citation | not supplied}
- Impact: {what a player in that locale sees - "blank boxes for all CJK text", "answer button clips at 60% of the German string"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

`TableResolution` covers an entry missing from a shipped locale's table or text bound before the table resolves (a raw key or blank on screen, High), and a missing locale-change re-bind (stale text, Medium). `Shaping` covers any script rendered unshaped (Arabic, Devanagari, Thai); `RTL` covers direction, bidi, and mirroring.

If the project ships a single locale and has no localization package installed (with the package installed, every category applies), the scope header is exactly `Single-locale project - i18n review limited to hardcoded-string and formatting findings.`, and only those two categories are reported (a concatenated sentence files as `HardcodedString`), at the bands below. Everything else in this format applies unchanged.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = a shipped locale is unusable (missing glyphs render as boxes, unshaped RTL or complex-script text, correctness keyed off translated text, culture-dependent formatting written to a save or wire format). High = a user-facing string untranslatable or wrong in a shipped locale (a hardcoded string on a player-visible surface, a concatenated sentence, a two-form plural in a multi-form language, text clipped by a fixed container). Medium = a locale-correctness gap on a secondary surface (a chrome element left unmirrored, a game board mirrored), an oversized font atlas, or a missing runtime locale-change re-bind. Low = a key naming or table organization nit. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: font atlas memory budget -> unity-performance`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No i18n findings.` |
| A review was requested with nothing to judge | `I18n check not run: no source supplied.` |

## Avoid

- User-facing strings literal in C#, UXML, prefabs, or ScriptableObjects
- Keys that are the English text, or derived from screen position or array index
- Sentences assembled from concatenated translated fragments
- `count == 1` plural branching in C#
- Format calls with no `CultureInfo`, or a hardcoded date/number pattern
- Culture-dependent formatting written to save files, wire formats, or dictionary keys
- One static atlas covering a full CJK font, shipped to every locale
- Long font fallback chains resolving misses on a hot path
- Fixed-width or fixed-height text containers sized to the English string
- Auto-shrink-to-fit used as the expansion strategy
- Shipping RTL with layout mirroring or shaping unverified
- Arabic, Hebrew, Thai, or Devanagari rendered without the Advanced Text Generator
- Mirroring game boards and numerals along with UI chrome
- Re-detecting locale over a persisted user override
- Locale change that requires an app restart
- All locales' bank text resident when one locale is active
