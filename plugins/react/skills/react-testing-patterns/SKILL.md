---
name: react-testing-patterns
description: "React 19 testing: Vitest + RTL, user-event, MSW network mocking, hook tests via renderHook, four-state data tests, axe a11y."
metadata:
  category: frontend
  tags: [react, testing, vitest, react-testing-library, msw, playwright, hooks]
user-invocable: false
---

# React Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack. Server code and database-backed tests belong to `react-server-testing`.

## When to Use

- Writing or reviewing tests for React components, hooks, and pages
- Setting up Vitest + RTL + MSW infrastructure
- Choosing between component, integration, and E2E coverage

## Rules

- Assert what the user sees and does; never read `useState`, refs, or class names
- Query by role/label/text; `getByTestId` is a last resort
- Forms and dialogs carry one axe test alongside role-based queries
- Mock HTTP at the network boundary with MSW; do not `vi.mock` API modules
- Data-fetching components and hooks require loading, success, error, and empty tests
- Test hooks with `renderHook`; never reach hook internals through a host component
- Tests are independent and parallel-safe; no shared mutable state, no order coupling

## Patterns

### Component + user-event

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

it("calls onEdit with user id", async () => {
  const onEdit = vi.fn();
  const user = userEvent.setup();
  render(<UserCard user={{ id: "1", name: "Alice" }} onEdit={onEdit} />);

  await user.click(screen.getByRole("button", { name: "Edit" }));
  expect(onEdit).toHaveBeenCalledWith("1");
});
```

### Render with Providers

```tsx
// Compose every provider the tree reads: query client, store, theme, auth.
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
export const renderWithProviders = (ui: ReactElement) => render(ui, { wrapper: Providers });
```

Reuse `renderWithProviders` for components that read a provider; plain `render` for those that read none. Hooks take the component itself: `renderHook(() => useUser("1"), { wrapper: Providers })` - a render helper returns a `RenderResult`, not JSX, and cannot be a `wrapper`.

The router is not a provider: `useRouter` / `usePathname` / `useSearchParams` read Next's App Router context, which jsdom lacks. Stub `next/navigation` at module level and assert navigation on `router.push`:

```tsx
const { router } = vi.hoisted(() => ({  // a factory reading a plain const at evaluation time hits the TDZ; hoisted is safe in every form
  router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), forward: vi.fn(), prefetch: vi.fn() },
}));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),  // keeps redirect / notFound real
  useRouter: () => router,         // one object: the real router is stable, so a [router] effect must not re-run
  usePathname: () => "/orders",
  useSearchParams: () => new URLSearchParams("status=open"),
  useParams: () => ({ id: "1" }),  // when the component reads params; the real one returns null outside the App Router
}));
// A Pages Router component reads `next/router`: stub that module the same way (`useRouter: () => router`).
// Vitest 5 clears spies before each test by default (`clearMocks: true`); add `beforeEach(() => vi.clearAllMocks())`
// only on Vitest 4 / Jest or when the config sets `clearMocks: false` - the spies are module-scoped
```

### MSW Setup

```tsx
// test/mocks/handlers.ts
import { http, HttpResponse } from "msw";
export const handlers = [
  http.get("/api/users", () =>
    HttpResponse.json([{ id: "1", name: "Alice" }]),
  ),
];

// vitest.config.mts: defineConfig({ plugins: [react()], resolve: { tsconfigPaths: true },   // @vitejs/plugin-react; Vite 8 resolves `@/` natively (vite-tsconfig-paths is stale)
//   test: { environment: "jsdom", globals: true, setupFiles: ["./vitest.setup.ts"] } })
// Without globals, import it/expect/vi and the hooks from "vitest" and RTL's automatic cleanup stops running.
// vitest.setup.ts - the reference types the bare globals; `next build` type-checks test files (TS2304 without it)
/// <reference types="vitest/globals" />
import "@testing-library/jest-dom/vitest";   // without this every toBeInTheDocument() throws
import { setupServer } from "msw/node";
import { handlers } from "./test/mocks/handlers";
export const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledFrame: "error" })); // MSW 3 key (a fresh install); MSW 2 takes onUnhandledRequest - each major's types reject the other's key (TS2353) and its runtime falls back to "warn"
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

