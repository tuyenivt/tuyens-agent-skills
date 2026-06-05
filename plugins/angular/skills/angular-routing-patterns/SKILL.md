---
name: angular-routing-patterns
description: Angular routing - lazy loading, functional guards/resolvers, nested routes, signal-based params, SSR hydration and TransferState.
metadata:
  category: frontend
  tags: [angular, routing, lazy-loading, guards, resolvers, nested-routes, ssr]
user-invocable: false
---

# Angular Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing route structure for a feature or app
- Adding lazy routes, guards, resolvers, or SSR-safe data flow
- Auditing routing for performance, accessibility, and safety

## Rules

- Standalone components + functional guards/resolvers. No NgModules, no class-based guards.
- Lazy-load non-initial routes via `loadComponent` / `loadChildren`. Use `canMatch` (not `canActivate`) to gate lazy chunk loading.
- Every route declares a `title` (string or `ResolveFn<string>`).
- Validate dynamic params before use (treat URL as untrusted).
- Use `Router` / `routerLink` for navigation; never `window.location`.
- Wildcard `**` route must resolve to a not-found component.

## Patterns

### Route Configuration

```typescript
export const routes: Routes = [
  { path: "", component: HomeComponent, title: "Home" },
  {
    path: "admin",
    canMatch: [authGuard, roleGuard("admin")],
    title: "Admin",
    children: [
      { path: "", pathMatch: "full", redirectTo: "users" },
      {
        path: "users",
        loadComponent: () => import("./admin/users/users-list.component").then(m => m.UsersListComponent),
        title: "Users - Admin",
      },
      {
        path: "users/:id",
        loadComponent: () => import("./admin/users/user-detail.component").then(m => m.UserDetailComponent),
        resolve: { user: userResolver },
        title: userTitleResolver,
      },
      {
        path: "settings",
        loadChildren: () => import("./admin/settings/settings.routes").then(m => m.SETTINGS_ROUTES),
      },
    ],
  },
  {
    path: "**",
    loadComponent: () => import("./not-found/not-found.component").then(m => m.NotFoundComponent),
    title: "Page Not Found",
  },
];
```

`loadChildren` points at a child `Routes` array (e.g., `SETTINGS_ROUTES`) with the same shape. Use `pathMatch: "full"` + `redirectTo` for default child routes.

### Functional Guards

```typescript
export const authGuard: CanActivateFn = (route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.isAuthenticated()
    ? true
    : router.createUrlTree(["/auth/login"], { queryParams: { returnUrl: state.url } });
};

// Parameterised guard
export const roleGuard = (role: string): CanActivateFn => () => inject(AuthService).hasRole(role);
```

Return `true`, `false`, or a `UrlTree` for redirects. Never call `router.navigate()` inside a guard.

`CanMatchFn` is identical in shape but prevents the lazy chunk from loading - prefer it for auth-gated lazy routes.

### Functional Resolvers

```typescript
export const teamResolver: ResolveFn<Team> = (route) => {
  const teamId = route.paramMap.get("teamId");
  if (!teamId) return inject(Router).createUrlTree(["/dashboard"]);
  return inject(TeamService).getTeam(teamId).pipe(
    catchError(() => { inject(Router).navigate(["/dashboard"]); return EMPTY; }),
  );
};

export const teamTitleResolver: ResolveFn<string> = (route) =>
  inject(TeamService).getTeam(route.paramMap.get("teamId")!).pipe(map(t => `${t.name} - Dashboard`));
```

### Component Input Binding (preferred in 17+)

Bind route params, query params, and `data` directly into component `input()` signals:

```typescript
// app.config.ts
provideRouter(routes, withComponentInputBinding())

// /users/:id  -> binds to component input named "id"
@Component({ ... })
export class UserDetailComponent {
  id = input.required<string>();                     // from path param
  tab = input('overview');                           // from query param ?tab=
  team = input<Team>();                              // from resolver data { team: ... }
}
```

Cleaner than subscribing to `ActivatedRoute.paramMap` - resolves to signals, plays naturally with OnPush, and re-runs `computed` automatically on route change.

### Other Guards

```typescript
// CanMatch - gates the lazy chunk load; preferred for auth-protected lazy routes.
// CanActivate - runs per navigation; use when the gate depends on state that can change post-load (subscription expiry, feature flag).
// CanActivateChild - runs on every child route change; use for breadcrumbs / context that must re-verify per step.
// CanDeactivate - confirms leaving (dirty form):
export const confirmLeave: CanDeactivateFn<EditorComponent> = (cmp) =>
  cmp.form.pristine || confirm("Discard unsaved changes?");
```

### Navigation with Query Param Merge

```typescript
this.router.navigate([], {
  relativeTo: this.route,
  queryParams: { page: 1, category },
  queryParamsHandling: "merge",
});
```

### SSR (Angular Universal)

Resolvers and guards run on the server too - any browser-only API (DOM, `window`, `localStorage`, `IntersectionObserver`) must wait for client init:

```typescript
constructor() {
  afterNextRender(() => this.initChart()); // runs only in the browser, after first DOM render
}
```

Pair with `TransferState` for any non-HTTP server-computed payload you want to reuse on hydration:

```typescript
private readonly state = inject(TransferState);
private readonly KEY = makeStateKey<Team>('current-team');

team = signal(this.state.get(this.KEY, null));
constructor() { effect(() => isPlatformServer(this.platformId) && this.state.set(this.KEY, this.team()!)); }
```

For HTTP transfer cache wiring (`provideClientHydration(withHttpTransferCacheOptions({...}))` and the `withFetch()` prerequisite), see `angular-data-fetching` - it owns the security-relevant defaults.

## Output Format

```
## Routing Design

**Angular version:** {detected}
**SSR:** {Yes | No}

### Route Map

| Path               | Component          | Guard           | Resolver     | Lazy | Title       |
| ------------------ | ------------------ | --------------- | ------------ | ---- | ----------- |
| /                  | HomeComponent      | -               | -            | No   | Home        |
| /admin             | -                  | canMatch:auth+r | -            | -    | Admin       |
| /admin/users/:id   | UserDetailComponent| -               | userResolver | Yes  | {user.name} |

### SSR Notes (if enabled)

- `provideClientHydration` configured / HTTP transfer cache options
- Browser-API guards in: {components/resolvers/guards}

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: {High | Medium | Low}] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

Omit `Issues Found` for greenfield design; omit `SSR Notes` when SSR is disabled.

## Avoid

- Class-based guards/resolvers or NgModule routing
- `canActivate` on lazy routes when `canMatch` would prevent the chunk load
- Routes without `title` (a11y + SEO regression)
- Trusting `:id` params without validation
- Calling `router.navigate()` inside a guard (return `UrlTree` instead)
- Re-fetching in a child what a parent resolver already provided
- Browser APIs in resolvers/guards/`ngOnInit` without `isPlatformBrowser` / `afterNextRender`
- Deeply nested routes that aren't lazy (inflates initial bundle)
