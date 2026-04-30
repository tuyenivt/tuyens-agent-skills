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

| Skill                | Purpose                                                                       |
| -------------------- | ----------------------------------------------------------------------------- |
| `task-angular-new`   | End-to-end Angular feature implementation (components + state + data + tests) |
| `task-angular-debug` | Debug Angular errors (change detection, RxJS, DI, routing, build, zone.js)    |

## Atomic Skills (Reusable Patterns)

8 atomic skills provide focused, reusable Angular patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

| Skill                        | Purpose                                                                           |
| ---------------------------- | --------------------------------------------------------------------------------- |
| `angular-component-patterns` | Standalone components, signals I/O, content projection, control flow, OnPush      |
| `angular-signals-patterns`   | signal(), computed(), effect(), toSignal/toObservable, linkedSignal, model inputs |
| `angular-routing-patterns`   | Lazy loading, functional guards/resolvers, nested routes, animations, SSR         |
| `angular-service-patterns`   | DI hierarchy, functional interceptors, HttpClient, injection tokens               |
| `angular-rxjs-patterns`      | Async pipe, takeUntilDestroyed, flattening operators, error handling              |
| `angular-state-patterns`     | Signals, NgRx Store, NgRx ComponentStore, service-based state, URL state          |
| `angular-styling-patterns`   | Tailwind CSS, Angular Material/CDK, PrimeNG, CSS custom properties, theming       |
| `angular-testing-patterns`   | Angular Testing Library, component harnesses, HttpTestingController, Playwright   |

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
/task-angular-new
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

The following workflows are provided by `core` (install separately):

- `/task-code-review` - Staff-level code review with risk assessment, framework-aware
- `/task-code-secure` - Security review
- `/task-code-test` - Test strategy
- `/task-code-refactor` - Refactoring plan
- `/task-code-perf-review` - Performance review
- `/task-docs-generate` - Documentation generation
- `/task-incident-root-cause` - Incident root cause analysis
- `/task-incident-postmortem` - Post-incident postmortem
- `/task-release-plan` - Production release planning
- `/task-design-risk-analysis` - Proactive risk assessment
- `/task-design-architecture` - Architecture design proposal
