---
name: angular-state-patterns
description: Angular state management - signals (primary), NgRx (enterprise), ComponentStore, service-based state, RxJS BehaviorSubject patterns, and state library selection for Angular 21+.
metadata:
  category: frontend
  tags: [angular, state, signals, ngrx, componentstore, rxjs, behaviorsubject]
user-invocable: false
---

# Angular State Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a state management approach for an Angular feature
- Deciding between signals, services, and NgRx
- Selecting a state library for enterprise or complex applications
- Reviewing existing state management for correctness and performance
- Migrating from BehaviorSubject or NgRx to signals

## Rules

- Start with the simplest state mechanism - upgrade only when proven necessary (signal > signal service > NgRx ComponentStore > NgRx Store)
- Server state belongs in HTTP services with caching - not duplicated in stores
- Every store must have a clear domain boundary - one store per domain
- Derived state must be computed via `computed()` signals - never stored separately
- State updates must be immutable - create new references for objects and arrays
- Prefer signals for component-local and shared state; use NgRx only for enterprise requirements (devtools, time-travel, effects middleware)
- Filters, pagination, sort, and search parameters belong in URL state (route query params) for bookmarkability, shareability, and back/forward button support - not in component signals or services

## Patterns

### State Mechanism Selection

| Mechanism           | When to Use                                   | Example                           |
| ------------------- | --------------------------------------------- | --------------------------------- |
| Signal              | Component-local state                         | Toggle, input value, local flag   |
| Signal service      | Shared state across components                | Cart, user preferences            |
| NgRx ComponentStore | Feature-scoped complex state                  | Feature with many interactions    |
| NgRx Store          | Enterprise: devtools, middleware, time-travel | Large team, complex workflows     |
| URL state           | State that should survive refresh/share       | Filters, sort, pagination, search |

### Signal-Based State Service

```typescript
@Injectable({ providedIn: "root" })
export class CartService {
  private readonly _items = signal<CartItem[]>([]);

  readonly items = this._items.asReadonly();
  readonly total = computed(() =>
    this._items().reduce((sum, i) => sum + i.price * i.quantity, 0),
  );
  readonly count = computed(() => this._items().length);
  readonly isEmpty = computed(() => this.count() === 0);

  addItem(product: Product): void {
    this._items.update((items) => {
      const existing = items.find((i) => i.productId === product.id);
      if (existing) {
        return items.map((i) =>
          i.productId === product.id ? { ...i, quantity: i.quantity + 1 } : i,
        );
      }
      return [
        ...items,
        {
          productId: product.id,
          name: product.name,
          price: product.price,
          quantity: 1,
        },
      ];
    });
  }

  removeItem(productId: string): void {
    this._items.update((items) =>
      items.filter((i) => i.productId !== productId),
    );
  }

  updateQuantity(productId: string, quantity: number): void {
    if (quantity <= 0) {
      this.removeItem(productId);
      return;
    }
    this._items.update((items) =>
      items.map((i) => (i.productId === productId ? { ...i, quantity } : i)),
    );
  }

  clear(): void {
    this._items.set([]);
  }
}
```

### NgRx Store (Enterprise)

```typescript
// state/cart/cart.actions.ts
export const CartActions = createActionGroup({
  source: "Cart",
  events: {
    "Add Item": props<{ product: Product }>(),
    "Remove Item": props<{ productId: string }>(),
    "Update Quantity": props<{ productId: string; quantity: number }>(),
    Clear: emptyProps(),
    "Load Cart Success": props<{ items: CartItem[] }>(),
    "Load Cart Failure": props<{ error: string }>(),
  },
});

// state/cart/cart.reducer.ts
export interface CartState {
  items: CartItem[];
  loading: boolean;
  error: string | null;
}

const initialState: CartState = {
  items: [],
  loading: false,
  error: null,
};

export const cartReducer = createReducer(
  initialState,
  on(CartActions.addItem, (state, { product }) => ({
    ...state,
    items: addOrIncrementItem(state.items, product),
  })),
  on(CartActions.removeItem, (state, { productId }) => ({
    ...state,
    items: state.items.filter((i) => i.productId !== productId),
  })),
  on(CartActions.clear, (state) => ({
    ...state,
    items: [],
  })),
  on(CartActions.loadCartSuccess, (state, { items }) => ({
    ...state,
    items,
    loading: false,
  })),
);

// state/cart/cart.selectors.ts
export const selectCartState = createFeatureSelector<CartState>("cart");
export const selectCartItems = createSelector(selectCartState, (s) => s.items);
export const selectCartTotal = createSelector(selectCartItems, (items) =>
  items.reduce((sum, i) => sum + i.price * i.quantity, 0),
);
export const selectCartCount = createSelector(
  selectCartItems,
  (items) => items.length,
);

// state/cart/cart.effects.ts
export const loadCart = createEffect(
  (actions$ = inject(Actions), cartApi = inject(CartApiService)) =>
    actions$.pipe(
      ofType(CartActions.loadCart),
      switchMap(() =>
        cartApi.getCart().pipe(
          map((items) => CartActions.loadCartSuccess({ items })),
          catchError((error) =>
            of(CartActions.loadCartFailure({ error: error.message })),
          ),
        ),
      ),
    ),
  { functional: true },
);
```

### NgRx ComponentStore

