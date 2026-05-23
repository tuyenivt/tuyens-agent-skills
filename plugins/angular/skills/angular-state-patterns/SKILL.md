---
name: angular-state-patterns
description: Angular state: signals, NgRx Store/ComponentStore, signal services, URL state, library selection, BehaviorSubject migration.
metadata:
  category: frontend
  tags: [angular, state, signals, ngrx, componentstore, rxjs, behaviorsubject]
user-invocable: false
---

# Angular State Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a state mechanism for an Angular feature
- Reviewing existing state for correctness, scope, or performance
- Migrating from BehaviorSubject or NgRx to signals

## Rules

- Climb the ladder only when justified: signal -> signal service -> ComponentStore -> NgRx Store. NgRx requires a concrete need (devtools, effects, time-travel).
- One store per domain boundary; never one mega-store.
- Server state lives in HTTP services with caching, never duplicated into stores.
- Filters, sort, pagination, and search belong in route query params (bookmarkable, shareable, back-button-safe).
- Derived state is `computed()`/selectors, never stored.
- Updates are immutable - return new references for objects and arrays.

## Patterns

### Mechanism Selection

| Mechanism           | Use for                                  | State category   |
| ------------------- | ---------------------------------------- | ---------------- |
| `signal()`          | Component-local UI (modal, form dirty)   | Local UI         |
| Signal service      | Shared UI/domain (cart, theme, prefs)    | Shared UI/domain |
| HTTP service        | Server data with caching                 | Server           |
| Router queryParams  | Filters, sort, pagination, search        | URL              |
| Reactive Forms      | Form values + validation                 | Form             |
| ComponentStore      | Feature-scoped complex state             | Feature          |
| NgRx Store          | Enterprise: devtools/effects/middleware  | Global           |

### Signal Service

```typescript
@Injectable({ providedIn: "root" })
export class CartService {
  private readonly _items = signal<CartItem[]>([]);
  readonly items = this._items.asReadonly();
  readonly total = computed(() =>
    this._items().reduce((s, i) => s + i.price * i.quantity, 0),
  );
  readonly isEmpty = computed(() => this._items().length === 0);

  addItem(p: Product): void {
    this._items.update((items) => {
      const existing = items.find((i) => i.productId === p.id);
      return existing
        ? items.map((i) =>
            i.productId === p.id ? { ...i, quantity: i.quantity + 1 } : i,
          )
        : [...items, { productId: p.id, name: p.name, price: p.price, quantity: 1 }];
    });
  }

  remove(id: string): void {
    this._items.update((items) => items.filter((i) => i.productId !== id));
  }
}
```

### ComponentStore (feature-scoped)

```typescript
@Injectable()
export class FilterStore extends ComponentStore<FilterState> {
  constructor() {
    super({ category: "all", sortBy: "name", page: 1 });
  }
  readonly filters$ = this.select((s) => s);
  readonly setCategory = this.updater((s, category: string) => ({ ...s, category, page: 1 }));
  readonly nextPage = this.updater((s) => ({ ...s, page: s.page + 1 }));
}

@Component({ providers: [FilterStore] }) // scoped to component subtree
export class ProductListComponent {
  private readonly store = inject(FilterStore);
  readonly filters$ = this.store.filters$;
}
```

### NgRx Store (enterprise only)

```typescript
// actions
export const CartActions = createActionGroup({
  source: "Cart",
  events: {
    "Add Item": props<{ product: Product }>(),
    "Load Success": props<{ items: CartItem[] }>(),
    "Load Failure": props<{ error: string }>(),
  },
});

// reducer
export const cartReducer = createReducer(
  initialState,
  on(CartActions.addItem, (state, { product }) => ({
    ...state,
    items: addOrIncrement(state.items, product),
  })),
  on(CartActions.loadSuccess, (state, { items }) => ({ ...state, items, loading: false })),
);

// selectors (derived state)
export const selectCartItems = createSelector(selectCartState, (s) => s.items);
export const selectCartTotal = createSelector(selectCartItems, (items) =>
  items.reduce((s, i) => s + i.price * i.quantity, 0),
);

// effect
export const loadCart = createEffect(
  (actions$ = inject(Actions), api = inject(CartApiService)) =>
    actions$.pipe(
      ofType(CartActions.loadCart),
      switchMap(() =>
        api.getCart().pipe(
          map((items) => CartActions.loadSuccess({ items })),
          catchError((err) => of(CartActions.loadFailure({ error: err.message }))),
        ),
      ),
    ),
  { functional: true },
);
```

### URL State (signals bridge)

Use route query params as the source of truth for filters/pagination; bridge to signals via `toSignal`, react via `toObservable`.

```typescript
@Component({
  template: `
    <app-search-bar [query]="q()" (queryChange)="update('q', $event)" />
    <app-product-grid [products]="products()" [loading]="loading()" />
    <app-pagination [page]="page()" (pageChange)="update('page', $event.toString())" />
  `,
})
export class ProductListComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ProductService);

  q = toSignal(this.route.queryParamMap.pipe(map((p) => p.get("q") ?? "")), { initialValue: "" });
  page = toSignal(
    this.route.queryParamMap.pipe(map((p) => parseInt(p.get("page") ?? "1", 10))),
    { initialValue: 1 },
  );
  private readonly params = computed(() => ({ q: this.q(), page: this.page() }));

  loading = signal(false);
  products = signal<Product[]>([]);

  constructor() {
    toObservable(this.params)
      .pipe(
        debounceTime(300),
        switchMap((p) => {
          this.loading.set(true);
          return this.api.search(p);
        }),
        takeUntilDestroyed(),
      )
      .subscribe({
        next: (r) => { this.products.set(r.items); this.loading.set(false); },
        error: () => this.loading.set(false),
      });
  }

  update(key: string, value: string): void {
    this.router.navigate([], {
      queryParams: { [key]: value, ...(key !== "page" ? { page: "1" } : {}) },
      queryParamsHandling: "merge",
    });
  }
}
```

## Output Format

```
## Angular State Architecture

**Stack:** {detected framework}
**State library:** {Signals | NgRx Store | ComponentStore | Services}

### State Map

| State        | Category  | Owner       | Mechanism        |
| ------------ | --------- | ----------- | ---------------- |
| {name}       | {Local UI | Shared | Server | URL | Form | Feature | Global} | {component/service} | {signal/computed/queryParams/HTTP/ReactiveForm/CS/NgRx} |

### Stores / Services

| Name   | Domain   | Scope        | Pattern              |
| ------ | -------- | ------------ | -------------------- |
| {name} | {domain} | {root/comp}  | {signal/CS/NgRx}     |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- NgRx for simple apps when signal services suffice
- Duplicating server data into stores instead of caching in HTTP services
- One mega-service holding unrelated domains
- Storing derived values instead of `computed()`/selectors
- Mutating state in place
- New `BehaviorSubject` for component-local state - use signals
- Filters/sort/pagination in signals or services - they belong in queryParams
- Mixing state patterns inconsistently across features
