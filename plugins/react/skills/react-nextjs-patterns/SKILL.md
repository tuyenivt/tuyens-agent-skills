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

Out of scope: Pages Router maintenance, generic React state, framework-neutral SEO. The Pages -> App migration itself is in scope.

Version scope: the patterns target Next.js 15. On 16 - `middleware.ts` is `proxy.ts` (Node runtime only); PPR and `unstable_cache` give way to Cache Components (`cacheComponents: true`, `"use cache"` + `cacheLife` / `cacheTag`); `revalidateTag(tag, profile)` takes a cacheLife profile and `updateTag(tag)` gives a Server Action read-your-own-writes; synchronous `params` access is removed; the `next/image` `priority` prop is deprecated for `preload`; every parallel-route slot needs a `default.tsx` to build. Read the installed `next` version before prescribing either form.

## Rules

- Server Components are the default. Add `"use client"` only for hooks, event handlers, or browser APIs - and push the boundary as far down the tree as possible.
- Server-only modules (DB clients, secrets, server SDKs) import `import "server-only"`. Never import them transitively into a client component.
- **Next.js 15+: `params` and `searchParams` are `Promise`s.** Type as `params: Promise<{ slug: string }>` and `await` before use. On 15 synchronous access still works but logs a deprecation warning (codemod: `next-async-request-api`); 16 removes the shim (a type error at build, `undefined` at runtime), so treat it as a break in waiting, not a warning to leave.
- Server Actions are public HTTP endpoints: authorize the caller, validate every input with a schema, then revalidate. Choose Server Action for first-party form/mutation flows; choose Route Handler only when you need a stable URL, non-form clients, webhooks, or non-JSON responses.
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

Next 15 default: `fetch` responses are uncached unless you opt in with `cache: "force-cache"` or `next: { revalidate: N }` - `tags` alone only label an entry that something else caches; routes without dynamic APIs still prerender statically. Never wrap per-user reads in `unstable_cache` - the cross-request cache serves one user's data to another (`react-server-data-layer` owns the ORM-side rules). Per-entity tags require building the wrapper per call: `unstable_cache(fn, ["product", slug], { tags: ["product:" + slug] })(slug)`. Periodic and event-driven caching combine: tags carry the event path, `revalidate` is the TTL backstop.

Invalidate from a Server Action or webhook handler:

```tsx
"use server";
import { revalidateTag, revalidatePath } from "next/cache";
export async function publishProduct(id: string) {
  const p = await db.product.update({ where: { id }, data: { published: true }, select: { slug: true } });
  revalidateTag("products");            // every page tagged "products" (16: revalidateTag("products", "max"))
  revalidatePath(`/products/${p.slug}`); // the real URL is keyed by slug, not id
}
```

Bad: `export const dynamic = "force-dynamic"` on a page whose data changes hourly - use `revalidate: 3600` and keep it static-ish. On a genuinely personalized page Dynamic is correct; a mostly-shared page with one personal widget wants PPR (canary-only on 15 - streaming `Suspense` on a stable release; Cache Components on 16), not `force-dynamic`.

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

export type State = { error?: Record<string, string[]>; ok?: boolean }; // type exports are erased, legal in "use server"

export async function createPost(_prev: State | null, formData: FormData): Promise<State> {
  const user = await requireUser();                    // authorize
  const parsed = CreatePost.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { error: z.flattenError(parsed.error).fieldErrors }; // Zod 3: parsed.error.flatten()
  await db.post.create({ data: { ...parsed.data, authorId: user.id } });
  revalidatePath("/posts");
  return { ok: true };
}
```

Consume with progressive enhancement - the form works without JS:

```tsx
"use client";
import { useActionState } from "react";
import { createPost, type State } from "./actions";

