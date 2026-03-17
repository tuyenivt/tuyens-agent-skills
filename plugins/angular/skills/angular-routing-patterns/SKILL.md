---
name: angular-routing-patterns
description: Angular routing patterns - lazy loading, functional route guards, resolvers, nested routes, route animations, and SSR with Angular Universal for Angular 21+.
metadata:
  category: frontend
  tags: [angular, routing, lazy-loading, guards, resolvers, nested-routes, ssr]
user-invocable: false
---

# Angular Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing route structure for a new feature or application
- Adding lazy-loaded routes for code splitting
- Implementing route guards for authentication and authorization
- Adding route resolvers for pre-fetching data
- Reviewing routing for correctness and performance

## Rules

- Every route must define a title for accessibility and SEO
- Lazy load feature routes with `loadComponent` or `loadChildren` for code splitting
- Use functional guards and resolvers (not class-based)
- Route parameters must be validated before use
- Provide loading indicators during lazy route loading
- Prefer standalone component routes over NgModule-based routing

## Patterns

### Route Configuration

```typescript
// app.routes.ts
export const routes: Routes = [
  {
    path: "",
    component: HomeComponent,
    title: "Home",
  },
  {
    path: "dashboard",
    loadComponent: () =>
      import("./dashboard/dashboard.component").then(
        (m) => m.DashboardComponent,
      ),
    title: "Dashboard",
    canActivate: [authGuard],
    children: [
      {
        path: "",
        loadComponent: () =>
          import("./dashboard/overview/overview.component").then(
            (m) => m.OverviewComponent,
          ),
        title: "Dashboard Overview",
      },
      {
        path: "settings",
        loadComponent: () =>
          import("./dashboard/settings/settings.component").then(
            (m) => m.SettingsComponent,
          ),
        title: "Settings",
      },
      {
        path: ":teamId",
        loadComponent: () =>
          import("./dashboard/team/team.component").then(
            (m) => m.TeamComponent,
          ),
        resolve: { team: teamResolver },
        title: teamTitleResolver,
      },
    ],
  },
  {
    path: "auth",
    loadChildren: () => import("./auth/auth.routes").then((m) => m.AUTH_ROUTES),
  },
  {
    path: "**",
    loadComponent: () =>
      import("./not-found/not-found.component").then(
        (m) => m.NotFoundComponent,
      ),
    title: "Page Not Found",
  },
];
```

### Feature Routes (loadChildren)

```typescript
// auth/auth.routes.ts
export const AUTH_ROUTES: Routes = [
  {
    path: "login",
    loadComponent: () =>
      import("./login/login.component").then((m) => m.LoginComponent),
    title: "Sign In",
  },
  {
    path: "signup",
    loadComponent: () =>
      import("./signup/signup.component").then((m) => m.SignupComponent),
    title: "Sign Up",
  },
  {
    path: "forgot-password",
    loadComponent: () =>
      import("./forgot-password/forgot-password.component").then(
        (m) => m.ForgotPasswordComponent,
      ),
    title: "Reset Password",
  },
];
```

### Functional Route Guards

```typescript
// guards/auth.guard.ts
export const authGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    return true;
  }

  return router.createUrlTree(['/auth/login'], {
    queryParams: { returnUrl: state.url },
  });
};

// Role-based guard
export const roleGuard = (requiredRole: string): CanActivateFn => {
  return () => {
    const authService = inject(AuthService);
    return authService.hasRole(requiredRole);
  };
};

// Usage in routes:
{
  path: 'admin',
  loadComponent: () => import('./admin/admin.component'),
  canActivate: [authGuard, roleGuard('admin')],
}
```

### Functional Resolvers

```typescript
// resolvers/team.resolver.ts
export const teamResolver: ResolveFn<Team> = (route) => {
  const teamService = inject(TeamService);
  const router = inject(Router);
  const teamId = route.paramMap.get("teamId")!;

  return teamService.getTeam(teamId).pipe(
    catchError(() => {
      router.navigate(["/dashboard"]);
      return EMPTY;
    }),
  );
};

// Dynamic title resolver
export const teamTitleResolver: ResolveFn<string> = (route) => {
  const teamService = inject(TeamService);
  const teamId = route.paramMap.get("teamId")!;
  return teamService
    .getTeam(teamId)
    .pipe(map((team) => `${team.name} - Dashboard`));
};
```

### Accessing Route Data in Components

