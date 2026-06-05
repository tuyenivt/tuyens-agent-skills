---
name: angular-state-patterns
description: Angular state - signals, NgRx Store/ComponentStore, signal services, URL state, persistence, auth lifecycle, BehaviorSubject migration.
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

- Climb the ladder only when justified: signal -> signal service -> ComponentStore -> NgRx. NgRx requires concrete need (devtools, effects, time-travel).
- One store per domain boundary; never one mega-store.
- Server state lives in HTTP services with caching, never duplicated into stores.
- Filters, sort, pagination, and search belong in route query params (bookmarkable, shareable, back-button-safe).
- Derived state is `computed()`/selectors, never stored.
- Updates are immutable - return new references.

## Patterns

### Mechanism Selection

| Mechanism           | Use for                                  |
| ------------------- | ---------------------------------------- |
| `signal()`          | Component-local UI (modal, form dirty)   |
| Signal service      | Shared UI/domain (cart, theme, prefs)    |
| NgRx Signal Store   | Domain store with methods + computed + RxJS interop, less ceremony than NgRx Store |
| HTTP service        | Server data with caching                 |
| Router queryParams  | Filters, sort, pagination, search        |
| Reactive Forms      | Form values + validation                 |
| ComponentStore      | Feature-scoped complex state             |
| NgRx Store          | Enterprise: devtools/effects/middleware  |

### Signal Service

```typescript
@Injectable({ providedIn: "root" })
export class CartService {
  private readonly _items = signal<CartItem[]>([]);
  readonly items = this._items.asReadonly();
  readonly total = computed(() => this._items().reduce((s, i) => s + i.price * i.quantity, 0));

  add(p: Product): void {
    this._items.update((items) => {
      const existing = items.find((i) => i.productId === p.id);
      return existing
        ? items.map((i) => i.productId === p.id ? { ...i, quantity: i.quantity + 1 } : i)
        : [...items, { productId: p.id, name: p.name, price: p.price, quantity: 1 }];
    });
  }
}
```

### NgRx Signal Store (`@ngrx/signals`)

NgRx's recommended starting point for new code - signal-based, composable, less boilerplate than NgRx Store. Use for domain state that benefits from `withMethods` + `withComputed` + RxJS interop without effects/devtools.

```typescript
type CartState = { items: CartItem[]; loading: boolean };
const initial: CartState = { items: [], loading: false };

export const CartStore = signalStore(
  { providedIn: 'root' },
  withState(initial),
  withComputed(({ items }) => ({
    total: computed(() => items().reduce((s, i) => s + i.price * i.quantity, 0)),
    count: computed(() => items().length),
  })),
  withMethods((store, http = inject(HttpClient)) => ({
    add(p: Product): void {
      patchState(store, (s) => ({
        items: s.items.find((i) => i.productId === p.id)
          ? s.items.map((i) => i.productId === p.id ? { ...i, quantity: i.quantity + 1 } : i)
          : [...s.items, { productId: p.id, name: p.name, price: p.price, quantity: 1 }],
      }));
    },
    reset(): void { patchState(store, initial); },
    loadFromApi: rxMethod<void>(pipe(
      tap(() => patchState(store, { loading: true })),
      switchMap(() => http.get<CartItem[]>('/api/cart').pipe(
        tap((items) => patchState(store, { items, loading: false })),
      )),
    )),
  })),
);

// component
private cart = inject(CartStore);
total = this.cart.total;            // Signal<number>
add(p: Product): void { this.cart.add(p); }
```

For per-entity collections, layer on `withEntities` from `@ngrx/signals/entities`. Provide at route level instead of root when state should reset on route exit.

### Persistence & Auth Lifecycle

Hydrate from storage at construction, persist on change, reset on logout. Guard `localStorage` for SSR.

```typescript
@Injectable({ providedIn: "root" })
export class CartService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly STORAGE_KEY = "cart";

  private readonly _items = signal<CartItem[]>(this.load());
  readonly items = this._items.asReadonly();

  constructor() {
    effect(() => {
      if (isPlatformBrowser(this.platformId)) {
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this._items()));
      }
    });
  }

  private load(): CartItem[] {
    if (!isPlatformBrowser(this.platformId)) return [];
    try { return JSON.parse(localStorage.getItem(this.STORAGE_KEY) ?? "[]"); }
    catch { return []; }
  }

  // Hook called from AuthService.logout()
  reset(): void { this._items.set([]); }
}
```

