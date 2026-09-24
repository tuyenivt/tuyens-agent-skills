---
name: react-routing-patterns
description: "React routing: Next.js App Router layouts, loading/error, parallel/intercepting routes, middleware; React Router loaders, guards, nested routes."
metadata:
  category: frontend
  tags: [react, routing, nextjs, react-router, layouts, middleware, parallel-routes]
user-invocable: false
---

# React Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For data-fetching boundaries defer to `react-data-fetching`. Guard mechanics (placement, redirect flow, a missing re-check at the page or data layer) are owned here; session/token validity and auth-logic review belong to `task-react-review-security`. Next.js 16 renames `middleware.ts` to `proxy.ts` (`export function proxy`, Node runtime only); everything below about middleware applies to either name.

## When to Use

- Designing or reviewing route structure (Next.js App Router or React Router)
- Adding layouts, loading/error UI, parallel/intercepting routes, middleware
- Implementing route guards, dynamic segments, nested data loaders

## Rules

- Every route segment that can fail has an error boundary; every segment that fetches has a loading UI.
- Validate dynamic params before use; treat them as untrusted input.
- Layouts must not re-fetch data the parent already provides; pass via props/context or co-locate the fetch in the deepest segment that needs it.
- Next.js: middleware is an optimistic gate, not the authorization boundary - it redirects the obviously-signed-out cheaply, and the page or data layer re-checks the session before returning anything. Keep it allocation-light (no DB or network calls, no heavy parsing - verifying a signed session cookie is fine) and scope `matcher` to the protected prefixes; a catch-all matcher runs that work on every asset/request. Never rely on middleware alone - re-check in the page or data layer. A layout check is not per-route either: a layout does not re-render on client-side navigation within its own subtree, so it runs once per mount.
- Next.js: error boundaries (`error.tsx`) must be Client Components; layouts default to Server Components unless interactivity is required.
- React Router: prefer `loader` for data and `<Outlet />` for nested rendering. Navigate via the router (`<Link>`, `useNavigate`), never `window.location`.
- File-based routing: follow framework conventions. Do not hand-roll a router on top of Next.js.

## Patterns

### Next.js App Router Conventions

```
app/
  layout.tsx              # Root layout (persists across all routes)
  page.tsx loading.tsx error.tsx not-found.tsx
  (auth)/login/page.tsx   # Route group - no URL segment
  dashboard/
    layout.tsx            # Persists across /dashboard/*
    page.tsx loading.tsx error.tsx
    [teamId]/page.tsx     # Dynamic segment -> params.teamId
    photo/[id]/page.tsx   # Real page - hard loads, refresh, shared links
    @modal/default.tsx    # Slot fallback (returns null) - required
    @modal/(.)photo/[id]/page.tsx  # Interceptor - soft navigation only
  api/users/route.ts      # Route handler
```

Special files compose top-down: `error.tsx` catches throws in its segment and below; a deeper `error.tsx` overrides the ancestor. A segment whose children are tabs gives its index `page.tsx` a redirect to the default tab.

### Layouts Persist State

Layouts render once for their subtree; only `{children}` changes on navigation - so sidebar scroll, form state, and subscriptions survive.

```tsx
// app/dashboard/layout.tsx (Server Component by default)
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <div className="flex"><Sidebar /><main>{children}</main></div>;
}
```

**Client-layout smell.** Marking `layout.tsx` `"use client"` purely to hold local state (filter, toggle) ships the layout and everything it imports to the client and stops it being async, fetching on the server or exporting `metadata`; its `{children}` stay Server Components.

```tsx
// Bad - layout and its imports shipped client, no server fetch or metadata, to hold one filter string
"use client";
export default function Layout({ children }) {
  const [filter, setFilter] = useState("");
  return <div><Sidebar filter={filter} onChange={setFilter} />{children}</div>;
}

// Good - server layout; state lives in the small interactive island
export default function Layout({ children }: { children: ReactNode }) {
  return <div><SidebarClient />{children}</div>; // SidebarClient is "use client"
}
```

### Loading and Error UI

```tsx
// app/dashboard/loading.tsx  - shown via Suspense while page.tsx awaits
export default function Loading() { return <DashboardSkeleton />; }

// app/dashboard/error.tsx - must be Client Component
"use client";
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div role="alert"><p>{error.message}</p><button onClick={reset}>Retry</button></div>;
}
```

### Parallel Routes

Render independent segments side-by-side; each has its own loading/error.

```tsx
// app/dashboard/layout.tsx
export default function Layout({ children, analytics, notifications }: {
  children: ReactNode; analytics: ReactNode; notifications: ReactNode;
}) {
  return <>{children}<aside>{analytics}{notifications}</aside></>;
}
// Slots resolve to app/dashboard/@analytics/page.tsx, @notifications/page.tsx
```

