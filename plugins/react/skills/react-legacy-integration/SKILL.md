---
name: react-legacy-integration
description: "Embed React into legacy apps: island adoption, React-in-Rails/Django/PHP, microfrontends (Module Federation, single-spa), createRoot, hydration boundaries."
metadata:
  category: frontend
  tags: [react, legacy, incremental-adoption, islands, microfrontend, module-federation, single-spa, ssr, hydration]
user-invocable: false
---

# React Legacy Integration

> Load `Use skill: stack-detect` first to determine the project stack. For Next.js-only concerns defer to `react-nextjs-patterns`.

## When to Use

- Adding React to a Rails / Django / Laravel / classic ASP.NET / PHP / Java server-rendered app, one island at a time
- Composing multiple independently-deployed React apps via Module Federation or single-spa
- Mounting React into a non-React shell (jQuery page, Backbone view, server-rendered template) without rewriting the host
- Sharing user / cart / auth state across React and non-React code on the same page

Out of scope: greenfield SPA setup, Next.js / Vite project bootstrap (covered by `react-routing-patterns`), classic Pages Router migration (covered by `react-nextjs-patterns`).

## Rules

- Mount each island with `createRoot(node).render(<App />)`; never share a root between islands. Unmount with `root.unmount()` when the host removes the node.
- Exactly one copy of `react` and `react-dom` on the page. Duplicate copies break hooks, context, and `Suspense`. Enforce via bundler `resolve.alias` (host) or webpack `singleton: true` (Module Federation `shared`).
- Server-rendered HTML inside a React mount point requires `hydrateRoot`, not `createRoot`. Markup mismatches throw - render exactly the same DOM on first paint.
- Cross-boundary state crosses through DOM events (`CustomEvent`), a typed event bus, or a global store (Zustand / Redux) imported as a federated singleton. Never via `window.someGlobal = {...}` ad hoc.
- One React copy owns one `<Suspense>` tree; do not nest islands from a separate React copy inside a suspended boundary - the parent's fallback won't catch the child.
- Bootstrap CSS scoping: scope island CSS (CSS Modules, scoped Tailwind preflight off, or shadow DOM) so host styles don't bleed in and island styles don't break host pages.
- Routing: in microfrontend setups, exactly one router owns the URL. Children consume the path via props or a shared history, not their own `<BrowserRouter>`.

## Patterns

### Island Mount into a Server-Rendered Page

The host template emits a placeholder; a bundled entry script finds it and mounts.

```erb
<%# Rails view %>
<div id="cart-island" data-user-id="<%= current_user.id %>"></div>
<%= javascript_pack_tag "cart-island" %>
```

```tsx
// cart-island.entry.tsx
import { createRoot } from "react-dom/client";
import { CartIsland } from "./CartIsland";

const node = document.getElementById("cart-island");
if (node) {
  const root = createRoot(node);
  root.render(<CartIsland userId={Number(node.dataset.userId)} />);

  // Unmount when the host turns the page (Turbo / pjax / HTMX swap).
  document.addEventListener("turbo:before-render", () => root.unmount(), { once: true });
}
```

Rules: read props from `data-*` attributes (already JSON-safe), never from inline `<script>` JSON without parsing through `JSON.parse(node.dataset.payload)`. Use a stable id; for multi-instance islands, use `data-island="cart"` and iterate.

### Hydrating Server-Rendered HTML

When the host server (Rails ERB, Django template) renders HTML *inside* the island's mount node to avoid FOUC, hydrate instead of replacing.

```tsx
import { hydrateRoot } from "react-dom/client";

const node = document.getElementById("product-card");
if (node) {
  hydrateRoot(node, <ProductCard initialData={parseProps(node)} />);
}
```

Bad: `createRoot(node).render(...)` on a pre-rendered node - throws away the SSR HTML and flashes empty content.

Mismatches throw `Hydration failed`. The fix is always the same: the first React render must produce the exact same DOM the server emitted. Common causes - locale-dependent dates, `Math.random`, `typeof window !== "undefined"` branches - get gated behind a post-mount effect, not the first render.

### Sharing State Across React and Non-React

DOM events are the lowest-coupling option - both sides speak the same protocol.

```tsx
// React publishes
window.dispatchEvent(new CustomEvent("cart:item-added", { detail: { id, qty } }));

// jQuery subscribes
$(window).on("cart:item-added", (e) => updateHeaderBadge(e.originalEvent.detail));

// React subscribes
useEffect(() => {
  const onLogout = () => queryClient.clear();
  window.addEventListener("auth:logout", onLogout);
  return () => window.removeEventListener("auth:logout", onLogout);
}, []);
```

For richer shared state, expose a typed singleton store (Zustand) on `window` once, then both sides subscribe.

```ts
// shared/store.ts (bundled once, exposed via shared chunk or federated singleton)
import { create } from "zustand";
export const useAppStore = create<{ user: User | null }>(() => ({ user: null }));
declare global { interface Window { __app_store?: typeof useAppStore } }
window.__app_store ||= useAppStore;
```

Bad: ad-hoc `window.cart = []` mutation - no subscribers, no type safety, no SSR story.

### Module Federation (Webpack 5 / Rspack)

Host + remotes ship as independent bundles; the host loads remote modules at runtime.

