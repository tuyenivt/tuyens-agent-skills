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

- Detect build framework first - Next.js (`next.config.*`) App Router (`app/`) vs Pages Router (`pages/`); Vite (`vite.config.*`); React Router framework mode / Remix (`react-router.config.*`, or legacy `remix.config.*`); CRA (`react-scripts` in `package.json`, sunset). Routing and mental model diverge. A repo running two conventions at once is mid-migration - report both as live and flag the dual mental model, whether that is `app/` beside `pages/` or a SPA beside server-rendered templates it is replacing.
- Detect React version - 18 vs 19 (`use()`, Server Actions). Server Components are most common in the Next App Router but no longer exclusive to it (React Router v7, Vite's RSC plugin).
- Detect package manager from lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock` or the older binary `bun.lockb`).
- Detect state layer - `useState`+`useContext` (Context-only providers count here), Zustand, Redux Toolkit, Jotai, MobX, or none. Server-cache libraries answer data fetching, not state. Report a second store library as a finding, not a footnote: two are a migration in progress or an accident.
- Detect data fetching - TanStack Query, SWR, Apollo, urql, RTK Query, native fetch in Server Components, or a raw HTTP client (axios/fetch with no cache library).
- Detect the persistence layer - Prisma (`prisma/schema.prisma`, a `prisma/schema/` directory, or a `prisma.config.*` pointing elsewhere), Drizzle (`drizzle.config.*`), Kysely or a raw driver (a `pg`/`mysql2`/`postgres` dependency with no ORM config), or none. A Next.js repo with an ORM is a fullstack app: report the server surface, not just the UI.
- Detect the deployment target - managed platform (`vercel.json`, platform config) vs self-hosted (`Dockerfile`, `docker-compose.*`, `output: "standalone"` in `next.config.*`); with neither signal, report `static/unknown - no deploy signal observed`. Self-hosted changes the caching, image, and ISR story materially.

## Patterns

### Build Inventory

| File                              | What it tells you                                          |
| --------------------------------- | ---------------------------------------------------------- |
| `next.config.*`                   | Next.js; App Router (`app/`) vs Pages Router (`pages/`)    |
| `vite.config.*`                   | Vite; check `@vitejs/plugin-react` vs `-swc`               |
| `tsconfig.json`                   | TS config; `strict: true` matters                          |
| `tailwind.config.*` / `postcss.config.*` | Tailwind v3 pipeline; v4 is CSS-first - look for `@import "tailwindcss"` in the entry CSS or `@tailwindcss/vite` |
| `.env.example` (`.env.local` is git-ignored) | Env vars; client-bundled prefixes: `NEXT_PUBLIC_*` (Next), `VITE_*` (Vite), `REACT_APP_*` (CRA) |
| `eslint.config.*` / `.eslintrc.*` / `.prettierrc.*` | Lint/format config                       |
| `vitest.config.*` / `jest.config.*` | Vitest or Jest unit/component runner                     |
| `playwright.config.*` / `cypress.config.*` | E2E framework (Cypress may also run component tests) |
| `prisma/schema.prisma` / `drizzle.config.*` | ORM and migration tool; fullstack app          |
| `Dockerfile` / `docker-compose.*` / `compose.*` | Self-hosted; check for `output: "standalone"` |
| `src/server/` or `lib/server/`    | Service layer; the reuse seam for a future API    |

### Bootstrap

1. Install: `<manager> install` (manager from lockfile; `engines.node` in `package.json`).
2. Env: copy `.env.example` when it exists - to `.env.local` for Next, or `.env.local` for Vite (`.env` is usually not git-ignored); fill required keys.
3. Fullstack (ORM detected): start the database (compose service when present) and run migrations through the package runner (`npx prisma migrate dev`, `pnpm exec drizzle-kit migrate`) before first run.
4. Run: `<manager> run dev` - Next defaults to `:3000`, Vite to `:5173`.
5. Verify: open entry route (mid-migration: one route from each router); check `pages/api/*` or `app/**/route.ts` if an API exists.

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
| `middleware.ts` (repo root, both routers) | Request middleware - auth, redirects, headers; Node runtime since 15.5 |
| `instrumentation.ts` (root) | OTel / Sentry server + edge registration; `instrumentation-client.ts` for the browser |
| `app/registry.tsx`              | CSS-in-JS SSR registry (styled-components / emotion) |

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
- **Component library:** check `package.json` for `@radix-ui/*`, `@mui/*`, `@chakra-ui/*`, `@headlessui/react`; shadcn/ui is never a dependency - look for `components.json` and `components/ui/`.
- **Styling:** Tailwind, CSS Modules, styled-components, emotion, vanilla CSS.
- **Forms:** React Hook Form + zod, Formik, controlled inputs.
- **Auth:** NextAuth/Auth.js, Clerk, Auth0, Supabase Auth, custom JWT.
- **Analytics/obs:** posthog-js, `@sentry/*`, `instrumentation.ts` registration - reported under Stack and Tooling.
- **Tests:** Vitest or Jest + React Testing Library + jsdom; Playwright/Cypress for E2E. A single-layer setup - E2E-only with no unit runner, or unit-only with no E2E - is a coverage gap worth noting.

### Risk Hotspots

- **`useEffect` misuse** - stale closures, derived state, missing AbortController, missing cleanup: see `react-hooks-patterns`.
- **Identity instability** - inline `{}`/`[]`/`() => ...` in JSX breaking memoization: see `react-component-patterns`.
- **`"use client"` creep** - boundary placed too high; importing server-only into Client Components: see `react-nextjs-patterns`.
- **Next fetch caching** - `fetch` is uncached by default since 15; `force-cache`, `next: { revalidate | tags }` and `unstable_cache` are the opt-ins: see `react-nextjs-patterns`.
- **Hydration mismatch** - timestamps, random IDs, browser-only APIs in render body; `next-themes` needs `suppressHydrationWarning` on `<html>`.
- **Server → Client leaks** - full ORM rows as props, `dangerouslySetInnerHTML` XSS, `NEXT_PUBLIC_*` secret leak, Server Action without auth/Zod: see `task-react-review-security`.
- **Store-on-server (Next.js + Zustand/Redux)** - module-level stores share state across requests on the server. Instantiate per-request in a provider or keep stores in `"use client"` modules only.
- **ORM client without a hot-reload guard** (Next.js + any ORM) - a module-scope client not cached on `globalThis` leaks a pool per edit in development until the database refuses connections: see `react-server-data-layer`.
- **Self-hosted ISR and CDN rules** (self-hosted only) - local-disk ISR cache with more than one instance, or a CDN cache rule that does not bypass on the session cookie: see `react-selfhost-operations`.

The hydration / `"use client"` / fetch-caching / `NEXT_PUBLIC_*` / store-on-server hotspots above are Next.js-only - omit them for a Vite/CRA SPA. SPA-specific hotspots to report instead: unstable Redux/Zustand selectors causing wide re-renders, axios/fetch without `AbortController` (no query-cache dedupe), and `MUI sx={{}}` / inline-object props defeating memoization.

### First-PR Safe Zones

Safe: new page in existing routing convention, new component in existing library structure, new hook in `src/hooks/`, new env var in `.env.example`. Config-routed SPAs (`createBrowserRouter`): a new route edits central config - still safe; flag the shared file.

Riskier: root layout / `_app.tsx`, `middleware.ts`, auth provider, `next.config.*` (rebuild required).

## Output Format

Composed by `task-onboard`, inject into its sections; invoked standalone, emit the same sections in this order as a self-contained `## React Onboard Map`, each section a `###` heading with bullet fields. The mid-migration flag lives in Stack and Tooling. Doc-vs-repo contradictions (a README command no script defines) are reported where they bite (Local Bootstrap); detection findings (non-strict TS, coverage gap) stay inside Conventions.

- **Stack and Tooling**: package manager, build framework (Next App/Pages, Vite, React Router framework mode, CRA), React version, TS strict, state management, data fetching, styling, component library, ORM and migration tool (or `none - client only`), deployment target (managed platform, self-hosted, or `static/unknown - no deploy signal observed`), analytics/observability deps (`@sentry/*`, `posthog-js`, an OTel package, `instrumentation*.ts`) when present. Where a signal is absent, write `none observed`; where two coexist, name the one the newest code uses and flag the other as a live second convention.
- **Local Bootstrap**: install command, env file, database and migration step when an ORM is detected, run command, port (read from the dev script or `vite.config`; the `:3000`/`:5173` defaults apply only when nothing overrides them), entry route. Any documented command the repo contradicts is reported here, naming both what the docs say and what the repo supports.
- **Architecture Map**: routing convention (file-based vs config), components/hooks/utilities layout, server/client boundary if Next App Router, API location (`app/*/route.ts`, `pages/api`, or external), service layer (`src/server/`, `lib/server/`) when present.
- **Conventions**: TS strict, styling, data fetching, form handling, auth provider, test framework.
- **Risk Hotspots**: the Risk Hotspots list above is the source; emit the entries matching the detected framework plus the conditional sets (ORM detected adds the hot-reload guard; self-hosted adds ISR/CDN). It is a floor, not a closed set - a hazard this project has that no entry names still gets reported here, one line, named plainly.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Treating Pages Router and App Router as interchangeable - different mental models
- Listing every UI dep - call out the one the project commits to
- Recommending CRA patterns - sunset by the React team in 2025; use Next or Vite
- Glossing over `"use client"` boundaries when describing App Router
- Skipping hydration mismatch as a risk class
- Recommending Apollo on a TanStack Query project (or vice versa) without justification