Each parallel slot needs a `default.tsx` (often returning `null`) so the slot resolves on routes that don't fill it. Without one, on 15 a soft navigation keeps the slot's previous content while a hard load or refresh of an unfilled route 404s; on 16 the build fails. A slot that must also render on hard loads and deep links (a persistent side panel) needs a `default.tsx` that renders the slot content, not `null`.

### Intercepting Routes (modal-over-page)

`@modal/(.)photo/[id]/page.tsx` intercepts client-side navigations to `photo/[id]` and renders a modal instead; a direct URL load, refresh, or share resolves the real `photo/[id]/page.tsx` full page. The marker describes where the intercepted path sits relative to the interceptor - `(.)` same level, `(..)` one up, `(...)` from root - not where the navigation started. Both are mandatory: the interceptor handles soft navigation, the full page handles hard loads. Add `@modal/default.tsx` returning `null` so the slot is empty elsewhere.

### Middleware (Next.js)

```ts
// middleware.ts at the root or in src/ (16: proxy.ts, export function proxy)
export function middleware(req: NextRequest) {
  const token = req.cookies.get("session")?.value;
  if (!token && req.nextUrl.pathname.startsWith("/dashboard")) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}
export const config = { matcher: ["/dashboard/:path*"] };   // matches exactly what the body guards
```

Bad: calling the DB or a network service, or parsing a large payload, in middleware - it runs on every matched request and delays every one of them. Verifying a signed session cookie (`jose`) is the docs' own optimistic check and is fine. Match only the prefixes the handler actually gates; a matcher wider than the guard buys cost with no protection.

### Dynamic Segments

```tsx
// Next.js (App Router, async params in 15+)
export default async function TeamPage({ params }: { params: Promise<{ teamId: string }> }) {
  const { teamId } = await params;
  if (!/^[a-z0-9-]+$/i.test(teamId)) notFound();   // validate
  const team = await getTeam(teamId);
  if (!team) notFound();
  return <TeamView team={team} />;
}

// React Router - validate in the loader; a Response thrown from render is not
// unwrapped into an ErrorResponse, so isRouteErrorResponse would be false.
async function teamLoader({ params }: LoaderFunctionArgs) {
  if (!/^[a-z0-9-]+$/i.test(params.teamId ?? "")) throw new Response("Bad param", { status: 400 });
  return getTeam(params.teamId!);
}
```

Locale prefixes: an `app/[lang]/` segment wraps the localized routes, `generateStaticParams` returns the supported locales, `lang` is validated against that list like any param, and middleware redirects unprefixed paths to the negotiated locale.

### React Router (Vite) Nested Routes + Loaders

```tsx
const router = createBrowserRouter([{
  path: "/",
  element: <RootLayout />,
  errorElement: <RootError />,
  children: [
    { index: true, element: <Home /> },
    {
      path: "dashboard",
      element: <DashboardLayout />,
      // Loaders run during navigation, before any element renders - and matched parent and child
      // loaders run in parallel, so this check does not gate teamLoader. Every loader under a protected
      // route calls a shared requireUser() (or use React Router middleware, 7.9+).
      loader: dashboardLoader,
      children: [
        { index: true, element: <DashboardHome /> },
        { path: ":teamId", element: <TeamPage />, loader: teamLoader },
      ],
    },
  ],
}]);

async function teamLoader({ params }: LoaderFunctionArgs) {
  await requireUser();                                           // its own check - see above
  if (!/^[a-z0-9-]+$/i.test(params.teamId ?? "")) throw new Response("Bad param", { status: 400 });
  const team = await getTeam(params.teamId!);
  if (!team) throw new Response("Not Found", { status: 404 });
  return team;
}

function DashboardLayout() {
  return <div className="flex"><Sidebar /><Outlet /></div>;
}
```

Loading UI in React Router: read `useNavigation().state === "loading"` for a global pending indicator, or return an object holding an un-awaited promise (`return { team: getTeam(id) }`) and render it with `<Suspense>` + `<Await resolve={data.team}>` (v7 removed the `defer()` wrapper; a loader that returns a bare promise is awaited before render, so nothing streams). `createBrowserRouter(routes, { basename })` serves the app under a prefix; Route Map paths are written as the browser sees them, basename included. (Layouts persisting state via `<Outlet />` applies here the same as Next.js layouts.)

### Route Guards

- **Next.js:** `middleware.ts` for redirect-style guards; the page or data layer for the authoritative check (`if (!user) redirect("/login")`) - a layout check is a UX redirect only, since it does not re-run on navigation within its subtree. Redirect-if-authed (`/login` for a signed-in user) is the inverse branch of the same middleware.
- **React Router:** loader throws a `redirect()` Response, or wrap the element in a guard component:

```tsx
function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return <PageSkeleton />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
```

Prefer loader-throw over client wrappers - it runs before render, gates the loader's own fetch, and avoids the auth-flash. The `RequireAuth` wrapper above is the fallback for routes with no loader.

## Output Format

