---
name: angular-signals-patterns
description: Angular Signals - signal/computed/effect, toSignal/toObservable bridge, signal inputs, resource(), linkedSignal, signal services.
metadata:
  category: frontend
  tags: [angular, signals, computed, effect, reactive, state, toSignal]
user-invocable: false
---

# Angular Signals Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Component-local reactive state and derived values
- Bridging RxJS observables and signals
- Side effects triggered by signal changes
- Migrating BehaviorSubject-based component state to signals

## Rules

- Signals are the default for component state in new code; prefer over BehaviorSubject
- `computed()` for derived state; `effect()` only for true side effects (DOM, storage, logging)
- Treat signal values as immutable - always pass a new reference on update
- `toSignal()` requires `initialValue` or `requireSync: true` unless the source emits synchronously
- Services expose signals via `.asReadonly()`; keep writable signals private
- No circular dependencies between computed signals

## Patterns

### Updating Signals

```typescript
const count = signal(0);
count.set(5);
count.update((c) => c + 1);

// Bad - mutation does not notify
user().name = "Bob";
items().push(newItem);

// Good - new reference
user.update((u) => ({ ...u, name: "Bob" }));
items.update((list) => [...list, newItem]);
items.update((list) => list.filter((i) => i.id !== id));
```

### Computed vs Effect

```typescript
// Bad - effect synchronising derived state
double = signal(0);
constructor() {
  effect(() => this.double.set(this.count() * 2));
}

// Good - computed
double = computed(() => this.count() * 2);
```

`effect()` is reserved for side effects outside the signal graph:

```typescript
constructor() {
  effect(() => localStorage.setItem("theme", this.theme()));

  effect((onCleanup) => {
    const id = setInterval(() => this.tick(), 1000);
    onCleanup(() => clearInterval(id));
  });
}
```

### toSignal / toObservable

```typescript
// Observable -> signal at the component boundary
user = toSignal(this.userService.getUser(id), { initialValue: null });

// Synchronous source (BehaviorSubject, store selector)
count = toSignal(this.store.select(selectCount), { requireSync: true });

// Signal -> observable to apply RxJS operators
search = signal("");
results = toSignal(
  toObservable(this.search).pipe(
    debounceTime(300),
    filter((t) => t.length >= 2),
    switchMap((t) => this.searchService.search(t)),
  ),
  { initialValue: [] },
);
```

### Signal-Based Service

```typescript
@Injectable({ providedIn: "root" })
export class CartService {
  private readonly _items = signal<CartItem[]>([]);

  readonly items = this._items.asReadonly();
  readonly total = computed(() =>
    this._items().reduce((sum, i) => sum + i.price * i.quantity, 0),
  );

  addItem(item: CartItem): void {
    this._items.update((items) => {
      const existing = items.find((i) => i.id === item.id);
      return existing
        ? items.map((i) =>
            i.id === item.id ? { ...i, quantity: i.quantity + 1 } : i,
          )
        : [...items, { ...item, quantity: 1 }];
    });
  }
}
```

### resource() - Async Data (Angular 19+)

Prefer `resource()` over manual `signal + toObservable + switchMap` for async data driven by signal inputs; it provides `status`, `value`, `error` signals.

```typescript
productId = input.required<string>();

productResource = resource({
  request: () => this.productId(),
  loader: ({ request: id }) => this.productService.getProduct(id),
});
```

```html
@switch (productResource.status()) {
  @case ("loading") { <app-spinner /> }
  @case ("error") { <app-error [error]="productResource.error()" /> }
  @case ("resolved") { <app-product [product]="productResource.value()!" /> }
}
```

### linkedSignal (Angular 19+)

Writable signal that resets when a source signal changes - use when a user selection must follow upstream changes.

```typescript
selectedCategory = signal("all");
filteredProducts = computed(() =>
  this.selectedCategory() === "all"
    ? this.products()
    : this.products().filter((p) => p.category === this.selectedCategory()),
);

// Resets to first product whenever filteredProducts changes
selectedProduct = linkedSignal(() => this.filteredProducts()[0]?.id ?? "");
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Signals Architecture

**Stack:** {detected framework}
**Angular version:** {detected version}

### Signal Map

| Signal       | Type                              | Scope                | Source                            |
| ------------ | --------------------------------- | -------------------- | --------------------------------- |
| {name}       | Writable | Computed | Bridged | Component | Service | signal() | computed() | toSignal() |

### Effects

| Purpose      | Triggers      | Cleanup Required |
| ------------ | ------------- | ---------------- |
| {desc}       | {signal deps} | {Yes | No}       |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- `effect()` that writes to other signals (use `computed()`)
- Mutating signal values in place
- Exposing writable signals from services
- `toSignal()` without `initialValue`/`requireSync` on async sources
- Circular computed dependencies
- Manual observable subscriptions where `toSignal()` fits
