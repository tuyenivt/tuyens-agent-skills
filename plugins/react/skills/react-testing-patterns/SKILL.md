---
name: react-testing-patterns
description: React testing patterns - Vitest + React Testing Library, component testing, hook testing, MSW for API mocking, Server Component testing, and Playwright e2e for React 19+.
metadata:
  category: frontend
  tags: [react, testing, vitest, react-testing-library, msw, playwright, hooks]
user-invocable: false
---

# React Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing tests for React components, hooks, and pages
- Setting up testing infrastructure for a React project
- Reviewing test quality and coverage
- Choosing between component, integration, and e2e test approaches
- Testing Server Components and Server Actions (Next.js)

## Rules

- Test behavior, not implementation - assert what the user sees and does, not internal component state
- Use Testing Library queries by role, label, and text - not test IDs or CSS selectors as primary strategy
- Mock at the network boundary (MSW) - not at the module level
- Every data-fetching component must have tests for loading, success, and error states
- Custom hooks must be tested via `renderHook` - not by testing internal behavior through components
- Tests must be independent - no shared mutable state, no order dependencies
- Colocate tests with components: `ComponentName.test.tsx` next to `ComponentName.tsx`

## Patterns

### Test File Structure

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { UserCard } from "./UserCard";

describe("UserCard", () => {
  const defaultProps = {
    user: { id: "1", name: "Alice", email: "alice@example.com" },
  };

  it("renders user name and email", () => {
    render(<UserCard {...defaultProps} />);
    expect(screen.getByRole("heading", { name: "Alice" })).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("calls onEdit when edit button is clicked", async () => {
    const onEdit = vi.fn();
    const user = userEvent.setup();
    render(<UserCard {...defaultProps} onEdit={onEdit} />);

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalledWith("1");
  });

  it("expands details on click", async () => {
    const user = userEvent.setup();
    render(<UserCard {...defaultProps} />);

    expect(screen.queryByText("alice@example.com")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("alice@example.com")).toBeVisible();
  });
});
```

### Component Testing with Providers

Wrap components that need context providers:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderWithProviders(ui: ReactElement) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

// Usage:
it("renders user list", async () => {
  renderWithProviders(<UserList />);
  expect(await screen.findByText("Alice")).toBeInTheDocument();
});
```

### MSW Integration

```tsx
// test/mocks/handlers.ts
import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/users", () => {
    return HttpResponse.json([
      { id: "1", name: "Alice" },
      { id: "2", name: "Bob" },
    ]);
  }),

  http.post("/api/users", async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: "3", ...body }, { status: 201 });
  }),

  http.get("/api/users/:id", ({ params }) => {
    return HttpResponse.json({ id: params.id, name: "Alice" });
  }),
];

// test/mocks/server.ts
import { setupServer } from "msw/node";
import { handlers } from "./handlers";
export const server = setupServer(...handlers);

// vitest.setup.ts
import { server } from "./test/mocks/server";
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// In tests - override handlers for specific scenarios:
it("shows error state when API fails", async () => {
  server.use(
    http.get("/api/users", () => {
      return HttpResponse.json({ message: "Server error" }, { status: 500 });
    }),
  );

  renderWithProviders(<UserList />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Failed to load users",
  );
});
```

### Three-State Testing for Data Components

Every component that fetches data must test:

```tsx
describe("UserList", () => {
  it("shows loading skeleton initially", () => {
    renderWithProviders(<UserList />);
    expect(
      screen.getByRole("status", { name: /loading/i }),
    ).toBeInTheDocument();
  });

  it("renders users on success", async () => {
    renderWithProviders(<UserList />);
    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("shows error state with retry button on failure", async () => {
    server.use(
      http.get("/api/users", () => HttpResponse.json(null, { status: 500 })),
    );
    renderWithProviders(<UserList />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows empty state when no users exist", async () => {
    server.use(http.get("/api/users", () => HttpResponse.json([])));
    renderWithProviders(<UserList />);
    expect(await screen.findByText("No users found")).toBeInTheDocument();
  });
});
```

### Custom Hook Testing

```tsx
import { renderHook, act, waitFor } from "@testing-library/react";
import { useCounter } from "./useCounter";

describe("useCounter", () => {
  it("initializes with default value", () => {
    const { result } = renderHook(() => useCounter(0));
    expect(result.current.count).toBe(0);
  });

  it("increments the count", () => {
    const { result } = renderHook(() => useCounter(0));
    act(() => result.current.increment());
    expect(result.current.count).toBe(1);
  });

  it("respects max value", () => {
    const { result } = renderHook(() => useCounter(9, { max: 10 }));
    act(() => result.current.increment());
    act(() => result.current.increment());
    expect(result.current.count).toBe(10); // capped at max
  });
});

// Hook with async behavior (e.g., wrapping TanStack Query)
describe("useUser", () => {
  it("returns user data", async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={createTestQueryClient()}>
        {children}
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useUser("1"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.name).toBe("Alice");
  });
});
```

### Form Testing

```tsx
describe("CreateUserForm", () => {
  it("submits valid form data", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CreateUserForm />);

    await user.type(screen.getByLabelText("Name"), "Charlie");
    await user.type(screen.getByLabelText("Email"), "charlie@example.com");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("User created")).toBeInTheDocument();
  });

  it("shows validation errors for empty required fields", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CreateUserForm />);

    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(screen.getByText("Email is required")).toBeInTheDocument();
  });

  it("disables submit button during submission", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CreateUserForm />);

    await user.type(screen.getByLabelText("Name"), "Charlie");
    await user.type(screen.getByLabelText("Email"), "charlie@example.com");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(screen.getByRole("button", { name: "Creating..." })).toBeDisabled();
  });
});
```

### Accessibility Testing in Component Tests

```tsx
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

it("has no accessibility violations", async () => {
  const { container } = render(<LoginForm />);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

### Playwright E2E (Critical Paths)

```tsx
// e2e/auth.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("user can sign in and see dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("user@example.com");
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page).toHaveURL("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible();
  });

  test("shows error for invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("wrong@example.com");
    await page.getByLabel("Password").fill("wrong");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByRole("alert")).toContainText("Invalid credentials");
  });
});
```

## Output Format

Consuming workflow skills depend on this structure.

```
## React Testing Plan

**Stack:** {detected framework}
**Test framework:** {Vitest | Jest}
**Component testing:** React Testing Library
**API mocking:** MSW
**E2E:** Playwright

### Test Coverage

| Component/Hook     | Unit | Component | Integration | E2E      |
| ------------------- | ---- | --------- | ----------- | -------- |
| {name}              | {Y/N}| {Y/N}    | {Y/N}       | {Y/N}    |

### Tests to Write

- {component}: {test description} ({level})
- {hook}: {test description} ({level})

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if testing is adequate - do not omit this section silently}
```

## Avoid

- Testing internal component state (useState values, useRef values)
- Using `getByTestId` as the primary query strategy (prefer role, label, text)
- Module-level mocking (`vi.mock`) for API calls (use MSW for network-level mocking)
- Testing third-party library behavior (test your integration, not their code)
- Snapshot testing large or frequently changing component trees
- Tests that depend on execution order or share mutable state
- Skipping loading, error, and empty state tests for data-fetching components
- Testing style values or CSS classes (test visible behavior instead)
