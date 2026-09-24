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

Out of scope: greenfield SPA setup; Next.js Pages -> App Router migration inside the same Next.js app (covered by `react-nextjs-patterns`).

## Rules

- Mount each island with `createRoot(node).render(<App />)`; never share a root between islands. Unmount with `root.unmount()` when the host removes the node.
- Exactly one copy of `react` and `react-dom` on the page. Duplicate copies break hooks, context, and `Suspense`. Enforce via bundler `resolve.alias` (host) or webpack `singleton: true` (Module Federation `shared`).
- Server-rendered HTML inside a React mount point requires `hydrateRoot`, not `createRoot`. A text or structure mismatch does not throw: React logs a recoverable error and client-renders up to the nearest `<Suspense>` boundary (the whole root without one) - a double render and a flash, logged but not thrown. An attribute-only mismatch is not patched at all (a dev warning) and the server value persists. Render exactly the same DOM on first paint.
- Cross-boundary state crosses through DOM events (`CustomEvent`), a typed event bus, or a global store (Zustand / Redux) imported as a federated singleton. Never via `window.someGlobal = {...}` ad hoc.
- A `<Suspense>` boundary only catches suspense thrown inside the same React tree. An island rendered by a separate React copy inside another tree's boundary will not be caught by that boundary's fallback.
- Scope island CSS so island styles never reach host pages, and accept that host element/`*` rules still reach in: CSS Modules for collision safety, Tailwind with preflight off for reset safety, shadow DOM when the island must be fully sealed.
- Routing: in microfrontend setups, exactly one router owns the URL. Children consume the path via props or a shared history, not their own `<BrowserRouter>`.

## Patterns

### Island Mount into a Server-Rendered Page

The host template emits a placeholder; a bundled entry script finds it and mounts.

```erb
<%# javascript_include_tag under jsbundling-rails; vite_javascript_tag under Vite Ruby; javascript_pack_tag under
    Shakapacker - the importmap default cannot build TSX. Load the entry from <head>: Turbo re-runs <body>
    scripts on every visit, stacking the listeners below. %>
<% content_for :head do %><%= javascript_include_tag "cart-island", defer: true %><% end %>
<div id="cart-island" data-user-id="<%= current_user.id %>"></div>
```

```tsx
// cart-island.entry.tsx
import { createRoot, type Root } from "react-dom/client";
import { CartIsland } from "./CartIsland";

let root: Root | undefined;

function mount() {
  const node = document.getElementById("cart-island");
  if (!node) return;
  root?.unmount(); // turbo:before-cache is skipped on a no-cache page, so never assume teardown ran
  root = createRoot(node);
  root.render(<CartIsland userId={Number(node.dataset.userId)} />);
}

// Turbo swaps insert fresh nodes on every visit, so mount per page, not once at import.
document.addEventListener("turbo:load", mount);
// Tear down before Turbo snapshots the page, or the cached snapshot keeps React-rendered DOM
// that the next back-navigation restores dead.
document.addEventListener("turbo:before-cache", () => { root?.unmount(); root = undefined; });
```

Rules: read props from `data-*` attributes, which are plain strings - a scalar needs only a cast, a JSON payload needs `JSON.parse(node.dataset.payload!)`. Use a stable id; for multi-instance islands, use `data-island="cart"` and iterate `querySelectorAll`.

`root.unmount()` is needed only when the host swaps DOM without a full reload (Turbo / pjax / HTMX), and the teardown event differs per library - `turbo:before-cache`, `pjax:beforeReplace`, `htmx:beforeSwap`. Bind the one the host actually emits; a handler for the wrong event never fires and the root leaks on every navigation. Under classic full-page navigation the browser discards the document and the root with it, so no handler is needed at all - and never unmount on `pagehide`, which fires when the page is frozen for bfcache and would restore an empty island.

### Hydrating Server-Rendered HTML