Override per test with `server.use(...)`; never edit the global handler array. Module-singleton stores are seeded per test before `render` (Zustand `useStore.setState({ ... })`) and reset in `afterEach` (`useStore.setState(initialState, true)`; Redux through a `makeStore()` factory per test). jsdom has no `IntersectionObserver` or `ResizeObserver`: stub them on `globalThis` in the setup file when a component in scope calls them. The paths here are defaults for a project with no tests; an existing test directory and naming convention win.

On Jest (`next/jest`): `jest.mock` is hoisted above imports, so a factory reads a `mock`-prefixed variable lazily (`useRouter: () => mockRouter`) - the prefix passes babel-jest's scope check (next/jest's SWC transform has none), not the TDZ; `jest.mocked` replaces `vi.mocked`, `clearMocks: true` goes in `jest.config`, `jest-axe` replaces `vitest-axe`, and MSW under `next/jest` needs `testEnvironment: 'jest-fixed-jsdom'` (MSW's own environment, restoring the fetch globals) plus the ESM-only packages in `next.config` `transpilePackages` (next/jest only appends to `transformIgnorePatterns`, so a pattern there cannot admit them): on MSW 2 `rettime`, `until-async`, `@open-draft/deferred-promise`; on MSW 3, itself ESM-only, `msw`, `@mswjs/interceptors`, `@msw/url`, `@open-draft/until`, `rettime`, `cookie`, `until-async` and a `setupFiles` polyfill `globalThis.setImmediate ??= require('timers').setImmediate`.

### Four-State Data Component

Loading, success, empty and error - required for every component that fetches:

```tsx
it("renders users", async () => {
  renderWithProviders(<UserList />);
  expect(await screen.findByText("Alice")).toBeInTheDocument();
});

it("shows alert on failure", async () => {
  server.use(
    http.get("/api/users", () => HttpResponse.json(null, { status: 500 })),
  );
  renderWithProviders(<UserList />);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

it("shows empty state", async () => {
  server.use(http.get("/api/users", () => HttpResponse.json([])));
  renderWithProviders(<UserList />);
  expect(await screen.findByText("No users found")).toBeInTheDocument();
});
```

Loading is asserted synchronously before the resolution: `expect(screen.getByRole("status")).toHaveTextContent(/loading/i)` - `role="status"` takes no accessible name from its content, so a `name:` query throws unless the element carries `aria-label`. A behaviour the component cannot exhibit as written (no error surface, a form that cannot validly submit) still gets its test, marked `(fails until <the change it forces>)`, with the component's gap in `Notes:` (in a plan, in that test bullet's parenthetical). A loading text with no `role="status"` is asserted with `getByText` and the missing role goes in `Notes:` (accessibility; in a plan, the same parenthetical). Mutating components additionally cover success feedback (toast, redirect), server rejection, and the in-flight disabled state.

### Custom Hook

```tsx
import { renderHook, act, waitFor } from "@testing-library/react";

it("caps at max", () => {
  const { result } = renderHook(() => useCounter(9, { max: 10 }));
  act(() => result.current.increment());
  act(() => result.current.increment());
  expect(result.current.count).toBe(10);
});

it("fetches user via query", async () => {
  const { result } = renderHook(() => useUser("1"), { wrapper: Providers });
  await waitFor(() => expect(result.current.data?.name).toBe("Alice"));
});
```

### Accessibility

```tsx
// vitest.setup.ts: import * as matchers from "vitest-axe/matchers"; expect.extend(matchers);
// ("vitest-axe/extend-expect" is an empty module in 0.1.0 and registers nothing), and type it - 0.1.0 augments the
// pre-1.0 Vi namespace: declare module "vitest" { interface Matchers<R, T> { toHaveNoViolations(): R } }
// (Vitest 5 declares Assertion<R, T>, so an Assertion<T> augmentation is TS2428 and breaks `next build`)
import { axe } from "vitest-axe";

it("has no a11y violations", async () => {
  const { container } = render(<LoginForm />);
  expect(await axe(container)).toHaveNoViolations();
});
```

Pair axe runs with role-based queries; a violation in axe and a missing role both signal the same gap. "Forms and dialogs" means any surface with an input or a modal.

