---
name: react-onboard-map
description: "Map Next.js onboarding signals: App/Pages Router, Next 16 config mode, React 19, TS strict, state, data fetching, styling, ORM, deploy target."
metadata:
  category: frontend
  tags: [onboarding, codebase-map, react, nextjs]
user-invocable: false
---

# React Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is `React (Next.js)`.

## When to Use

Workflow needs Next.js-specific orientation: router, config mode, state, data fetching, styling, component library, server/client boundary. Project has `next` in `package.json`; a React app without it is out of scope - say so in one line and map nothing.

## Rules

- Detect the router first - App Router (`app/` or `src/app/`) vs Pages Router (`pages/` or `src/pages/`); the mental models diverge. `app/` beside `pages/` is mid-migration - report both as live and flag the dual mental model. Separate apps in one workspace are parallel conventions, not a migration: map each Next app, and name any non-Next app as out of scope.
- Read the declared `next` and `react` versions from the owning app's `package.json` and report them as declared.
- Detect the config mode from `next.config.*`: `cacheComponents: true` (decides the caching model every downstream rule follows) and `reactCompiler`, each set top-level or under `experimental` (the `experimental.*` form is a moved-key leftover Next still applies, with a warning); `reactCompiler: { compilationMode: 'annotation' }` is on for `"use memo"` components only; `output: "standalone"`. Report as Stack and Tooling findings the Next 16 leftovers, including: a `webpack` key with no `turbopack` key in the resolved config (your own or injected by a `with...()` wrapper) when `next build` passes neither `--webpack` nor `--turbopack` (the build exits with an error; `turbopack: {}` or a flag silences it); removed or moved config keys (`eslint`, `experimental.ppr` / `dynamicIO` / `useCache`, `experimental.reactCompiler` / `cacheComponents` / `typedRoutes`, `serverRuntimeConfig` / `publicRuntimeConfig`, `experimental.turbopack`, `skipMiddlewareUrlNormalize`); a `next lint` script (command removed), `.eslintrc.*` (`eslint-config-next` is flat-config only), `middleware.ts` (deprecated name for `proxy.ts`), an `engines.node` range admitting Node below 20.9.
- Detect package manager from lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock` or the older binary `bun.lockb`), else the `packageManager` field; with neither, report `none observed` and write the install command as `npm install (unconfirmed - no lockfile)`.
- Detect state layer - `useState`+`useContext` (Context-only providers count here), Zustand, Redux Toolkit, Jotai, MobX, or none. Server-cache libraries answer data fetching, not state. Report a second store library as a finding, not a footnote: two are a migration in progress or an accident - a library installed beside code still on its predecessor's API (Redux Toolkit in dependencies, `createStore` in the code) counts.
- Detect data fetching - Server Components (`fetch` or the ORM) with Server Actions for mutations, TanStack Query, SWR, Apollo, urql, RTK Query, or a raw HTTP client (axios/fetch with no cache library).
- Detect the persistence layer - Prisma (`prisma/schema.prisma`, a `prisma/schema/` directory, or a `prisma.config.*` pointing elsewhere), Drizzle (`drizzle.config.*`), Kysely or a raw driver (a `pg`/`mysql2`/`postgres` dependency with no ORM config), or none. A Next.js repo with an ORM is a fullstack app: report the server surface, not just the UI.
- Detect the deployment target - managed platform (`vercel.json`, platform config) vs self-hosted (`Dockerfile`, `docker-compose.*`, `output: "standalone"` in `next.config.*`); with neither signal, report `static/unknown - no deploy signal observed`. Self-hosted changes the caching, image, and ISR story materially.

## Patterns

### Build Inventory

| File                              | What it tells you                                          |
| --------------------------------- | ---------------------------------------------------------- |
| `next.config.*`                   | Config mode (`cacheComponents`, `reactCompiler`, top-level or `experimental.*`), `output`, a `webpack` key with no `turbopack` key (own or from a `with...()` wrapper) |
| `tsconfig.json`                   | TS config; `strict: true` matters                          |
| `tailwind.config.*` / `postcss.config.*` | Tailwind; the version is in the plugin, not the file - `tailwindcss` as a PostCSS plugin or a config without `@config` is v3; `@tailwindcss/postcss` or `@import "tailwindcss"` in the entry CSS is v4 |
| `.env.example` (`.env*` is git-ignored by create-next-app, `.env.example` included unless negated) | Env vars; `NEXT_PUBLIC_*` values are inlined into the client bundle at build |
| `eslint.config.*` / `biome.json` / `.prettierrc.*` | Lint/format config; a `.eslintrc.*` is a leftover |
| `vitest.config.*` / `jest.config.*` | Vitest or Jest unit/component runner             |
| `playwright.config.*` / `cypress.config.*` | E2E framework (Cypress may also run component tests) |
| `prisma/schema.prisma` / `drizzle.config.*` | ORM and migration tool; fullstack app          |
| `Dockerfile` / `docker-compose.*` / `compose.*` | Self-hosted; check for `output: "standalone"` |
| `src/server/` or `lib/server/`    | Service layer; the reuse seam for a future API    |

### Bootstrap

1. Install: `<manager> install` (manager from lockfile; Node from `engines.node` or `.nvmrc`, else Node 22.12+ or 24).
2. Env: copy `.env.example` when it exists to `.env.local` - Next loads it and create-next-app git-ignores `.env*`; check `.gitignore` before trusting that for `.env`; fill required keys. The Prisma CLI does not read `.env.local`: it takes `DATABASE_URL` from what `prisma.config.ts` loads (typically `dotenv/config`, i.e. `.env`) or the shell.
3. Fullstack (ORM detected): start the database (compose service when present) and run migrations through the package runner (`npx prisma migrate dev`, then `npx prisma generate` on Prisma 7+, where migrate no longer generates; `pnpm exec drizzle-kit migrate`) before first run.
4. Run: `<manager> run dev` - `:3000` unless the script passes `-p`/`--port` or `PORT` is set.
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
| `app/<seg>/@slot/`              | Parallel route slot; each needs a `default.tsx` or the build fails |
| `app/providers.tsx`             | Conventional `"use client"` provider wrapper (QueryClient, Theme, Auth) imported by `layout.tsx` |
| `proxy.ts` (repo root or `src/`, both routers) | Request interception - auth redirects, headers, CSP nonce; Node runtime only. A `middleware.ts` here is the deprecated name, reported for rename |
| `instrumentation.ts` (root or `src/`) | OTel / Sentry server registration (`register()`, `onRequestError`); `instrumentation-client.ts` for the browser |
| a `registry.tsx` (docs example: `lib/registry.tsx`) | CSS-in-JS SSR registry using `useServerInsertedHTML`, imported by the root layout |

**Next.js Pages Router (legacy):** `pages/_app.tsx` root, `pages/_document.tsx` shell, `pages/<route>.tsx`, `pages/api/<route>.ts`.

### Conventions

- **TS strict** from `tsconfig.json`; non-strict is a finding.
- **Component library:** check `package.json` for `radix-ui` or `@radix-ui/*`, `@mui/*`, `@chakra-ui/*`, `@headlessui/react`; shadcn/ui is never a dependency - look for `components.json` and `components/ui/`. `components/ui/` built on cva and Radix with no `components.json` is shadcn-shaped code: report it so, provenance unconfirmed.
- **Styling:** Tailwind, CSS Modules, styled-components, emotion, vanilla CSS.
- **Forms:** React Hook Form + zod, `useActionState` with Server Actions, Formik, controlled inputs.
- **Auth:** NextAuth (v4; Auth.js v5 is still beta), Clerk, Auth0, Supabase Auth, custom JWT.
- **Analytics/obs:** posthog-js, `@sentry/*`, `instrumentation.ts` registration - reported under Stack and Tooling.
- **Tests:** Vitest or Jest + React Testing Library + jsdom; Playwright/Cypress for E2E. A single-layer setup - E2E-only with no unit runner, or unit-only with no E2E - is a coverage gap worth noting.

### Risk Hotspots

- **`useEffect` misuse** - stale closures, derived state, missing AbortController, missing cleanup: see `react-hooks-patterns`.
- **Identity instability** - inline `{}`/`[]`/`() => ...` in JSX breaking memoization: see `react-hooks-patterns`.
- **Store over-subscription** - whole-store subscriptions or selectors returning fresh objects re-render every consumer: see `react-state-patterns`.
- **`"use client"` creep** (App Router) - boundary placed too high; importing server-only into Client Components: see `react-nextjs-patterns`.
- **Caching model** (App Router) - with `cacheComponents: true`, caching is `"use cache"` + `cacheLife` / `cacheTag` and request-time data must sit inside `<Suspense>`; without it, `fetch` caches only with `cache: "force-cache"` or `next: { revalidate }`, yet a route with no Request-time API is prerendered at build, freezing its `fetch` results; `unstable_cache` covers non-fetch reads. Name the mode the app runs: see `react-nextjs-patterns`.
- **Hydration mismatch** - timestamps, random IDs, browser-only APIs in render body; `next-themes` needs `suppressHydrationWarning` on `<html>`.
- **Server -> Client leaks** - full ORM rows as props, `dangerouslySetInnerHTML` XSS, `NEXT_PUBLIC_*` secret leak, Server Action without auth/Zod: see `task-react-review-security`.
- **Store-on-server (Zustand/Redux)** - module-level stores share state across requests on the server. Instantiate per-request in a provider or keep stores in `"use client"` modules only.
- **ORM client without a hot-reload guard** (any ORM) - a module-scope client not cached on `globalThis` leaks a pool per edit in development until the database refuses connections: see `react-server-data-layer`.
- **Self-hosted ISR and CDN rules** (self-hosted only) - local-disk ISR cache with more than one instance, or a CDN cache rule that does not bypass on the session cookie: see `react-selfhost-operations`.

### First-PR Safe Zones

Safe: new page in existing routing convention, new component in existing library structure, new hook in `src/hooks/`, new env var in `.env.example` (on create-next-app's `.env*` ignore, only once `!.env.example` is added).

Riskier: root layout / `_app.tsx`, `proxy.ts` (or a leftover `middleware.ts`), auth provider, `next.config.*` (rebuild required).

## Output Format

Composed by `task-onboard`, inject into its sections; invoked standalone, emit the same sections in this order as a self-contained `## React Onboard Map`, each section a `###` heading with bullet fields. Map the whole repo unless the request names an app or area; then scope to it and add one line naming what was left out. The mid-migration flag and the Next 16 leftover findings live in Stack and Tooling. Doc-vs-repo contradictions (a README command no script defines) are reported where they bite (Local Bootstrap); detection findings (non-strict TS, coverage gap) stay inside Conventions.

- **Stack and Tooling**: package manager, router (App Router, Pages Router, or both mid-migration), `next` and `react` versions as declared, config mode (`cacheComponents` on or off; `reactCompiler` on, on for `"use memo"` components only, or off), TS strict, state management, data fetching, styling, component library, ORM and migration tool (`none observed`, or `none - client only` for an app with no server surface), deployment target (managed platform, self-hosted, or `static/unknown - no deploy signal observed`), analytics/observability deps (`@sentry/*`, `posthog-js`, an OTel package, `instrumentation*.ts`) when present, then one line per Next 16 leftover found. Where a signal is absent, write `none observed`; where two coexist, name the one the newest code uses (with no history in the input, the wider-adopted one, said so) and flag the other as a live second convention.
- **Local Bootstrap**: install command, env file, database and migration step when an ORM is detected, run command, port (from the dev script's `-p`/`--port` or `PORT`, else `:3000`), entry route. Any documented command the repo contradicts is reported here, naming both what the docs say and what the repo supports.
- **Architecture Map**: router convention, components/hooks/utilities layout, server/client boundary (`"use client"` placement) on the App Router, API location (`app/**/route.ts`, `pages/api`, or external), service layer (`src/server/`, `lib/server/`) when present.
- **Conventions**: TS strict, styling, data fetching, form handling, auth provider, test framework.
- **Risk Hotspots**: the Risk Hotspots list above is the source; emit every entry that applies to the detected router plus the conditional sets (ORM detected adds the hot-reload guard; self-hosted adds ISR/CDN). It is a floor, not a closed set - a hazard this project has that no entry names still gets reported here, one line, named plainly.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Treating Pages Router and App Router as interchangeable - different mental models
- Listing every UI dep - call out the one the project commits to
- Glossing over `"use client"` boundaries when describing App Router
- Skipping hydration mismatch as a risk class
- Recommending Apollo on a TanStack Query project (or vice versa) without justification
