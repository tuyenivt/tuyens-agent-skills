---
name: angular-signals-patterns
description: Angular Signals patterns - signal(), computed(), effect(), toSignal/toObservable bridge, signal-based inputs, model signals, and reactive state management for Angular 21+.
metadata:
  category: frontend
  tags: [angular, signals, computed, effect, reactive, state, toSignal]
user-invocable: false
---

# Angular Signals Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Managing component-local reactive state
- Computing derived values from other signals
- Bridging between RxJS observables and signals
- Reacting to signal changes with side effects
- Migrating from BehaviorSubject to signals for component state

## Rules

- Signals are the primary mechanism for component-local state in new code
- `computed()` for derived values - never store computed values in separate signals
- `effect()` is for side effects (logging, localStorage, external APIs) - not for updating other signals
- Use `toSignal()` to convert observables to signals at the component boundary
- Use `toObservable()` when you need RxJS operators on a signal value
- Signal updates must be immutable - create new references for objects and arrays
- Avoid `effect()` for state synchronization between signals (use `computed()` instead)

## Patterns

### Basic Signal Usage

```typescript
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2>{{ title() }}</h2>
    <p>Count: {{ count() }}</p>
    <p>Double: {{ double() }}</p>
    <button (click)="increment()">+1</button>
    <button (click)="reset()">Reset</button>
  `,
})
export class CounterComponent {
  title = input("Counter");
  count = signal(0);
  double = computed(() => this.count() * 2);

  increment() {
    this.count.update((c) => c + 1);
  }

  reset() {
    this.count.set(0);
  }
}
```

### Signal Update Patterns

```typescript
// Primitive - use set()
const count = signal(0);
count.set(5);
count.update((c) => c + 1);

// Object - create new reference
const user = signal<User>({ name: "Alice", age: 30 });

// Bad - mutating object
user().name = "Bob"; // signal won't detect change

// Good - new reference
user.update((u) => ({ ...u, name: "Bob" }));

// Array - create new reference
const items = signal<Item[]>([]);

// Bad - mutating array
items().push(newItem); // signal won't detect change

// Good - new reference
items.update((list) => [...list, newItem]);

// Remove item
items.update((list) => list.filter((i) => i.id !== itemId));
```

### Computed Signals

```typescript
@Component({
  template: `
    <p>Total: {{ total() | currency }}</p>
    <p>Items: {{ itemCount() }}</p>
    @if (isEmpty()) {
      <p>Your cart is empty</p>
    }
  `,
})
export class CartSummaryComponent {
  private readonly cartService = inject(CartService);

  items = this.cartService.items; // signal from service
  total = computed(() =>
    this.items().reduce((sum, item) => sum + item.price * item.quantity, 0),
  );
  itemCount = computed(() => this.items().length);
  isEmpty = computed(() => this.itemCount() === 0);
}
```

**Bad** - Using effect to sync derived state:

```typescript
// Don't do this - effect for derived state
count = signal(0);
double = signal(0);

constructor() {
  effect(() => {
    this.double.set(this.count() * 2); // anti-pattern
  });
}
```

**Good** - Use computed:

```typescript
count = signal(0);
double = computed(() => this.count() * 2);
```

### Effect for Side Effects

```typescript
@Component({
  template: `
    <select (change)="theme.set($any($event.target).value)">
      <option value="light">Light</option>
      <option value="dark">Dark</option>
    </select>
  `,
})
export class ThemeToggleComponent {
  theme = signal<"light" | "dark">("light");

  constructor() {
    // Persist to localStorage on change
    effect(() => {
      localStorage.setItem("theme", this.theme());
    });

    // Sync with document class
    effect(() => {
      document.documentElement.classList.toggle(
        "dark",
        this.theme() === "dark",
      );
    });
  }
}
```

**Effect cleanup:**

```typescript
constructor() {
  effect((onCleanup) => {
    const id = setInterval(() => this.tick(), 1000);
    onCleanup(() => clearInterval(id));
  });
}
```

### toSignal - Observable to Signal Bridge

```typescript
@Component({
  template: `
    @if (user(); as user) {
      <h2>{{ user.name }}</h2>
    } @else {
      <app-spinner />
    }
  `,
})
export class UserProfileComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly userService = inject(UserService);

  // Convert route params observable to signal
  private readonly userId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get("id")!)),
  );

  // Convert HTTP observable to signal
  user = toSignal(this.userService.getUser(this.userId()!), {
    initialValue: null,
  });
}

