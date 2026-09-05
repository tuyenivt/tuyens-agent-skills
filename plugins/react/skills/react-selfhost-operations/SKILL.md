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
- The CDN must bypass cache when the session cookie is present - matched **by name** (the app's observed cookie: `authjs.session-token` under Auth.js v5, prefixed `__Secure-` on HTTPS; `next-auth.session-token` on the v4 line. When the auth stack is unknown, state the bypass requirement and flag the cookie name unverified). A path-only rule serves an authenticated page to the next visitor; an any-cookie rule lets consent and analytics cookies bypass every request.
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
ENV HOSTNAME="0.0.0.0"
ENV PORT=3000
ENV NEXT_MANUAL_SIG_HANDLE=true
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
// A server component reads at runtime only when the route renders dynamically.
// A prerendered layout bakes the value in exactly like NEXT_PUBLIC_, so read it
// somewhere already dynamic, or opt the segment out of prerendering.
export const dynamic = "force-dynamic";
export default async function Layout({ children }: { children: React.ReactNode }) {
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
export default config;                                     // without the export Next loads its defaults
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

"Cache" means honor the origin `Cache-Control` - ISR pages already emit `s-maxage`; never force an edge TTL onto HTML the origin marked `no-store`. A default edge TTL that applies only when the origin sends no header is not forcing - `ForcedEdgeTtlOnHtml` fires when a floor or override discards the origin header. Bypass means the response is not served from cache at all: on CloudFront that is a caching-disabled behavior for the authenticated path, or an origin that returns `Cache-Control: private, no-store` when the session cookie is present. Putting the session cookie in the **cache key** is not a bypass - it stores one object per session token and fragments the cache while still caching. Forwarding a cookie to the origin (origin request policy) and keying on it (cache policy) are separate settings; neither one alone is a bypass.

Purge scoped to what changed on publish - by surrogate key/tag where the CDN supports it (Fastly, Cloudflare), by the changed paths on CloudFront, whose invalidations are path-only. A full purge sends every page to the origin at once, and the resulting render storm looks exactly like the traffic spike it actually is.

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
// run stage: ENV NEXT_MANUAL_SIG_HANDLE=true - without it the standalone server.js
// installs its own SIGTERM/SIGINT handlers and exits before any draining happens
// instrumentation.ts
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;   // process.on does not exist on Edge
  process.on("SIGTERM", async () => {
    await drainInFlight();     // the LB has stopped routing; bounded wait for open requests
    await db.$disconnect();    // close the pool only after the last response
    process.exit(0);
  });
}
```

Without this the old container holds its pool through the deploy overlap, which is the input that breaks the arithmetic in `backend-connection-pooling`.

## Output Format

When setting up a deployment (authoring), emit each artifact under a `### <file path>` heading with a one-line comment in the file itself carrying the justification, then this assessment block covering what the artifacts do not settle. When diagnosing a reported symptom (high origin CPU, stale pages after publish, one user seeing another's content), emit the block with `Findings` ordered by how well each explains the symptom, and `{file or config location}` naming the configuration responsible; when the input does not contain it, name the artifact that would and put it in `Not assessed:`. When reviewing, emit the block alone: findings ordered by severity, user-facing blast radius breaking ties, one finding per root cause (a config defect with several symptoms is one finding carrying them in Risk); then the `Not assessed:` and `Notes:` slots as templated. Outside the artifacts and their inline comments, no prose beyond the template.

```
## Self-Host Assessment

**Target:** {VPS | container host | Kubernetes | bare metal | unknown; write `<current> -> <planned>` when a move is in scope}

**Instances:** {<count> | `<current> -> <planned>` when a change is in scope | unknown (assumed 1). When sources disagree, take the deployed configuration and note the other in Findings}

**CDN:** {present | absent}

### Findings

- [Severity: High | Medium | Low] {file or config location} - {description}
  - Issue: {NotStandalone | BuildOnHost | PublicEnvBakedIn | UnsharedIsrCache | CdnCookieBypassMissing | ForcedEdgeTtlOnHtml | FullPurgeOnPublish | ImageOptimizerUnbounded | MissingStaticCopy | NoGracefulShutdown}
  - Risk: {what fails in production}
  - Fix: {concrete change; reference a Pattern by name}

Not assessed: {surfaces the input never showed - Dockerfile, shutdown handling, image config; omit when all shown}

Notes: {single line - out-of-scope observations, each naming the concern that owns it (`connection pool sizing`, `rollout sequencing`, `application security`) rather than a skill filename; omit when none}

### No Findings

{State explicitly when the deployment configuration is sound - do not omit silently.}
```

Severity:

- **High**: CDN caching authenticated responses; more than one instance without a shared cache handler; building on the production host.
- **Medium**: `NEXT_PUBLIC_` values that must vary per environment; full purge on publish; unbounded image optimization on a small host; missing graceful shutdown.
- **Low**: not using standalone output; missing static asset copy in an image not yet serving traffic (High once deployed - it is a no-CSS outage).

No Issue value is left unscored, and where a value appears in more than one band the band naming your defect's condition wins; `ForcedEdgeTtlOnHtml` is High, since a floor or override that discards the origin header serves stale or personalized HTML. A bypass rule matching any cookie rather than the session cookie by name is also `CdnCookieBypassMissing` - the value covers a bypass that is absent or wrongly scoped in either direction.

Omit "No Findings" when findings were listed. When instance count is unknown, assume one and say so. If the project is not self-hosted Next.js, emit `No self-host findings (managed platform or SPA).` bare - no envelope - and stop; one `Notes:` line naming the evidence read and any handoff may follow. The gate reads deployed state: platform config (`vercel.json`, Netlify/Amplify config) with no self-host artifact stops; any self-host artifact (Dockerfile, compose file, `output: "standalone"`), even beside a platform config, gets the full assessment of that artifact.

## Avoid

- Running `next build` on the same machine as the production database
- Treating a successful local build as evidence the image is correctly packaged; the static-asset omission only appears in the container
- Scaling to a second instance to fix load before the ISR cache is shared, which converts a slow site into an inconsistent one
- Caching by path alone when any authenticated route shares a prefix with a public one
