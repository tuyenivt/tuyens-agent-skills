---
name: react-nextjs-patterns
description: "Next.js 15 App Router: RSC vs client islands, Server Actions vs Route Handlers, fetch/tag caching, ISR, streaming, metadata, next/image."
metadata:
  category: frontend
  tags: [nextjs, app-router, server-components, server-actions, caching, isr, metadata]
user-invocable: false
---

# Next.js App Router Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For state/store choices defer to `react-state-patterns`; for form/validation schemas defer to `frontend-form-handling`.

## When to Use

- Designing or reviewing a Next.js 15 App Router service
- Splitting work between Server Components, client islands, Server Actions, and Route Handlers
- Configuring caching (fetch options, `unstable_cache`, `revalidatePath`/`revalidateTag`), ISR, streaming, metadata, and `next/image`

Out of scope: Pages Router, generic React state, framework-neutral SEO.

## Rules

- Server Components are the default. Add `"use client"` only for hooks, event handlers, or browser APIs - and push the boundary as far down the tree as possible.
- Server-only modules (DB clients, secrets, server SDKs) import `import "server-only"`. Never import them transitively into a client component.
- **Next.js 15+: `params` and `searchParams` are `Promise`s.** Type as `params: Promise<{ slug: string }>` and `await` before use. Reading synchronously is a silent-breaking change from 14.
- Server Actions are public HTTP endpoints: validate every input with a schema, authorize the caller, then revalidate. Choose Server Action for first-party form/mutation flows; choose Route Handler only when you need a stable URL, non-form clients, webhooks, or non-JSON responses.
- Cache by intent: static by default, `revalidate: N` for periodic refresh, tags + `revalidateTag` for event-driven invalidation, `cache: "no-store"` or `dynamic = "force-dynamic"` only when per-request data is required.
- Metadata via the Metadata API (`metadata` export or `generateMetadata`). No manual `<head>` writes.
- All images use `next/image` with explicit `width`/`height` (or static import); mark the LCP image `priority`.
- Navigate with `<Link>`; reach for `router.push` only for post-mutation redirects.

## Patterns

### Server Component as the Data Layer

Fetch on the server, pass props to small client islands. The client bundle should contain interactivity, not data fetching.

```tsx
// app/products/[slug]/page.tsx - Server Component
import "server-only";
import { notFound } from "next/navigation";
import { AddToCart } from "./add-to-cart"; // client island

export default async function ProductPage({
  params,
}: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const product = await getProduct(slug); // direct DB or fetch()
  if (!product) notFound();
  return (
    <article>
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <AddToCart productId={product.id} /> {/* only this ships to client */}
    </article>
  );
}
```

### Caching: fetch options, tags, and `unstable_cache`

```tsx
// Time-based: ISR, refreshed in the background after `revalidate` seconds.
const res = await fetch(`${API}/products/${slug}`, {
  next: { revalidate: 3600, tags: [`product:${slug}`, "products"] },
});

// Per-request, never cached.
const session = await fetch(`${API}/me`, { cache: "no-store" });

// Wrap non-fetch data sources (DB calls, SDKs) with unstable_cache.
import { unstable_cache } from "next/cache";
export const getProduct = unstable_cache(
  async (slug: string) => db.product.findUnique({ where: { slug } }),
  ["product"],
  { revalidate: 3600, tags: ["products"] },
);
```

Invalidate from a Server Action or webhook handler:

```tsx
"use server";
import { revalidateTag, revalidatePath } from "next/cache";
export async function publishProduct(id: string) {
  await db.product.update({ where: { id }, data: { published: true } });
  revalidateTag("products");        // every page tagged "products"
  revalidatePath(`/products/${id}`); // this specific URL
}
```

Bad: `export const dynamic = "force-dynamic"` on a page whose data changes hourly - use `revalidate: 3600` and keep it static-ish.

### Server Actions: validation, auth, revalidation

```tsx
// app/posts/actions.ts
"use server";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireUser } from "@/lib/auth";

const CreatePost = z.object({
  title: z.string().min(1).max(200),
  content: z.string().min(1),
});

export async function createPost(_prev: State, formData: FormData) {
  const user = await requireUser();                    // authorize
  const parsed = CreatePost.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { error: parsed.error.flatten().fieldErrors };
  await db.post.create({ data: { ...parsed.data, authorId: user.id } });
  revalidatePath("/posts");
  return { ok: true };
}
```

