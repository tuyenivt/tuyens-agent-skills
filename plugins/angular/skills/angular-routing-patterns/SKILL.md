---
name: angular-routing-patterns
description: Angular routing - lazy loading, functional guards/resolvers, nested routes, signal-based params, route animations, SSR safety.
metadata:
  category: frontend
  tags: [angular, routing, lazy-loading, guards, resolvers, nested-routes, ssr]
user-invocable: false
---

# Angular Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing route structure for a feature or app
- Adding lazy routes, guards, resolvers, or SSR-safe code
- Auditing routing for performance, accessibility, and safety

## Rules

- Standalone components + functional guards/resolvers (no NgModules, no class-based `CanActivate`)
- Lazy-load non-initial routes via `loadComponent` / `loadChildren`
- Every route declares a `title` (string or `ResolveFn<string>`)
- Validate dynamic params before use (treat URL as untrusted)
- Use `Router` / `routerLink` for navigation; never `window.location`
- Wildcard `**` route must resolve to a not-found component

## Patterns

### Route configuration

```typescript
// app.routes.ts
export const routes: Routes = [
  { path: "", component: HomeComponent, title: "Home" },
  {
    path: "dashboard",
    loadComponent: () => import("./dashboard/dashboard.component").then(m => m.DashboardComponent),
    canActivate: [authGuard],
    title: "Dashboard",
    children: [
      {
        path: ":teamId",
        loadComponent: () => import("./dashboard/team/team.component").then(m => m.TeamComponent),
        resolve: { team: teamResolver },
        title: teamTitleResolver,
      },
    ],
  },
  { path: "auth", loadChildren: () => import("./auth/auth.routes").then(m => m.AUTH_ROUTES) },
  {
    path: "**",
    loadComponent: () => import("./not-found/not-found.component").then(m => m.NotFoundComponent),
    title: "Page Not Found",
  },
];
```

`loadChildren` points at a child `Routes` array (e.g. `AUTH_ROUTES`) whose entries follow the same shape.

### Functional guards

```typescript
export const authGuard: CanActivateFn = (route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.isAuthenticated()
    ? true
    : router.createUrlTree(["/auth/login"], { queryParams: { returnUrl: state.url } });
};

// Parameterised guard - factory returns CanActivateFn
export const roleGuard = (role: string): CanActivateFn => () => inject(AuthService).hasRole(role);

// Usage: canActivate: [authGuard, roleGuard("admin")]
```

Return `true`, `false`, or a `UrlTree` for redirects. Never call `router.navigate()` inside a guard.

### Functional resolvers

```typescript
export const teamResolver: ResolveFn<Team> = (route) => {
  const teamId = route.paramMap.get("teamId");
  if (!teamId) return inject(Router).createUrlTree(["/dashboard"]);
  return inject(TeamService).getTeam(teamId).pipe(
    catchError(() => { inject(Router).navigate(["/dashboard"]); return EMPTY; }),
  );
};

// Dynamic title
export const teamTitleResolver: ResolveFn<string> = (route) =>
  inject(TeamService).getTeam(route.paramMap.get("teamId")!).pipe(map(t => `${t.name} - Dashboard`));
```

### Signal-based route data in components

```typescript
@Component({ template: `@if (team(); as t) { <h2>{{ t.name }}</h2> }` })
export class TeamComponent {
  private readonly route = inject(ActivatedRoute);
  team = toSignal(this.route.data.pipe(map(d => d["team"] as Team)));
  teamId = toSignal(this.route.paramMap.pipe(map(p => p.get("teamId")!)));
  tab = toSignal(this.route.queryParamMap.pipe(map(p => p.get("tab") ?? "overview")));
}
```

### Navigation

```typescript
// Template
<a routerLink="/dashboard" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Dashboard</a>
<a [routerLink]="['/dashboard', teamId()]">Team</a>

// Programmatic - merge query params for filters/pagination
this.router.navigate([], {
  relativeTo: this.route,
  queryParams: { page: 1, category },
  queryParamsHandling: "merge",
});
```

### Route animations

Bind `<router-outlet>` to a trigger keyed off `activatedRouteData`; declare animation in `app.config.ts` via `provideAnimations()`.

```typescript
@Component({
  template: `<main [@routeAnimations]="o.activatedRouteData"><router-outlet #o="outlet"/></main>`,
  animations: [trigger("routeAnimations", [transition("* <=> *", [/* enter/leave queries */])])],
})
export class AppComponent {}
```

### SSR (Angular Universal)

Guard browser-only APIs; resolvers and guards run on the server too.

```typescript
private readonly platformId = inject(PLATFORM_ID);
ngOnInit() {
  if (isPlatformBrowser(this.platformId)) this.initChart(); // window/document/localStorage
}
```

## Output Format

```
## Routing Design

**Stack:** {Angular version}
**SSR:** {Yes | No}

### Route Map

| Path               | Component          | Guard     | Resolver     | Lazy | Title       |
| ------------------ | ------------------ | --------- | ------------ | ---- | ----------- |
| /                  | HomeComponent      | -         | -            | No   | Home        |
| /dashboard         | DashboardComponent | authGuard | -            | Yes  | Dashboard   |
| /dashboard/:teamId | TeamComponent      | authGuard | teamResolver | Yes  | {team.name} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: {High | Medium | Low}] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Class-based guards/resolvers or NgModule routing
- Routes without `title` (a11y + SEO regression)
- Trusting `:id` params without validation
- Calling `router.navigate()` inside a guard (return `UrlTree` instead)
- Re-fetching in a child what a parent resolver already provided
- Browser APIs in resolvers/guards/`ngOnInit` without `isPlatformBrowser`
- Deeply nested routes that aren't lazy (inflates initial bundle)
