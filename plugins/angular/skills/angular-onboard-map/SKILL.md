---
name: angular-onboard-map
description: Angular 21 project onboarding signals - Angular CLI workspace, standalone components, Signals vs Zone.js, RxJS usage, routing, state management (NgRx/Akita), and styling. Used by task-onboard to map an Angular codebase for a new engineer.
metadata:
  category: frontend
  tags: [onboarding, codebase-map, angular, rxjs, signals]
user-invocable: false
---

# Angular Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Angular.

## When to Use

- A workflow needs Angular-specific orientation: workspace structure, change detection model, standalone vs NgModule, RxJS usage, state management, routing.
- Project has `angular.json` and `package.json` with `@angular/core`.

## Rules

- Identify Angular version (`package.json` `@angular/core`); 21 is current; 17+ has standalone-by-default and signals.
- Identify standalone vs NgModule: standalone has no `app.module.ts`; bootstrap via `bootstrapApplication(AppComponent, { providers: [...] })` in `main.ts`.
- Identify change detection model: signal-based (`signal()`/`computed()`/`effect()`), `OnPush`, or default (Zone.js global).
- Identify state management: NgRx (`@ngrx/*` deps, `store/` directory), NGXS, Akita (legacy), Signal Store (NgRx Signals), or just services with signals/BehaviorSubjects.
- Identify routing: `provideRouter(routes)` (standalone) or `RouterModule.forRoot(routes)` (NgModule).

## Patterns

### Build Inventory

| File                | What it tells you                                                                |
| ------------------- | -------------------------------------------------------------------------------- |
| `angular.json`      | Angular CLI workspace; build/serve/test config; multi-project support             |
| `package.json`      | Angular core/CLI/material versions                                                |
| `tsconfig.json` + `tsconfig.app.json` + `tsconfig.spec.json` | TS configs split by build target  |
| `karma.conf.js`     | Karma test runner (legacy default)                                                |
| `.eslintrc.json` / `eslint.config.js` | ESLint config (replacing TSLint long ago)                       |
| `nx.json` / `nx-cloud.json` | Nx monorepo config (if applicable)                                       |

### Bootstrap Path

1. Node toolchain: confirm `engines.node` in `package.json`. Angular 17+ requires Node 18.13+.
2. Install: `npm install` (or `pnpm`/`yarn`).
3. Env: typically via `environment.ts` files (`src/environments/environment.ts` and `environment.prod.ts`); some projects use runtime config loaded at startup.
4. Run: `ng serve` or `npm start` (often aliases `ng serve --open`); default port 4200.
5. Verify: `http://localhost:4200`; default app shell.
6. Build: `ng build` (`--configuration=production` or by default).
7. Test: `ng test` (Karma + Jasmine; some projects on Jest or Vitest).
8. E2E: project-specific (Cypress, Playwright; Protractor deprecated).

### Key File Inventory

**Standalone (Angular 17+ default):**

| Location                  | Purpose                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `src/main.ts`             | `bootstrapApplication(AppComponent, { providers: [...] })`              |
| `src/app/app.component.ts` | Root component                                                          |
| `src/app/app.routes.ts`   | Route definitions: `Routes` array passed to `provideRouter`              |
| `src/app/app.config.ts`   | App-level providers (router, http, animations, custom services)          |
| `src/app/<feature>/`      | Feature directories with components/services                              |
| `src/app/<feature>/<feat>.component.ts` | Component (standalone with `imports: [...]`)               |
| `src/app/<feature>/<feat>.service.ts`   | Service (`@Injectable({ providedIn: 'root' })`)            |
| `src/app/<feature>/<feat>.routes.ts`    | Feature routes (lazy-loaded via `loadChildren`)            |
| `src/environments/`       | Environment configs                                                       |
| `src/styles.css` / `.scss` | Global styles                                                           |
| `src/assets/`             | Static assets                                                              |

**NgModule (legacy):**

| Location                  | Purpose                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `src/app/app.module.ts`   | Root NgModule                                                              |
| `src/app/app-routing.module.ts` | Root routing module                                                  |
| `src/app/<feature>/<feature>.module.ts` | Feature module                                              |
| `src/app/<feature>/<feature>-routing.module.ts` | Feature routing                                      |

