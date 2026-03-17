---
name: react-routing-patterns
description: React routing patterns - React Router (Vite) and Next.js App Router layouts, loading states, error boundaries, parallel routes, intercepting routes, and middleware.
metadata:
  category: frontend
  tags: [react, routing, nextjs, react-router, layouts, middleware, parallel-routes]
user-invocable: false
---

# React Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing route structure for a new feature or application
- Choosing between Next.js App Router conventions and React Router patterns
- Adding layouts, loading states, or error boundaries to routes
- Implementing advanced routing (parallel routes, intercepting routes, middleware)
- Reviewing routing for correctness and performance

## Rules

- Every route must have an error boundary - unhandled errors should not crash the entire app
- Loading states must be defined for routes that fetch data - no blank screens during navigation
- Layouts must not re-render when navigating between child routes
- Route parameters must be validated before use - never trust URL params as safe input
- Middleware must be fast and avoid heavy computation - it runs on every matching request (Next.js)
- Prefer file-based routing conventions when using Next.js - do not fight the framework

## Patterns

### Next.js App Router File Conventions

```
app/
  layout.tsx          # Root layout (wraps all pages)
  page.tsx            # Home page (/)
  loading.tsx         # Loading UI for this segment
  error.tsx           # Error UI for this segment
  not-found.tsx       # 404 UI
  dashboard/
    layout.tsx        # Dashboard layout (persistent sidebar)
    page.tsx          # /dashboard
    loading.tsx       # Loading UI for dashboard
    settings/
      page.tsx        # /dashboard/settings
    [teamId]/
      page.tsx        # /dashboard/:teamId (dynamic segment)
  (auth)/
    login/
      page.tsx        # /login (route group - no /auth prefix)
    signup/
      page.tsx        # /signup
  @modal/             # Parallel route slot
    (.)photo/[id]/
      page.tsx        # Intercepting route for photo modal
  api/
    users/
      route.ts        # API route handler: GET, POST /api/users
```

### Next.js Layouts

Layouts persist across child route navigations and preserve state:

```tsx
// app/dashboard/layout.tsx
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex">
      <Sidebar /> {/* persists across dashboard pages */}
      <main className="flex-1">
        {children} {/* only this part changes on navigation */}
      </main>
    </div>
  );
}
```

### Next.js Loading and Error States

```tsx
// app/dashboard/loading.tsx - shown while page.tsx is loading
export default function DashboardLoading() {
  return <DashboardSkeleton />;
}

// app/dashboard/error.tsx - shown when page.tsx throws
("use client"); // error boundaries must be Client Components
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div role="alert">
      <h2>Something went wrong</h2>
      <p>{error.message}</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

### Next.js Parallel Routes

Render multiple pages simultaneously in the same layout:

```tsx
// app/dashboard/layout.tsx
export default function DashboardLayout({
  children,
  analytics,
  notifications,
}: {
  children: ReactNode;
  analytics: ReactNode;
  notifications: ReactNode;
}) {
  return (
    <div>
      {children}
      <div className="grid grid-cols-2">
        {analytics} {/* @analytics/page.tsx */}
        {notifications} {/* @notifications/page.tsx */}
      </div>
    </div>
  );
}
```

### Next.js Middleware

```tsx
// middleware.ts (root level)
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("session")?.value;

  // Redirect unauthenticated users
  if (!token && request.nextUrl.pathname.startsWith("/dashboard")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Add custom headers
  const response = NextResponse.next();
  response.headers.set("x-request-id", crypto.randomUUID());
  return response;
}

export const config = {
  matcher: ["/dashboard/:path*", "/api/:path*"],
};
```

### React Router (Vite) Patterns

```tsx
// Route configuration
const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    errorElement: <RootError />,
    children: [
      { index: true, element: <Home /> },
      {
        path: "dashboard",
        element: <DashboardLayout />,
        loader: dashboardLoader,
        children: [
          { index: true, element: <DashboardHome /> },
          { path: "settings", element: <Settings /> },
          { path: ":teamId", element: <TeamPage />, loader: teamLoader },
        ],
      },
    ],
  },
]);

// Layout with Outlet
function DashboardLayout() {
  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1">
        <Outlet /> {/* child routes render here */}
      </main>
    </div>
  );
}

// Loader for data fetching
async function teamLoader({ params }: LoaderFunctionArgs) {
  const team = await getTeam(params.teamId!);
  if (!team) throw new Response("Not Found", { status: 404 });
  return team;
}
```

### Dynamic Route Parameters

```tsx
// Next.js - params are passed as props
interface PageProps {
  params: Promise<{ teamId: string }>;
}

export default async function TeamPage({ params }: PageProps) {
  const { teamId } = await params;
  const team = await getTeam(teamId);
  if (!team) notFound();
  return <TeamView team={team} />;
}

// React Router - useParams hook
function TeamPage() {
  const { teamId } = useParams<{ teamId: string }>();
  // validate teamId before using
}
```

### Route Guards / Protected Routes

**Next.js** - Use middleware for auth checks (runs before render):

```tsx
// middleware.ts handles redirects (see Middleware section above)
```

**React Router** - Use loader or wrapper component:

```tsx
function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <PageSkeleton />
  if (!user) return <Navigate to="/login" replace />
  return children
}

// In route config:
{ path: "dashboard", element: <ProtectedRoute><Dashboard /></ProtectedRoute> }
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Routing Design

**Stack:** {Next.js App Router | React Router (Vite)}

### Route Map

| Path                 | Page Component    | Layout      | Loading    | Error      | Auth      |
| -------------------- | ----------------- | ----------- | ---------- | ---------- | --------- |
| /                    | HomePage          | RootLayout  | loading.tsx| error.tsx  | Public    |
| /dashboard           | DashboardPage     | DashLayout  | loading.tsx| error.tsx  | Protected |
| /dashboard/:teamId   | TeamPage          | DashLayout  | loading.tsx| error.tsx  | Protected |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Routes without error boundaries (unhandled errors crash the app)
- Routes without loading states (blank screens during data fetching)
- Heavy computation in Next.js middleware (runs on every matching request)
- Using `window.location` for navigation instead of the router (breaks SPA behavior)
- Dynamic segments without validation (trusting URL params as safe data)
- Nested layouts that re-fetch data the parent already has (pass via context or props)
- Client-side redirects for auth when middleware can handle it server-side (Next.js)
