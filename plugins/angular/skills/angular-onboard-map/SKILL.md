---
name: angular-onboard-map
description: Map Angular codebase for onboarding - CLI/Nx workspace, standalone, signals, zoneless, SSR, RxJS, routing, state, auth.
metadata:
  category: frontend
  tags: [onboarding, codebase-map, angular, rxjs, signals]
user-invocable: false
---

# Angular Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-onboard` when stack is Angular.

## When to Use

- Workflow needs Angular-specific orientation: workspace, change detection, standalone vs NgModule, RxJS, state, routing, SSR.
- Project has `angular.json` and `@angular/core` in `package.json`.

## Rules

- Identify Angular major version from `package.json`. 17+ defaults to standalone + new control flow; 18+ supports zoneless; 19+ standalone is default; 19+ adds `linkedSignal`/`resource`.
- Identify bootstrap: standalone (`bootstrapApplication` in `main.ts`) vs NgModule (`AppModule` + `platformBrowserDynamic`).
- Identify change detection: signal-based, `OnPush`, default Zone.js, or zoneless (`provideZonelessChangeDetection` / `provideExperimentalZonelessChangeDetection`).
- Identify state: NgRx Store (`@ngrx/store`), NgRx Signals (`@ngrx/signals`), NGXS, or services with signals/`BehaviorSubject`. Note when mixed.
- Identify routing: `provideRouter(routes)` vs `RouterModule.forRoot(routes)`.
- Identify deployment: SPA, SSR (`@angular/ssr` + `provideClientHydration`), or SSG.
- Identify monorepo: `nx.json` or multi-project `angular.json`.
- Identify auth: `@auth0/auth0-angular`, `angular-oauth2-oidc`, `keycloak-angular`, `msal-angular`, or custom.

## Patterns

### File Inventory

| File / Path                                  | Tells you                                                     |
| -------------------------------------------- | ------------------------------------------------------------- |
| `angular.json`                               | CLI workspace, build/serve/test targets, multi-project layout |
| `nx.json` / `apps/` / `libs/`                | Nx monorepo with app/lib split + boundary tags                |
| `pnpm-workspace.yaml` / `turbo.json`         | pnpm or Turborepo monorepo (may coexist with or replace Nx)    |
| `project.json` per project                   | Nx target config; `tags` field declares boundary scope/type    |
| `package.json`                               | Angular/CLI/Material versions, RxJS, state libs, auth lib     |
| `src/main.ts` / `apps/<app>/src/main.ts`     | `bootstrapApplication` (standalone) or `platformBrowserDynamic` |
| `src/app/app.config.ts`                      | Standalone providers (router, http, hydration, zoneless)      |
| `src/app/app.routes.ts`                      | Route table for `provideRouter`                               |
| `src/app/app.module.ts`                      | NgModule legacy root (if present)                             |
| `src/main.server.ts` / `server.ts`           | SSR entry; Node OTel init lives here                          |
| `vitest.config.ts` / `jest.config.*` / `karma.conf.js` | Test runner                                          |
| `src/environments/`                          | `environment.ts` / `.prod.ts` - flag secrets here             |

### Bootstrap Path

1. Install: `npm install` (or `pnpm`/`yarn`).
2. Env: edit `src/environments/environment.ts` (some apps fetch runtime config at startup).
3. Run: `ng serve` (or `nx serve <app>`); default port 4200.
4. Test: `ng test` / `nx test` (Vitest, Jest, or Karma depending on config).
5. Build: `ng build --configuration=production` / `nx build <app>`.
6. E2E: Playwright or Cypress.

### Conventions

- One concept per file; component triplet `<name>.component.ts/.html/.scss`.
- DI lifetimes: `providedIn: 'root'` (most), per-component `providers`, per-route `providers`.
- `ChangeDetectionStrategy.OnPush` common; signal-based components behave OnPush-like.
- Zoneless apps: third-party libs assuming Zone.js may need manual CD triggers or migration.
- Reactive Forms preferred for non-trivial forms.
- RxJS hygiene: `async` pipe in templates; `takeUntilDestroyed()` (16+) replaces manual `destroy$`.
- HTTP: functional `HttpInterceptorFn` for auth/logging/retries; `provideHttpClient(withInterceptors([...]))`.
- Templates 17+: `@if`/`@for`/`@switch` over `*ngIf`/`*ngFor`.
- Lint: `@angular-eslint/*`.
- Monorepo (Nx): `@nx/enforce-module-boundaries`, `nx affected`, project tags scope cross-lib imports. See `angular-nx-patterns`.

### Risk Hotspots

- **OnPush + mutation**: in-place input mutation skips CD; pure pipes need new refs. See `angular-component-patterns`, `angular-signals-patterns`.
- **RxJS leaks**: manual `.subscribe()` without teardown, duplicate HTTP from cold observables, `takeUntilDestroyed` outside injection context. See `angular-rxjs-patterns`.
- **Lifecycle/DI timing**: `@ViewChild` undefined in `ngOnInit`; `inject()` only in injection context. See `angular-component-patterns`, `angular-service-patterns`.
- **Routing**: missing `canMatch` on lazy routes, lazy-route drift. See `angular-routing-patterns`.
- **Mid-migration churn**: mixed standalone/NgModule, mixed Zone/zoneless, mixed NgRx Store + NgRx Signals.
- **SSR**: missing `provideClientHydration` / HTTP transfer cache; browser-API access without `isPlatformBrowser` / `afterNextRender`; module-level mutable state leaking across requests.
- **Security**: `[innerHTML]` XSS, `bypassSecurityTrust*` misuse, secrets in `environment.ts`, open redirects. See `task-angular-review-security`.
- **Auth integration**: redirect callback handling, token storage choice, interceptor origin-scoping. See `angular-service-patterns`.

### First-PR Safe Zones

Safe: new component in an existing feature/lib, new `providedIn: 'root'` service, new unit test, new route in an existing routes file.

Riskier: `app.config.ts`/`app.module.ts` providers, HTTP interceptors, auth guards, shared-component CD strategies, anything in `server.ts`.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Angular version, bootstrap style, CD model (Default / OnPush / Signal / Zoneless), state library (NgRx Store / Signals / mixed), RxJS-vs-signals split, test runner, E2E framework, monorepo (Nx) yes/no, auth library.

**Deployment Model:** SPA / SSR / SSG; `provideClientHydration` and HTTP transfer cache status; browser-API guard idiom in use.

**Monorepo Layout (if Nx):** app and lib counts, boundary-tag scheme, `nx affected` usage.

**Local Bootstrap:** install command, env file, serve command + port, test command, build command.

**Architecture Map:** workspace layout, feature directory pattern, root config file (`app.config.ts` or `app.module.ts`), routing API, auth flow entry points.

**Conventions:** OnPush/signal usage, `inject()` vs constructor DI, async pipe vs manual subscribe, `takeUntilDestroyed`, control flow blocks, zoneless considerations.

**Risk Hotspots:** observed instances from the list above.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating pre-17 patterns as current
- Recommending NgModule patterns on a standalone project (or vice versa)
- Listing every dependency; name only architectural ones
- Skipping change detection identification - it shapes everything else
- Confusing `inject()` and constructor injection contexts
