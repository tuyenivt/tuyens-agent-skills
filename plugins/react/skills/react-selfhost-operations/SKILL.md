---
name: react-selfhost-operations
description: "Self-hosted Next.js on a VPS or container: standalone output, CI builds, image CPU cost, ISR cache locality, CDN cookie bypass, build-time env."
metadata:
  category: ops
  tags: [nextjs, self-hosting, docker, isr, cdn, caching, deployment]
user-invocable: false
---

# Self-Hosted Next.js Operations

> Load `Use skill: stack-detect` first to determine the project stack. Rollout sequencing and rollback triggers are `ops-release-safety`; pool arithmetic is `backend-connection-pooling`. This skill owns what breaks when Next.js runs somewhere other than a managed platform.

## When to Use

- Deploying Next.js to a VPS, container host, or any self-managed environment
- Putting a CDN in front of a Next.js origin
- Diagnosing high origin CPU, stale pages after a publish, or a page serving one user's content to another

## Rules

- Build with `output: "standalone"`. It emits a minimal server and only the traced dependencies, which is the difference between a small image and shipping `node_modules`.
- **Build in CI, never on the production host.** A production build peaks well above a gigabyte and will contend with the database for memory on a small machine.
- `NEXT_PUBLIC_` variables are **inlined at build time**. One image cannot serve two environments that differ in any public variable. Anything that must vary per environment is read at runtime on the server and passed down.
- **The ISR cache is on local disk.** A second instance has its own copy, so revalidation on one leaves the other stale. Running more than one instance requires a shared cache handler.
- The CDN must bypass cache when the session cookie is present - matched **by name** (`next-auth.session-token`, the app's session cookie). A path-only rule serves an authenticated page to the next visitor; an any-cookie rule lets consent and analytics cookies bypass every request.
- Image optimization consumes origin CPU per distinct source and size. On a small host this saturates before anything else.
- Handle the termination signal: stop accepting connections, finish in-flight requests, close the database pool, then exit.

## Patterns

### Build and Run

```dockerfile
# build stage produces .next/standalone
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

`.next/static` and `public` are not included in the standalone output and must be copied explicitly. Omitting them produces a site that boots and then serves no CSS, which looks like a styling bug rather than a packaging one.

### Build-Time Versus Runtime Configuration

```
Bad   NEXT_PUBLIC_API_URL baked at build -> a separate image per environment
Good  read on the server at request time, pass to the client as props
```

```tsx
// server component reads at runtime, client island receives a value
export default async function Layout({ children }) {
  return <ConfigProvider apiBase={process.env.API_BASE_URL!}>{children}</ConfigProvider>;
}
```

The symptom of getting this wrong is a staging image promoted to production that keeps calling staging, with nothing in the logs to explain it.

### ISR Cache Locality

One instance: the on-disk cache is correct and needs nothing.

Two or more instances: a write revalidates the tag on the instance that handled it. Every other instance keeps serving its own stale copy until its own entry expires. The fix is a shared cache handler, configured before the second instance exists, not after the bug reports.

```ts
// next.config.ts
const config = {
  output: "standalone",
  cacheHandler: require.resolve("./cache-handler.mjs"),   // Redis-backed
  cacheMaxMemorySize: 0,                                   // disable in-memory layer
};
```

Treat the shared handler as the trigger condition for horizontal scaling: until it exists, the deployment is single-instance by construction.

### CDN Rules

| Request                          | Cache        | Why                                          |
| -------------------------------- | ------------ | ---------------------------------------------- |
| Content page, no session cookie  | Cache        | Identical for every visitor                  |
| Session cookie present (by name) | **Bypass**  | Personalized; caching it leaks between users |
| `/_next/static/*`                | Cache 1 year | Content-hashed filenames                     |
| `/_next/image*`                  | Cache long   | Each miss costs origin CPU                   |
| Server Action POST               | Bypass       | Mutations                                    |

"Cache" means honor the origin `Cache-Control` - ISR pages already emit `s-maxage`; never force an edge TTL onto HTML the origin marked `no-store`.

Purge by tag on publish rather than purging everything. A full purge sends every page to the origin at once, and the resulting render storm looks exactly like the traffic spike it actually is.

### Image Optimization Cost

The optimizer runs on the origin CPU, once per unique source and size combination. On a two-core host this is usually the first bottleneck to appear.

```ts
// Option 1 - pre-size at upload, serve directly
const config = { images: { unoptimized: true } };

// Option 2 - delegate to the CDN's image service
const config = { images: { loader: "custom", loaderFile: "./cdn-loader.ts" } };
```

Keep the default only when the image set is small and mostly cached. Measure before assuming it is.

### Graceful Shutdown

```ts
// instrumentation.ts
export async function register() {
  const shutdown = async () => {
    await db.$disconnect();
    process.exit(0);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}
```

Without this the old container holds its pool through the deploy overlap, which is the input that breaks the arithmetic in `backend-connection-pooling`.

## Output Format

```
## Self-Host Assessment

**Target:** {VPS | container host | unknown}

**Instances:** {1 | N}

**CDN:** {present | absent}

### Findings

- [Severity: High | Medium | Low] {file or config location} - {description}
  - Issue: {NotStandalone | BuildOnHost | PublicEnvBakedIn | UnsharedIsrCache | CdnCookieBypassMissing | ForcedEdgeTtlOnHtml | FullPurgeOnPublish | ImageOptimizerUnbounded | MissingStaticCopy | NoGracefulShutdown}
  - Risk: {what fails in production}
  - Fix: {concrete change; reference a Pattern by name}

### No Findings

{State explicitly when the deployment configuration is sound - do not omit silently.}
```

Severity:

- **High**: CDN caching authenticated responses; more than one instance without a shared cache handler; building on the production host.
- **Medium**: `NEXT_PUBLIC_` values that must vary per environment; full purge on publish; unbounded image optimization on a small host; missing graceful shutdown.
- **Low**: not using standalone output; missing static asset copy in an image not yet serving traffic (High once deployed - it is a no-CSS outage).

Omit "No Findings" when findings were listed. When instance count is unknown, assume one and say so. If the project is not self-hosted Next.js, emit `No self-host findings (managed platform or SPA).` and stop.

## Avoid

- Running `next build` on the same machine as the production database
- Treating a successful local build as evidence the image is correctly packaged; the static-asset omission only appears in the container
- Scaling to a second instance to fix load before the ISR cache is shared, which converts a slow site into an inconsistent one
- Caching by path alone when any authenticated route shares a prefix with a public one
