---
name: angular-component-patterns
description: Angular component design - standalone components, signals, input/output, content projection, control flow (@if/@for/@switch), OnPush change detection, and TypeScript patterns for Angular 21+.
metadata:
  category: frontend
  tags: [angular, components, standalone, signals, content-projection, onpush, typescript]
user-invocable: false
---

# Angular Component Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing component architecture for a new feature
- Choosing between standalone components and NgModule-based components
- Implementing content projection, control flow, and OnPush change detection
- Adding error handling for component subtrees
- Reviewing component design for reusability and correctness

## Rules

- Standalone components by default - no NgModules for new components
- OnPush change detection on every component - no exceptions
- Use signals for component state - avoid manual change detection triggers
- Content projection over prop-heavy configuration
- Single responsibility - each component does one thing; split when responsibilities diverge
- Inputs must be typed - use `input()` / `input.required()` signal-based inputs
- Outputs must use `output()` function for signal-based event emission
- Use new control flow syntax (`@if`, `@for`, `@switch`) instead of structural directives (`*ngIf`, `*ngFor`, `*ngSwitch`)

## Patterns

### Standalone Component Structure

**Bad** - NgModule-based component:

```typescript
@NgModule({
  declarations: [UserCardComponent],
  imports: [CommonModule],
  exports: [UserCardComponent],
})
export class UserCardModule {}

@Component({
  selector: "app-user-card",
  templateUrl: "./user-card.component.html",
})
export class UserCardComponent {
  @Input() user!: User;
}
```

Problem: NgModule boilerplate, indirect dependency management, harder tree-shaking.

**Good** - Standalone component:

```typescript
@Component({
  selector: "app-user-card",
  standalone: true,
  imports: [DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="user-card">
      <h3>{{ user().name }}</h3>
      <p>{{ user().email }}</p>
      <time>{{ user().joinedAt | date: "mediumDate" }}</time>
    </article>
  `,
})
export class UserCardComponent {
  user = input.required<User>();
}
```

### Signal-Based Inputs and Outputs

```typescript
@Component({
  selector: "app-product-card",
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article>
      <h3>{{ product().name }}</h3>
      <p>{{ formattedPrice() }}</p>
      @if (showActions()) {
        <button (click)="onAddToCart()">Add to Cart</button>
      }
    </article>
  `,
})
export class ProductCardComponent {
  // Required input
  product = input.required<Product>();
  // Optional input with default
  showActions = input(true);

  // Computed from inputs (signal-based)
  formattedPrice = computed(() =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(this.product().price),
  );

  // Output
  addToCart = output<Product>();

  onAddToCart() {
    this.addToCart.emit(this.product());
  }
}
```

### Model Inputs (Two-Way Binding)

```typescript
@Component({
  selector: "app-search-input",
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <input
      [value]="query()"
      (input)="query.set($any($event.target).value)"
      placeholder="Search..."
    />
  `,
})
export class SearchInputComponent {
  query = model(""); // two-way bindable signal
}

// Usage:
// <app-search-input [(query)]="searchTerm" />
```

### Content Projection

**Bad** - Prop-heavy configuration:

```typescript
@Component({
  template: `
    <div class="card">
      <div class="header">{{ title }}</div>
      <div class="icon">
        <ng-container *ngComponentOutlet="iconComponent" />
      </div>
      <div class="body">{{ content }}</div>
      <div class="footer">{{ footerText }}</div>
    </div>
  `,
})
export class CardComponent {
  @Input() title = "";
  @Input() content = "";
  @Input() footerText = "";
  @Input() iconComponent: any;
}
```

**Good** - Content projection with named slots:

```typescript
@Component({
  selector: "app-card",
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="card">
      <header class="card-header">
        <ng-content select="[card-icon]" />
        <ng-content select="[card-title]" />
      </header>
      <div class="card-body">
        <ng-content />
      </div>
      <footer class="card-footer">
        <ng-content select="[card-footer]" />
      </footer>
    </article>
  `,
})
export class CardComponent {}

// Usage:
// <app-card>
//   <mat-icon card-icon>shopping_cart</mat-icon>
//   <h3 card-title>Order #123</h3>
//   <p>Order details here...</p>
//   <button card-footer (click)="view()">View</button>
// </app-card>
```

### Control Flow Syntax

```typescript
@Component({
  template: `
    <!-- @if replaces *ngIf -->
    @if (user(); as user) {
      <app-user-card [user]="user" />
    } @else {
      <app-skeleton />
    }

    <!-- @for replaces *ngFor - track is required -->
    @for (item of items(); track item.id) {
      <app-item-card [item]="item" />
    } @empty {
      <p>No items found</p>
    }

    <!-- @switch replaces *ngSwitch -->
    @switch (status()) {
      @case ("loading") {
        <app-spinner />
      }
      @case ("error") {
        <app-error-state [message]="errorMessage()" />
      }
      @case ("success") {
        <app-content [data]="data()" />
      }
    }
  `,
})
export class DashboardComponent {
  user = input<User | null>(null);
  items = input.required<Item[]>();
  status = input.required<"loading" | "error" | "success">();
  data = input<DashboardData | null>(null);
  errorMessage = input("");
}
```

### OnPush Change Detection

OnPush components only re-render when:

1. An input reference changes
2. A signal value changes
3. An event handler runs in the component
4. The `async` pipe receives a new value
5. `markForCheck()` is called (avoid when possible)

```typescript
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2>{{ title() }}</h2>
    <p>Count: {{ count() }}</p>
    <button (click)="increment()">+1</button>
  `,
})
export class CounterComponent {
  title = input("Counter");
  count = signal(0);

