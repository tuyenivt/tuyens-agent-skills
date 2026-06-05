---
name: angular-i18n-patterns
description: Angular i18n - @angular/localize, $localize, i18n attribute, ICU expressions, LOCALE_ID, build-time vs runtime, ngx-translate/transloco.
metadata:
  category: frontend
  tags: [angular, i18n, localize, $localize, icu, locale, ngx-translate, transloco]
user-invocable: false
---

# Angular i18n Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding a second locale to an Angular app
- Choosing between built-in `@angular/localize` and a runtime library (`ngx-translate`, `transloco`)
- Marking user-facing strings, ICU plurals/genders, or attribute translations
- Reviewing date / number / currency formatting under non-default locales

## Rules

- One mechanism per app: `@angular/localize` (build-time) or `transloco`/`ngx-translate` (runtime). Mixing fragments translations across two systems.
- Every user-visible string is translated, including attributes (`title`, `aria-label`, `placeholder`, `alt`).
- ICU expressions are used for plurals, genders, and select - never string-concatenated translations.
- `LOCALE_ID` is provided explicitly per build / runtime; pipes (`date`, `currency`, `number`) honor it.
- IDs on `i18n` attributes are stable and meaningful (`@@user.greeting`) so extraction does not churn keys on copy edits.

## Patterns

### Decision: Build-Time vs Runtime

| Need                                                | Pick                              |
| --------------------------------------------------- | --------------------------------- |
| Few locales, ship per-locale bundles, SEO/SSR per locale | `@angular/localize` (build-time) |
| Many locales, runtime language switcher, lazy translations | `transloco` (preferred) or `ngx-translate` |
| Pure formatting (date, number, currency) only       | `LOCALE_ID` + built-in pipes only |

`@angular/localize` is the official path; `transloco` (by ngneat) is the most actively maintained runtime alternative.

### `@angular/localize` Setup

```bash
ng add @angular/localize
```

```typescript
// angular.json (per-app)
"i18n": {
  "sourceLocale": "en-US",
  "locales": {
    "ja": { "translation": "src/locale/messages.ja.xlf", "baseHref": "/ja/" },
    "fr": { "translation": "src/locale/messages.fr.xlf", "baseHref": "/fr/" }
  }
},
"architect": {
  "build": {
    "configurations": {
      "ja": { "localize": ["ja"] },
      "fr": { "localize": ["fr"] },
      "production": { "localize": true }
    }
  }
}
```

```bash
ng extract-i18n --output-path src/locale       # generates messages.xlf
ng build --configuration=production            # builds dist/<app>/{en-US,ja,fr}/
```

Deploy each locale folder under its `baseHref`. SSR: one Node server per locale (or one router that dispatches by URL prefix).

### Template Translation: `i18n` Attribute

```html
<h1 i18n="@@dashboard.title">Welcome back</h1>
<button i18n-title="@@dashboard.refresh.tooltip" title="Refresh dashboard">Refresh</button>
<img i18n-alt="@@hero.alt" alt="Team celebrating launch" ngSrc="..." />
```

Always assign a meaning + ID with `@@id` - keys without IDs are auto-hashed from source text, so any copy change breaks every translation.

### Code Translation: `$localize`

```typescript
const title = $localize`:@@dashboard.title:Welcome back`;
const greeting = $localize`:@@user.greeting:Hello, ${name}:USER:!`;
this.toast.show($localize`:@@toast.saved:Changes saved successfully`);
```

Use in services, validators, error messages - anywhere a string lives outside a template.

### ICU Plurals and Selects

```html
<p i18n="@@inbox.count">
  {count, plural,
    =0 {You have no messages}
    =1 {You have one message}
    other {You have {{count}} messages}
  }
</p>

<p i18n="@@user.invite.gender">
  {gender, select,
    male {He invited you}
    female {She invited you}
    other {They invited you}
  }
</p>
```

Never build plurals by concatenation (`${count} message${count === 1 ? '' : 's'}`) - other locales (Polish, Russian, Arabic) have more than two plural forms.

### Runtime: `transloco` (alternative)

```typescript
// app.config.ts
providers: [
  provideTransloco({
    config: {
      availableLangs: ['en', 'ja', 'fr'],
      defaultLang: 'en',
      fallbackLang: 'en',
      prodMode: !isDevMode(),
    },
    loader: TranslocoHttpLoader, // loads assets/i18n/{lang}.json
  }),
],
```

```html
<h1>{{ 'dashboard.title' | transloco }}</h1>
<p>{{ 'inbox.count' | transloco: { count: count() } }}</p>
```

```typescript
private transloco = inject(TranslocoService);
switchLocale(lang: 'en' | 'ja' | 'fr'): void { this.transloco.setActiveLang(lang); }
```

Trade-off vs `@angular/localize`: smaller initial bundle (translations are lazy JSON), runtime language switch, but no compile-time validation that every key exists.

### `LOCALE_ID` + Built-in Pipes

```typescript
// per-locale provider (build-time mode auto-provides LOCALE_ID from the build target)
providers: [{ provide: LOCALE_ID, useValue: 'ja-JP' }],
```

```typescript
// register data for non-default locales used at runtime
import { registerLocaleData } from '@angular/common';
import localeJa from '@angular/common/locales/ja';
registerLocaleData(localeJa, 'ja-JP');
```

```html
{{ amount | currency:'JPY':'symbol':'1.0-0' }}     <!-- yen -->
{{ when   | date:'medium' }}                       <!-- locale-aware -->
{{ count  | number:'1.0-2' }}
```

### Date / Number Formatting Outside Pipes

```typescript
private locale = inject(LOCALE_ID);
formatPrice(n: number): string {
  return new Intl.NumberFormat(this.locale, { style: 'currency', currency: 'JPY' }).format(n);
}
```

Prefer `Intl.*` over hand-rolled formatting for any user-visible number, date, or list.

### Right-to-Left

```html
<html [attr.dir]="locale === 'ar' ? 'rtl' : 'ltr'">
```

CSS uses logical properties (`margin-inline-start`, `padding-block`) instead of `margin-left` so layouts mirror automatically.

### Translation Keys Hygiene

- Namespace keys: `feature.area.element` (`dashboard.header.title`), not flat strings.
- Do not translate proper nouns or brand names unless the brand book says so.
- Pluralization always via ICU - even for English-only-for-now apps that may add locales later.
- Avoid sentence fragments concatenated in code (`'Hello, ' + name`) - whole-sentence translations only.

## Output Format

```
## i18n Plan

**Library:** @angular/localize (build-time) | transloco | ngx-translate
**Source locale:** {e.g. en-US}
**Target locales:** {list}
**Routing strategy:** per-locale baseHref | runtime switch
**SSR:** per-locale build | single build with runtime language

### Strings Inventory (delta)

| Location           | Key / ID                  | ICU? | Notes        |
| ------------------ | ------------------------- | ---- | ------------ |

### Recommendations

- {recommendation}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Mixing `@angular/localize` and a runtime library in the same app
- Auto-hashed `i18n` IDs - every copy edit breaks the translation file
- String concatenation for plurals or genders
- Hardcoded `en` formatting (`new Date().toLocaleString()` without a locale arg) leaking into a localized app
- Forgetting attribute translations (`title`, `aria-label`, `placeholder`, `alt`)
- Forgetting `registerLocaleData(...)` for runtime locale switching - pipes silently fall back to `en`
- One giant `messages.xlf` per app in a multi-team monorepo - split by feature lib
