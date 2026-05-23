---
name: angular-component-patterns
description: Angular component design - standalone, OnPush, signal inputs/outputs/model, content projection, control flow, @defer.
metadata:
  category: frontend
  tags: [angular, components, standalone, signals, content-projection, onpush, defer, typescript]
user-invocable: false
---

# Angular Component Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing component architecture (tree, boundaries, composition)
- Choosing between content projection, inputs, services, or provide/inject
- Migrating legacy components to standalone + signals + new control flow

For signal internals (`computed`, `effect`, `toSignal`, `resource`), use `angular-signals-patterns`.

## Rules

- Standalone + OnPush for every new component; no NgModules.
- Signal inputs/outputs only: `input()`, `input.required()`, `output()`, `model()`. No `@Input()`/`@Output()` decorators.
- New control flow only: `@if`, `@for` (with `track`), `@switch`. No `*ngIf`/`*ngFor`/`*ngSwitch`.
- One responsibility per component; split when concerns diverge.
- Compose via content projection (named slots) before adding configuration inputs.
- Prop drilling stops at 2 levels - escalate to service, projection, or provide/inject.
- No direct DOM access (`ElementRef.nativeElement`); template-driven only.

## Patterns

### Standalone + Signal IO

```typescript
@Component({
  selector: "app-product-card",
  standalone: true,
  imports: [CurrencyPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article>
      <h3>{{ product().name }}</h3>
      <p>{{ product().price | currency }}</p>
      @if (showActions()) {
        <button (click)="addToCart.emit(product())">Add</button>
      }
    </article>
  `,
})
export class ProductCardComponent {
  product = input.required<Product>();
  showActions = input(true);
  addToCart = output<Product>();
}
```

### Model Inputs (Two-Way Binding)

Use `model()` for form-like components that own a value the parent also reads/writes.

```typescript
export class SearchInputComponent {
  query = model("");
}
// <app-search-input [(query)]="searchTerm" />
```

### Content Projection over Configuration

**Bad** - prop-heavy:

```typescript
@Input() title = ""; @Input() icon = ""; @Input() footerText = "";
```

**Good** - named slots:

```typescript
template: `
  <article class="card">
    <header>
      <ng-content select="[card-icon]" />
      <ng-content select="[card-title]" />
    </header>
    <div class="body"><ng-content /></div>
    <footer><ng-content select="[card-footer]" /></footer>
  </article>
`;
// <app-card>
//   <mat-icon card-icon>cart</mat-icon>
//   <h3 card-title>Order</h3>
//   <p>Body</p>
//   <button card-footer>View</button>
// </app-card>
```

### Control Flow

```typescript
@if (user(); as u) { <app-user-card [user]="u" /> } @else { <app-skeleton /> }

@for (item of items(); track item.id) {
  <app-item-card [item]="item" />
} @empty {
  <p>No items</p>
}

@switch (status()) {
  @case ("loading") { <app-spinner /> }
  @case ("error")   { <app-error [message]="errorMessage()" /> }
  @case ("success") { <app-content [data]="data()" /> }
}
```

`track` is required on `@for`. Use a stable id, not `$index`, unless the list is append-only.

### OnPush Mental Model

OnPush re-renders only when: input reference changes, a read signal changes, a template event fires, or `async` pipe emits. Signal-driven components rarely need `markForCheck()`; if you reach for it, the state likely belongs in a signal.

### Deferred Loading (@defer)

```typescript
@for (product of products(); track product.id) {
  @defer (on viewport) {
    <app-product-card [product]="product" />
  } @placeholder {
    <div class="skeleton"></div>
  } @loading (minimum 200ms) {
    <app-spinner />
  }
}
```

| Trigger          | Use for                                |
| ---------------- | -------------------------------------- |
| `on viewport`    | Below-the-fold content                 |
| `on idle`        | Non-critical UI (analytics, ads)       |
| `on interaction` | Revealed by user action (tabs, modals) |
| `on hover`       | Prefetch likely navigation             |
| `on timer(Xms)`  | Delayed loading after page stabilizes  |
| `when expr`      | Signal/expression-gated loading        |

### Error Surfaces

Angular has no error boundary. Pair a global `ErrorHandler` (reports to logging) with component-level error inputs:

```typescript
@Component({
  template: `
    @if (error()) {
      <div role="alert">{{ error() }} <button (click)="retry.emit()">Retry</button></div>
    } @else {
      <ng-content />
    }
  `,
})
export class ErrorStateComponent {
  error = input<string | null>(null);
  retry = output<void>();
}
```

### Communication Choices

| Pattern            | Use for                                  |
| ------------------ | ---------------------------------------- |
| Input/output       | Parent-child, 1-2 levels                 |
| `model()`          | Two-way bindable form-like component     |
| Service (signals)  | Siblings, distant components, app state  |
| Content projection | Flexible layout composition              |
| `provide`/`inject` | Subtree-scoped config (theme, flags)     |

## Output Format

```
## Component Design

**Stack:** {framework + Angular version}

### Component Tree

{Root} (standalone) - {responsibility}
  ├── {ChildA} (standalone) - {responsibility}
  └── {ChildB} (standalone) - {responsibility}

### Component Specifications

| Component | Inputs       | Outputs   | State (signals) | Composition         |
| --------- | ------------ | --------- | --------------- | ------------------- |
| {name}    | {key inputs} | {events}  | {signals}       | {projection/defer}  |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

All listed components are standalone + OnPush by default; call out exceptions explicitly.

## Avoid

- God components combining unrelated concerns; split by responsibility.
- Prop drilling past 2 levels.
- Inline complex types on inputs; use named interfaces.
- Deeply nested ternaries in templates; extract to `computed()` or sub-components.
- `markForCheck()` as a fix for stale views; convert the source to a signal.
- Mixing legacy decorators/structural directives with new APIs in the same component.