```typescript
@Component({
  template: `
    @if (team(); as team) {
      <h2>{{ team.name }}</h2>
      <p>{{ team.description }}</p>
    }
  `,
})
export class TeamComponent {
  private readonly route = inject(ActivatedRoute);

  // Signal-based route data access
  team = toSignal(this.route.data.pipe(map((data) => data["team"] as Team)));

  // Signal-based route params
  teamId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get("teamId")!)),
  );

  // Signal-based query params
  tab = toSignal(
    this.route.queryParamMap.pipe(
      map((params) => params.get("tab") ?? "overview"),
    ),
  );
}
```

### Router Navigation

```typescript
@Component({
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav>
      <a
        routerLink="/dashboard"
        routerLinkActive="active"
        [routerLinkActiveOptions]="{ exact: true }"
      >
        Dashboard
      </a>
      <a [routerLink]="['/dashboard', teamId()]" routerLinkActive="active">
        Team
      </a>
    </nav>
  `,
})
export class SidebarComponent {
  private readonly router = inject(Router);
  teamId = input.required<string>();

  navigateToSettings() {
    this.router.navigate(["/dashboard/settings"], {
      queryParams: { tab: "profile" },
    });
  }
}
```

### Route Animations

```typescript
// animations.ts
export const routeAnimations = trigger("routeAnimations", [
  transition("* <=> *", [
    query(":enter, :leave", [style({ position: "absolute", width: "100%" })], {
      optional: true,
    }),
    query(":enter", [style({ opacity: 0, transform: "translateX(20px)" })], {
      optional: true,
    }),
    group([
      query(
        ":leave",
        [
          animate(
            "200ms ease-out",
            style({ opacity: 0, transform: "translateX(-20px)" }),
          ),
        ],
        { optional: true },
      ),
      query(
        ":enter",
        [
          animate(
            "300ms 100ms ease-out",
            style({ opacity: 1, transform: "translateX(0)" }),
          ),
        ],
        { optional: true },
      ),
    ]),
  ]),
]);

@Component({
  template: `
    <main [@routeAnimations]="outlet.activatedRouteData">
      <router-outlet #outlet="outlet" />
    </main>
  `,
  animations: [routeAnimations],
})
export class AppComponent {}
```

### Route Query Params for Filters and Pagination

Persist filter, search, and pagination state in query params so users can bookmark and share URLs:

```typescript
@Component({
  template: `
    <app-filter-bar
      [category]="category()"
      (categoryChange)="setParam('category', $event)"
    />
    <app-product-grid [products]="products()" />
    <app-pagination
      [page]="page()"
      [total]="totalPages()"
      (pageChange)="setParam('page', $event.toString())"
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

  setParam(key: string, value: string): void {
    this.router.navigate([], {
      queryParams: { [key]: value, ...(key !== "page" ? { page: "1" } : {}) },
      queryParamsHandling: "merge",
    });
  }
}
```

### SSR Considerations (Angular Universal)

```typescript
// Check platform before using browser APIs
import { isPlatformBrowser, PLATFORM_ID } from "@angular/common";

@Component({})
export class ChartComponent {
  private readonly platformId = inject(PLATFORM_ID);

  ngOnInit() {
    if (isPlatformBrowser(this.platformId)) {
      // Safe to use window, document, localStorage
      this.initializeChart();
    }
  }
}
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Routing Design

**Stack:** {Angular version}
**SSR:** {Yes | No}

### Route Map

| Path                 | Component         | Guard      | Resolver   | Lazy   | Title             |
| -------------------- | ----------------- | ---------- | ---------- | ------ | ----------------- |
| /                    | HomeComponent     | -          | -          | No     | Home              |
| /dashboard           | DashboardComponent| authGuard  | -          | Yes    | Dashboard         |
| /dashboard/:teamId   | TeamComponent     | authGuard  | teamResolver| Yes   | {team.name}       |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Eager loading all routes (use `loadComponent` / `loadChildren` for code splitting)
- Class-based guards and resolvers (use functional guards with `inject()`)
- Routes without titles (accessibility and SEO issue)
- Trusting URL params without validation (security risk)
- Using `window.location` for navigation instead of the Router (breaks SPA behavior)
- Nested routes that re-fetch data the parent already resolved (use the resolver data)
- Wildcard routes without a not-found component
- Deep nesting without lazy loading (increases initial bundle size)
