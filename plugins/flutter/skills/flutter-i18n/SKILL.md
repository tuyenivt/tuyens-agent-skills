---
name: flutter-i18n
description: "Localize Flutter with gen_l10n and ARB files: no hardcoded strings, plurals, locale date/number/currency formats, RTL layout, text expansion."
metadata:
  category: mobile
  tags: [flutter, dart, i18n, l10n, gen-l10n, arb, intl, rtl, localization, pluralization]
user-invocable: false
---

# Flutter Internationalization

> Platform tiers are defined in `flutter-adaptive-responsive`; localization behaves identically across tiers, so patterns here are `All` unless stated. Semantic labels are user-facing text and are localized under the same rule - see `flutter-accessibility`.

## When to Use

- Adding or reviewing any user-facing string, number, date, or currency
- Setting up `gen_l10n` and ARB files, or adding a locale to an existing setup
- Adding support for an RTL language, or auditing a layout for directional correctness
- A report of untranslated text, a wrong plural form, a date in the wrong format, a mirrored layout defect, or a label overflowing in one language only

## Rules

- No user-facing string is written as a literal in Dart, including strings handed to a plugin for display (a biometric prompt reason, a notification title). Every one lives in an ARB file and is read through the generated localizations class
- Sentences are never assembled by concatenating translated fragments. One key holds one complete sentence with placeholders
- Counted quantities use ICU `plural`; conditional phrasing uses ICU `select`. `if (count == 1)` in Dart is a defect - the number of plural categories is a property of the language, not of the code
- Dates, times, numbers, percentages, and currency are formatted through the ARB placeholder `format` (or `intl` directly) with the active locale. Never `toString()`, never `toStringAsFixed`, never manual `dd/MM/yyyy`
- Every ARB key carries an `@key` entry with a `description`. Translators see the string with no surrounding UI; the description is the only context they get
- Directional padding, alignment, and positioning use the `*Directional` variants in new code, and in any layout once an RTL locale ships. `left` and `right` mean physical sides and do not mirror
- Locale resolution has an explicit fallback and the fallback locale is complete. A missing key must not be able to reach the user
- Layout accommodates text expansion: no fixed-width box around translated text, no single-line assumption on a label
- Currency formatting and currency *conversion* are separate concerns. Formatting an amount in the user's locale never changes which currency it is in, and amounts in different currencies are never summed into one figure. A hand-written `supportedLocales` list, instead of the generated one, is a `Locale-Resolution` finding

## Patterns

### Setup and the no-hardcoding rule

*Tiers: All.*

`l10n.yaml` at the project root, with `generate: true` under `flutter:` and `flutter_localizations` (sdk) plus `intl` under `dependencies:` in `pubspec.yaml`:

```yaml
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
preferred-supported-locales: [en]   # generated supportedLocales is alphabetical without this
```

```dart
MaterialApp(
  onGenerateTitle: (context) => AppLocalizations.of(context)!.appTitle, // `title:` cannot read localizations
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  home: const HomeScreen(),
)
```

```dart
// Bad - untranslatable, and invisible to any search for user-facing text
const Text('Order total')

// Good
Text(AppLocalizations.of(context)!.orderTotalLabel)
```

The generated class is build output: raise findings against the ARB file and the call site, never against `app_localizations.dart`. Import it from its generated path (`output-dir` in `l10n.yaml`, defaulting to `arb-dir`); the synthetic `package:flutter_gen` import was deprecated in Flutter 3.29 and removed after. Setting `nullable-getter: false` in `l10n.yaml` removes the `!` at every call site.

```dart
// Bad - two fragments; word order, gender agreement, and spacing are not translatable
Text('${l10n.deletedPrefix} ${item.name}')

// Good - one key, one placeholder
Text(l10n.deletedItem(item.name))
```

Concatenation bakes English grammar into the code. Languages that reorder the sentence, inflect the noun, or attach a particle cannot be expressed by joining two independently translated halves.

### Plurals and select

*Tiers: All.*

```dart
// Bad - two categories; correct for English, wrong for Polish, Russian, and Arabic
Text(count == 1 ? l10n.oneOrder : l10n.manyOrders(count))
```

```json
{
  "orderCount": "{count, plural, =0{No orders} =1{1 order} other{{count} orders}}",
  "@orderCount": {
    "description": "Number of orders shown in the list header",
    "placeholders": { "count": { "type": "int", "format": "decimalPattern" } }
  }
}
```