```typescript
interface FilterState {
  category: string;
  priceRange: [number, number];
  sortBy: string;
  page: number;
}

@Injectable()
export class FilterStore extends ComponentStore<FilterState> {
  constructor() {
    super({
      category: "all",
      priceRange: [0, 1000],
      sortBy: "name",
      page: 1,
    });
  }

  // Selectors
  readonly category$ = this.select((s) => s.category);
  readonly filters$ = this.select((s) => s);

  // Updaters
  readonly setCategory = this.updater((state, category: string) => ({
    ...state,
    category,
    page: 1,
  }));

  readonly setSort = this.updater((state, sortBy: string) => ({
    ...state,
    sortBy,
  }));

  readonly nextPage = this.updater((state) => ({
    ...state,
    page: state.page + 1,
  }));

  readonly reset = this.updater(() => this.get());
}

// Usage in component
@Component({
  providers: [FilterStore], // scoped to this component
})
export class ProductListComponent {
  private readonly filterStore = inject(FilterStore);
  readonly filters$ = this.filterStore.filters$;
}
```

### URL State

```typescript
@Component({
  template: `
    <app-filter-bar
      [category]="category()"
      (categoryChange)="setFilter('category', $event)"
    />
    <app-product-grid [products]="products()" />
    <app-pagination
      [page]="page()"
      (pageChange)="setFilter('page', $event.toString())"
    />
  `,
})
export class ProductListComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  category = toSignal(
    this.route.queryParamMap.pipe(map((p) => p.get("category") ?? "all")),
    { initialValue: "all" },
  );

  page = toSignal(
    this.route.queryParamMap.pipe(
      map((p) => parseInt(p.get("page") ?? "1", 10)),
    ),
    { initialValue: 1 },
  );

  setFilter(key: string, value: string): void {
    this.router.navigate([], {
      queryParams: { [key]: value, ...(key !== "page" ? { page: "1" } : {}) },
      queryParamsHandling: "merge",
    });
  }
}
```

### URL State with Signals Bridge

Combine route query params with signals for reactive filter/pagination state that survives refresh and supports sharing:

```typescript
@Component({
  template: `
    <app-search-bar
      [query]="searchQuery()"
      (queryChange)="updateParams('q', $event)"
    />
    <app-filters
      [category]="category()"
      (categoryChange)="updateParams('category', $event)"
    />
    <app-product-grid [products]="products()" [loading]="loading()" />
    <app-pagination
      [page]="page()"
      [total]="totalPages()"
      (pageChange)="updateParams('page', $event.toString())"
    />
  `,
})
export class ProductListComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly productService = inject(ProductService);

  // URL state -> signals via toSignal
  searchQuery = toSignal(
    this.route.queryParamMap.pipe(map((p) => p.get("q") ?? "")),
    { initialValue: "" },
  );
  category = toSignal(
    this.route.queryParamMap.pipe(map((p) => p.get("category") ?? "all")),
    { initialValue: "all" },
  );
  page = toSignal(
    this.route.queryParamMap.pipe(
      map((p) => parseInt(p.get("page") ?? "1", 10)),
    ),
    { initialValue: 1 },
  );

  // Derived: fetch products reactively when URL params change
  private readonly params = computed(() => ({
    q: this.searchQuery(),
    category: this.category(),
    page: this.page(),
  }));

  loading = signal(false);
  products = signal<Product[]>([]);
  totalPages = signal(1);

  constructor() {
    // React to URL param changes
    toObservable(this.params)
      .pipe(
        debounceTime(300),
        switchMap((params) => {
          this.loading.set(true);
          return this.productService.search(params);
        }),
        takeUntilDestroyed(),
      )
      .subscribe({
        next: (result) => {
          this.products.set(result.items);
          this.totalPages.set(result.totalPages);
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
  }

  updateParams(key: string, value: string): void {
    this.router.navigate([], {
      queryParams: { [key]: value, ...(key !== "page" ? { page: "1" } : {}) },
      queryParamsHandling: "merge",
    });
  }
}
```

### State Categorization

| Category  | Example                     | Mechanism              |
| --------- | --------------------------- | ---------------------- |
| Local UI  | Modal open, form dirty      | Component signal       |
| Shared UI | Sidebar collapsed, theme    | Signal service         |
| Server    | User list, product data     | HTTP service (cache)   |
| URL       | Filters, pagination, search | Router queryParams     |
| Form      | Form values, validation     | Reactive Forms         |
| Global    | Auth user, permissions      | Signal service or NgRx |

## Output Format

Consuming workflow skills depend on this structure.

```
## Angular State Architecture

**Stack:** {detected framework}
**State library:** {Signals | NgRx Store | NgRx ComponentStore | Services}

### State Map

| State          | Category   | Owner             | Mechanism               |
| -------------- | ---------- | ----------------- | ----------------------- |
| {state name}   | Local UI   | {component}       | signal()                |
| {state name}   | Shared UI  | {service}         | Signal service          |
| {state name}   | Server     | -                 | HTTP service            |
| {state name}   | URL        | -                 | queryParams             |

### Stores / Services

| Store/Service    | Domain         | Scope       | Pattern             |
| ---------------- | -------------- | ----------- | ------------------- |
| {name}           | {domain}       | {root/comp} | {signal/NgRx/CS}    |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- NgRx Store for simple apps (signal services are sufficient)
- Duplicating server state in stores (use HTTP services with caching)
- Creating one mega-service for all application state (separate domains)
- Storing derived values instead of computing them with `computed()`
- Mutable state updates (always create new references)
- BehaviorSubject for new component-local state (use signals)
- NgRx without clear justification for its complexity (devtools, effects, middleware needs)
- Mixing state management patterns inconsistently across the app
- Storing pagination, filter, sort, or search state in signals or services when it should live in route query params (loses bookmarkability and back button support)