export function CreatePostForm() {
  const [state, action, pending] = useActionState<State | null, FormData>(createPost, null);
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
| PPR        | `experimental_ppr = true` + `Suspense` over dynamic holes (15 canary only; Cache Components on 16) | One mostly-static page with a per-user widget; avoids `force-dynamic` |

`generateStaticParams()` prerenders a dynamic segment's known paths at build time. It need not list every path - return `[]` (or set `dynamic = "force-static"`) and, with `dynamicParams` at its default, an unlisted path renders on first request and is cached from then on. With no `generateStaticParams` export at all, the segment renders dynamically on every request (fetch-level caching still applies).

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

// Dynamic: runs on the server. Wrap the shared loader in React `cache()` to dedupe it within the render,
// or in `unstable_cache` to share it across requests - `fetch` alone memoizes, an ORM call does not.
export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params;
  const product = await getProduct(slug); // same call as the page; the shared cache serves both
  if (!product) notFound();               // without this guard a null deref makes an unknown slug a 500, not a 404
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

PPR renders a static shell instantly and streams dynamic holes at request time, so a route is static *and* dynamic in one response - no `force-dynamic` for one personalized widget. On the 15 line `experimental.ppr` is **canary-only**: a stable 15.x build throws `CanaryOnlyError`, so treat PPR as a design target and reach for streaming Suspense on a stable release.

```ts
// next.config.ts - requires next@canary on the 15 line
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

Routes coexist: `pages/` and `app/` ship in the same build, so migrate route-by-route - but the same path defined in both fails the build (`Conflicting app and page file`). Delete the `pages/` route in the same change that adds its `app/` replacement.

| Pages Router                       | App Router equivalent                                                          |
| ---------------------------------- | ------------------------------------------------------------------------------ |
| `getStaticProps`                   | `fetch(url, { next: { revalidate: N } })` or `unstable_cache` in a Server Component |
| `getStaticPaths` + `getStaticProps` | `generateStaticParams()` + Server Component fetch                              |
| `getServerSideProps`               | Server Component reading `cookies()` / `headers()` / dynamic `searchParams`    |
| `getInitialProps` (`_app`/page)    | Server Component fetch, or layout for shared data; no per-request props plumbing |
| Built-in `i18n` config (`next.config`) | Removed in App Router - use a `[lang]` segment + middleware locale routing (no config-based i18n) |
| `revalidate: N` (ISR)              | `next: { revalidate: N }` per fetch, or route-level `export const revalidate = N` |
| `_app.tsx`                         | Root `app/layout.tsx` (shared shell) + per-segment layouts                      |
| `_document.tsx`                    | `app/layout.tsx` (`<html>` / `<body>` live there; fonts move to `next/font`)   |
| `pages/api/*` API Routes           | `app/api/*/route.ts` Route Handlers, or Server Actions for first-party forms   |
| `next/router` (`useRouter`)        | `next/navigation`: `useRouter`, `useSearchParams`, `usePathname`, `useParams`  |
| `next/head`                        | Metadata API (`export const metadata` / `generateMetadata`)                    |
| `pages/_error.tsx`                 | `app/**/error.tsx` (segment-scoped) + `app/global-error.tsx` (root)            |

Migration order: shared shell (`_app` -> root layout, `_document` -> `<html>`/`<body>`) first, then leaf routes one at a time, then `pages/api/*` to Route Handlers or Server Actions. Don't mix `getServerSideProps` with App Router patterns inside the same route - the App Router version owns the path once it exists.

Gotcha: `next/router` route events (`routeChangeStart`/`routeChangeComplete`) have no direct `next/navigation` equivalent - replace with `usePathname`/`useSearchParams` effects, or on 15.3+ with `<Link onNavigate>` and `useLinkStatus` for per-link start/pending signals.

## Output Format

When designing, emit one block per surface - a `- Surface: <route or component>` bullet with indented `Strategy:` (Rendering Strategy row), `Cache:` (mechanism with TTL/tags) and `Invalidation:` lines; when PPR is canary-only for the installed version, the streaming-Suspense shape is the design and PPR its upgrade path - then findings for risks in the design, using the same envelope, ordering, and `Notes:` line as audits (Location names the planned file). When auditing, emit one block per finding, ordered by severity; Fix references a Pattern by name, or the governing Rule when no Pattern covers it; handoffs and off-enum observations go in one trailing `Notes:` line. Consuming workflows synthesize the route/mutation summary; do not produce one here.

```
- Location: <file>:<line>
  Issue: {RscBoundary | ClientLeak | ServerOnlyImport | UseClientAtRoot | ServerActionAuth | ServerActionValidation | ServerOnlyExport | OrmRowToClient | CachingMisuse | MissingRevalidation | DynamicWithoutSuspense | PprConflict | MetadataManual | ImageRaw | NavigationPush | ParamsNotAwaited | RouteConflict | LegacyRouterInApp | LegacyI18nConfig | MigrationOrder}
  Severity: {Blocker | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name, or the governing Rule>

Not assessed: {input the review needed but never saw - a file referenced but not provided, a module whose behaviour decides a severity, a symptom whose trigger lies outside scope; never a guessed finding; omit when none}

Notes: {handoffs and off-enum observations, each naming the owning concern; omit when none}
```

`CachingMisuse` is a wrong caching choice (`force-dynamic` for periodic data, `no-store` on cacheable data, missing TTL). `MissingRevalidation` is a write (Server Action / Route Handler) that mutates data without a following `revalidatePath`/`revalidateTag`, so cached views stay stale. `ServerOnlyExport` is a `"use server"` file exporting an async function that is not meant to be an endpoint - every exported async function becomes network-callable. A non-async export fails the build rather than shipping, so it is a compile error, not this finding. An exported async helper with no authorization is `ServerOnlyExport` when it was never meant as an endpoint and `ServerActionAuth` when it was. `OrmRowToClient` is a raw ORM row passed as a prop into a Client Component - Blocker when the row carries secret fields, High otherwise. Migration codes: `RouteConflict` = same path in `pages/` and `app/` (build fails); `LegacyRouterInApp` = `next/router` or its route events inside `app/` (crashes at mount, listeners never fire); `LegacyI18nConfig` = config-based i18n serving App Router routes; `MigrationOrder` = shell migrated out of order (`_app`/`_document` still authoritative - fonts or `<html>` diverging from `app/layout.tsx` - while `app/` routes ship). `ServerActionAuth`/`ServerActionValidation` cover Route Handlers too; Location may list two files when the defect spans them.

Severity guide:
- **Blocker**: server-only import or ORM/secret leak into a client bundle (`ServerOnlyImport` for the import, `ClientLeak` for a secret value that reaches the client, `OrmRowToClient` for a raw row with secret fields; a missing `import "server-only"` guard is `ServerOnlyImport` even with no proven leak); missing auth on a mutating Server Action, or on one returning per-user data; `params`/`searchParams` used without `await`; `"use server"` file exporting a non-action endpoint (`ServerOnlyExport`); per-user data wrapped in `unstable_cache` or a tagged cache (`CachingMisuse`, which this row raises from its Medium default); `RouteConflict`; `LegacyRouterInApp`; `experimental.ppr` on a stable 15.x release (`PprConflict`).
- **High**: `"use client"` at a page/layout root that needs no interactivity (an extractable leaf listener does not count as needing it); missing input validation on an action; `MissingRevalidation` after a write; dynamic subtree not wrapped in `<Suspense>` under PPR; `LegacyI18nConfig`.
- **Medium**: wrong caching choice (`CachingMisuse`); `MigrationOrder`; manual `<head>` instead of Metadata API; raw `<img>` instead of `next/image`.
- **Low**: `router.push` where `<Link>` fits; minor convention drift.

No Issue value is left unscored. Where a value appears in more than one band, the band naming your defect's condition wins; where two fit equally, take the higher. `RscBoundary` (a client component fetching what a parent Server Component could pass down) is Medium; `PprConflict` (`force-dynamic` on a route that also opts into PPR) is Medium; `experimental.ppr` enabled on a stable 15.x release is also `PprConflict`, at Blocker, since the build throws `CanaryOnlyError`. Per-user data reaching a cross-request cache is `CachingMisuse` at Blocker, which overrides that value's Medium default; the Blocker anchor names the case, the enum value carries it.

App Router = an `app/` or `src/app/` directory with a root layout (`layout.{tsx,jsx,js}` at its top, or atop each route group) - beside `pages/` the tree is hybrid and the App Router rules apply to `app/`; Pages Router = `pages/` or `src/pages/` alone. `stack-detect` reports `React (Next.js)` for both. If the project is not Next.js App Router, apply only the framework-neutral rules - server/client boundary, input validation on anything network-reachable, cache-by-intent - opening with `Scope: framework-neutral review (not App Router - Next-specific rules skipped)`. The block shape, severity bands and `Notes:` line apply unchanged; use the Issue value whose defect matches regardless of its Next-flavoured name (`ServerActionValidation` for any unvalidated mutation entry point, `CachingMisuse` for any wrong caching choice). Emit `No Next.js findings (not App Router).` only when those rules are clean. A hybrid `pages/` + `app/` tree is in scope - audit both sides against the migration table.

## Avoid

(Rules above cover boundary, validation, caching, metadata, and navigation defaults; these are the extras.)

- Mutating data from a Route Handler that a first-party form could call as a Server Action - duplicates validation, loses progressive enhancement.
- Fetching in a Client Component when the parent Server Component could pass props - extra round trip, ships fetch code, breaks streaming.
- `'use server'` files that export an async function not meant as an endpoint - every exported async function becomes network-callable.
- Returning a raw ORM row (`prisma.user.findUnique(...)`) into a Client Component - leaks fields like `passwordHash` into the HTML payload.