```dart
Text(l10n.orderCount(orders.length))
```

The ICU categories are `zero`, `one`, `two`, `few`, `many`, `other`; gen_l10n also accepts the exact forms `=0`, `=1`, `=2`, each merged with `zero`, `one`, `two` (so `zero` matches exactly 0 even in English, and a message may not hold both forms of a pair). The template ARB only needs the forms English uses; translators supply the forms their language needs (Polish uses `one`, `few`, `many`, `other`; Arabic uses all six), which is exactly what the Dart branch makes impossible.

`select` handles non-numeric variation, most commonly gender:

```json
{
  "invitedBy": "{gender, select, male{He invited you} female{She invited you} other{They invited you}}",
  "@invitedBy": {
    "description": "Shown on an invitation card",
    "placeholders": { "gender": { "type": "String" } }
  }
}
```

`other` is mandatory in both forms and is the fallback for any unmatched value.

### Dates, numbers, and currency

*Tiers: All.*

```dart
// Bad - month/day order is a locale property; this is US-only and unlocalized
Text('${d.month}/${d.day}/${d.year}')
Text('\$${amount.toStringAsFixed(2)}')
```

```json
{
  "placedOn": "Placed on {date}",
  "@placedOn": {
    "description": "Order detail header",
    "placeholders": { "date": { "type": "DateTime", "format": "yMMMd" } }
  },
  "orderTotal": "Total: {amount}",
  "@orderTotal": {
    "description": "Order total; amount is already formatted in the order's own currency",
    "placeholders": { "amount": { "type": "String" } }
  }
}
```

```dart
final fmt = NumberFormat.currency(locale: l10n.localeName, name: order.currencyCode); // import 'dart:math' as math
final amount = fmt.format(order.totalMinor / math.pow(10, fmt.decimalDigits ?? 2)); // JPY has 0, KWD 3
Text(l10n.orderTotal(amount))
```

The `format` value maps to an `intl` `DateFormat` / `NumberFormat` skeleton, and the generated code passes the active locale automatically. ARB `"format": "currency"` fixes its `optionalParameters` at build time and otherwise uses the locale's own currency, so it suits only an app with one currency; an amount whose currency varies per record is formatted with `NumberFormat.currency(locale:, name:)` and passed as a `String` placeholder. Outside ARB (a chart axis, an export), use `intl` explicitly with the locale: `DateFormat.yMMMd(Localizations.localeOf(context).toString()).format(d)`.

Locale changes the decimal separator, the grouping separator, the digit set, and the symbol position, so a number rendered by string interpolation is wrong in most locales even when the digits are right. Format at the point of display, never store a formatted string.

### RTL and directional layout

*Tiers: All.*

Text direction comes from the resolved locale via the localization delegates; no manual `Directionality` wrapper is needed for the app as a whole.

```dart
// Bad - the icon stays on the physical left in Arabic and Hebrew, colliding with the text
Padding(padding: const EdgeInsets.only(left: 16), child: Row(children: [icon, label]))

// Good - start and end follow the reading direction
Padding(padding: const EdgeInsetsDirectional.only(start: 16), child: Row(children: [icon, label]))
```

| Physical | Directional |
|----------|-------------|
| `EdgeInsets.only(left:, right:)` | `EdgeInsetsDirectional.only(start:, end:)` |
| `Alignment.centerLeft` | `AlignmentDirectional.centerStart` |
| `BorderRadius.only(topLeft:)` | `BorderRadiusDirectional.only(topStart:)` |
| `Positioned(left:, right:)` | `PositionedDirectional(start:, end:)` |

`Row` with `MainAxisAlignment.start` already mirrors; it is the explicit `left` / `right` values that do not. Material's directional icons (`arrow_back`, `chevron_right`, `send`, `undo`) set `matchTextDirection` and mirror themselves; custom or third-party directional icons need a mirrored asset or a flip on `Directionality.of(context)`, and `Image` exposes `matchTextDirection` for the asset case. Icons with intrinsic orientation (a clock, a checkmark, a brand mark) must not be mirrored. When no RTL locale ships, physical-side geometry in existing code is not a finding; in lines a change adds it is `RTL-Layout`, Medium.

Verify with a real RTL locale (`ar`, `he`) rather than by inspection: `MaterialApp(locale: const Locale('ar'), ...)` in a widget or golden test.

### Locale resolution and fallback