When the host server (Rails ERB, Django template) renders HTML *inside* the island's mount node to avoid FOUC, hydrate instead of replacing.

```tsx
import { hydrateRoot } from "react-dom/client";

const node = document.getElementById("product-card");
if (node) {
  hydrateRoot(node, <ProductCard initialData={parseProps(node)} />);
}
```

Bad: `createRoot(node).render(...)` on a pre-rendered node - throws away the SSR HTML and re-creates the DOM (focus, input values and scroll lost), with a visible change wherever the client output differs or suspends.

A text or structure mismatch is reported through `onRecoverableError` and recovered by discarding the server HTML and client-rendering (an attribute-only one is left as-is), so the symptom is a console error plus a visible flash rather than a crash. The fix is always the same: the first React render must produce the exact same DOM the server emitted. When the same component also renders on a JS server (react_on_rails, a Node SSR service), the common causes - locale-dependent dates, `Math.random`, `typeof window !== "undefined"` branches - get gated behind a post-mount effect. When a hand-written ERB or Django template supplies the HTML, the cause is template markup drifting from the component's render.

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

For richer shared state, expose a typed singleton store (Zustand) on `window` once, then both sides subscribe. The `window` exposure is for non-React consumers; an all-React federation imports the store as a federated singleton module instead.

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
    react:       { singleton: true, requiredVersion: "^19.0.0", strictVersion: true },
    "react-dom": { singleton: true, requiredVersion: "^19.0.0", strictVersion: true },
    "react-router": { singleton: true },     // one history owner across remotes
    zustand:     { singleton: true },        // shared store = one instance all remotes import
  },
});
// Remotes declare the same `shared` block. `eager` is per build, so each host and each
// remote decides for itself: mark its own shared modules eager, or keep the async
// boundary below. One side's choice never removes the requirement from the other.
```

```tsx
// host App.tsx
const Checkout = lazy(() => import("checkout/CheckoutApp"));
<ErrorBoundary fallback={<CheckoutUnavailable />}>
  <Suspense fallback={<Spinner />}><Checkout /></Suspense>
</ErrorBoundary>
```

Rules: `react` and `react-dom` MUST be `singleton: true` - duplicated copies break hooks. With `singleton` alone a remote outside the declared range still loads against the one shared copy - the highest version in the share scope, not necessarily the host's - and only warns; add `strictVersion: true` when that mismatch must fail the load instead of shipping a subtly wrong pairing. Upgrade the lagging remote rather than widening the pin. Every host and remote entry needs the async boundary (`index.ts` doing `import("./bootstrap")`) so shared-module negotiation runs before React loads, unless that build marks its own shared modules `eager`. The decision is per build - a host's `eager` does nothing for a remote's entry. If the remote is offline, the host's `Suspense` boundary needs an `ErrorBoundary` above it to fall back gracefully - federation errors aren't suspense-catchable.

### single-spa (Multi-Framework Shell)

When the host orchestrates React alongside Angular / Vue / vanilla apps.

```ts
// react-app/main.tsx
import React from "react";
import * as ReactDOMClient from "react-dom/client";
import singleSpaReact from "single-spa-react";
import { App } from "./App";

