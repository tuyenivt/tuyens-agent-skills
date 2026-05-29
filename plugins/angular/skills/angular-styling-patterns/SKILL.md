---
name: angular-styling-patterns
description: Angular styling - Tailwind + Angular Material hybrid, CSS custom properties, theming, dark mode toggle, design tokens.
metadata:
  category: frontend
  tags: [angular, styling, tailwind, angular-material, css, theming, responsive]
user-invocable: false
---

# Angular Styling Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a styling approach for an Angular project
- Implementing dark mode, design tokens, or responsive design
- Integrating Angular Material/CDK or PrimeNG with Tailwind
- Reviewing styling patterns for consistency

## Rules

- Follow the project's established styling approach; do not mix paradigms within one component.
- Tailwind for greenfield. Add Angular Material selectively when prebuilt complex widgets (dialog, table, datepicker) are required - hybrid is the common case.
- Theme via CSS custom properties (single source) consumed by both Tailwind config and Material theme.
- Mobile-first responsive design.
- Keep `ViewEncapsulation.Emulated` (default). Use `ShadowDom` only for true isolation; never `None`. No `::ng-deep`, no `!important` for overrides.

## Patterns

### Styling Approach Selection

| Approach              | When to Use                                    |
| --------------------- | ---------------------------------------------- |
| Tailwind CSS          | Greenfield, rapid development, custom UI       |
| Angular Material      | Enterprise, accessibility-first, Material spec |
| Tailwind + Material   | Custom UI with Material's complex widgets      |
| Component SCSS        | Scoped styles, complex animations              |
| CSS custom properties | Design tokens, theming, runtime customization  |

### Tailwind: Variants via `computed`

```typescript
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button [class]="classes()"><ng-content /></button>`,
})
export class ButtonComponent {
  variant = input<"primary" | "secondary" | "destructive">("primary");
  size = input<"sm" | "md" | "lg">("md");

  private static readonly BASE = "inline-flex items-center justify-center rounded-lg font-medium focus-visible:ring-2";
  private static readonly VARIANTS = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-300",
    secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100",
    destructive: "bg-red-600 text-white hover:bg-red-700",
  };
  private static readonly SIZES = { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-base" };

  classes = computed(() =>
    `${ButtonComponent.BASE} ${ButtonComponent.VARIANTS[this.variant()]} ${ButtonComponent.SIZES[this.size()]}`,
  );
}
```

### Design Tokens (CSS Custom Properties)

Tokens live in CSS; Tailwind config and Material theme both reference them.

```css
/* styles.css */
:root {
  --brand-50: #eff6ff;
  --brand-600: #2563eb;
  --brand-700: #1d4ed8;
  --surface: #ffffff;
  --text: #111827;
}
.dark {
  --surface: #111827;
  --text: #f9fafb;
}
```

```typescript
// tailwind.config.ts
export default {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "rgb(var(--brand-50) / <alpha-value>)",
          600: "var(--brand-600)",
          700: "var(--brand-700)",
        },
        surface: "var(--surface)",
      },
    },
  },
};
```

### Dark Mode Toggle (SSR-safe)

```typescript
@Injectable({ providedIn: "root" })
export class ThemeService {
  private readonly platformId = inject(PLATFORM_ID);
  readonly mode = signal<"light" | "dark">(this.load());

  constructor() {
    effect(() => {
      if (!isPlatformBrowser(this.platformId)) return;
      document.documentElement.classList.toggle("dark", this.mode() === "dark");
      localStorage.setItem("theme", this.mode());
    });
  }

  toggle(): void { this.mode.update((m) => (m === "dark" ? "light" : "dark")); }
  private load(): "light" | "dark" {
    if (!isPlatformBrowser(this.platformId)) return "light";
    return (localStorage.getItem("theme") as "light" | "dark") ?? "light";
  }
}
```

### Tailwind + Angular Material Coexistence

- Disable Tailwind's `preflight` only if it conflicts with Material; usually fine.
- `@layer` order in `styles.css`: `@tailwind base; @tailwind components; @tailwind utilities;` then Material theme imports last so Material tokens win where they overlap.
- Reuse design tokens: pass CSS-var-backed colors into `mat.define-theme()` so brand colors stay in sync.

```typescript
// Import Material widgets per-component (tree-shake friendly)
@Component({
  imports: [MatDialogModule, MatTableModule],
  template: `
    <mat-table [dataSource]="users()" class="!bg-surface">
      <ng-container matColumnDef="name">
        <mat-header-cell *matHeaderCellDef class="text-text">Name</mat-header-cell>
        <mat-cell *matCellDef="let u">{{ u.name }}</mat-cell>
      </ng-container>
    </mat-table>
  `,
})
export class UserTableComponent { users = input.required<User[]>(); }
```

### Host Binding with Signals

```typescript
@Component({
  host: {
    "[class.is-active]": "isActive()",
    "[attr.aria-disabled]": "disabled()",
  },
})
export class TabComponent {
  isActive = input(false);
  disabled = input(false);
}
```

### Responsive Design (mobile-first)

```css
:host { display: grid; grid-template-columns: 1fr; gap: 1rem; }
@media (min-width: 768px) { :host { grid-template-columns: 250px 1fr; } }
```

Or Tailwind: `grid grid-cols-1 md:grid-cols-[250px_1fr] gap-4`.

## Output Format

```
## Styling Architecture

**Approach:** {Tailwind | Material | Tailwind+Material | SCSS}
**Component library:** {Angular Material | PrimeNG | CDK only | None}

### Design Tokens

| Token Category | Source                                |
| -------------- | ------------------------------------- |
| Colors         | CSS vars (`--brand-*`) + Tailwind ref |
| Spacing        | Tailwind default                      |
| Typography     | {font families and scale}             |
| Dark mode      | class strategy + ThemeService         |

### Component Variants

| Component | Variants                           | Approach        |
| --------- | ---------------------------------- | --------------- |
| Button    | primary, secondary, destructive    | computed class  |

### Theming Strategy

- Token source: {CSS vars / Tailwind config / Material theme}
- Toggle mechanism: {ThemeService signal / class on <html>}

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

Omit `Issues Found` for greenfield design.

## Avoid

- `ViewEncapsulation.None`, `::ng-deep`, `!important` for overrides
- Mixing styling paradigms in one component
- Hardcoded colors instead of tokens/utilities
- Desktop-first breakpoints
- Reimplementing primitives that Material/CDK already provides
- `localStorage` / `document` access without `isPlatformBrowser` guard