### Conventions

- **One concept per file:** component, service, directive, pipe, guard, interceptor each get their own file.
- **Component naming:** `<name>.component.ts` (with `<name>.component.html` + `<name>.component.scss/css`).
- **`ChangeDetectionStrategy.OnPush`** common for performance; signal-based components are inherently OnPush-like.
- **DI lifetimes:** `providedIn: 'root'` (most services), `providedIn: 'any'` (instance per lazy-loaded module - rare), per-component `providers: [...]`.
- **Reactive Forms** preferred over Template-driven for non-trivial forms.
- **RxJS:**
  - `async` pipe in templates (auto-subscribe/unsubscribe).
  - `takeUntilDestroyed()` operator (Angular 16+) replacing manual `destroy$` patterns.
  - `inject(DestroyRef)` for explicit cleanup outside components.
- **HttpClient interceptors** (`HttpInterceptorFn` functional or class-based) for auth, logging, retries.
- **Tests:** Karma + Jasmine default; Jest/Vitest gaining ground; component tests use `TestBed.createComponent` or `@analog/vitest-angular`.
- **Linting:** `@angular-eslint/*` rules.

### Risk Hotspots Specific to Angular

- **`OnPush` not detecting in-place mutations:** mutating an array/object input does not trigger CD. Replace the reference.
- **Cold observable triggering one HTTP per subscription:** `<div>{{user$ | async}}</div>` and another `*ngFor` over the same observable issues two requests.
- **`@ViewChild` undefined in `ngOnInit`:** view is not yet initialized; use `ngAfterViewInit` or `viewChild()` signal.
- **`inject()` outside injection context:** throws; can only be called in constructor, field initializer, factory, or guard/resolver.
- **Subscription leaks:** manual `subscribe` without `takeUntilDestroyed` or `ngOnDestroy` cleanup.
- **Pure pipe array mutation:** in-place push to an array does not re-run pure pipes; use new array.
- **Route guard on lazy module/route configuration drift:** missing `canActivate` cascades to children unless overridden.
- **NgZone reentry:** mixing zone-aware and zone-free code causes change detection skips.
- **Standalone migration churn:** some projects in mid-migration from NgModule to standalone; mixed bootstrap can confuse.

### First-PR Safe Zones

- New component in existing feature directory.
- New service with `providedIn: 'root'`.
- New unit test next to a service.
- New route in existing routes file.

Riskier:

- `app.config.ts` / `app.module.ts` - app-level provider list.
- HTTP interceptors - apply to every request.
- Auth guards.
- Custom change detection strategies in shared components.

### Ecosystem Currency

- Angular 17+ default to standalone components; Angular 18+ has zoneless mode (experimental in 18, stable in 19+).
- Signals stable since 17; `viewChild()`/`contentChild()` signal-based queries in 17+.
- Control flow blocks (`@if`, `@for`, `@switch`) replacing `*ngIf`/`*ngFor` in templates.
- Material 3 design system rolling out; `@angular/material` updated alongside.
- NgRx 18+ adopting signal-based stores; Signal Store and Component Store coexist.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Angular version, standalone vs NgModule, change detection (default/OnPush/signal/zoneless), state management, RxJS-vs-signals split, test framework.

**Local Bootstrap:** `npm install`, env config, `ng serve`, default port, `ng test` for tests.

**Architecture Map:** workspace structure (single project vs Nx), feature directory layout, root config (`app.config.ts` or `app.module.ts`), routing strategy.

**Conventions:** OnPush usage, `inject()` style vs constructor-injection, async pipe vs manual subscribe, takeUntilDestroyed pattern, control flow blocks vs structural directives.

**Risk Hotspots:** OnPush mutation, subscription leaks, ViewChild timing, inject() context, cold observable HTTP duplication, NgZone reentry, mid-migration mixed bootstrap.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Angular 2-12 patterns as current; modern Angular is meaningfully different
- Recommending NgModule patterns on a standalone project (or vice versa)
- Listing every dep - focus on the architectural ones
- Skipping the change detection model identification - it shapes everything
- Recommending Protractor (deprecated)
- Confusing `inject()` and constructor injection contexts