const lifecycles = singleSpaReact({
  React, ReactDOMClient,
  rootComponent: App,
  errorBoundary: (err) => <div role="alert">{String(err)}</div>,
});
export const { bootstrap, mount, unmount } = lifecycles;
```

Rules: a single-spa child does not own routing - the shell decides which app is active per URL. Inside the React child, use a memory router, or a `<BrowserRouter basename={...}>` whose basename the shell injects - `basename` is a router prop, not a `<Routes>` prop. Mount / unmount must be idempotent; the shell may activate/deactivate the child multiple times per session.

### Routing Boundary in Hybrid Apps

| Scenario                            | URL owner                           | Child react routing               |
| ----------------------------------- | ----------------------------------- | --------------------------------- |
| Island on a Rails page              | Server (Rails routes)               | None or memory router             |
| Module Federation, host owns shell  | Host's `<BrowserRouter>`            | Remote renders `<Routes>` only, no Router |
| single-spa shell                    | single-spa's `registerApplication`  | Memory router or basename-scoped   |
| Two SPAs sharing a domain (path split) | Reverse proxy / NGINX rewrite     | Each owns its own subtree         |

Two `<BrowserRouter>` instances on one page fight over `history` and break the back button.

### Avoiding Two React Copies

Symptoms: `Invalid hook call`, context returning `undefined` from a provider that is clearly present, `Suspense` not catching a `use()` promise from a different bundle.

Fixes:

1. `npm ls react react-dom` - any duplicate version is a bug.
2. Bundler: alias `react` / `react-dom` to a single resolved path in host config; in monorepos, hoist via the workspace, run `pnpm dedupe`, or pin one version with `pnpm.overrides`.
3. Module Federation: `shared: { react: { singleton: true, ... } }`.
4. CDN-loaded React + bundled React: don't mix. React 19 ships no UMD build, so there is no `window.React` to externalize against - move the CDN consumer onto the bundle, or serve React as an ES module through an import map.
5. SystemJS / import-map shells: the shell provides `react`/`react-dom` in the import map and children externalize them - never a UMD `<script>`.

### Style Isolation

Host CSS resets (Bootstrap `reboot`, normalize) collide with island styles. Options, lowest cost first:

- **CSS Modules**: every class is hashed, so the island's own styles never collide with the host's. It does nothing about the host's element and `*` selectors, which still apply inside the island.
- **Scoped Tailwind**: on v3, set `corePlugins: { preflight: false }` and `prefix: "tw-"` in the config. On v4 there is no `corePlugins`: import only the layers you want and carry the prefix on each import, which yields `tw:flex` rather than `tw-flex`:
  ```css
  @import "tailwindcss/theme.css" layer(theme) prefix(tw);
  @import "tailwindcss/utilities.css" layer(utilities) prefix(tw);
  ```
  Importing bare `tailwindcss` pulls preflight back in, so never combine the two forms.
- **Shadow DOM**: full isolation. Cost: hard to use most React component libraries (portals escape; `<style>` injection needs custom resolver).

## Output Format

When designing an integration (island rollout, federation split), emit `## Integration Design` with sections {Shared/singleton config | URL ownership | Cross-boundary state | Failure behavior | Rollout order}, then render the design's residual risks as the audit-block list below (`Location:` names the design section rather than a path, Evidence quotes the designed config, Severity rates the defect the risk would realize). When the host is a third party you do not build - a CMS page, a partner site - you cannot dedupe its bundle: ship the widget as a self-contained bundle that exposes nothing on `window`. Cross-origin session sharing is its own design decision, and it drives the mount: a token the host passes in keeps the widget in the host document, while a cookie only the app's origin can read forces the UI into an iframe served from that origin, with `postMessage` as the only channel back; that iframe's cookie is third-party on the host page, so browsers blocking third-party cookies need a `Partitioned` (CHIPS) session or the Storage Access API behind a user gesture - a Failure behavior entry, not an afterthought. `Shared/singleton config` then reads `none - the iframe isolates the bundle`. Same-document mechanisms do not cross origins. When auditing, open with one line `Scope: <files/modules audited>`, then emit one block per finding, ordered by severity, one finding per root cause (a duplicate-React page is one finding listing all copies; a shared global channel is one finding covering producer and consumer; a version skew cites both configs; Location may list several modules, comma-separated, the file the fix changes first; island-to-host and host-to-island style bleed are separate findings, since their fixes differ). The blocks are emitted as plain Markdown bullets; the fence below is display only:

