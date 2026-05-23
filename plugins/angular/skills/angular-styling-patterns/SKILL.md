---
name: angular-styling-patterns
description: Angular styling: ViewEncapsulation, Tailwind, Angular Material/CDK, PrimeNG, CSS custom properties, theming, responsive design.
metadata:
  category: frontend
  tags: [angular, styling, tailwind, angular-material, css, theming, responsive]
user-invocable: false
---

# Angular Styling Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a styling approach for an Angular project
- Implementing responsive design, dark mode, or design tokens
- Integrating Angular Material/CDK or PrimeNG
- Reviewing styling patterns for consistency

## Rules

- Follow the project's established styling approach; do not mix paradigms.
- Tailwind for new greenfield projects; Angular Material + CDK when a mature component library is required.
- Mobile-first responsive design; dark mode via CSS custom properties or Tailwind `dark:` variant.
- Keep `ViewEncapsulation.Emulated` (default). Use `ShadowDom` only for true isolation; never `None`.
- Theme via CSS custom properties or Tailwind config. No hardcoded colors, no `!important`, no `::ng-deep`.

## Patterns

### Styling Approach Selection

| Approach              | When to Use                                    |
| --------------------- | ---------------------------------------------- |
| Tailwind CSS          | New projects, rapid development, custom UI     |
| Angular Material      | Enterprise, accessibility-first, Material spec |
| PrimeNG               | Rich prebuilt widget library                   |
| Component SCSS        | Scoped styles, complex animations              |
| CSS custom properties | Design tokens, theming, runtime customization  |

### Tailwind: Variants via `computed`

```typescript
@Component({
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button [class]="classes()"><ng-content /></button>`,
})
export class ButtonComponent {
  variant = input<"primary" | "secondary" | "destructive">("primary");
  size = input<"sm" | "md" | "lg">("md");

  private static readonly BASE =
    "inline-flex items-center justify-center rounded-lg font-medium focus-visible:ring-2";
  private static readonly VARIANTS = {
    primary: "bg-blue-600 text-white hover:bg-blue-700 disabled:bg-blue-300",
    secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200",
    destructive: "bg-red-600 text-white hover:bg-red-700",
  };
  private static readonly SIZES = {
    sm: "h-8 px-3 text-sm",
    md: "h-10 px-4 text-sm",
    lg: "h-12 px-6 text-base",
  };

  classes = computed(
    () =>
      `${ButtonComponent.BASE} ${ButtonComponent.VARIANTS[this.variant()]} ${ButtonComponent.SIZES[this.size()]}`,
  );
}
```

### Angular Material

```typescript
// app.config.ts
providers: [provideAnimationsAsync()];

@Component({
  standalone: true,
  imports: [MatButtonModule, MatCardModule],
  template: `
    <mat-card>
      <mat-card-title>{{ user().name }}</mat-card-title>
      <mat-card-actions>
        <button mat-button (click)="edit.emit()">Edit</button>
        <button mat-button color="warn" (click)="delete.emit()">Delete</button>
      </mat-card-actions>
    </mat-card>
  `,
})
export class UserCardComponent {
  user = input.required<User>();
  edit = output<void>();
  delete = output<void>();
}
```

For unstyled primitives (dropdowns, dialogs, focus traps), use `@angular/cdk` directives (`CdkOverlayOrigin`, `CdkConnectedOverlay`, `cdkTrapFocus`) and style with your chosen approach.

### Design Tokens with CSS Custom Properties

```css
/* styles.css */
:root {
  --color-primary: #2563eb;
  --color-surface: #ffffff;
  --color-text: #111827;
  --radius-md: 0.5rem;
}
.dark {
  --color-primary: #3b82f6;
  --color-surface: #111827;
  --color-text: #f9fafb;
}
```

```typescript
@Component({
  styles: [
    `
      :host {
        display: block;
        background: var(--color-surface);
        color: var(--color-text);
        border-radius: var(--radius-md);
      }
    `,
  ],
})
export class CardComponent {}
```

### Responsive Design (mobile-first)

```css
:host {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}
@media (min-width: 768px) {
  :host {
    grid-template-columns: 250px 1fr;
  }
}
```

### Host Binding with Signals

```typescript
@Component({
  host: {
    "[class.is-active]": "isActive()",
    "[class.is-disabled]": "disabled()",
    "[attr.aria-disabled]": "disabled()",
  },
})
export class TabComponent {
  isActive = input(false);
  disabled = input(false);
}
```

### ViewEncapsulation

| Mode       | Use                                                           |
| ---------- | ------------------------------------------------------------- |
| `Emulated` | Default. Scoped styles via attribute selectors.               |
| `ShadowDom`| True isolation; styles cannot be pierced from outside.        |
| `None`     | Avoid. Component styles leak globally.                        |

## Output Format

```
## Styling Architecture

**Styling approach:** {Tailwind | Angular Material | PrimeNG | Component SCSS}
**Component library:** {Angular Material | PrimeNG | CDK only | None}

### Design Tokens

| Token Category | Source                           |
| -------------- | -------------------------------- |
| Colors         | {CSS vars | Tailwind config}     |
| Spacing        | {Tailwind default | custom}      |
| Typography     | {font families and scale}        |
| Dark mode      | {class strategy | media query}   |

### Component Variants

| Component | Variants                           | Approach        |
| --------- | ---------------------------------- | --------------- |
| Button    | primary, secondary, destructive    | computed class  |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- `ViewEncapsulation.None`, `::ng-deep`, `!important` for overrides.
- Mixing styling paradigms in one project.
- Inline styles or hardcoded colors instead of tokens/utilities.
- Desktop-first breakpoints.
- Reimplementing primitives that Angular Material/CDK already provides.