*Tiers: All.*

Default resolution walks the device's preferred-locale list, matching the full locale, then language plus script, then language plus country, then language alone, with a country-only match as the last resort, and falls back to `supportedLocales.first` only when nothing matches. Two consequences worth stating explicitly:

- The first entry in `supportedLocales` is the fallback for every unmatched device locale. The generated list is alphabetical, so set `preferred-supported-locales` in `l10n.yaml` to put the complete locale first.
- A key present in the template ARB but missing from a translation falls back to the template value; `flutter gen-l10n` prints only a per-locale count, so set `untranslated-messages-file` in `l10n.yaml` to get a per-key artifact CI can fail on.

Override only when the default is wrong for the product (for example, routing a language the app does not ship to a related one it does, such as Catalan to Spanish, instead of the fallback):

```dart
MaterialApp(
  localeListResolutionCallback: (deviceLocales, supported) {
    final first = deviceLocales?.firstOrNull;
    return first?.languageCode == 'ca' ? const Locale('es') : null; // null falls through to the default resolution
  },
)
```

A user-selected locale is app state that must be persisted and applied through `MaterialApp(locale:)`; reading the device locale alone cannot express "the user chose a different language than their phone".

### Text expansion

*Tiers: All.*

Translated strings are commonly longer than English: short labels can double or more, and running text typically grows 20-40%. German, Finnish, and Russian are the usual first failures.

```dart
// Bad - fits "Save"; wraps or truncates "Speichern" in German
SizedBox(width: 88, child: ElevatedButton(onPressed: _save, child: Text(l10n.save, maxLines: 1, overflow: TextOverflow.ellipsis)))

// Good - the button sizes to its label, with a floor rather than a fixed width
ConstrainedBox(
  constraints: const BoxConstraints(minWidth: 88),
  child: ElevatedButton(onPressed: _save, child: Text(l10n.save)),
)
```

The same defect class as fixed-height text containers in `flutter-accessibility`, on the other axis, and it compounds with text scaling: a long German string at 200% font scale is the worst case both mechanisms produce together. Where truncation is genuinely acceptable, make it explicit and reversible (`maxLines` plus `overflow: TextOverflow.ellipsis` plus a way to see the full text), rather than letting a `Row` overflow.

Test the long case: render key screens in a verbose locale in golden or widget tests instead of only in the template locale.

## Output Format

When invoked from an implementation workflow, emit the localization plan:

```
Setup: {l10n.yaml at <path> | l10n.yaml at <path>, keys added | not configured}

Template locale: {code}

Supported: {codes}

RTL in scope: {yes | no}

Layout: {directional conversions / expansion floors at file:line | none needed}

| String / value | ARB key | Form | Format | Notes |
|----------------|---------|------|--------|-------|
| {what the user reads or types} | {key \| -} | {plain \| plural \| select \| input} | {placeholder type and skeleton \| -} | {states, currency, label role} |
```

For example: `Order count header | orderCount | plural | int decimalPattern | =0 / =1 / other`, `Order date | placedOn | plain | DateTime yMMMd | placeholder`, `Order total | orderTotal | plain | String, NumberFormat.currency(name: order code) | currency is the order's, not the locale's`, `Delete tooltip | deleteOrder | plain | - | semantic label`. `Form: input` is a value the user types (an amount, a date) with no ARB key: it is parsed with `NumberFormat.decimalPattern(locale).parse` or `DateFormat`, accepting the locale's separators and digit set, Arabic-Indic included. Semantic labels, tooltips, and error messages (reason as a placeholder) are rows, in screen order. Layout cites `<path> (new)` for unwritten code. New locales are listed in the `Supported` header, not as rows. New keys go into the template ARB only; existing translations surface them through `untranslated-messages-file` until translated. Once an RTL locale ships, every physical-side value in the lines the plan edits goes on the Layout line; the rest are `Pre-existing`.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow or directly to diagnose a localization defect report, emit one block per finding:

```
### [{Blocker | High | Medium | Low}] {file:line}

- Area: I18n
- Check: {Setup | Hardcoded-String | Concatenation | Plural-Form | Locale-Format | RTL-Layout | Locale-Resolution | Text-Expansion | Translator-Context}
- Tier: {Mobile | Desktop | Web | All}
- Code: {one-line citation}
- Impact: {what a user in an affected locale reads, or cannot read}
- Fix: {concrete edit}
```