// With requireSync for observables that emit synchronously (BehaviorSubject)
@Component({})
export class StoreComponent {
  private readonly store = inject(Store);
  count = toSignal(this.store.select(selectCount), { requireSync: true });
}
```

### toObservable - Signal to Observable Bridge

```typescript
@Component({
  template: `
    <input (input)="search.set($any($event.target).value)" />
    @for (result of results(); track result.id) {
      <app-result-card [result]="result" />
    }
  `,
})
export class SearchComponent {
  private readonly searchService = inject(SearchService);

  search = signal("");

  // Convert signal to observable for debounce/switchMap
  results = toSignal(
    toObservable(this.search).pipe(
      debounceTime(300),
      filter((term) => term.length >= 2),
      switchMap((term) => this.searchService.search(term)),
    ),
    { initialValue: [] },
  );
}
```

### Signal-Based Services

```typescript
@Injectable({ providedIn: "root" })
export class CartService {
  // Private writable signal
  private readonly _items = signal<CartItem[]>([]);

  // Public read-only signal
  readonly items = this._items.asReadonly();
  readonly total = computed(() =>
    this._items().reduce((sum, i) => sum + i.price * i.quantity, 0),
  );
  readonly count = computed(() => this._items().length);

  addItem(item: CartItem): void {
    this._items.update((items) => {
      const existing = items.find((i) => i.id === item.id);
      if (existing) {
        return items.map((i) =>
          i.id === item.id ? { ...i, quantity: i.quantity + 1 } : i,
        );
      }
      return [...items, { ...item, quantity: 1 }];
    });
  }

  removeItem(id: string): void {
    this._items.update((items) => items.filter((i) => i.id !== id));
  }

  clear(): void {
    this._items.set([]);
  }
}
```

### resource() - Signal-Based Async Data (Angular 19+)

`resource()` connects signals to async data fetching, providing built-in loading/error states:

```typescript
@Component({
  template: `
    @switch (productResource.status()) {
      @case ("loading") {
        <app-spinner />
      }
      @case ("error") {
        <app-error-state [error]="productResource.error()" />
      }
      @case ("resolved") {
        <app-product-detail [product]="productResource.value()!" />
      }
    }
  `,
})
export class ProductDetailComponent {
  private readonly productService = inject(ProductService);
  productId = input.required<string>();

  productResource = resource({
    request: () => this.productId(),
    loader: ({ request: id }) => this.productService.getProduct(id),
  });
}
```

Use `resource()` instead of manual signal + `toObservable` + `switchMap` when loading async data that depends on signal inputs. It handles loading/error states automatically.

### linkedSignal (Angular 19+)

```typescript
@Component({
  template: `
    <select (change)="selectedCategory.set($any($event.target).value)">
      @for (cat of categories(); track cat) {
        <option [value]="cat">{{ cat }}</option>
      }
    </select>
    <select (change)="selectedProduct.set($any($event.target).value)">
      @for (product of filteredProducts(); track product.id) {
        <option [value]="product.id">{{ product.name }}</option>
      }
    </select>
  `,
})
export class ProductSelectorComponent {
  categories = input.required<string[]>();
  products = input.required<Product[]>();

  selectedCategory = signal("all");

  filteredProducts = computed(() =>
    this.selectedCategory() === "all"
      ? this.products()
      : this.products().filter((p) => p.category === this.selectedCategory()),
  );

  // Reset selected product when category changes
  selectedProduct = linkedSignal(() => this.filteredProducts()[0]?.id ?? "");
}
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Signals Architecture

**Stack:** {detected framework}
**Angular version:** {detected version}

### Signal Map

| Signal          | Type     | Scope       | Source              |
| --------------- | -------- | ----------- | ------------------- |
| {signalName}    | Writable | Component   | signal()            |
| {signalName}    | Computed | Component   | computed()          |
| {signalName}    | Bridged  | Component   | toSignal()          |

### Effects

| Effect Purpose    | Triggers            | Cleanup Required |
| ----------------- | ------------------- | ---------------- |
| {description}     | {signal deps}       | {Yes | No}       |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Using `effect()` to update other signals (use `computed()` for derived state)
- Mutating signal values directly (create new references for objects/arrays)
- Using BehaviorSubject for simple component-local state (use signals)
- Calling `toSignal()` without `initialValue` or `requireSync` when the observable may not emit synchronously
- Creating circular signal dependencies (A computed from B, B computed from A)
- Using `effect()` where `computed()` would suffice (effects are for side effects, not state derivation)
- Exposing writable signals from services (use `.asReadonly()`)
- Subscribing to observables manually when `toSignal()` handles it
