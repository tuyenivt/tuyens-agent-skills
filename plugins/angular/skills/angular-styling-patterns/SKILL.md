---
name: angular-styling-patterns
description: Angular styling patterns - ViewEncapsulation, Tailwind CSS, Angular Material/CDK, PrimeNG, CSS custom properties, theme system, and responsive design for Angular 21+.
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
- Reviewing styling patterns for consistency and maintainability
- Setting up a theme system with CSS custom properties

## Rules

- Use the project's established styling approach - do not mix paradigms without good reason
- Tailwind CSS is the primary recommendation for new projects without a component library
- Angular Material + CDK for projects needing a mature component library
- Responsive design must be mobile-first
- Dark mode must use CSS custom properties or Tailwind's `dark:` variant
- ViewEncapsulation should be Emulated (default) unless there's a reason to change
- Never use `ViewEncapsulation.None` without understanding the global CSS impact

## Patterns

### Styling Approach Selection

| Approach              | When to Use                                    | Encapsulation |
| --------------------- | ---------------------------------------------- | ------------- |
| Tailwind CSS          | New projects, rapid development, custom UI     | N/A (utility) |
| Angular Material      | Enterprise, accessibility-first, Material spec | Emulated      |
| PrimeNG               | Rich component library, many prebuilt widgets  | Emulated      |
| Component SCSS        | Scoped styles, complex animations              | Emulated      |
| CSS custom properties | Design tokens, theming, runtime customization  | N/A (global)  |

### Tailwind CSS in Angular

```typescript
@Component({
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button [class]="buttonClasses()" [disabled]="disabled()">
      <ng-content />
    </button>
  `,
})
export class ButtonComponent {
  variant = input<"primary" | "secondary" | "destructive">("primary");
  size = input<"sm" | "md" | "lg">("md");
  disabled = input(false);

  buttonClasses = computed(() => {
    const base =
      "inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2";

    const variants: Record<string, string> = {
      primary: "bg-blue-600 text-white hover:bg-blue-700 disabled:bg-blue-300",
      secondary:
        "bg-gray-100 text-gray-900 hover:bg-gray-200 disabled:bg-gray-50",
      destructive: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
    };

    const sizes: Record<string, string> = {
      sm: "h-8 px-3 text-sm",
      md: "h-10 px-4 text-sm",
      lg: "h-12 px-6 text-base",
    };

    return `${base} ${variants[this.variant()]} ${sizes[this.size()]}`;
  });
}
```

### Angular Material/CDK

```typescript
// app.config.ts - configure Material theme
import { provideAnimationsAsync } from "@angular/platform-browser/animations/async";

export const appConfig: ApplicationConfig = {
  providers: [provideAnimationsAsync()],
};

// Component using Material
@Component({
  standalone: true,
  imports: [MatButtonModule, MatCardModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card>
      <mat-card-header>
        <mat-icon mat-card-avatar>person</mat-icon>
        <mat-card-title>{{ user().name }}</mat-card-title>
        <mat-card-subtitle>{{ user().role }}</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <p>{{ user().bio }}</p>
      </mat-card-content>
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

### CDK for Custom Components

```typescript
// Using CDK Overlay for custom dropdown
import { CdkOverlayOrigin, CdkConnectedOverlay } from "@angular/cdk/overlay";

@Component({
  standalone: true,
  imports: [CdkOverlayOrigin, CdkConnectedOverlay],
  template: `
    <button
      cdkOverlayOrigin
      #trigger="cdkOverlayOrigin"
      (click)="isOpen.set(!isOpen())"
    >
      {{ selectedLabel() }}
    </button>
    <ng-template
      cdkConnectedOverlay
      [cdkConnectedOverlayOrigin]="trigger"
      [cdkConnectedOverlayOpen]="isOpen()"
    >
      <div class="dropdown-panel">
        <ng-content />
      </div>
    </ng-template>
  `,
})
export class DropdownComponent {
  isOpen = signal(false);
  selectedLabel = input("Select...");
}
```

### ViewEncapsulation

```typescript
// Default - Emulated (scoped styles via attribute selectors)
@Component({
  encapsulation: ViewEncapsulation.Emulated, // default, can omit
  styles: [
    `
      :host {
        display: block;
        padding: 1rem;
      }
      .title {
        font-size: 1.5rem; /* scoped to this component only */
      }
    `,
  ],
})
export class CardComponent {}

// ShadowDom - true encapsulation via native Shadow DOM
@Component({
  encapsulation: ViewEncapsulation.ShadowDom,
  styles: [
    `
      :host {
        display: block;
      }
      /* Styles are truly encapsulated - cannot be overridden from outside */
    `,
  ],
})
export class IsolatedWidgetComponent {}
```

### Design Tokens with CSS Custom Properties

```css
/* styles.css - global design tokens */
:root {
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-surface: #ffffff;
  --color-text: #111827;
  --color-border: #e5e7eb;
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px rgb(0 0 0 / 0.1);
}

.dark {
  --color-primary: #3b82f6;
  --color-primary-hover: #60a5fa;
  --color-surface: #111827;
  --color-text: #f9fafb;
  --color-border: #374151;
}
```

```typescript
// Component using design tokens
@Component({
  styles: [
    `
      :host {
        display: block;
        background: var(--color-surface);
        color: var(--color-text);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-sm);
      }
    `,
  ],
})
export class CardComponent {}
```

### Responsive Design

```css
/* Mobile-first with component styles */
:host {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

@media (min-width: 768px) {
  :host {
    grid-template-columns: 250px 1fr;
    gap: 1.5rem;
  }
}

@media (min-width: 1024px) {
  :host {
    gap: 2rem;
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

## Output Format

Consuming workflow skills depend on this structure.

```
## Styling Architecture

**Stack:** {detected framework}
**Styling approach:** {Tailwind CSS | Angular Material | PrimeNG | Component SCSS}
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
| Card      | default, outlined                  | CSS vars        |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- `ViewEncapsulation.None` without understanding the global CSS impact
- Mixing multiple styling paradigms inconsistently (pick one approach per project)
- Inline styles for static values (use classes, CSS variables, or Tailwind utilities)
- Desktop-first responsive design (mobile-first is the standard)
- Hardcoded color values instead of design tokens or Tailwind classes
- `::ng-deep` for piercing encapsulation (deprecated, fragile - use CSS custom properties or CDK theming)
- Using `!important` to override styles (indicates specificity issues)
- Creating custom components when Angular Material/CDK already provides them
