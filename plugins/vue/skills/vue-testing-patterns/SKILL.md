---
name: vue-testing-patterns
description: Vue 3.5 testing: Vitest, Vue Test Utils, composables, Pinia, @nuxt/test-utils, MSW network mocking, Playwright E2E.
metadata:
  category: frontend
  tags: [vue, testing, vitest, vue-test-utils, nuxt-test-utils, msw, playwright, composables]
user-invocable: false
---

# Vue Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing tests for Vue components, composables, pages, or server routes
- Setting up testing infrastructure for a Vue or Nuxt project
- Choosing between component, integration, and E2E levels

## Rules

- Assert what the user sees and does; never `wrapper.vm`, internal refs, CSS values, or snapshots of large trees.
- Select by role, label, text, or `data-testid`; not by component internals.
- Mock at the network boundary with MSW; do not `vi.mock` API modules.
- Data-fetching components require tests for loading, success, error, and empty states.
- Test composables through a wrapper component, not by inspecting returned refs in isolation.
- Tests must be independent: no shared mutable state, no order dependencies, reset MSW handlers per test.
- Colocate: `ComponentName.test.ts` next to `ComponentName.vue`.

## Patterns

### Component test shape

```ts
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import UserCard from "./UserCard.vue";

describe("UserCard", () => {
  const props = { user: { id: "1", name: "Alice", email: "alice@example.com" } };

  it("renders user info", () => {
    const wrapper = mount(UserCard, { props });
    expect(wrapper.get("h2").text()).toBe("Alice");
    expect(wrapper.text()).toContain("alice@example.com");
  });

  it("emits edit with user id when edit clicked", async () => {
    const wrapper = mount(UserCard, { props });
    await wrapper.get("[data-testid='edit-btn']").trigger("click");
    expect(wrapper.emitted("edit")).toEqual([["1"]]);
  });
});
```

### Mounting with plugins (Pinia, Router)

Wrap once; pass `initialState` per test. Use `createSpy: vi.fn` so store actions become spies.

```ts
import { createTestingPinia } from "@pinia/testing";
import { mount } from "@vue/test-utils";
import { vi } from "vitest";

export function mountWithPlugins(component: any, options: any = {}) {
  return mount(component, {
    global: {
      plugins: [createTestingPinia({ createSpy: vi.fn, initialState: options.initialState })],
      stubs: options.stubs,
    },
    props: options.props,
  });
}

it("calls store action on click", async () => {
  const wrapper = mountWithPlugins(AddToCartButton, {
    props: { product: { id: "1", name: "Widget", price: 10 } },
  });
  const cart = useCartStore();
  await wrapper.get("button").trigger("click");
  expect(cart.addItem).toHaveBeenCalledWith(expect.objectContaining({ id: "1" }));
});
```

### MSW setup

```ts
// test/mocks/server.ts
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

export const server = setupServer(
  http.get("/api/products", () =>
    HttpResponse.json([{ id: "1", name: "Widget", price: 10 }]),
  ),
);

// vitest.setup.ts
import { server } from "./test/mocks/server";
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

Override per scenario with `server.use(...)`; never reach into the module.

### Four-state data component tests

```ts
import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { server } from "../test/mocks/server";

describe("ProductList", () => {
  it("shows skeleton while loading", () => {
    expect(mount(ProductList).find("[data-testid='skeleton']").exists()).toBe(true);
  });

  it("renders products on success", async () => {
    const wrapper = mount(ProductList);
    await flushPromises();
    expect(wrapper.text()).toContain("Widget");
  });

  it("shows alert and retry on failure", async () => {
    server.use(http.get("/api/products", () => HttpResponse.json(null, { status: 500 })));
    const wrapper = mount(ProductList);
    await flushPromises();
    expect(wrapper.get("[role='alert']").exists()).toBe(true);
    expect(wrapper.get("button").text()).toContain("Retry");
  });

  it("shows empty state when list is empty", async () => {
    server.use(http.get("/api/products", () => HttpResponse.json([])));
    const wrapper = mount(ProductList);
    await flushPromises();
    expect(wrapper.text()).toContain("No products");
  });
});
```

### Composables

Mount inside a throwaway component so the setup context exists.

```ts
import { mount } from "@vue/test-utils";
import { useCounter } from "./useCounter";

function withSetup<T>(composable: () => T): T {
  let result!: T;
  mount({ setup() { result = composable(); return () => null; } });
  return result;
}

it("respects max", () => {
  const { count, increment } = withSetup(() => useCounter(9, { max: 10 }));
  increment(); increment();
  expect(count.value).toBe(10);
});
```

### Nuxt (@nuxt/test-utils)

```ts
// runtime (in-process): mount pages/components with Nuxt context
import { mountSuspended } from "@nuxt/test-utils/runtime";

it("renders product page", async () => {
  const wrapper = await mountSuspended(ProductPage, { route: "/products/1" });
  expect(wrapper.text()).toContain("Widget");
});

// server routes use the e2e harness: `import { setup, $fetch } from "@nuxt/test-utils/e2e"`
// with `await setup({ server: true })` in describe - distinct from the runtime helper above.
```

### Playwright E2E (critical paths only)

```ts
import { test, expect } from "@playwright/test";

test("user signs in and lands on dashboard", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("user@example.com");
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).toHaveURL("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});
```

## Output Format

```
## Vue Testing Plan

**Stack:** {detected framework}
**Component:** Vitest + Vue Test Utils
**Network mocking:** MSW
**E2E:** Playwright (critical paths)

### Coverage

| Target | Component | Integration | E2E |
| ------ | --------- | ----------- | --- |
| {name} | {Y/N}     | {Y/N}       | {Y/N} |

### Tests to Write

- {target}: {scenario} ({level})

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if testing is adequate; do not omit this section.}
```

## Avoid

- `wrapper.vm` / internal refs in assertions.
- Selecting by CSS class for styling intent; asserting style values.
- Snapshots of large or frequently-changing trees.
- Testing third-party library internals instead of your integration.
