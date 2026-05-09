---
name: react-onboard-map
description: Map React 19 / Next.js / Vite codebase for onboarding: framework, TypeScript, routing, state, data fetching, styling, component library.
metadata:
  category: frontend
  tags: [onboarding, codebase-map, react, nextjs, vite]
user-invocable: false
---

# React Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is React.

## When to Use

- A workflow needs React-specific orientation: package manager, build framework, routing, state, styling, component library, data fetching.
- Project has `package.json` with `react` dep.

## Rules

- Identify build framework first: Next.js (`next` dep + `next.config.*`) - App Router (`app/`) vs Pages Router (`pages/`); Vite (`vite.config.*`); CRA (legacy); Remix; React Router + custom build.
- Identify package manager (npm/yarn/pnpm/bun) - same as Node onboarding.
- Identify React version: 18 (mature, hooks era) vs 19 (use(), Server Actions, Actions).
- Identify state management: built-in (`useState`+`useContext`), Zustand, Redux Toolkit, Jotai, Recoil, MobX, or none.
- Identify data fetching: TanStack Query, SWR, Apollo, urql, RTK Query, native fetch in Server Components.

## Patterns

### Build Framework Inventory

| File                  | What it tells you                                                              |
| --------------------- | ------------------------------------------------------------------------------ |
| `next.config.js` / `.ts` / `.mjs` | Next.js project; check for App Router (`app/`) vs Pages (`pages/`) |
| `vite.config.js` / `.ts` | Vite project; check `plugins` for `@vitejs/plugin-react` or `-swc`           |
| `tsconfig.json`       | TypeScript config; `strict` mode setting matters                                |
| `tailwind.config.*`   | Tailwind CSS                                                                    |
| `postcss.config.*`    | PostCSS pipeline                                                                |
| `.env.local`, `.env.development` | Env vars (Next.js convention `NEXT_PUBLIC_*` for client)            |
| `eslint.config.*` / `.eslintrc.*` | ESLint config                                                       |
| `.prettierrc.*`       | Formatter config                                                                |
| `playwright.config.*` / `cypress.config.*` | E2E test framework                                          |
| `vitest.config.*`     | Vitest unit/component tests                                                     |

### Bootstrap Path

1. Node toolchain: confirm `engines.node` in `package.json`.
2. Install: `<manager> install`.
3. Env: `cp .env.example .env.local` (Next.js) or `.env` (Vite); fill required vars.
4. Run:
   - **Next.js:** `npm run dev` (defaults to port 3000); App Router shows `loading.tsx` on initial load.
   - **Vite:** `npm run dev` (port 5173); fast HMR.
5. Verify: open browser; for Next.js, check `/api/*` route handlers; for SPA, hit the entry route.

### Key File Inventory

**Next.js App Router:**

| Location                  | Purpose                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `app/layout.tsx`          | Root layout (Server Component); HTML shell                                |
| `app/page.tsx`            | Root page                                                                  |
| `app/<segment>/page.tsx`  | Page for the route segment                                                 |
| `app/<segment>/layout.tsx` | Nested layout                                                              |
| `app/<segment>/loading.tsx` | Suspense fallback                                                        |
| `app/<segment>/error.tsx` | Error boundary (Client Component)                                          |
| `app/<segment>/route.ts`  | API route handler (replaces `pages/api`)                                   |
| `app/<segment>/[id]/page.tsx` | Dynamic segment                                                       |
| `middleware.ts`           | Edge middleware (auth, redirects, headers)                                 |
| `next.config.*`           | Build config; `images`, `redirects`, `experimental` flags                   |

**Next.js Pages Router (legacy):**

| Location                  | Purpose                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `pages/_app.tsx`          | Root component                                                            |
| `pages/_document.tsx`     | HTML shell                                                                 |
| `pages/index.tsx`         | Home page                                                                  |
| `pages/<route>.tsx`       | Route                                                                      |
| `pages/api/<route>.ts`    | API route                                                                  |

**Vite SPA:**

