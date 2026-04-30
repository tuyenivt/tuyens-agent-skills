# Tuyen's Agent Skills - React

Claude Code plugin for React 19+ / TypeScript / Next.js (primary), Vite (secondary) development.

## Stack

- React 19+
- TypeScript (strict mode)
- Next.js App Router (primary), Vite + React Router (secondary)

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

| Skill              | Purpose                                                                       |
| ------------------ | ----------------------------------------------------------------------------- |
| `task-react-new`   | End-to-end React feature implementation (components + state + data + tests)   |
| `task-react-debug` | Debug React errors (hydration, hooks, render loops, Server Components, build) |

## Atomic Skills (Reusable Patterns)

8 atomic skills provide focused, reusable React patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

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

## Agents

| Agent                        | Focus                                                                  |
| ---------------------------- | ---------------------------------------------------------------------- |
| `react-architect`            | React/Next.js architecture: components, data flow, routing, TypeScript |
| `react-tech-lead`            | Code review with session context - tracks recurring patterns           |
| `react-performance-engineer` | Core Web Vitals, bundle analysis, React Profiler, Server Components    |
| `react-security-engineer`    | XSS prevention, CSP, auth patterns, Server Action validation           |
| `react-test-engineer`        | Testing strategy: React Testing Library, Vitest, MSW, Playwright       |

## Usage Examples

**Implement a full feature (components + state + data + tests):**

```
/task-react-new
Feature: Product catalog with filtering and search
Components: ProductList, ProductCard, FilterSidebar, SearchBar
Data: GET /api/products with category, search, pagination
State: URL-synced filters, local UI state for sidebar toggle
```

**Debug a React error:**

```
/task-react-debug
Error: "Hydration failed because the initial UI does not match what was rendered on the server"
Component: ProductList
Steps: Page loads fine on refresh, but shows hydration error on client navigation
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
