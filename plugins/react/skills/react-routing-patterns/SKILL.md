---
name: react-routing-patterns
description: "React routing: Next.js App Router layouts, loading/error, parallel/intercepting routes, middleware; React Router loaders, guards, nested routes."
metadata:
  category: frontend
  tags: [react, routing, nextjs, react-router, layouts, middleware, parallel-routes]
user-invocable: false
---

# React Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For data-fetching boundaries defer to `react-data-fetching`. Guard mechanics (placement, redirect flow) are owned here; session/token validity and auth-logic review belong to `task-react-review-security`.

## When to Use

- Designing or reviewing route structure (Next.js App Router or React Router)
- Adding layouts, loading/error UI, parallel/intercepting routes, middleware
- Implementing route guards, dynamic segments, nested data loaders

## Rules

- Every route segment that can fail has an error boundary; every segment that fetches has a loading UI.
- Validate dynamic params before use; treat them as untrusted input.
- Layouts must not re-fetch data the parent already provides; pass via props/context or co-locate the fetch in the deepest segment that needs it.
- Next.js: middleware is an optimistic gate, not the authorization boundary - it redirects the obviously-signed-out cheaply, and the page or data layer re-checks the session before returning anything. Keep it allocation-light (no DB calls, no heavy parsing) and scope `matcher` to the protected prefixes; a catch-all matcher runs that work on every asset/request. Never rely on middleware alone: a layout does not re-render on client-side navigation within its own subtree, so a layout-only check runs once per mount, not per route change.
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

**Client-layout smell.** Marking `layout.tsx` `"use client"` purely to hold local state (filter, toggle) collapses the whole subtree client-side.

```tsx
// Bad - whole subtree forced client to hold one filter string
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

Each parallel slot needs a `default.tsx` (often returning `null`) so the slot resolves on routes that don't fill it. Without one a soft navigation keeps the slot's previous content, while a hard load or refresh of an unfilled route 404s. A slot that must also render on hard loads and deep links (a persistent side panel) needs a `default.tsx` that renders the slot content, not `null`.

### Intercepting Routes (modal-over-page)

`@modal/(.)photo/[id]/page.tsx` intercepts client-side navigations to `photo/[id]` and renders a modal instead; a direct URL load, refresh, or share resolves the real `photo/[id]/page.tsx` full page. The marker describes where the intercepted path sits relative to the interceptor - `(.)` same level, `(..)` one up, `(...)` from root - not where the navigation started. Both are mandatory: the interceptor handles soft navigation, the full page handles hard loads. Add `@modal/default.tsx` returning `null` so the slot is empty elsewhere. `(.)` = same level, `(..)` = one up, `(...)` = from root.

### Middleware (Next.js)

```ts
// middleware.ts (root)
export function middleware(req: NextRequest) {
  const token = req.cookies.get("session")?.value;
  if (!token && req.nextUrl.pathname.startsWith("/dashboard")) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}
export const config = { matcher: ["/dashboard/:path*"] };   // matches exactly what the body guards
```

Bad: calling the DB or decoding a full JWT in middleware - it runs on every matched request and delays every one of them. Match only the prefixes the handler actually gates; a matcher wider than the guard buys cost with no protection.

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
      // The loader runs during navigation, before the element renders, so an element
      // wrapper cannot gate it. Do the auth check at the top of the loader itself.
      loader: dashboardLoader,
      children: [
        { index: true, element: <DashboardHome /> },
        { path: ":teamId", element: <TeamPage />, loader: teamLoader },
      ],
    },
  ],
}]);

async function teamLoader({ params }: LoaderFunctionArgs) {
  const team = await getTeam(params.teamId!);
  if (!team) throw new Response("Not Found", { status: 404 });
  return team;
}

function DashboardLayout() {
  return <div className="flex"><Sidebar /><Outlet /></div>;
}
```

Loading UI in React Router: read `useNavigation().state === "loading"` for a global pending indicator, or return a promise from the loader and render it inside `<Suspense>` via `<Await>` (v7 removed the `defer()` wrapper; return the promise directly). (Layouts persisting state via `<Outlet />` applies here the same as Next.js layouts.)

### Route Guards

- **Next.js:** `middleware.ts` for redirect-style guards; Server Component layout for richer checks (`if (!user) redirect("/login")`). Redirect-if-authed (`/login` for a signed-in user) is the inverse branch of the same middleware.
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

Both modes emit the Route Map (the Layout column names the nearest layout). When designing, add a `### File Tree` section after the Route Map (the `app/` or router-config skeleton, middleware `matcher` included); Issues Found flags risks in the requirements and `File:` names the proposed path. When reviewing, the consuming workflow owns the finding envelope; invoked standalone, order Issues by severity and `File:` anchors the reviewed file (`(not shown)` for files referenced but not provided). An intercepted URL takes two Route Map rows (soft-nav modal, hard-load page); parallel slots use `@slot` as Path; absent Loading/Error artifacts are `None`. Auth records enforced behavior - a broken guard is `Public` plus an Issue.

```
## Routing Design

Stack: {Next.js App Router | React Router (Vite) | Other}

### Route Map

| Path | Component | Layout | Loading | Error | Auth |
| ---- | --------- | ------ | ------- | ----- | ---- |
| ...  | ...       | ...    | ...     | ...   | {Public \| Protected \| Protected (role: <role>) \| Public (redirect-if-authed)} |

`File:` is the reviewed path; append ` (not shown)` to the path when the file was referenced but not provided, so the value always carries a path. Auth records what the route actually enforces: a guard that lets any unauthenticated request through is `Public` plus an Issue; a guard that blocks the common case but fails open on an edge case keeps its enforced value and takes an Issue at the severity of what gets through.

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
- **High**: client layout used for trivial state; missing error boundary on a fetching segment; effect-fetch in place of a loader leaving 404/error states unrendered (`Loader`); a guard that fails open; a parallel slot the layout never renders; unvalidated dynamic params reaching ORM; missing `default.tsx` for a parallel/intercepting slot (404s on unfilled routes).
- **Medium**: missing loading UI; auth duplicated client-side that middleware/layout should own; `window.location` navigation (`Navigation`); over-broad `matcher` even with cheap logic (excess per-request work).
- **Low**: minor convention drift.

No Category value is left unscored, and where a value appears in more than one band the band naming your defect's condition wins; `Nesting` (a layout refetching data the parent already provides, a missing index route leaving a blank `<Outlet />`) is Medium. A route that fails to compile is Blocker whether or not the band names its exact shape - an async Client Component and a layout missing `<Outlet />` are both `Nesting` at Blocker.

If the stack is neither Next.js App Router nor React Router, apply only the stack-neutral Rules - validate dynamic params before use, give every failing segment an error boundary and every fetching segment a loading state, navigate through the router - opening the Route Map with `Stack: Other`. The table, block shape, categories and severity bands apply unchanged. `Navigation` covers any full-page reload used for in-app movement, `window.location` or a bare `<a href>` to an internal route alike.

## Avoid

- `window.location.href` / full reloads for navigation - breaks SPA state and prefetch.
- DB calls, JWT crypto, or large parses in Next.js `middleware.ts` - runs on the edge per request.
- Client-only auth guards in Next.js when middleware or a Server Component can redirect server-side.
- Layouts that refetch parent data, or pages that duplicate a layout's fetch.
- Dynamic segments consumed without validation.
- `error.tsx` as a Server Component (won't compile) or used to catch an error thrown by its own layout - the parent segment's `error.tsx` catches that; `global-error.tsx` covers only the root layout and must render its own `<html>`/`<body>`.
- Hand-rolled routers layered on top of Next.js file conventions.
