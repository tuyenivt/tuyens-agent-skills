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
// Compose every provider the tree reads: query client, store, router (MemoryRouter / createMemoryRouter).
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
export const renderWithProviders = (ui: ReactElement) => render(ui, { wrapper: Providers });
```

Reuse `renderWithProviders` for components that read a provider; plain `render` for those that read none. Hooks take the component itself: `renderHook(() => useUser("1"), { wrapper: Providers })` - a render helper returns a `RenderResult`, not JSX, and cannot be a `wrapper`.

### MSW Setup

```tsx
// test/mocks/handlers.ts
import { http, HttpResponse } from "msw";
export const handlers = [
  http.get("/api/users", () =>
    HttpResponse.json([{ id: "1", name: "Alice" }]),
  ),
];

// vitest config: test: { environment: "jsdom", globals: true, setupFiles: ["./vitest.setup.ts"] } -
// without globals, import it/expect/vi from "vitest" and RTL's automatic cleanup stops running.
// vitest.setup.ts
import "@testing-library/jest-dom/vitest";   // without this every toBeInTheDocument() throws
import { setupServer } from "msw/node";
import { handlers } from "./test/mocks/handlers";
export const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

Override per test with `server.use(...)`; never edit the global handler array. Module-singleton stores reset in `afterEach` too (Zustand `useStore.setState(initialState, true)`; Redux through a `makeStore()` factory per test). jsdom has no `IntersectionObserver` or `ResizeObserver`: stub them on `globalThis` in the setup file.

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

Loading is asserted synchronously before the resolution: `expect(screen.getByRole("status")).toHaveTextContent(/loading/i)` - `role="status"` takes no accessible name from its content, so a `name:` query throws unless the element carries `aria-label`. A component with no observable error surface still gets its error test, marked `(fails until <the component renders an error state>)`, with the component's gap in `Notes:` (in a plan, in that test bullet's parenthetical). Mutating components additionally cover success feedback (toast, redirect), server rejection, and the in-flight disabled state.

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
// vitest.setup.ts: import "vitest-axe/extend-expect"; - vitest-axe 0.1.0 augments the pre-1.0 Vi namespace,
// so on Vitest 1+ also declare: declare module "vitest" { interface Assertion<T = any> { toHaveNoViolations(): T } }
import { axe } from "vitest-axe";

it("has no a11y violations", async () => {
  const { container } = render(<LoginForm />);
  expect(await axe(container)).toHaveNoViolations();
});
```

Pair axe runs with role-based queries; a violation in axe and a missing role both signal the same gap. "Forms and dialogs" means any surface with an input or a modal.

### Server Components and Server Actions

jsdom cannot render an async Server Component - don't `render(<RSC/>)`. Two paths:

```tsx
// Async RSC: call it as a function, assert on the returned tree (mock the data boundary).
const ui = await OrderSummary({ orderId: "1" });
render(ui);
expect(screen.getByText("Total: $42")).toBeInTheDocument();

// Server Action: import and call directly with FormData; mock the DB/auth boundary.
const fd = new FormData();
fd.set("qty", "2");
const result = await submitOrder({}, fd);
expect(result).toEqual({ ok: true });
```

Prefer covering the full RSC + action render/submit cycle in a Playwright E2E - the function-call approach tests logic, not the server render pipeline. A client component invoking a Server Action in jsdom has no network boundary for MSW to intercept: mock the action at its import (own-module mocks are sanctioned only at server boundaries - data, DB and auth in RSC and action tests, the action import here) or cover it in the E2E.

### Timer-driven behavior (debounce / throttle)

```tsx
afterEach(() => vi.useRealTimers());  // inline restore leaks fake timers when an assertion fails first

it("debounces search", async () => {
  vi.useFakeTimers();
  // user-event's delay waits on the (now faked) global setTimeout; wire it to the fake clock or it hangs.
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<Search />);
  await user.type(screen.getByRole("searchbox"), "ab");
  await vi.advanceTimersByTimeAsync(300);          // flush the debounce
  vi.useRealTimers();                              // restore before any findBy*
  expect(await screen.findByText("results")).toBeInTheDocument();
});
```

Under fake timers pass `advanceTimers` (or `delay: null`) - without either, `userEvent` waits on a clock that never moves. Under Vitest, `waitFor` does not detect fake timers (its auto-advance path checks for Jest), so its poll interval and timeout run on the frozen clock and a `findBy*` hangs to the suite timeout instead of failing. Advance the clock to flush the timer, restore real timers, then make the async assertion. TanStack Query retries freeze the same way - scope fake timers to the single test that needs the clock.

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

Finding: <one-line summary>
Category: {Queries | Assertions | Mocking | Coverage | Hooks | Isolation | Accessibility | E2E | Environment}
Severity: {Critical | Major | Minor}
Location: <path>:<line or range>, <path>:<line> for every site of a merged finding - any file read, listed in the brief or not
Evidence: <code excerpt>
Fix: <Pattern name, Rule, or Avoid bullet that governs; name the correction directly when none does> - <one-line correction>

Tally: <N> findings (<C> Critical, <M> Major, <m> Minor)

Notes: <defects in the code under test rather than the tests - a placeholder-only input, an `alert()` error surface - each naming its concern; omit when none>
```

