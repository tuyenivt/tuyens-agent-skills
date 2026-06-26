---
name: react-onboard-map
description: "Map React onboarding signals: Next.js App/Pages or Vite, React 18/19, TS strict, state, data fetching, styling, component library."
metadata:
  category: frontend
  tags: [onboarding, codebase-map, react, nextjs, vite]
user-invocable: false
---

# React Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is React.

## When to Use

Workflow needs React-specific orientation: build framework, routing, state, data fetching, styling, component library, server/client boundary. Project has `package.json` with `react`.

## Rules

- Detect build framework first - Next.js (`next.config.*`) App Router (`app/`) vs Pages Router (`pages/`); Vite (`vite.config.*`); Remix; CRA (legacy). Routing and mental model diverge. A repo with both `app/` and `pages/` is mid-migration - report both routers as live and flag the dual mental model.
- Detect React version - 18 vs 19 (`use()`, Server Actions). Server Components only in Next App Router today.
- Detect package manager from lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`).
- Detect state layer - `useState`+`useContext`, Zustand, Redux Toolkit, Jotai, Recoil, MobX, or none.
- Detect data fetching - TanStack Query, SWR, Apollo, urql, RTK Query, or native fetch in Server Components.

## Patterns

### Build Inventory

| File                              | What it tells you                                          |
| --------------------------------- | ---------------------------------------------------------- |
| `next.config.*`                   | Next.js; App Router (`app/`) vs Pages Router (`pages/`)    |
| `vite.config.*`                   | Vite; check `@vitejs/plugin-react` vs `-swc`               |
| `tsconfig.json`                   | TS config; `strict: true` matters                          |
| `tailwind.config.*` / `postcss.config.*` | Tailwind / PostCSS pipeline                          |
| `.env.local`, `.env.example`      | Env vars; Next public prefix `NEXT_PUBLIC_*`               |
| `eslint.config.*` / `.prettierrc.*` | Lint/format config                                       |
| `vitest.config.*` / `jest.config.*` | Vitest or Jest unit/component runner                     |
| `playwright.config.*` / `cypress.config.*` | E2E framework                                     |

### Bootstrap

1. Install: `<manager> install` (manager from lockfile; `engines.node` in `package.json`).
2. Env: `cp .env.example .env.local` (Next) or `.env` (Vite); fill required keys.
3. Run: `npm run dev` - Next defaults to `:3000`, Vite to `:5173`.
4. Verify: open entry route; Next App Router shows `loading.tsx` boundaries; check `/api/*` or `app/*/route.ts` if API exists.

### Key Files

**Next.js App Router**

| Location                        | Purpose                                          |
| ------------------------------- | ------------------------------------------------ |
| `app/layout.tsx`                | Root layout (Server Component); HTML shell       |
| `app/<seg>/page.tsx`            | Route page (`[id]` dynamic; `(group)` = no URL segment, layout grouping) |
| `app/<seg>/layout.tsx`          | Nested layout                                    |
| `app/<seg>/loading.tsx` / `error.tsx` | Suspense fallback / error boundary         |
| `app/<seg>/route.ts`            | API route handler                                |
| `app/providers.tsx`             | Conventional `"use client"` provider wrapper (QueryClient, Theme, Auth) imported by `layout.tsx` |
| `middleware.ts`                 | Edge middleware (auth, redirects, headers)       |
| `instrumentation.ts`            | OTel / Sentry server registration                |

**Next.js Pages Router (legacy):** `pages/_app.tsx` root, `pages/_document.tsx` shell, `pages/<route>.tsx`, `pages/api/<route>.ts`.

**Vite SPA**

| Location                                | Purpose                                  |
| --------------------------------------- | ---------------------------------------- |
| `index.html` + `src/main.tsx`           | HTML entry + mount to `#root`            |
| `src/App.tsx`                           | Root component                           |
| `src/routes/` or `src/pages/`           | React Router / TanStack Router files     |
| `src/components/`, `src/hooks/`, `src/lib/` | UI, hooks, utilities                 |
| `src/api/` or `src/services/`           | HTTP clients                             |

