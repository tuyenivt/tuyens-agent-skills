---
name: angular-onboard-map
description: Map Angular codebase for onboarding: CLI workspace, standalone components, signals vs Zone.js, RxJS, routing, NgRx/Akita state, styling.
metadata:
  category: frontend
  tags: [onboarding, codebase-map, angular, rxjs, signals]
user-invocable: false
---

# Angular Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Angular.

## When to Use

- A workflow needs Angular-specific orientation: workspace, change detection, standalone vs NgModule, RxJS, state, routing.
- Project has `angular.json` and `@angular/core` in `package.json`.

## Rules

- Identify Angular major version from `package.json` (`@angular/core`). 17+ defaults to standalone and signals; 18+ supports zoneless.
- Identify bootstrap style: standalone (`bootstrapApplication` in `main.ts`, no `app.module.ts`) vs NgModule (`AppModule` + `platformBrowserDynamic`).
- Identify change detection: signal-based (`signal()`/`computed()`/`effect()`), `OnPush`, default Zone.js, or zoneless (`provideExperimentalZonelessChangeDetection`).
- Identify state: NgRx (`@ngrx/store`), NgRx Signals (`@ngrx/signals`), NGXS, Akita (legacy), or services with signals/`BehaviorSubject`.
- Identify routing: `provideRouter(routes)` (standalone) vs `RouterModule.forRoot(routes)` (NgModule).
- Identify monorepo: `nx.json` or multi-project `angular.json`.

## Patterns

### File Inventory

| File / Path                                  | Tells you                                                     |
| -------------------------------------------- | ------------------------------------------------------------- |
| `angular.json`                               | CLI workspace, build/serve/test targets, multi-project layout |
| `package.json`                               | Angular/CLI/Material versions, RxJS, state libs               |
| `tsconfig*.json`                             | TS configs split by build/spec target                         |
| `nx.json`                                    | Nx monorepo (if present)                                      |
| `karma.conf.js` / `jest.config.*`            | Test runner                                                   |
| `src/main.ts`                                | Bootstrap: `bootstrapApplication` or `platformBrowserDynamic` |
| `src/app/app.config.ts`                      | Standalone app-level providers (router, http, animations)     |
| `src/app/app.routes.ts`                      | Route table for `provideRouter`                               |
| `src/app/app.module.ts` + `*-routing.module.ts` | NgModule legacy roots                                      |
| `src/app/<feature>/`                         | Feature folders: `*.component.ts`, `*.service.ts`, `*.routes.ts` |
| `src/environments/`                          | `environment.ts` / `environment.prod.ts`                      |

### Bootstrap Path

1. Node toolchain: confirm `engines.node` in `package.json` (Angular 17+ needs Node 18.13+).
2. Install: `npm install` (or `pnpm`/`yarn`).
3. Configure env: edit `src/environments/environment.ts` (some projects fetch runtime config at startup).
4. Run: `ng serve` (port 4200).
5. Test: `ng test` (Karma + Jasmine default; some on Jest/Vitest).
6. Build: `ng build --configuration=production`.
7. E2E: Cypress or Playwright (Protractor deprecated).

### Conventions

- One concept per file: component, service, directive, pipe, guard, interceptor.
- Component triplet: `<name>.component.ts/.html/.scss`.
- DI lifetimes: `providedIn: 'root'` (most), per-component `providers: [...]`, per-route `providers`.
- `ChangeDetectionStrategy.OnPush` common; signal-based components behave OnPush-like.
- Reactive Forms preferred for non-trivial forms.
- RxJS hygiene: `async` pipe in templates; `takeUntilDestroyed()` (16+) replaces manual `destroy$`; `inject(DestroyRef)` outside components.
- HTTP: functional `HttpInterceptorFn` interceptors for auth/logging/retries.
- Templates 17+: control flow blocks (`@if`/`@for`/`@switch`) replacing `*ngIf`/`*ngFor`.
- Lint: `@angular-eslint/*`.

### Risk Hotspots

- **OnPush + mutation**: in-place input mutation skips CD; pure pipes need new refs. See `angular-component-patterns`, `angular-signals-patterns`.
- **RxJS leaks**: manual `.subscribe()` without teardown, duplicate HTTP from cold observables, `takeUntilDestroyed` outside injection context. See `angular-rxjs-patterns`.
- **Lifecycle/DI timing**: `@ViewChild` undefined in `ngOnInit` (use `viewChild()` signal or `ngAfterViewInit`); `inject()` only in injection context. See `angular-component-patterns`, `angular-service-patterns`.
- **Routing**: missing `canActivate` cascades, lazy-route drift. See `angular-routing-patterns`.
- **Mid-migration churn**: mixed standalone/NgModule, mixed Zone/zoneless. See `task-angular-review`.
- **Security**: `[innerHTML]` XSS, `bypassSecurityTrust*` misuse, secrets in `environment.ts`, open redirects. See `task-angular-review-security`.

### First-PR Safe Zones

Safe: new component in an existing feature, new `providedIn: 'root'` service, new unit test, new route in an existing routes file.

Riskier: `app.config.ts`/`app.module.ts` providers, HTTP interceptors, auth guards, shared-component CD strategies.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Angular version, bootstrap style, change detection model, state library, RxJS-vs-signals split, test framework, monorepo (Nx) yes/no.

**Local Bootstrap:** install command, env file, `ng serve` port, `ng test`, build command.

**Architecture Map:** workspace layout, feature directory pattern, root config file (`app.config.ts` or `app.module.ts`), routing API.

**Conventions:** OnPush/signal usage, `inject()` vs constructor DI, async pipe vs manual subscribe, `takeUntilDestroyed`, control flow blocks.

**Risk Hotspots:** observed instances from the Risk Hotspots list above.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating pre-17 patterns as current.
- Recommending NgModule patterns on a standalone project (or vice versa).
- Listing every dependency; name only architectural ones.
- Skipping change detection identification - it shapes everything else.
- Recommending Protractor.
- Confusing `inject()` and constructor injection contexts.
