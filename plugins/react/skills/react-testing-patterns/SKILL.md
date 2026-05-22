---
name: react-testing-patterns
description: "React 19 testing: Vitest + RTL, user-event, MSW network mocking, hook tests via renderHook, three-state data tests, axe a11y."
metadata:
  category: frontend
  tags: [react, testing, vitest, react-testing-library, msw, playwright, hooks]
user-invocable: false
---

# React Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing tests for React components, hooks, and pages
- Setting up Vitest + RTL + MSW infrastructure
- Choosing between component, integration, and E2E coverage

## Rules

- Assert what the user sees and does; never read `useState`, refs, or class names
- Query by role/label/text; `getByTestId` is a last resort
- Mock HTTP at the network boundary with MSW; do not `vi.mock` API modules
- Data-fetching components require loading, success, error, and empty tests
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
function renderWithProviders(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
```

Reuse this helper for every test that needs context. Hooks pass it as `{ wrapper }` to `renderHook`.

### MSW Setup

```tsx
// test/mocks/handlers.ts
import { http, HttpResponse } from "msw";
export const handlers = [
  http.get("/api/users", () =>
    HttpResponse.json([{ id: "1", name: "Alice" }]),
  ),
];

// vitest.setup.ts
import { setupServer } from "msw/node";
import { handlers } from "./test/mocks/handlers";
export const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

Override per test with `server.use(...)`; never edit the global handler array.

### Three-State Data Component

Required for every component that fetches:

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

Loading is asserted synchronously before the resolution: `expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument()`.

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
  const { result } = renderHook(() => useUser("1"), {
    wrapper: ({ children }) => renderWithProviders(<>{children}</>),
  });
  await waitFor(() => expect(result.current.data?.name).toBe("Alice"));
});
```

### Accessibility

```tsx
import { axe, toHaveNoViolations } from "jest-axe";
expect.extend(toHaveNoViolations);

it("has no a11y violations", async () => {
  const { container } = render(<LoginForm />);
  expect(await axe(container)).toHaveNoViolations();
});
```

Pair axe runs with role-based queries; a violation in axe and a missing role both signal the same gap.

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

When reviewing a test suite, emit one finding per issue:

```
Finding: <one-line summary>
Category: {Queries | Mocking | Coverage | Hooks | Isolation | Accessibility | E2E}
Severity: {Critical | Major | Minor}
Location: <path>:<line>
Evidence: <code excerpt>
Fix: <pattern name from this skill> - <one-line correction>
```

When designing a plan, emit:

```
## React Testing Plan

**Stack:** {detected framework}
**Tooling:** Vitest + RTL + MSW (+ Playwright for critical paths)

### Tests to Write
- {component|hook}: {state(s) covered} - {level}

### No Issues Found
{State explicitly if testing is adequate}
```

## Avoid

- Asserting on internal state, refs, CSS classes, or style values
- `vi.mock` for HTTP modules - intercept at MSW instead
- Large or churn-prone snapshots
- `waitFor` wrapping a synchronous assertion - use `findBy*` for async, `getBy*` for sync
- `--test-threads=1` or `beforeAll` mutation to paper over flakiness
- Testing third-party library behavior rather than your integration