  increment() {
    this.count.update((c) => c + 1); // triggers change detection via signal
  }
}
```

**Bad** - Mutating object without signal update:

```typescript
// This will NOT trigger change detection with OnPush
this.items.push(newItem); // mutating array reference
```

**Good** - Creating new reference:

```typescript
this.items = signal<Item[]>([]);
// Update with new reference
this.items.update((items) => [...items, newItem]);
```

### Error Handling

Angular does not have React-style error boundaries. Use `ErrorHandler` for global error handling and local try-catch in services:

```typescript
// Global error handler
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  constructor(private readonly logger: LoggingService) {}

  handleError(error: unknown): void {
    this.logger.error("Unhandled error", error);
    // Report to error tracking service
  }
}

// Register in app config
export const appConfig: ApplicationConfig = {
  providers: [{ provide: ErrorHandler, useClass: GlobalErrorHandler }],
};

// Component-level error state
@Component({
  template: `
    @if (error()) {
      <div role="alert">
        <p>{{ error() }}</p>
        <button (click)="retry()">Try again</button>
      </div>
    } @else {
      <ng-content />
    }
  `,
})
export class ErrorStateComponent {
  error = input<string | null>(null);
  retryAction = output<void>();

  retry() {
    this.retryAction.emit();
  }
}
```

### Deferred Loading (@defer)

Use `@defer` to lazy-load heavy child components, reducing initial bundle and improving perceived performance:

```typescript
@Component({
  template: `
    <app-header />
    <app-product-filters />

    @for (product of products(); track product.id) {
      @defer (on viewport) {
        <app-product-card [product]="product" />
      } @placeholder {
        <div
          class="product-skeleton h-48 animate-pulse bg-gray-200 rounded-lg"
        ></div>
      } @loading (minimum 200ms) {
        <app-spinner />
      }
    }
  `,
})
export class ProductListComponent {
  products = input.required<Product[]>();
}
```

**Trigger options:**

| Trigger          | When to Use                                    |
| ---------------- | ---------------------------------------------- |
| `on viewport`    | Below-the-fold content (product cards, charts) |
| `on idle`        | Non-critical UI (analytics, ads)               |
| `on interaction` | Content shown after user action (tabs, modals) |
| `on hover`       | Prefetch on hover (navigation targets)         |
| `on timer(Xms)`  | Delayed loading after page stabilizes          |
| `when condition` | Conditional loading based on signal/expression |

### Component Communication Patterns

| Pattern            | When to Use                              | Example                         |
| ------------------ | ---------------------------------------- | ------------------------------- |
| Input/Output       | Parent-child, 1-2 levels deep            | Form field to form container    |
| Model input        | Two-way binding for form-like components | Search input, toggle, slider    |
| Service (shared)   | Sibling or distant components            | Cart state, notifications       |
| Content projection | Flexible layout composition              | Card, dialog, layout containers |
| Inject + provide   | Subtree-scoped configuration             | Theme, feature flags            |

## Output Format

Consuming workflow skills depend on this structure.

```
## Component Design

**Stack:** {detected framework}
**Component model:** {Standalone | NgModule}

### Component Tree

{ComponentName} (standalone) - {responsibility}
  ├── {ChildA} (standalone) - {responsibility}
  └── {ChildB} (standalone) - {responsibility}

### Component Specifications

| Component      | Standalone | Inputs                 | State          | Pattern            |
| -------------- | ---------- | ---------------------- | -------------- | ------------------ |
| {name}         | Yes        | {key inputs}           | {signal fields}| Content projection |
| {name}         | Yes        | {key inputs}           | {signal fields}| Simple             |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- NgModules for new code (use standalone components)
- Default change detection strategy (always use OnPush)
- `@Input()` and `@Output()` decorators in new code (use `input()` and `output()` functions)
- `*ngIf`, `*ngFor`, `*ngSwitch` structural directives (use `@if`, `@for`, `@switch` control flow)
- Prop drilling through more than 2 levels (use services, content projection, or inject/provide)
- God components that handle multiple unrelated concerns
- Direct DOM manipulation with `ElementRef.nativeElement` (use Angular templating)
- Inline types on complex components (use named interfaces)
- Deeply nested ternaries in templates (extract to computed signals or sub-components)