`Environment` covers render-environment and harness defects: an async RSC rendered in jsdom, a missing provider wrapper, fake timers without `advanceTimers` wiring, a setup file missing an import the suite depends on, and a devDependency the recommended matcher or query needs but the manifest lacks. `Assertions` covers wrong-axis assertions - a CSS class, style value, or internal field standing in for observable behaviour. `Queries` also covers interaction-API drift (`fireEvent` where `user-event` belongs); snapshots fall under `Coverage`, including a CI script passing the update flag (`-u`); a fixed sleep standing in for an awaited outcome is `Assertions`. A component that is not role-queryable is tested through what exists (`getByPlaceholderText` for a placeholder-only input) and its defect goes in `Notes:`.

Merge occurrences of one defect into one finding listing every location - identical means the same defect with the same fix, so three `getByTestId` calls merge while a test-id query and a CSS-selector query stay separate. Emit a finding even when another fix would subsume it, naming the subsuming change in Fix; when both a Pattern and a Rule cover it, cite the Pattern. Close with `Tally: <N> findings (<C> Critical, <M> Major, <m> Minor)` and the `Notes:` line when one applies; a clean review emits `Scope:` plus `No issues found.`, with `Notes:` after it when one applies.

Severity rubric:
- **Critical**: test does not exercise the intended behavior, or cannot pass/fail as written (e.g., a `vi.mock` factory closing over a top-level binding without `vi.hoisted`, or a per-test mock that needs `vi.doMock`; renders an async Server Component in jsdom; missing provider wrapper; a missing setup import that disables the matchers the test relies on; unhandled request under `onUnhandledRequest: "error"`; a CI script passing the snapshot update flag, so the snapshot can never fail).
- **Major**: false confidence risk - wrong-axis assertion (CSS class for behavior), `vi.mock` for HTTP modules instead of MSW, hook tested indirectly through a host, missing boundary coverage on a data path, order-coupled tests sharing mutable state (a setup without `server.resetHandlers()` or `onUnhandledRequest: "error"` included), a fixed sleep standing in for an awaited outcome.
- **Minor**: readability / idiom drift - `getByTestId` over `getByRole`, `fireEvent` over `user-event`, `waitFor` wrapping a query that should be `findBy*`, large churn-prone snapshots.

No Category value is left unscored. Where a value appears in more than one band, the band naming your defect's condition wins; where two fit equally, take the higher. `Accessibility` is Major when a form or dialog carries no axe test, Minor when an axe test exists but role queries are missing. `E2E` is Major when a journey asserts on a timer or a CSS selector rather than a user-visible outcome, Minor otherwise. `Fix:` cites a Pattern, a Rule, or an `Avoid` bullet - whichever governs; when none does, name the correction directly.

When writing tests rather than reviewing them, emit the tests themselves, then this same review envelope over what you wrote (or `Scope:` plus `No issues found.`). When designing a plan, emit:

```
## React Testing Plan

**Stack:** {detected framework}

**Tooling:** {the detected runner, component library and network-mocking layer; recommend Vitest + RTL + MSW (+ Playwright for critical paths) only where nothing is in place}

### Tests to Write
- {component|hook|flow}: {state(s) covered} - {level: component | hook | integration | E2E}

### Infrastructure
- {setup files, MSW handlers, provider helpers the plan requires}

### Out of Scope
- {surface -> owning skill}

### No Issues Found
{When the plan assessed existing coverage and found it adequate, say so explicitly. Omit for a greenfield plan.}
```

## Avoid

- Asserting on internal state, refs, CSS classes, or style values
- `vi.mock` for HTTP modules - intercept at MSW instead
- Large or churn-prone snapshots
- `waitFor` wrapping a synchronous assertion - use `findBy*` for async, `getBy*` for sync
- Serializing workers (`--no-file-parallelism` / `--maxWorkers=1` on Vitest, `--workers=1` on Playwright) a raised `retry` count, or `beforeAll` mutation to paper over flakiness
- Testing third-party library behavior rather than your integration