### Server Components and Server Actions

Vitest and Jest do not render async Server Components: `render(<Page />)` never commits, and `render(await Page())` holds only while nothing below it is async - so test the data function beneath it (`react-server-testing`) and cover the rendered page in Playwright. A synchronous Server Component renders like any component once `server-only` is aliased to an empty module (the `react-server-testing` config alias). A `"use client"` page unwrapping `params` with `use()` renders with `params={Promise.resolve({ id: "1" })}` inside `<Suspense>` when the render is awaited (`await act(async () => { render(...) })` - a bare `render()` leaves the fallback up and `findBy*` times out); assert with `findBy*`.

```tsx
// Server Action: call directly with FormData; mock the DB/auth boundary and stub next/cache
// (+ async next/headers) per react-server-testing - both throw outside a request.
const fd = new FormData();
fd.set("qty", "2");
const result = await submitOrder({}, fd);
expect(result).toEqual({ ok: true });
```

Cover the full RSC + action render/submit cycle in a Playwright E2E - the direct call tests the action's logic, not the server render pipeline. A client component invoking a Server Action in jsdom has no network boundary for MSW to intercept: mock the action at its import (own-module mocks are sanctioned only at server boundaries - data, DB and auth in action tests, the action import here) or cover it in the E2E.

### Timer-driven behavior (debounce / throttle)

```tsx
afterEach(() => vi.useRealTimers());  // inline restore leaks fake timers when an assertion fails first

it("debounces search", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true }); // RTL ends every user-event call with a setTimeout(0); a frozen clock never fires it
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime }); // optional: runs user-event's own delay on the fake clock instead of real time
  render(<Search />);
  await user.type(screen.getByRole("searchbox"), "ab");
  await vi.advanceTimersByTimeAsync(300);          // flush the debounce
  vi.useRealTimers();                              // optional under shouldAdvanceTime; a frozen-clock test without user-event must restore before findBy*
  expect(await screen.findByText("results")).toBeInTheDocument();
});
```

Under Vitest the fake clock needs `shouldAdvanceTime: true` - `advanceTimers` or `delay: null` alone still hang, because RTL's async wrapper waits on a real `setTimeout(0)` after each interaction. With it the fake clock tracks real time, so `waitFor` / `findBy*` poll and time out normally; a frozen clock hangs them to the suite timeout, because RTL auto-advances only Jest fake timers. Advance with `vi.advanceTimersByTimeAsync` to flush deterministically. TanStack Query retries freeze the same way on a frozen clock - scope fake timers to the single test that needs the clock.

### Playwright E2E

Reserve for critical paths (auth, checkout). Query with `getByRole`/`getByLabel`, never CSS selectors.

```tsx
test("user signs in", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("user@example.com");
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).toHaveURL("/dashboard");
});
```

## Output Format

When reviewing a test suite, open with one line `Scope: <files reviewed>`, then emit one finding per issue, ordered by severity:

```
Scope: <files reviewed>

Finding: <one-line summary>{ (pre-existing)}

Category: {Queries | Assertions | Mocking | Coverage | Hooks | Isolation | Accessibility | E2E | Environment}

Severity: {Critical | Major | Minor}

Location: <path>:<line or range>, <path>:<line> for every site of a merged finding - any file read, listed in the brief or not

Evidence: <code excerpt>

Fix: <Pattern name, Rule, or Avoid bullet that governs; name the correction directly when none does> - <one-line correction>

Tally: <N> findings (<C> Critical, <M> Major, <m> Minor) {when at least one finding}

No issues found. {instead, when none}

Notes: {observations outside this skill's concern or unconfirmed from the input - defects in the code under test (a placeholder-only input, an `alert()` error surface) - each naming the owning concern; omit when none}
```

