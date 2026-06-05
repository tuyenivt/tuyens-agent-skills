# Tuyen's Agent Skills - Angular

Claude Code plugin for Angular 21+ / TypeScript / Angular CLI development.

## Stack

- Angular 21+
- TypeScript (strict mode)
- Angular CLI

## Key Features

- **Standalone Components**: Standalone by default, OnPush change detection everywhere, signal-based inputs/outputs
- **Signals**: signal(), computed(), effect(), toSignal/toObservable bridge, linkedSignal, model inputs
- **RxJS Integration**: Proper operator selection, async pipe, takeUntilDestroyed, signals migration path
- **State Management**: Signals (primary), NgRx Store (enterprise), NgRx ComponentStore, service-based stores
- **Routing**: Lazy loading with loadComponent/loadChildren, functional guards and resolvers, route animations, SSR
- **Services & DI**: Injectable hierarchy, functional HTTP interceptors, HttpClient patterns, injection tokens
- **Styling**: Tailwind CSS (primary), Angular Material/CDK, PrimeNG, CSS custom properties, ViewEncapsulation
- **Testing**: Vitest/Jest + Angular Testing Library, component harnesses, HttpTestingController, Playwright e2e
- **TypeScript-First**: Strict mode, proper typing, no `any` types

## Workflow Skills

Workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. They are invoked as slash commands.

| Skill                                | Agent                          | Purpose                                                                                                          |
| ------------------------------------ | ------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `task-angular-implement`             | `angular-architect`            | End-to-end Angular feature implementation (components + state + data + tests)                                    |
| `task-angular-debug`                 | `angular-tech-lead`            | Debug Angular errors (change detection, RxJS, DI, routing, build, zone.js)                                       |
| `task-angular-review`                | `angular-tech-lead`            | Angular staff-level code review umbrella (Phases A-E + parallel perf/security/observability subagents)           |
| `task-angular-review-perf`           | `angular-performance-engineer` | Angular performance review (CWV, bundle, change detection, signals, `@defer`, SSR + HTTP transfer cache)         |
| `task-angular-review-security`       | `angular-security-engineer`    | Angular security review (`[innerHTML]`, `bypassSecurityTrust*`, CSP, functional guards/interceptors, OWASP)      |
| `task-angular-review-observability`  | `angular-tech-lead`            | Angular observability review (web-vitals, Sentry + ErrorHandler, OTel, RUM, structured logging)                  |
| `task-angular-test`                  | `angular-test-engineer`        | Angular test strategy and scaffolding (TestBed, ATL, `HttpTestingController`, CDK harnesses, Playwright)         |
| `task-angular-refactor`              | `angular-tech-lead`            | Angular refactor planning (god component, BehaviorSubject→signals, OnPush migration, NgModule→standalone, etc.)  |

## Atomic Skills (Reusable Patterns)

Atomic skills provide focused, reusable Angular patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

| Skill                        | Purpose                                                                           |
| ---------------------------- | --------------------------------------------------------------------------------- |
| `angular-component-patterns` | Standalone components, signals I/O, content projection, control flow, OnPush      |
| `angular-signals-patterns`   | signal(), computed(), effect(), untracked, toSignal/toObservable, linkedSignal, model inputs |
| `angular-routing-patterns`   | Lazy loading, functional guards/resolvers, nested routes, `withComponentInputBinding`, SSR |
| `angular-service-patterns`   | DI hierarchy, functional interceptors, HttpClient, `httpResource`, injection tokens |
| `angular-data-fetching`      | HttpClient, `resource`/`httpResource`, TanStack Query for Angular, Apollo, SSR transfer cache, cache invalidation, optimistic updates |
| `angular-rxjs-patterns`      | Async pipe, takeUntilDestroyed, flattening operators, error handling              |
| `angular-state-patterns`     | Signals, NgRx Signal Store, NgRx Store, ComponentStore, service-based state, URL state |
| `angular-forms-patterns`     | Typed Reactive Forms, `FormArray`, async/cross-field validators, `ControlValueAccessor`, server validation surfacing |
| `angular-nx-patterns`        | Nx monorepo - tags + `enforce-module-boundaries`, library taxonomy, `nx affected`, generators |
| `angular-styling-patterns`   | Tailwind CSS, Angular Material/CDK + M3 theming, PrimeNG, CSS custom properties, CDK overlay |
| `angular-i18n-patterns`      | `@angular/localize`, `$localize`, `i18n` attribute, ICU expressions, `LOCALE_ID`, `transloco` |
| `angular-testing-patterns`   | Angular Testing Library, component harnesses, HttpTestingController, Playwright   |
| `angular-code-explain`       | Signals and zoneless CD, standalone components, DI hierarchy, RxJS + async pipe, lifecycle, routing - injected into `task-code-explain` |
| `angular-onboard-map`        | Angular CLI workspace, standalone vs NgModule, Signals vs Zone.js, RxJS, routing, state (NgRx/Signal Store), Nx - injected into `task-onboard` |

## Agents

| Agent                          | Focus                                                                   |
| ------------------------------ | ----------------------------------------------------------------------- |
| `angular-architect`            | Angular architecture: standalone components, signals, DI, routing, RxJS |
| `angular-tech-lead`            | Code review with session context - tracks recurring patterns            |
| `angular-performance-engineer` | Change detection, bundle analysis, lazy loading, signals migration, CWV |
| `angular-security-engineer`    | XSS prevention, DomSanitizer, auth guards, HTTP interceptor security    |
| `angular-test-engineer`        | Testing strategy: Angular Testing Library, Vitest/Jest, Playwright      |

## Usage Examples

**Implement a full feature (components + state + data + tests):**

```
/task-angular-implement
Feature: Product catalog with filtering and search
Components: ProductListComponent, ProductCardComponent, FilterSidebarComponent, SearchBarComponent
Data: GET /api/products with category, search, pagination
State: URL-synced filters, local signal for sidebar toggle
```

**Debug an Angular error:**

```
/task-angular-debug
Error: "NullInjectorError: No provider for ProductService"
Component: ProductListComponent
Steps: Added ProductService but forgot to add providedIn: 'root'
```

## Core Plugin Skills

The following workflows are provided by `core` (install separately) and dispatch to the Angular workflows above when stack-detect resolves to Angular:

- `/task-code-review` - dispatches to `task-angular-review`
- `/task-code-review-security` - dispatches to `task-angular-review-security`
- `/task-code-review-perf` - dispatches to `task-angular-review-perf`
- `/task-code-review-observability` - dispatches to `task-angular-review-observability`
- `/task-code-test` - dispatches to `task-angular-test`
- `/task-code-refactor` - dispatches to `task-angular-refactor`
