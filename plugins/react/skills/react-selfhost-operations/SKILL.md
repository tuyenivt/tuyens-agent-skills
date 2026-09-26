---
name: react-selfhost-operations
description: "Self-hosted Next.js on a VPS or container: standalone output, CI builds, multi-instance caches and keys, CDN cookie bypass, image cost, runtime env."
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
- **Caches are per instance.** The ISR cache is on local disk and `"use cache"` entries live in process memory, so revalidation on one instance leaves the others stale. More than one instance requires every Multi-Instance Prerequisite below: shared cache handlers, one Server Action encryption key, and a `deploymentId`.
- The CDN must bypass cache when the session cookie is present - matched **by name** as a prefix (the app's observed cookie: `authjs.session-token` under Auth.js v5 (still beta), prefixed `__Secure-` on HTTPS; `next-auth.session-token` on the v4 line, which also takes the `__Secure-` prefix on HTTPS; a session over ~4 KB splits into `.0`, `.1` chunks, which an exact-name rule misses. When the auth stack is unknown, state the bypass requirement and flag the cookie name unverified). A path-only rule serves an authenticated page to the next visitor; an any-cookie rule lets consent and analytics cookies bypass every request.
- Image optimization consumes origin CPU per distinct source and size. On a small host this saturates before anything else.
- Handle the termination signal: keep serving through the load balancer's deregistration delay, let in-flight requests finish, close the database pool, then exit.

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
# Only with the instrumentation.ts handler below: set without it, node runs as PID 1 with no SIGTERM
# listener, the kernel ignores the signal, and the orchestrator SIGKILLs after the grace period.
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
// A prerendered component bakes process.env in exactly like NEXT_PUBLIC_. `await connection()` defers
// the read to request time. Under Cache Components only the subtree below it (inside <Suspense>) renders
// per request, so call it in the leaf that needs the value; without it the whole route becomes dynamic.
import { connection } from "next/server";

export async function CheckoutWidget() {
  await connection();
  return <CheckoutClient apiBase={process.env.API_BASE_URL!} />;
}
```

The symptom of getting this wrong is a staging image promoted to production that keeps calling staging, with nothing in the logs to explain it.

### Multi-Instance Prerequisites

One instance: the on-disk ISR cache and the in-memory `"use cache"` store are correct and need nothing. Two or more instances need all of these, configured before the second instance exists:

| Concern | Without it | Fix |
| ------- | ---------- | --- |
| ISR / fetch cache | A write revalidates only the instance that handled it; the others serve stale copies until their own entries expire | `cacheHandler` (singular) on shared storage, `cacheMaxMemorySize: 0` |
| `"use cache"` entries (Cache Components) | Per-process memory, never shared, lost on restart - `cacheHandler` does not cover them | `cacheHandlers` (plural) on shared storage: a `default` handler shares plain `"use cache"`; a `remote` handler serves `"use cache: remote"` |
| Tag invalidation | `revalidateTag` / `updateTag` expires the tag on the local instance only | Each `cacheHandlers` handler implements `updateTags()` (writes the invalidation to shared storage) and `refreshTags()` (reads it before each request; catch its errors, or every request fails) |
| Server Action encryption key | The default key is generated per build; a rolling deploy, a per-stage rebuild or a second image build gives instances different keys, and actions fail with "Failed to find Server Action" | One `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` (base64 of 16, 24 or 32 bytes: `openssl rand -base64 32`) set at `next build`, where it is embedded |
| Version skew | A rolling deploy serves old clients new assets and unknown Server Action IDs | `deploymentId` (or `NEXT_DEPLOYMENT_ID`), one value per deployment; a mismatched client hard-reloads |

```ts
// next.config.ts
import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  deploymentId: process.env.DEPLOYMENT_VERSION,                          // same on every instance of one deploy
  cacheHandler: require.resolve("./cache-handler.mjs"),                  // ISR + fetch cache, Redis-backed
  images: { customCacheHandler: true },                                  // optimized images through it too
  cacheMaxMemorySize: 0,                    // disables BOTH built-in memory caches - plain "use cache" too, so replace `default`
  cacheHandlers: {                           // shared storage; implements updateTags() + refreshTags()
    default: require.resolve("./use-cache-handler.mjs"),                  // plain "use cache"
    remote: require.resolve("./use-cache-handler.mjs"),                   // "use cache: remote"
  },
};
export default config;                                                   // without the export Next loads its defaults
```

Treat these as the trigger condition for horizontal scaling: until they exist, the deployment is single-instance by construction.

### CDN Rules

| Request                          | Cache        | Why                                          |
| -------------------------------- | ------------ | ---------------------------------------------- |
| Content page, no session cookie  | Cache, `_rsc` in the key | Identical for every visitor; one URL serves HTML and RSC payloads |
| Session cookie present (by name) | **Bypass**  | Personalized; caching it leaks between users |
| `/_next/static/*`                | Cache 1 year | Content-hashed filenames                     |
| `/_next/image*`                  | Cache long, query string and `Accept` in the key | Each miss costs origin CPU; `url`/`w`/`q` and AVIF/WebP negotiation vary the response |
| Server Action POST               | Bypass       | Mutations                                    |

"Cache" means honor the origin `Cache-Control` - ISR pages already emit `s-maxage`, dynamically rendered pages `private, no-cache, no-store, max-age=0, must-revalidate`; never force an edge TTL onto HTML the origin marked `no-store`. The `rsc` request header selects HTML or the RSC payload for one URL: forward it and keep the `_rsc` query parameter in the cache key (some CDNs drop query strings from it by default), or one variant answers the other's request and client navigation breaks (`RscCacheKeyMissing`); cache both variants under one TTL and one purge, or client navigation shows a different render than the page load. A default edge TTL that applies only when the origin sends no header is not forcing - `ForcedEdgeTtlOnHtml` fires when a floor or override discards the origin header. Bypass means the response is not served from cache at all, and the edge must skip the lookup itself: an origin returning `Cache-Control: private, no-store` only stops authenticated responses being stored, while a request carrying the cookie still gets the cached anonymous copy. On CloudFront, behaviors select by path, not cookie, so a caching-disabled behavior works only for paths that are authenticated-only; shared paths need a viewer-request CloudFront Function or Lambda@Edge that makes cookie-bearing requests key separately (rewrite the URI to an uncached prefix, or add a marker header or query value the cache policy keys on) - a function cannot move a request to another behavior, and changing its origin does not skip the cache lookup. Keying on the session cookie itself is safe only while every authenticated response is `no-store` (and every chunk name is listed, since cache policies match cookie names exactly); one cacheable authenticated response then stores an object per token, so prefer the explicit bypass. Forwarding a cookie to the origin (origin request policy) and keying on it (cache policy) are separate settings; neither one alone is a bypass.

Streaming needs every hop to pass chunked responses through. nginx buffers by default, so `<Suspense>` fallbacks and the static shell arrive only with the full render - send `X-Accel-Buffering: no` from `next.config` `headers()` (or set `proxy_buffering off`), and confirm the load balancer does not buffer either.

Purge scoped to what changed on publish - by surrogate key/tag where the CDN supports it (Fastly, Cloudflare), by the changed paths on CloudFront, whose invalidations are path-only. A full purge sends every page to the origin at once, and the resulting render storm looks exactly like the traffic spike it actually is.

### Image Optimization Cost

The optimizer runs on the origin CPU, once per unique source and size combination - per instance, unless `images.customCacheHandler: true` routes them through the shared `cacheHandler`. On a two-core host this is usually the first bottleneck to appear.

```ts
// Merge the chosen option into next.config.ts's exported config.
// Option 1 - pre-size at upload, serve directly
const optionA = { images: { unoptimized: true } };

// Option 2 - delegate to the CDN's image service
const optionB = { images: { loader: "custom", loaderFile: "./cdn-loader.ts" } };
```

Keep the default only when the image set is small and mostly cached. Measure before assuming it is. The defaults bound the work - `images.qualities` is `[75]` (one variant per width), `minimumCacheTTL` 4 hours, `maximumRedirects` 3 - and block sources that resolve to a private IP: behind a VPC or split-horizon DNS the optimizer returns 400 until `images.dangerouslyAllowLocalIP: true` is set deliberately (an SSRF trade-off).

### Graceful Shutdown

```ts
// run stage: ENV NEXT_MANUAL_SIG_HANDLE=true. The default handler stops listening at once - requests the LB
// routes during its deregistration delay are refused - then awaits in-flight requests and pending after()
// callbacks. This handler replaces it: nothing awaits after() work, so the sleep must cover it too.
// instrumentation.ts cannot reach the listener, so it keeps serving and waits.
// instrumentation.ts
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;   // defensive: process.on is Node-only
  process.on("SIGTERM", async () => {
    await sleep(LB_DEREGISTRATION_MS + LONGEST_REQUEST_MS); // bounded, after() work included; keep it under the grace period
    await db.$disconnect();    // close the pool only after the last response
    process.exit(0);
  });
}
```

Without this the old container holds its pool through the deploy overlap, which is the input that breaks the arithmetic in `backend-connection-pooling`.

## Output Format

When setting up a deployment (authoring), emit each artifact under a `### <file path>` heading with a one-line comment in the file itself carrying the justification, then this assessment block covering what the artifacts do not settle - a concern the artifacts resolve is not a Finding, and a path an artifact assumes but the repo lacks (`public/`) is left out of the artifact and named in `Not assessed:`. CDN rules take the CDN's config-as-code form when the repo has one (Terraform, `wrangler.toml`), else a rules table. Authoring the first self-host artifacts for a project on a managed platform is in scope; the gate below applies to reviews and diagnoses. When diagnosing a reported symptom (high origin CPU, stale pages after publish, one user seeing another's content), emit the block with `Findings` ordered by how well each explains the symptom (several symptoms: group the findings by order under the symptom each explains - no group headings - best explanation first within a group, then file-evidenced latent findings), and `{file or config location}` naming the configuration responsible; when the input does not contain it, name the artifact that would and put it in `Not assessed:`. When reviewing, emit the block alone: findings ordered by severity, user-facing blast radius breaking ties (cross-user exposure, then stale serving, then capacity), one finding per root cause (a config defect with several symptoms is one finding carrying them in Risk; two Issue values in one config block are two findings); then the `Not assessed:` and `Notes:` slots as templated. Outside the artifacts and their inline comments, no prose beyond the template.

```
## Self-Host Assessment

**Target:** {VPS | container host | Kubernetes | bare metal | unknown; write `<current> -> <planned>` when a move is in scope, a managed platform named as the current value (`Vercel -> VPS`)}

**Instances:** {<count> | `<current> -> <planned>` when a change is in scope | unknown (assumed 1). When sources disagree, take the deployed configuration and note the other in `Notes:`}

**CDN:** {present | absent | unknown - CDN config not in scope (list it under Not assessed)}

### Findings

- [Severity: High | Medium | Low] {file or config location} - {description}
  - Issue: {NotStandalone | BuildOnHost | PublicEnvBakedIn | UnsharedIsrCache | ActionKeyUnshared | NoDeploymentId | CdnCookieBypassMissing | ForcedEdgeTtlOnHtml | RscCacheKeyMissing | FullPurgeOnPublish | StreamingBuffered | ImageOptimizerUnbounded | MissingStaticCopy | NoGracefulShutdown}
  - Risk: {what fails in production}
  - Fix: {concrete change; reference a Pattern by name}

Not assessed: {surfaces the input never showed - Dockerfile, shutdown handling, image config; omit when all shown}

Notes: {single line - out-of-scope observations, each naming the concern that owns it (`connection pool sizing`, `rollout sequencing`, `application security`) rather than a skill filename; omit when none}

### No Findings

{State explicitly when the deployment configuration is sound - do not omit silently.}
```

Severity:

- **High**: CDN caching authenticated responses; a CDN key or forwarding rule that drops `_rsc` or the `rsc` header (`RscCacheKeyMissing`); more than one instance without a shared cache handler for a cache the app uses, or without `updateTags()` / `refreshTags()` coordination (`UnsharedIsrCache`, which covers `"use cache"` entries too); more than one instance, or separately built images, without one `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` (`ActionKeyUnshared`); building on the production host.
- **Medium**: `NEXT_PUBLIC_` values that must vary per environment; rolling deploys without a `deploymentId` (`NoDeploymentId`); full purge on publish; a buffering proxy in front of a streaming app (`StreamingBuffered`); unbounded image optimization on a small host; missing graceful shutdown.
- **Low**: not using standalone output; missing static asset copy in an image not yet serving traffic (High once deployed - it is a no-CSS outage).

No Issue value is left unscored, and where a value appears in more than one band the band naming your defect's condition wins; `ForcedEdgeTtlOnHtml` is High, since a floor or override that discards the origin header serves stale or personalized HTML. A bypass rule matching any cookie rather than the session cookie by name is also `CdnCookieBypassMissing` - the value covers a bypass that is absent or wrongly scoped in either direction; the over-broad form caches nothing and leaks nothing, so it is Medium (lost cache hit rate).

Omit "No Findings" when findings were listed. When instance count is unknown, assume one and say so. If the project is not self-hosted Next.js, emit `No self-host findings (managed platform).` bare - no envelope - and stop; one `Notes:` line naming the evidence read and any handoff may follow. The gate reads deployed state: platform config (`vercel.json`, Netlify/Amplify config) with no self-host artifact stops; any self-host artifact (Dockerfile, compose file, `output: "standalone"`), even beside a platform config, gets the full assessment of that artifact.

## Avoid

- Running `next build` on the same machine as the production database
- Treating a successful local build as evidence the image is correctly packaged; the static-asset omission only appears in the container
- Scaling to a second instance to fix load before the caches are shared, which converts a slow site into an inconsistent one
- Caching by path alone when any authenticated route shares a prefix with a public one