| Location                  | Purpose                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `index.html`              | Entry HTML                                                                 |
| `src/main.tsx` or `src/index.tsx` | Render entry; mounts to `#root`                                  |
| `src/App.tsx`             | Root component                                                             |
| `src/routes/` or `src/pages/` | If using React Router or TanStack Router                              |
| `src/components/`         | Reusable components                                                        |
| `src/hooks/`              | Custom hooks                                                               |
| `src/lib/` or `src/utils/` | Utilities                                                                  |
| `src/api/` or `src/services/` | HTTP clients                                                          |

### Conventions

- **TypeScript** with strict mode; check `tsconfig.json` `strict: true`.
- **Component library:** check `package.json` for `@radix-ui/*`, `@mui/*`, `@chakra-ui/*`, `shadcn/ui` (look in `components/ui/`), `tailwindcss`, `headlessui`.
- **Styling:** Tailwind (`tailwind.config.*`), CSS Modules (`*.module.css`), styled-components, emotion, CSS-in-JS, vanilla CSS.
- **Forms:** React Hook Form + zod schema, Formik, plain controlled inputs.
- **Data fetching:** TanStack Query (`@tanstack/react-query`), SWR, native fetch in Server Components.
- **Auth:** NextAuth.js / Auth.js (Next), Clerk, Auth0, Supabase Auth, custom JWT.
- **Tests:** Vitest + React Testing Library + jsdom for unit/component; Playwright/Cypress for E2E.

### Risk Hotspots Specific to React

- **Stale closures in `useEffect`:** insufficient deps cause "the value never updates".
- **Inline objects/arrays/functions in JSX:** break memoization; `<Child config={{x: 1}} />` re-creates on every render.
- **Server Components importing Client Components correctly, but client importing server components directly** (forbidden in Next App Router).
- **`'use client'` boundary creep:** marking too many files as client undermines SSR/streaming benefits.
- **`useEffect` for derived state:** state that should be `useMemo` (or no state at all) wrapped in effect causes update cycles.
- **Race conditions in async effects:** missing AbortController; response from old request applied after newer request resolved.
- **Default Next.js fetch caching:** Next aggressively caches `fetch` calls; `cache: 'no-store'` or `next: { revalidate: ... }` may be needed.
- **`process.env` in client code:** in Next.js, only `NEXT_PUBLIC_*` vars are exposed; others are `undefined` at runtime in the browser.
- **Hydration mismatch:** Server render diverges from client render (timestamps, random IDs, browser-only APIs in render).
- **Unbounded re-renders:** state setter called inside render without condition.

### First-PR Safe Zones

- New page in existing routing convention.
- New component in existing component library structure.
- New hook in `src/hooks/`.
- New env var in `.env.example` with safe default.

Riskier:

- Root layout / `_app.tsx` - affects every page.
- Middleware - runs on every request.
- Auth flow / providers.
- `next.config.*` changes - rebuild required.

### Ecosystem Currency

- React 19 GA; React 18 still common.
- Next.js 14/15 - App Router stable, Pages Router deprecated for new apps.
- Vite 5/6 with React SWC plugin standard.
- TanStack Query 5; SWR 2.
- Tailwind 3 standard; Tailwind 4 in beta.
- Server Components in Next.js App Router only (not standard React 19 SSR yet).

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** package manager, build framework (Next App/Pages, Vite, Remix), React version, TS strict, state management, data fetching, styling, component library.

**Local Bootstrap:** install command, env file, run command, default port, key routes to hit first.

**Architecture Map:** routing convention (file-based vs config), component library location, hooks/utilities directory, server/client boundary if Next App Router.

**Conventions:** TS strict, styling approach, data fetching, form handling, auth provider, test framework.

**Risk Hotspots:** stale closures, inline JSX objects, server/client import boundary, hydration mismatch, Next fetch caching, NEXT_PUBLIC env var rules.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Pages Router and App Router as interchangeable - they have different mental models
- Listing every component library dep - focus on the one(s) the project commits to
- Recommending CRA patterns - it is deprecated; new projects use Next or Vite
- Glossing over `'use client'` boundaries when describing Next App Router structure
- Skipping hydration mismatch as a risk class
- Recommending Apollo on a TanStack Query project (or vice versa) without justification