`Environment` covers render-environment and harness defects: an async RSC rendered in jsdom, a missing provider wrapper or `next/navigation` stub, fake timers without `shouldAdvanceTime: true` under user-event or `findBy*` / `waitFor`, a setup file missing an import the suite depends on, and a devDependency the recommended matcher needs but the manifest lacks. `Isolation` covers state crossing tests: shared mutable fixtures, an un-restored fake timer or mock, and flakiness masked by serialized workers, raised retries or `beforeAll` mutation. A stub for a browser API no component in scope calls is not a finding. `Assertions` covers wrong-axis assertions - a CSS class, style value, or internal field standing in for observable behaviour. `Queries` also covers interaction-API drift (`fireEvent` where `user-event` belongs); snapshots fall under `Coverage`, including a CI script passing the update flag (`-u`); a fixed sleep standing in for an awaited outcome is `Assertions`. A component that is not role-queryable is tested through what exists (`getByPlaceholderText` for a placeholder-only input) and its defect goes in `Notes:`.

Merge occurrences of one defect into one finding listing every location - identical means the same defect with the same fix, so three `getByTestId` calls merge while a test-id query and a CSS-selector query stay separate. Emit a finding even when another fix would subsume it, naming the subsuming change in Fix; when both a Pattern and a Rule cover it, cite the Pattern.

Severity rubric:
- **Critical**: test does not exercise the intended behavior, or cannot pass/fail as written (e.g., a `vi.mock` factory reading a top-level binding at evaluation time without `vi.hoisted` - a lazy `() => value` read passes and is not this finding - or a per-test mock that needs `vi.doMock`; renders an async Server Component in jsdom; missing provider wrapper or `next/navigation` stub; a missing setup import or devDependency that disables the matchers the test relies on; fake timers without `shouldAdvanceTime` while the test drives user-event or awaits `findBy*` / `waitFor` (the test hangs to the timeout); unhandled request under `onUnhandledFrame: "error"` (MSW 2: `onUnhandledRequest`); a CI script passing the snapshot update flag, so the snapshot can never fail).
- **Major**: false confidence risk - wrong-axis assertion (CSS class for behavior), `vi.mock` for HTTP modules instead of MSW, hook tested indirectly through a host, missing boundary coverage on a data path, order-coupled tests sharing mutable state (a setup without `server.resetHandlers()` or the `error` unhandled strategy - `onUnhandledFrame` on MSW 3, `onUnhandledRequest` on MSW 2, each ignored by the other major - included), an un-restored fake timer or mock, masked flakiness (`Isolation`), a fixed sleep standing in for an awaited outcome.
- **Minor**: readability / idiom drift - `getByTestId` or `container.querySelector` over `getByRole`, `fireEvent` over `user-event`, `waitFor` wrapping a query that should be `findBy*`, large churn-prone snapshots, a test of third-party library behaviour rather than the integration (`Coverage`).

No Category value is left unscored. Where a value appears in more than one band, the band naming your defect's condition wins; where two fit equally, take the higher. `Accessibility` is Major when a form or dialog carries no axe test, Minor when an axe test exists but role queries are missing. `E2E` is Major when a journey asserts on a timer or a CSS selector rather than a user-visible outcome, Minor otherwise.

When writing tests rather than reviewing them, emit the tests themselves, then this same review envelope over what you wrote; `Scope:` lists the test files written and any setup file edited. A pre-existing setup defect the new tests need fixed is fixed and listed in `Scope:`; one they do not need is a finding marked `(pre-existing)`. When designing a plan, emit:

```
## React Testing Plan

**Stack:** {detected framework}

**Tooling:** {the detected runner, component library and network-mocking layer, kept as found; per missing layer only, recommend Vitest + RTL + MSW (+ Playwright for critical paths) - MSW beside an existing Jest, not a runner swap}

### Tests to Write
- {component|hook|flow}: {state(s) covered} - {level: component | hook | integration | E2E}{ (fails until <change>)}{ (<code-under-test gap>)}

### Infrastructure
- {setup files, MSW handlers, provider helpers the plan requires}

### Out of Scope
- {surface -> owning skill}

### Existing Coverage {when existing tests were assessed}
- {test file}: {adequate | gap - <states or paths missing>}
```

## Avoid

- Large or churn-prone snapshots
- `waitFor` wrapping a synchronous assertion - use `findBy*` for async, `getBy*` for sync
- Serializing workers (`--no-file-parallelism` / `--maxWorkers=1` on Vitest, `--workers=1` on Playwright), a raised `retries` count, or `beforeAll` mutation to paper over flakiness
- Testing third-party library behavior rather than your integration