### Conventions

- **TS strict** from `tsconfig.json`; non-strict is a finding.
- **Component library:** check `package.json` for `@radix-ui/*`, `shadcn/ui` (look in `components/ui/`), `@mui/*`, `@chakra-ui/*`, `headlessui`.
- **Styling:** Tailwind, CSS Modules, styled-components, emotion, vanilla CSS.
- **Forms:** React Hook Form + zod, Formik, controlled inputs.
- **Auth:** NextAuth/Auth.js, Clerk, Auth0, Supabase Auth, custom JWT.
- **Tests:** Vitest or Jest + React Testing Library + jsdom; Playwright/Cypress for E2E. An E2E-only setup with no unit/component runner is a coverage gap worth noting.

### Risk Hotspots

- **`useEffect` misuse** - stale closures, derived state, missing AbortController, missing cleanup: see `react-hooks-patterns`.
- **Identity instability** - inline `{}`/`[]`/`() => ...` in JSX breaking memoization: see `react-component-patterns`.
- **`"use client"` creep** - boundary placed too high; importing server-only into Client Components: see `react-nextjs-patterns`.
- **Next fetch caching** - default behavior, `cache: 'no-store'`, `next: { revalidate }`, `unstable_cache`: see `react-data-fetching`.
- **Hydration mismatch** - timestamps, random IDs, browser-only APIs in render body; `next-themes` needs `suppressHydrationWarning` on `<html>`.
- **Server → Client leaks** - full ORM rows as props, `dangerouslySetInnerHTML` XSS, `NEXT_PUBLIC_*` secret leak, Server Action without auth/Zod: see `task-react-review-security`.
- **Store-on-server (Next.js + Zustand/Redux)** - module-level stores share state across requests on the server. Instantiate per-request in a provider or keep stores in `"use client"` modules only.

The hydration / `"use client"` / fetch-caching / `NEXT_PUBLIC_*` / store-on-server hotspots above are Next.js-only - omit them for a Vite/CRA SPA. SPA-specific hotspots to report instead: unstable Redux/Zustand selectors causing wide re-renders, axios/fetch without `AbortController` (no query-cache dedupe), and `MUI sx={{}}` / inline-object props defeating memoization.

### First-PR Safe Zones

Safe: new page in existing routing convention, new component in existing library structure, new hook in `src/hooks/`, new env var in `.env.example`.

Riskier: root layout / `_app.tsx`, `middleware.ts`, auth provider, `next.config.*` (rebuild required).

## Output Format

Inject into `task-onboard` sections:

- **Stack and Tooling**: package manager, build framework (Next App/Pages, Vite, Remix), React version, TS strict, state management, data fetching, styling, component library.
- **Local Bootstrap**: install command, env file, run command, default port, entry route.
- **Architecture Map**: routing convention (file-based vs config), components/hooks/utilities layout, server/client boundary if Next App Router, API location (`app/*/route.ts`, `pages/api`, or external).
- **Conventions**: TS strict, styling, data fetching, form handling, auth provider, test framework.
- **Risk Hotspots**: stale closures and inline JSX identity (all stacks); for Next.js add `"use client"` boundary, fetch caching, hydration mismatch, `NEXT_PUBLIC_*`, store-on-server; for a Vite/CRA SPA add unstable Redux/Zustand selectors, axios/fetch without `AbortController`, inline-object/`sx` props defeating memoization. Emit only the hotspots that match the detected framework.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Treating Pages Router and App Router as interchangeable - different mental models
- Listing every UI dep - call out the one the project commits to
- Recommending CRA patterns - deprecated; use Next or Vite
- Glossing over `"use client"` boundaries when describing App Router
- Skipping hydration mismatch as a risk class
- Recommending Apollo on a TanStack Query project (or vice versa) without justification
