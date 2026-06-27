---
name: angular-state-patterns
description: Angular state - signals, NgRx Signal Store/Store/ComponentStore, signal services, URL state, persistence, auth lifecycle.
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

- Climb the ladder only when justified: `signal` → signal service → NgRx Signal Store → NgRx Store. ComponentStore is acceptable in existing codebases; for greenfield, Signal Store has replaced it. Reach for NgRx Store only when you need devtools time-travel, structured `Effects`, or middleware (`@ngrx/router-store`, action-replay logs) - "devtools" alone is not enough.
- One store per domain boundary; never one mega-store.
- Server state lives in HTTP services with caching (or TanStack Query - see `angular-data-fetching`), never duplicated into stores.
- Filters, sort, pagination, and search belong in route query params (bookmarkable, shareable, back-button-safe).
- Derived state is `computed()`/selectors, never stored.
- Updates are immutable - return new references.

## Patterns

### Mechanism Selection

| Mechanism           | Use for                                                                              |
| ------------------- | ------------------------------------------------------------------------------------ |
| `signal()`          | Component-local UI (modal, form dirty)                                               |
| Signal service      | Shared UI/domain (cart, theme, prefs)                                                |
| NgRx Signal Store   | Domain store with methods + computed + entity collections + RxJS interop             |
| HTTP service / TanStack Query | Server data with caching                                                   |
| Router queryParams  | Filters, sort, pagination, search                                                    |
| Reactive Forms      | Form values + validation                                                             |
| ComponentStore      | Existing codebases; Signal Store covers new feature-scoped state                     |
| NgRx Store          | Devtools time-travel, structured Effects, action-replay - rarely justified on greenfield |

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

Route query params own filter/sort/page; bridge them to signals via `toSignal`, then drive fetching with `resource()` (or `toObservable` for an RxJS pipeline).

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

### ComponentStore (legacy / feature-scoped)

```typescript
// EditorState is genuinely component-local (not URL-bookmarkable): undo stack, cursor pos, focus mode.
@Injectable()
export class EditorStore extends ComponentStore<EditorState> {
  constructor() { super({ undoStack: [], cursorLine: 0, focusMode: false }); }
  readonly cursorLine$ = this.select((s) => s.cursorLine);
  readonly setCursor = this.updater((s, line: number) => ({ ...s, cursorLine: line }));
}

@Component({ providers: [EditorStore] })  // scoped to component subtree
export class EditorComponent {
  private readonly store = inject(EditorStore);
}
```

For greenfield, prefer NgRx Signal Store providing `provideComponentStore`-equivalent scoping via route-level providers.

### NgRx Store (enterprise only)

Use when you need devtools, effects, or middleware. Shape: `createActionGroup` + `createReducer` + `createSelector` + `createEffect({ functional: true })`. One feature store per domain; never a mega-store.

### Server Cache + Pagination

For multi-filter pagination, prefer TanStack Query (see `angular-data-fetching`) - its key factory + staleTime handles the eviction problem. A hand-rolled Map cache is acceptable only for a small, bounded key space (e.g., one resource, recent N pages):

```typescript
private readonly cache = new Map<string, Observable<Page<Product>>>();
private readonly MAX_ENTRIES = 50;  // bound the cache; LRU eviction below

getPage(page: number, filters: Filters): Observable<Page<Product>> {
  const key = `${page}|${JSON.stringify(filters)}`;
  if (!this.cache.has(key)) {
    if (this.cache.size >= this.MAX_ENTRIES) this.cache.delete(this.cache.keys().next().value!); // evict oldest
    this.cache.set(key, this.http.get<Page<Product>>("/api/products", { params: { page, ...filters } })
      .pipe(shareReplay({ bufferSize: 1, refCount: false })));
  }
  return this.cache.get(key)!;
}

invalidate(): void { this.cache.clear(); }  // on mutation
```

Unbounded caches leak memory across long sessions - always cap.

## Output Format

```
## Angular State Architecture

**State library:** {Signals | Signal services | NgRx Signal Store | NgRx Store | ComponentStore}

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
- `BehaviorSubject` for component-local state - use signals (see migration table in `angular-signals-patterns`)
- Filters/sort/pagination in signals or services - they belong in queryParams
- `providedIn: 'root'` for per-user state without an explicit reset on logout
- `localStorage` access without `isPlatformBrowser` guard (SSR crash)