Both modes emit the Route Map (the Layout column names the nearest layout). When designing, add a `### File Tree` section after the Route Map (the `app/` or router-config skeleton, middleware `matcher` included); Issues Found flags risks in the requirements and `File:` names the proposed path. When reviewing, the consuming workflow owns the finding envelope; invoked standalone, order Issues by severity and `File:` anchors the reviewed file (`(not shown)` for files referenced but not provided). An intercepted URL takes two Route Map rows (soft-nav modal, hard-load page); parallel slots use `@slot` as Path; absent Loading/Error artifacts are `None`; a page not in the read set writes its Component as `(not shown)`; a slot's nested segment writes `@slot/segment`. Auth records enforced behavior - a broken guard is `Public` plus an Issue. A guard that blocks the common case but fails open on an edge case keeps its enforced value and takes an Issue at the severity of what gets through. `Stack` maps from the detected framework: App Router = an `app/` or `src/app/` directory with a root layout (`layout.{tsx,jsx,js}` at its top, or atop each route group) - beside `pages/` the tree is hybrid and the App Router rules apply to `app/`; Pages Router = `pages/` or `src/pages/` alone. `stack-detect` reports `React (Next.js)` for both. React Router in data mode (`createBrowserRouter`/`createHashRouter` + `RouterProvider` in the entry; `stack-detect` reports it as `React (Vite/CRA/custom)`) or framework mode is `React Router (Vite)`; declarative `<BrowserRouter>`, Pages Router and anything else is `Other`.

```
## Routing Design

**Stack:** {Next.js App Router | React Router (Vite) | Other}

### Route Map

| Path | Component | Layout | Loading | Error | Auth |
| ---- | --------- | ------ | ------- | ----- | ---- |
| ...  | ...       | ...    | ...     | ...   | {Public \| Protected \| Protected (role: <role>[ or <role>]) \| Public (redirect-if-authed)} |

### File Tree

{design mode only - the `app/` skeleton or router config the Route Map implies, middleware `matcher` included; omit when reviewing}

### Issues Found

- [Severity: {Blocker|High|Medium|Low}] [Category: {Layout|Loading|Error|Guard|Middleware|DynamicParam|Parallel|Nesting|Navigation|Loader}]
  File: <path>
  Issue: <one-line>
  Fix: <referencing a Pattern by name, or the governing Rule when no Pattern covers it>

### Recommendations

- <change with rationale>
```

Severity rubric:
- **Blocker**: route fails to compile/run (e.g., async Client Component, wrong `params` shape, `error.tsx` without `"use client"`, a layout missing `<Outlet />` so children never mount), or middleware does DB/heavy work on every matched request.
- **High**: client layout used for trivial state; missing error boundary (`error.tsx` or `errorElement`) on a fetching segment; effect-fetch in place of a loader leaving 404/error states unrendered (`Loader`); a guard that fails open (including one rendering children while its check is still pending); a parallel slot the layout never renders; unvalidated dynamic params reaching an ORM, an HTTP client URL, or a file path; missing `default.tsx` for a parallel/intercepting slot - one Issue per layout, listing every slot without one (404s on unfilled routes on 15; a build failure, and so Blocker, on 16).
- **Medium**: missing loading UI; auth duplicated client-side that middleware or the page/data layer should own; `window.location` navigation (`Navigation`); over-broad `matcher` even with cheap logic (excess per-request work).
- **Low**: minor convention drift.

No Category value is left unscored, and where a value appears in more than one band the band naming your defect's condition wins; `Nesting` (a layout refetching data the parent already provides, a missing index route leaving a blank `<Outlet />`) is Medium. A route that fails to compile, errors at runtime or never mounts its children is Blocker whether or not the band names its exact shape - a layout missing `<Outlet />` is `Nesting` at Blocker, an async Client Component `Layout` at Blocker.

If the stack is neither Next.js App Router nor React Router, apply only the stack-neutral Rules - validate dynamic params before use, give every failing segment an error boundary and every fetching segment a loading state, navigate through the router - opening the Route Map with `Stack: Other`. The table, block shape, categories and severity bands apply unchanged. `Navigation` covers any full-page reload used for in-app movement, `window.location` or a bare `<a href>` to an internal route alike.

## Avoid

- `window.location.href` / full reloads for navigation - breaks SPA state and prefetch.
- DB or network calls, or large parses, in Next.js `middleware.ts` / `proxy.ts` - it runs before every matched request.
- Client-only auth guards in Next.js when middleware or a Server Component can redirect server-side.
- Layouts that refetch parent data, or pages that duplicate a layout's fetch.
- Dynamic segments consumed without validation.
- `error.tsx` as a Server Component (won't compile) or used to catch an error thrown by its own layout - the parent segment's `error.tsx` catches that; `global-error.tsx` covers only the root layout and must render its own `<html>`/`<body>`.
- Hand-rolled routers layered on top of Next.js file conventions.