For per-user state (wishlist, profile), AuthService coordinates lifecycle: `effect(() => { if (!this.auth.user()) this.cart.reset(); })`.

### URL State (signals bridge)

Route query params own filter/sort/page; bridge via `toSignal` and react via `toObservable`.

```typescript
@Component({...})
export class ProductListComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ProductService);

  q = toSignal(this.route.queryParamMap.pipe(map(p => p.get("q") ?? "")), { initialValue: "" });
  page = toSignal(this.route.queryParamMap.pipe(map(p => +(p.get("page") ?? 1))), { initialValue: 1 });

  productsResource = resource({
    request: () => ({ q: this.q(), page: this.page() }),
    loader: ({ request, abortSignal }) =>
      firstValueFrom(this.api.search(request, { signal: abortSignal })),
  });

  update(key: string, value: string): void {
    this.router.navigate([], {
      queryParams: { [key]: value, ...(key !== "page" ? { page: "1" } : {}) },
      queryParamsHandling: "merge",
    });
  }
}
```

### Reactive Forms (form state)

```typescript
form = inject(FormBuilder).group({
  email: ["", [Validators.required, Validators.email]],
  password: ["", Validators.required],
});

readonly value = toSignal(this.form.valueChanges, { initialValue: this.form.getRawValue() });
readonly isValid = toSignal(this.form.statusChanges.pipe(map((s) => s === "VALID")), { initialValue: false });
```

### ComponentStore (feature-scoped)

```typescript
@Injectable()
export class FilterStore extends ComponentStore<FilterState> {
  constructor() { super({ category: "all", sortBy: "name", page: 1 }); }
  readonly filters$ = this.select((s) => s);
  readonly setCategory = this.updater((s, category: string) => ({ ...s, category, page: 1 }));
}

@Component({ providers: [FilterStore] })  // scoped to component subtree
export class ProductListComponent {
  private readonly store = inject(FilterStore);
}
```

### NgRx Store (enterprise only)

Use when you need devtools, effects, or middleware. Shape: `createActionGroup` + `createReducer` + `createSelector` + `createEffect({ functional: true })`. One feature store per domain; never a mega-store.

### Server Cache + Pagination

```typescript
private readonly cache = new Map<string, Observable<Page<Product>>>();

getPage(page: number, filters: Filters): Observable<Page<Product>> {
  const key = `${page}|${JSON.stringify(filters)}`;
  if (!this.cache.has(key)) {
    this.cache.set(key, this.http.get<Page<Product>>("/api/products", { params: { page, ...filters } })
      .pipe(shareReplay({ bufferSize: 1, refCount: false })));
  }
  return this.cache.get(key)!;
}

invalidate(): void { this.cache.clear(); }  // on mutation
```

## Output Format

```
## Angular State Architecture

**State library:** {Signals | NgRx Store | ComponentStore | Services}

### State Map

| State        | Category  | Owner       | Mechanism        |
| ------------ | --------- | ----------- | ---------------- |
| {name}       | {Local UI | Shared | Server | URL | Form | Feature | Global} | {component/service} | {signal/computed/queryParams/HTTP/ReactiveForm/CS/NgRx} |

### Stores / Services

| Name   | Domain   | Scope        | Persistence | Lifecycle reset           |
| ------ | -------- | ------------ | ----------- | ------------------------- |
| {name} | {domain} | {root/comp}  | {localStorage/none} | {on logout/never} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

Omit `Issues Found` for greenfield design.

## Avoid

- NgRx for simple apps when signal services suffice
- Duplicating server data into stores instead of caching in HTTP services
- One mega-service holding unrelated domains
- Storing derived values instead of `computed()`/selectors
- Mutating state in place
- `BehaviorSubject` for component-local state - use signals
- Filters/sort/pagination in signals or services - they belong in queryParams
- `providedIn: 'root'` for per-user state without an explicit reset on logout
- `localStorage` access without `isPlatformBrowser` guard (SSR crash)