```ts
// host webpack.config.ts (excerpt)
new ModuleFederationPlugin({
  name: "host",
  remotes: { checkout: "checkout@https://cdn.example.com/checkout/remoteEntry.js" },
  shared: {
    react:     { singleton: true, requiredVersion: "^18.0.0", eager: true },
    "react-dom": { singleton: true, requiredVersion: "^18.0.0", eager: true },
  },
});
```

```tsx
// host App.tsx
const Checkout = lazy(() => import("checkout/CheckoutApp"));
<Suspense fallback={<Spinner />}><Checkout /></Suspense>
```

Rules: `react` and `react-dom` MUST be `singleton: true` - duplicated copies break hooks. Version-skew across remotes is real; pin a compatible range per remote and fail loudly at load (`requiredVersion`) rather than silently dual-loading. If the remote is offline, the host's `Suspense` boundary needs an `ErrorBoundary` above it to fall back gracefully - federation errors aren't suspense-catchable.

### single-spa (Multi-Framework Shell)

When the host orchestrates React alongside Angular / Vue / vanilla apps.

```ts
// react-app/main.tsx
import singleSpaReact from "single-spa-react";
import { App } from "./App";

const lifecycles = singleSpaReact({
  React, ReactDOMClient,
  rootComponent: App,
  errorBoundary: (err) => <div role="alert">{String(err)}</div>,
});
export const { bootstrap, mount, unmount } = lifecycles;
```

Rules: a single-spa child does not own routing - the shell decides which app is active per URL. Inside the React child, use a memory router or `<Routes>` with a `basename` injected from the shell, never a fresh `<BrowserRouter>`. Mount / unmount must be idempotent; the shell may activate/deactivate the child multiple times per session.

### Routing Boundary in Hybrid Apps

| Scenario                            | URL owner                           | Child react routing               |
| ----------------------------------- | ----------------------------------- | --------------------------------- |
| Island on a Rails page              | Server (Rails routes)               | None or memory router             |
| Module Federation, host owns shell  | Host's `<BrowserRouter>`            | Remote uses `<Routes>` (no Router) |
| single-spa shell                    | single-spa's `registerApplication`  | Memory router or basename-scoped   |
| Two SPAs sharing a domain (path split) | Reverse proxy / NGINX rewrite     | Each owns its own subtree         |

Two `<BrowserRouter>` instances on one page fight over `history` and break the back button.

### Avoiding Two React Copies

Symptoms: `Invalid hook call`, context returning `undefined` from a provider that is clearly present, `Suspense` not catching a `use()` promise from a different bundle.

Fixes:

1. `npm ls react react-dom` - any duplicate version is a bug.
2. Bundler: alias `react` / `react-dom` to a single resolved path in host config; in monorepos, hoist via workspace or `pnpm.dedupe`.
3. Module Federation: `shared: { react: { singleton: true, ... } }`.
4. CDN-loaded React + bundled React: don't mix. Pick one and externalize the other (`externals: { react: "React" }`).

### Style Isolation

Host CSS resets (Bootstrap `reboot`, normalize) collide with island styles. Options, lowest cost first:

- **CSS Modules**: every class is hashed; no global collisions inside the island. The host's `*` rules still leak in.
- **Scoped Tailwind**: in `tailwind.config.ts` set `corePlugins: { preflight: false }` and prefix utilities (`prefix: "tw-"`) so reset / utility classes don't fight host CSS.
- **Shadow DOM**: full isolation. Cost: hard to use most React component libraries (portals escape; `<style>` injection needs custom resolver).

## Output Format

When auditing an integration, emit one block per finding:

```
- Location: <file>:<line> (or <module / federated remote>)
  Issue: {DuplicateReact | MissingHydrate | RootLeak | UnmountMissing | RouterCollision | CrossBoundaryGlobal | StyleBleed | FederationVersionSkew | SuspenseBoundaryMissing | MountIdNotUnique}
  Severity: {Critical | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name>
```

Severity guide:
- **Critical**: duplicate React copies; `createRoot` on server-rendered HTML; two `<BrowserRouter>` on one page.
- **High**: missing `root.unmount()` on host page swap (memory leak across navigations); ad hoc `window.X = ...` shared state without subscribers; federated remote without `ErrorBoundary` above its `Suspense`.
- **Medium**: missing CSS scoping (host bleed); single-spa child running its own `<BrowserRouter>`; mount node id not unique on a page with multiple instances.
- **Low**: `data-*` props not parsed through a schema; entry script not deferred.

If no issues, emit a single line: `No legacy-integration issues found in <scope>.`

## Avoid

- `createRoot` on a node containing server-rendered HTML - use `hydrateRoot`.
- Sharing a root between islands - each mount gets its own `createRoot` / `hydrateRoot`.
- Two copies of `react` / `react-dom` on a page (federated or otherwise) - `singleton: true` plus version pin.
- A child app running its own `<BrowserRouter>` inside a shell that already owns the URL.
- Reading shared cross-boundary state from `window.X` without a typed singleton and a subscribe protocol.
- Tailwind preflight enabled on an island mounted into a Bootstrap host - resets fight.
- Federated remote loaded under a `<Suspense>` without an enclosing `ErrorBoundary` - load failures aren't suspense-catchable.
- Mounting on `document.querySelector(".widget")` - multiple matches throw; use unique ids or iterate `querySelectorAll`.