Consume with progressive enhancement - the form works without JS:

```tsx
"use client";
import { useActionState } from "react";
import { createPost } from "./actions";

export function CreatePostForm() {
  const [state, action, pending] = useActionState(createPost, null);
  return (
    <form action={action}>
      <input name="title" required />
      {state?.error?.title && <p role="alert">{state.error.title[0]}</p>}
      <textarea name="content" required />
      <button disabled={pending}>{pending ? "Creating..." : "Create"}</button>
    </form>
  );
}
```

### Route Handlers: when a URL is the product

Use for webhooks, OAuth callbacks, non-JSON responses, or external/non-form clients. Same validation + auth rules as Server Actions.

```tsx
// app/api/webhooks/stripe/route.ts
import { headers } from "next/headers";
import { revalidateTag } from "next/cache";

export async function POST(req: Request) {
  const sig = (await headers()).get("stripe-signature");
  if (!sig) return new Response("missing signature", { status: 400 });
  const event = verifyStripe(await req.text(), sig); // throws on bad sig
  if (event.type === "product.updated") revalidateTag("products");
  return Response.json({ received: true });
}
```

### Rendering Strategy

| Strategy   | Trigger                                                   | Use for                                  |
| ---------- | --------------------------------------------------------- | ---------------------------------------- |
| Static     | No dynamic APIs, no `cache: "no-store"`                   | Marketing, docs, catalog                 |
| ISR        | `next.revalidate` or `unstable_cache` w/ TTL              | Periodically changing content            |
| Dynamic    | `cookies()`, `headers()`, `searchParams`                  | Personalized, auth-gated pages           |
| Streaming  | `Suspense` around async children                          | Slow data alongside fast shell           |
| PPR        | `experimental_ppr = true` + `Suspense` over dynamic holes | One mostly-static page with a per-user widget; avoids `force-dynamic` |

```tsx
// Stream slow widgets without blocking the shell.
export default function Dashboard() {
  return (
    <>
      <Header />                          {/* fast, renders immediately */}
      <Suspense fallback={<ChartSkeleton />}>
        <RevenueChart />                  {/* async RSC, streams in */}
      </Suspense>
    </>
  );
}
```

### Metadata API

```tsx
// Static
export const metadata: Metadata = { title: "My App", description: "..." };

// Dynamic: runs on the server, deduped with the page's own fetch by request memoization.
export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params;
  const product = await getProduct(slug); // same call as the page; React cache dedupes
  return {
    title: product.name,
    description: product.summary,
    openGraph: { title: product.name, images: [product.coverImage] },
  };
}
```

### Image Optimization

```tsx
import Image from "next/image";
import hero from "@/public/hero.jpg"; // static import: dimensions + blur baked in

<Image src={hero} alt="Hero" priority placeholder="blur" />
<Image src={user.avatarUrl} alt={user.name} width={48} height={48} />
// Remote sources must be allow-listed in next.config.ts `images.remotePatterns`.
```

### Server-Only Boundary

```tsx
// lib/db.ts
import "server-only"; // build error if imported from a Client Component
export const db = new PrismaClient();
```

### Partial Prerendering (PPR)

Next.js 15 ships PPR: a static shell renders instantly; dynamic holes stream at request time. The route is static *and* dynamic in one response - no `force-dynamic` for one personalized widget.

```ts
// next.config.ts
import type { NextConfig } from "next";
const config: NextConfig = { experimental: { ppr: "incremental" } };
export default config;
```

```tsx
// app/dashboard/page.tsx
export const experimental_ppr = true; // opt this route in (incremental mode)

export default function DashboardPage() {
  return (
    <>
      <StaticHeader />                       {/* prerendered into the shell */}
      <Suspense fallback={<UserSkeleton />}>
        <UserPanel />                        {/* dynamic hole; streams per request */}
      </Suspense>
    </>
  );
}

async function UserPanel() {
  const user = await getCurrentUser(); // uses cookies() -> dynamic
  return <p>Welcome, {user.name}</p>;
}
```

Rules: every dynamic subtree (anything reading `cookies()` / `headers()` / `searchParams`, or `fetch` with `cache: "no-store"`) must be wrapped in `<Suspense>`. Without the boundary, PPR falls back to fully dynamic and you lose the static shell. Don't mix `force-dynamic` with PPR on the same route - they conflict.

### Pages Router -> App Router Migration