```
- Location: <file>:<line> (or <module / federated remote>)
  Issue: {DuplicateReact | MissingHydrate | RootLeak | UnmountMissing | RouterCollision | CrossBoundaryGlobal | StyleBleed | FederationVersionSkew | FederationWiringMissing | SuspenseBoundaryMissing | MountIdNotUnique | UnparsedIslandProps | EntryNotDeferred}
  Severity: {Critical | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name>

Not assessed: {input the review needed but never saw - a file referenced but not provided, a module whose behaviour decides a severity, a symptom whose trigger lies outside scope; never a guessed finding; omit when none}

Notes: <observations outside the enum - a security hazard, an infrastructure or CDN risk, a dependency the code imports but never declares - each naming the concern that owns it; omit when none>
```

`RootLeak`: a root object retained after the host removed its DOM node - a re-mount that leaves the previous root live, scoring High for the same reason a missing teardown does. When the defect is the absent teardown itself, prefer `UnmountMissing`, which covers a missing teardown, a teardown bound to an event the host never emits, and a mount routine that never re-runs after a host swap. `SuspenseBoundaryMissing`: a lazy or federated remote rendered with no `<Suspense>` or no `ErrorBoundary` above it (High), and a single-spa child without its `errorBoundary` option (Medium). `FederationWiringMissing` also covers wiring that exists but an entry with neither the async bootstrap nor `eager` shared modules ("Shared module is not available for eager consumption" - a blank page). A component consuming router context (`useLocation`, `Link`) mounted where no router exists is `RouterCollision` at High, since it throws.

Severity guide:
- **Critical**: duplicate React copies; `createRoot` on server-rendered HTML; `RouterCollision` with two routers mounted at once or observable navigation breakage (back button, URL desync). A host library that owns history itself - Turbo, pjax - counts as the second router when a child also mounts a `BrowserRouter`.
- **High**: missing `root.unmount()` on host page swap (memory leak across navigations); ad hoc `window.X = ...` shared state without subscribers; `SuspenseBoundaryMissing` on a federated remote; island CSS rewriting host-wide elements (Tailwind preflight on in a styled host).
- **Medium**: host CSS visibly breaking island rendering (inbound element rules the island has not sealed against are expected, per Rules); a child router that is not the URL owner but shows no navigation breakage yet (`RouterCollision`); mount node id not unique on a page with multiple instances.
- **Low**: `UnparsedIslandProps` - a `data-*` value parsed but not validated (Medium when used without the cast or `JSON.parse` it needs and behaviour changes, e.g. a string id compared with `===` to a number); `EntryNotDeferred` - a blocking entry script on an island page, legacy widget scripts included.

No Issue value is left unscored. Where a value appears in more than one band, the band naming your defect's condition wins; where two fit equally, take the higher. `FederationVersionSkew` is Critical when the mismatch is on `react`/`react-dom` (a remote runs against a React major it was not built for, or fails to load under `strictVersion`) and High otherwise. `FederationWiringMissing` - a remote consumed with no federation or import-map wiring on the host, or an entry with neither the async bootstrap nor `eager` shared modules - is Critical, since nothing resolves or renders at runtime. Wiring is established by the host's own build config (a `ModuleFederationPlugin`/`federation` block, or an import map naming the remote); when that file is not in scope, say so in `Not assessed:` rather than inferring absence from a dependency list.

Anything real but outside the enum goes in the single trailing `Notes:` line with the owning concern named - injection in inlined JSON (application security), a CDN or cookie-forwarding risk in front of the host (delivery and caching), a package imported but not declared (dependency hygiene).

If no issues, emit a single line: `No legacy-integration issues found in <scope>.`

## Avoid

(Rules above cover the common cases; these are the extras.)

- Federated remote loaded under a `<Suspense>` without an enclosing `ErrorBoundary` - load failures are not suspense-catchable.
- Mounting on `document.querySelector(".widget")` - it silently returns the first match, so a second instance never mounts and no error says so; use unique ids or iterate `querySelectorAll`.
- Tailwind preflight enabled on an island mounted into a Bootstrap / Foundation host - the resets fight host-wide; drop preflight and prefix utilities.
