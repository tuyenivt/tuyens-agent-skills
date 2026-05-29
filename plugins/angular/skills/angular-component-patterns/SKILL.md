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

- Standalone + OnPush for every new component. `standalone: true` is default on Angular 19+; explicit on older versions. No NgModules.
- Signal inputs/outputs only: `input()`, `input.required()`, `output()`, `model()`. No `@Input()`/`@Output()` decorators.
- New control flow only: `@if`, `@for` (with `track item.id`, never `$index` on dynamic lists), `@switch`. No `*ngIf`/`*ngFor`/`*ngSwitch`.
- Prefer content projection (named slots) over `showX`/`showY` boolean flags or configuration props.
- Prop drilling stops at 2 levels - escalate to service, projection, or provide/inject.
- One responsibility per component; split when concerns diverge.
- No `ElementRef.nativeElement` DOM access; template-driven only.

## Patterns

### Standalone + Signal IO

```typescript
@Component({
  selector: "app-product-card",
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

Required vs nullable: use `input.required<T>()` and wrap consumers in `@if (x(); as v)`. Reserve `input<T | null>(null)` for genuinely optional data.

### Model Inputs (Two-Way Binding)

Use `model()` when the parent reads and writes the same value:

```typescript
query = model("");
// Parent: <app-search-input [(query)]="searchTerm" />
```

### Content Projection over Boolean Flags

**Bad** - boolean flag explosion:

```typescript
@Input() showIcon = false;
@Input() showActions = true;
@Input() showFooter = true;
@Input() theme = "light";
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

### Deferred Loading (@defer)

```typescript
@defer (on viewport) {
  <app-chart [data]="data()" />
} @placeholder {
  <div class="skeleton h-64 w-full"></div>
}
```

Triggers: `on viewport` (below-the-fold), `on interaction` (tabs/modals), `on hover` (prefetch), `when <expr>` (signal-gated). Default `on idle` is rarely intended. `@placeholder` with reserved dimensions prevents CLS.

### Communication Choices

| Pattern            | Use for                                  |
| ------------------ | ---------------------------------------- |
| Input/output       | Parent-child, 1-2 levels                 |
| `model()`          | Two-way bindable form-like component     |
| Service (signals)  | Siblings, distant components, app state  |
| Content projection | Flexible layout composition              |
| `provide`/`inject` | Subtree-scoped config (theme, flags)     |

OnPush re-renders when: input reference changes, a read signal changes, a template event fires, or `async` emits. Reaching for `markForCheck()` signals the source should be a signal.

## Output Format

```
## Component Design

**Angular version:** {detected}

### Component Tree

{Root} - {responsibility}
  ├── {ChildA} - {responsibility}
  └── {ChildB} - {responsibility}

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

Components are standalone + OnPush by default; call out exceptions explicitly. Omit `Issues Found` for greenfield design.

## Avoid

- God components combining unrelated concerns.
- Prop drilling past 2 levels.
- Boolean flag explosion (`showX`/`showY`) where content projection fits.
- Deeply nested template ternaries; extract to `computed()` or sub-components.
- `markForCheck()` to fix stale views; convert the source to a signal.
- Mixing legacy decorators/structural directives with new APIs in the same component.
