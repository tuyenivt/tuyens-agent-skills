# Tuyen's Agent Skills - React

Claude Code plugin for React 18+ (React 19 hooks) / TypeScript / Next.js 15 App Router (primary), Vite 5+ (secondary) development.

## Stack

- React 18+ baseline; React 19 hooks (`use`, `useOptimistic`, `useActionState`, `useFormStatus`) used throughout
- TypeScript (strict mode)
- Next.js 15 App Router (primary), Vite 5+ + React Router 6+ (secondary)

## Key Features

- **Server Components**: Server Components by default, `"use client"` only when needed (hooks, events, browser APIs)
- **React 19 Hooks**: use, useOptimistic, useActionState, useFormStatus
- **Data Fetching**: TanStack Query (primary), Server Component async fetching, Suspense streaming
- **State Management**: Zustand (primary), Redux Toolkit (enterprise), Jotai (atomic), proper state categorization
- **Next.js App Router**: Layouts, loading/error states, parallel routes, intercepting routes, middleware, Server Actions, ISR, Metadata API
- **Styling**: Tailwind CSS (primary), CSS Modules, cva + cn for component variants, shadcn/ui
- **Testing**: Vitest + React Testing Library, MSW for API mocking, Playwright for e2e
- **TypeScript-First**: Strict mode, proper prop typing, no `any` types

## Workflow Skills

Workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. They are invoked as slash commands.

| Skill                             | Purpose                                                                                                                                   | Agent                        |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `task-react-implement`            | End-to-end React feature implementation (components + state + data + tests)                                                               | `react-engineer`             |
| `task-react-review`               | Staff-level umbrella review with Phases A-E; spawns parallel perf / security / observability / reliability subagents                      | `react-tech-lead`            |
| `task-react-review-perf`          | Core Web Vitals (LCP / INP / CLS), bundle, hydration, RSC vs Client boundary, TanStack Query cache, ISR / `revalidate`                    | `react-performance-engineer` |
| `task-react-review-security`      | XSS via `dangerouslySetInnerHTML`, CSP / nonce, Server Action validation, `NEXT_PUBLIC_` leakage, open redirect, OWASP (React lens)       | `react-security-engineer`    |
| `task-react-review-observability` | `web-vitals`, Sentry browser SDK + error boundaries, OTel browser, Next.js `instrumentation.ts`, RUM, structured client logging           | `react-observability-engineer` |
| `task-react-review-reliability`   | Error boundary coverage, retry / backoff and cancellation, optimistic-update rollback, offline and reconnect, hydration and chunk-load failure | `react-reliability-engineer` |
| `task-react-test`                 | Test strategy / coverage assessment / scaffolds with Vitest + RTL + MSW + Playwright; Server Component testing strategy                   | `react-test-engineer`        |

## Atomic Skills (Reusable Patterns)

Atomic skills provide focused, reusable React patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

| Skill                      | Purpose                                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------------------- |
| `react-component-patterns` | Component design: composition, compound components, Server/Client boundaries, error boundaries |
| `react-hooks-patterns`     | Custom hooks, hook rules, useEffect discipline, React 19 hooks                                 |
| `react-routing-patterns`   | React Router (Vite) / Next.js App Router: layouts, loading, error, parallel routes             |
| `react-nextjs-patterns`    | Next.js App Router: Server Components, Server Actions, ISR, metadata                           |
| `react-state-patterns`     | State management: useState/useReducer, Zustand, Redux Toolkit, Jotai                           |
| `react-data-fetching`      | TanStack Query, Server Component fetching, cache invalidation, optimistic updates              |
| `react-styling-patterns`   | Tailwind CSS, CSS Modules, cva + cn, dark mode, design tokens                                  |
| `react-testing-patterns`   | Vitest + React Testing Library, MSW, hook testing, Playwright e2e                              |
| `react-legacy-integration` | Embed React into legacy apps: island adoption, React-in-Rails/Django/PHP, Module Federation, single-spa, hydration boundaries |
| `react-overengineering-review` | Flag React overengineering: premature memo, single-consumer Context, store-for-two-slices, single-use hooks, generic-for-one-usage |
| `react-onboard-map`        | Build framework (Next App/Pages, Vite), routing, state management, data fetching, styling, component library - injected into `task-onboard` |

## Agents

| Agent                        | Focus                                                                  |
| ---------------------------- | ---------------------------------------------------------------------- |
| `react-engineer`             | Builds React/Next.js features end-to-end; debugs hydration, hooks, render loops |
| `react-tech-lead`            | Code review with session context - tracks recurring patterns           |
| `react-performance-engineer` | Core Web Vitals, bundle analysis, React Profiler, Server Components    |
| `react-security-engineer`    | XSS prevention, CSP, auth patterns, Server Action validation           |
| `react-observability-engineer` | web-vitals RUM, Sentry browser SDK + error boundaries, source maps, OTel, trace propagation |
| `react-reliability-engineer` | Error boundary placement, retry and cancellation, optimistic rollback, offline and reconnect, chunk-load recovery |
| `react-test-engineer`        | Testing strategy: React Testing Library, Vitest, MSW, Playwright       |

## Usage Examples

**Implement a full feature (components + state + data + tests):**

```
/task-react-implement
Feature: Product catalog with filtering and search
Components: ProductList, ProductCard, FilterSidebar, SearchBar
Data: GET /api/products with category, search, pagination
State: URL-synced filters, local UI state for sidebar toggle
```

**Review reliability of a checkout flow:**

```
/task-react-review-reliability
Scope: app/checkout - Server Action submit, TanStack Query cart, optimistic quantity updates
Concern: users report a blank screen when the payment API is slow
```

## Core Plugin Skills

The following workflows are provided by `core` (install separately):

- `/task-code-review` - Staff-level code review with risk assessment, framework-aware
- `/task-code-review-security` - Security review
- `/task-code-review-perf` - Performance review
- `/task-code-review-reliability` - Reliability review
- `/task-code-test` - Test strategy