**Severity calibration.** `Blocker` = text is unreadable or wrong in a supported locale (clipped label, mirrored layout collision, a date or amount that reads as a different value). `High` = correct characters, wrong language or wrong grammatical form for a supported locale (hardcoded string, two-branch plural), or physical-side geometry misaligning a supported RTL locale short of collision. `Medium` = correct today but structurally fragile (concatenation that no supported locale breaks yet, fixed-width box that currently fits, missing `description`). `Low` = key naming and ARB organization. Concatenation is `High` once a supported locale's word order or agreement breaks the joined sentence. When a finding matches two bands, the higher band wins. A line that fits two Checks is filed once, under the Check whose fix also fixes the other (a hardcoded literal inside a concatenation is `Hardcoded-String`; a literal inside a Dart plural branch is `Plural-Form` at its own severity, uncapped); when the two fixes differ it is two blocks. A key missing from a shipped translation is `Locale-Resolution`, one block per locale file anchored on that file's `@@locale` line and naming the keys; an unused key is not a finding; the deprecated `flutter_gen` import is `Setup`, Medium, one block per file. A missing `l10n.yaml` option (`preferred-supported-locales`, `untranslated-messages-file`) is `Setup`, Medium, anchored on `l10n.yaml`. A brand name is not a finding; a unit (`kg`) is a key with a placeholder; the wording of a translation is not reviewed. A raw `e.toString()` shown to the user is `Also seen` for `flutter-error-handling`.

**Label mapping for the umbrella review:** `Blocker`, `High` -> `[Must]`; `Medium`, `Low` -> `[Recommend]`.

If the project has no `l10n.yaml` or ARB directory, emit `Localization not configured` once, raise the setup as one `High` finding with Check `Setup` anchored at the `dependencies:` line of `pubspec.yaml`, and still file each hardcoded literal as its own `Hardcoded-String` finding capped at `Medium`, and `Locale-Format` is capped the same; other Checks keep their normal severity. Findings cite the ARB file or the Dart call site, never the generated localizations output. With localization not configured, `Locale-Resolution` and `Translator-Context` are `Not checked`.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value; a pairing the calibration paragraph names is filed as it says).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Check` values, or the path of a file that could not be read) when any check could not be exercised, then the `Checks clean:` line. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean and is listed on `Checks clean:`; a check on the `Not checked` line is not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Impact:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape, a request to review or audit takes the review shape, and a supplied symptom or bug report takes diagnose mode.

The closing lines - `Also seen` and `Not checked` only when they have content, `Checks clean:` in review mode:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

Checks clean: {comma-separated Check values with zero findings | none}
```

Diagnose mode opens with one line per reported symptom, `Symptom <n>: <the report's title or first sentence>`, a title that lists two symptoms is two lines, naming on each any premise the files read contradict (a flag the report says is on, a version it names) - the diagnosis then proceeds on what the code shows - and stating when the files read cannot cause the symptom. Blocks for the causes of the reported symptoms come first, grouped by symptom in reported order and within a group by severity, each such block's `Impact:` line opening with `Symptom <n>:`; a cause shared by two symptoms is one block opening `Symptom 1, 2:`, placed with the lower-numbered symptom; every other defect seen in the files read follows, ordered as in review mode. The `Checks clean:` line is omitted in diagnose mode; `Also seen` and `Not checked` lines are kept.

## Avoid

- User-facing string literals in Dart, including semantic labels, tooltips, error messages, and dialog titles
- Sentences built by concatenating or interpolating translated fragments
- `count == 1` branching in Dart instead of an ICU `plural` key
- `toString()`, `toStringAsFixed`, or a hand-built `dd/MM/yyyy` for anything the user reads
- A hardcoded currency symbol, or reformatting an amount into the locale's currency instead of the order's
- ARB keys with no `@key` description
- `EdgeInsets.only(left:)`, `Alignment.centerLeft`, `Positioned(left:)` in a layout that ships an RTL locale
- Mirroring an icon with intrinsic orientation, or leaving a directional arrow unmirrored
- `supportedLocales.first` chosen by accident - it is the fallback for every unmatched device
- Shipping without `untranslated-messages-file`, so missing translations are a console count nobody reads
- Fixed-width buttons, chips, and labels around translated text
- Verifying RTL or long-text behaviour by inspection instead of rendering an `ar` or `de` locale in a test
- Raising findings against generated localization output instead of the ARB source