Routes coexist: `pages/` and `app/` ship in the same build, so migrate route-by-route. App Router wins when both define the same path.

| Pages Router                       | App Router equivalent                                                          |
| ---------------------------------- | ------------------------------------------------------------------------------ |
| `getStaticProps`                   | `fetch(url, { next: { revalidate: N } })` or `unstable_cache` in a Server Component |
| `getStaticPaths` + `getStaticProps` | `generateStaticParams()` + Server Component fetch                              |
| `getServerSideProps`               | Server Component reading `cookies()` / `headers()` / dynamic `searchParams`    |
| `getInitialProps` (`_app`/page)    | Server Component fetch, or layout for shared data; no per-request props plumbing |
| Built-in `i18n` config (`next.config`) | Removed in App Router - use a `[lang]` segment + middleware locale routing (no config-based i18n) |
| `revalidate: N` (ISR)              | `next: { revalidate: N }` per fetch, or route-level `export const revalidate = N` |
| `_app.tsx`                         | Root `app/layout.tsx` (shared shell) + per-segment layouts                      |
| `_document.tsx`                    | `app/layout.tsx` (`<html>` / `<body>` live there)                              |
| `pages/api/*` Route Handlers       | `app/api/*/route.ts` Route Handlers, or Server Actions for first-party forms   |
| `next/router` (`useRouter`)        | `next/navigation`: `useRouter`, `useSearchParams`, `usePathname`, `useParams`  |
| `next/head`                        | Metadata API (`export const metadata` / `generateMetadata`)                    |
| `pages/_error.tsx`                 | `app/**/error.tsx` (segment-scoped) + `app/global-error.tsx` (root)            |

Migration order: shared shell (`_app` -> root layout, `_document` -> `<html>`/`<body>`) first, then leaf routes one at a time, then `pages/api/*` to Route Handlers or Server Actions. Don't mix `getServerSideProps` with App Router patterns inside the same route - the App Router version owns the path once it exists.

Gotcha: `next/router` route events (`routeChangeStart`/`routeChangeComplete`) have no `next/navigation` equivalent - replace with `usePathname`/`useSearchParams` effects or `next/navigation`'s navigation hooks.

## Output Format

When auditing, emit one block per finding. Consuming workflows synthesize the route/mutation summary; do not produce one here.

```
- Location: <file>:<line>
  Issue: {RscBoundary | ClientLeak | ServerOnlyImport | UseClientAtRoot | ServerActionAuth | ServerActionValidation | ServerOnlyExport | OrmRowToClient | CachingMisuse | MissingRevalidation | DynamicWithoutSuspense | PprConflict | MetadataManual | ImageRaw | NavigationPush | ParamsNotAwaited}
  Severity: {Blocker | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name>
```

`CachingMisuse` is a wrong caching choice (`force-dynamic` for periodic data, `no-store` on cacheable data, missing TTL). `MissingRevalidation` is a write (Server Action / Route Handler) that mutates data without a following `revalidatePath`/`revalidateTag`, so cached views stay stale.

Severity guide:
- **Blocker**: server-only import or ORM/secret leak into a client bundle; missing auth on a mutating Server Action; `params`/`searchParams` used without `await` (silent-breaks on Next 15); `"use server"` file exporting a non-action.
- **High**: `"use client"` at a page/layout root that needs no interactivity; missing input validation on an action; `MissingRevalidation` after a write; dynamic subtree not wrapped in `<Suspense>` under PPR.
- **Medium**: wrong caching choice (`CachingMisuse`); manual `<head>` instead of Metadata API; raw `<img>` instead of `next/image`.
- **Low**: `router.push` where `<Link>` fits; minor convention drift.

If the project is not Next.js App Router, emit `No Next.js findings (not App Router).` and apply only framework-neutral rules (server/client boundary, input validation, cache-by-intent).

## Avoid

(Rules above cover boundary, validation, caching, metadata, and navigation defaults; these are the extras.)

- Mutating data from a Route Handler that a first-party form could call as a Server Action - duplicates validation, loses progressive enhancement.
- Fetching in a Client Component when the parent Server Component could pass props - extra round trip, ships fetch code, breaks streaming.
- `'use server'` files that export anything other than Server Actions - any export becomes network-callable.
- Returning a raw ORM row (`prisma.user.findUnique(...)`) into a Client Component - leaks fields like `passwordHash` into the HTML payload.
