---
name: react-routing-patterns
description: "React routing: Next.js App Router layouts, loading/error, parallel/intercepting routes, middleware; React Router loaders, guards, nested routes."
metadata:
  category: frontend
  tags: [react, routing, nextjs, react-router, layouts, middleware, parallel-routes]
user-invocable: false
---

# React Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For data-fetching boundaries defer to `react-data-fetching`; auth/session review belongs to `task-react-review-security`.

## When to Use

- Designing or reviewing route structure (Next.js App Router or React Router)
- Adding layouts, loading/error UI, parallel/intercepting routes, middleware
- Implementing route guards, dynamic segments, nested data loaders

## Rules

- Every route segment that can fail has an error boundary; every segment that fetches has a loading UI.
- Validate dynamic params before use; treat them as untrusted input.
- Layouts must not re-fetch data the parent already provides; pass via props/context or co-locate the fetch in the deepest segment that needs it.
- Next.js: enforce auth in `middleware.ts` or a Server Component layout, not on the client. Keep middleware allocation-light (no DB calls, no heavy parsing).
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
    @modal/(.)photo/[id]/page.tsx  # Parallel slot + intercepting route
  api/users/route.ts      # Route handler
```

Special files compose top-down: `error.tsx` catches throws in its segment and below; a deeper `error.tsx` overrides the ancestor.

### Layouts Persist State

Layouts render once for their subtree; only `{children}` changes on navigation - so sidebar scroll, form state, and subscriptions survive.

```tsx
// app/dashboard/layout.tsx (Server Component by default)
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <div className="flex"><Sidebar /><main>{children}</main></div>;
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
export const config = { matcher: ["/dashboard/:path*", "/api/:path*"] };
```

Bad: calling the DB or decoding a full JWT in middleware - it runs on every matched request and blocks the edge.

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

// React Router
function TeamPage() {
  const { teamId = "" } = useParams<{ teamId: string }>();
  if (!/^[a-z0-9-]+$/i.test(teamId)) throw new Response("Bad param", { status: 400 });
  // ...
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
      element: <RequireAuth><DashboardLayout /></RequireAuth>,
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

### Route Guards

- **Next.js:** `middleware.ts` for redirect-style guards; Server Component layout for richer checks (`if (!user) redirect("/login")`).
- **React Router:** loader throws a `redirect()` Response, or wrap the element in a guard component:

```tsx
function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return <PageSkeleton />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
```

Prefer loader-throw over client wrappers - it runs before render and avoids the auth-flash.

## Output Format

```
## Routing Design

Stack: {Next.js App Router | React Router (Vite) | Other}

### Route Map

| Path | Component | Layout | Loading | Error | Auth |
| ---- | --------- | ------ | ------- | ----- | ---- |
| ...  | ...       | ...    | ...     | ...   | {Public|Protected} |

### Issues Found

- [Severity: {Blocker|High|Medium|Low}] [Category: {Layout|Loading|Error|Guard|Middleware|DynamicParam|Parallel|Nesting}]
  File: <path>
  Issue: <one-line>
  Fix: <referencing a Pattern by name>

### Recommendations

- <change with rationale>
```

If stack is neither Next.js App Router nor React Router, apply only the stack-neutral Rules (validate params, error/loading boundaries, no `window.location` navigation).

## Avoid

- `window.location.href` / full reloads for navigation - breaks SPA state and prefetch.
- DB calls, JWT crypto, or large parses in Next.js `middleware.ts` - runs on the edge per request.
- Client-only auth guards in Next.js when middleware or a Server Component can redirect server-side.
- Layouts that refetch parent data, or pages that duplicate a layout's fetch.
- Dynamic segments consumed without validation.
- `error.tsx` as a Server Component (won't compile) or used to catch errors in its own layout (use `global-error.tsx` for that).
- Hand-rolled routers layered on top of Next.js file conventions.
