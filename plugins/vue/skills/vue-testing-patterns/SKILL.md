---
name: vue-testing-patterns
description: Vue testing patterns - Vitest + Vue Test Utils, component testing, composable testing, @nuxt/test-utils for Nuxt, MSW for API mocking, and Playwright e2e for Vue 3.5+.
metadata:
  category: frontend
  tags: [vue, testing, vitest, vue-test-utils, nuxt-test-utils, msw, playwright, composables]
user-invocable: false
---

# Vue Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing tests for Vue components, composables, and pages
- Setting up testing infrastructure for a Vue or Nuxt project
- Reviewing test quality and coverage
- Choosing between component, integration, and e2e test approaches
- Testing Nuxt-specific features (useFetch, server routes, middleware)

## Rules

- Test behavior, not implementation - assert what the user sees and does, not internal component state
- Use Vue Test Utils `find` and `findAll` by role, label, or text selectors - not internal component structure
- Mock at the network boundary (MSW) - not at the module level
- Every data-fetching component must have tests for loading, success, and error states
- Composables must be tested via mount helper or wrapper component - not by testing internal refs
- Tests must be independent - no shared mutable state, no order dependencies
- Colocate tests with components: `ComponentName.test.ts` next to `ComponentName.vue`

## Patterns

### Test File Structure

```ts
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import UserCard from "./UserCard.vue";

describe("UserCard", () => {
  const defaultProps = {
    user: { id: "1", name: "Alice", email: "alice@example.com" },
  };

  it("renders user name and email", () => {
    const wrapper = mount(UserCard, { props: defaultProps });
    expect(wrapper.find("h2").text()).toBe("Alice");
    expect(wrapper.text()).toContain("alice@example.com");
  });

  it("emits edit event when edit button is clicked", async () => {
    const wrapper = mount(UserCard, { props: defaultProps });
    await wrapper.find("[data-testid='edit-btn']").trigger("click");
    expect(wrapper.emitted("edit")).toEqual([["1"]]);
  });

  it("expands details on click", async () => {
    const wrapper = mount(UserCard, { props: defaultProps });
    expect(wrapper.find(".details").isVisible()).toBe(false);
    await wrapper.find("button").trigger("click");
    expect(wrapper.find(".details").isVisible()).toBe(true);
  });
});
```

### Component Testing with Plugins

Wrap components that need Pinia, Vue Router, or other plugins:

```ts
import { createTestingPinia } from "@pinia/testing";
import { mount } from "@vue/test-utils";

function mountWithPlugins(component: any, options: any = {}) {
  return mount(component, {
    global: {
      plugins: [
        createTestingPinia({
          createSpy: vi.fn,
          initialState: options.initialState,
        }),
      ],
      stubs: options.stubs ?? {},
    },
    ...options,
  });
}

// Usage:
it("renders cart items from store", () => {
  const wrapper = mountWithPlugins(CartView, {
    initialState: {
      cart: { items: [{ id: "1", name: "Widget", price: 10, quantity: 2 }] },
    },
  });
  expect(wrapper.text()).toContain("Widget");
  expect(wrapper.text()).toContain("$20");
});
```

### MSW Integration

```ts
// test/mocks/handlers.ts
import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/products", () => {
    return HttpResponse.json([
      { id: "1", name: "Widget", price: 10 },
      { id: "2", name: "Gadget", price: 20 },
    ]);
  }),

  http.post("/api/products", async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: "3", ...body }, { status: 201 });
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

// In tests - override for specific scenarios:
it("shows error state when API fails", async () => {
  server.use(
    http.get("/api/products", () => {
      return HttpResponse.json({ message: "Server error" }, { status: 500 });
    }),
  );

  const wrapper = mount(ProductList);
  await flushPromises();
  expect(wrapper.find("[role='alert']").text()).toContain("Failed to load");
});
```

### Three-State Testing for Data Components

Every component that fetches data must test:

```ts
import { flushPromises } from "@vue/test-utils";

describe("ProductList", () => {
  it("shows loading skeleton initially", () => {
    const wrapper = mount(ProductList);
    expect(wrapper.find(".skeleton").exists()).toBe(true);
  });

  it("renders products on success", async () => {
    const wrapper = mount(ProductList);
    await flushPromises();
    expect(wrapper.text()).toContain("Widget");
    expect(wrapper.text()).toContain("Gadget");
  });

  it("shows error state with retry button on failure", async () => {
    server.use(
      http.get("/api/products", () => HttpResponse.json(null, { status: 500 })),
    );
    const wrapper = mount(ProductList);
    await flushPromises();
    expect(wrapper.find("[role='alert']").exists()).toBe(true);
    expect(wrapper.find("button").text()).toContain("Retry");
  });

  it("shows empty state when no products exist", async () => {
    server.use(http.get("/api/products", () => HttpResponse.json([])));
    const wrapper = mount(ProductList);
    await flushPromises();
    expect(wrapper.text()).toContain("No products found");
  });
});
```

### Composable Testing

```ts
import { describe, it, expect } from "vitest";
import { ref } from "vue";
import { mount } from "@vue/test-utils";
import { useCounter } from "./useCounter";

// Test composable via wrapper component
function withSetup<T>(composable: () => T) {
  let result: T;
  mount({
    setup() {
      result = composable();
      return () => null;
    },
  });
  return result!;
}

describe("useCounter", () => {
  it("initializes with default value", () => {
    const { count } = withSetup(() => useCounter(0));
    expect(count.value).toBe(0);
  });

  it("increments the count", () => {
    const { count, increment } = withSetup(() => useCounter(0));
    increment();
    expect(count.value).toBe(1);
  });

  it("respects max value", () => {
    const { count, increment } = withSetup(() => useCounter(9, { max: 10 }));
    increment();
    increment();
    expect(count.value).toBe(10);
  });
});
```

### Testing Pinia Store Interactions

```ts
import { createTestingPinia } from "@pinia/testing";

describe("AddToCartButton", () => {
  it("calls addItem on store when clicked", async () => {
    const wrapper = mount(AddToCartButton, {
      props: { product: { id: "1", name: "Widget", price: 10 } },
      global: {
        plugins: [createTestingPinia({ createSpy: vi.fn })],
      },
    });

    const cart = useCartStore();
    await wrapper.find("button").trigger("click");

    expect(cart.addItem).toHaveBeenCalledWith(
      expect.objectContaining({ id: "1" }),
    );
  });

  it("shows updated count from store", () => {
    const wrapper = mount(CartBadge, {
      global: {
        plugins: [
          createTestingPinia({
            createSpy: vi.fn,
            initialState: { cart: { items: [{ id: "1", quantity: 3 }] } },
          }),
        ],
      },
    });

    expect(wrapper.text()).toContain("3");
  });
});
```

### Nuxt Testing with @nuxt/test-utils

```ts
import { describe, it, expect } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import ProductPage from "~/pages/products/[id].vue";

describe("ProductPage", () => {
  it("renders product details", async () => {
    const wrapper = await mountSuspended(ProductPage, {
      route: "/products/1",
    });
    expect(wrapper.text()).toContain("Widget");
  });
});
```

```ts
// Testing server routes
import { describe, it, expect } from "vitest";
import { $fetch } from "@nuxt/test-utils";

describe("GET /api/products", () => {
  it("returns product list", async () => {
    const products = await $fetch("/api/products");
    expect(products).toBeInstanceOf(Array);
    expect(products[0]).toHaveProperty("name");
  });
});
```

### Form Testing

```ts
describe("CreateProductForm", () => {
  it("submits valid form data", async () => {
    const wrapper = mount(CreateProductForm);

    await wrapper.find("input[name='name']").setValue("New Widget");
    await wrapper.find("input[name='price']").setValue("25");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Product created");
  });

  it("shows validation errors for empty required fields", async () => {
    const wrapper = mount(CreateProductForm);

    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Name is required");
    expect(wrapper.text()).toContain("Price is required");
  });

  it("disables submit button during submission", async () => {
    const wrapper = mount(CreateProductForm);

    await wrapper.find("input[name='name']").setValue("New Widget");
    await wrapper.find("input[name='price']").setValue("25");
    await wrapper.find("form").trigger("submit");

    expect(
      wrapper.find("button[type='submit']").attributes("disabled"),
    ).toBeDefined();
  });
});
```

### Playwright E2E (Critical Paths)

```ts
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
## Vue Testing Plan

**Stack:** {detected framework}
**Test framework:** Vitest
**Component testing:** Vue Test Utils
**API mocking:** MSW
**E2E:** Playwright

### Test Coverage

| Component/Composable | Unit | Component | Integration | E2E      |
| -------------------- | ---- | --------- | ----------- | -------- |
| {name}               | {Y/N}| {Y/N}    | {Y/N}       | {Y/N}    |

### Tests to Write

- {component}: {test description} ({level})
- {composable}: {test description} ({level})

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if testing is adequate - do not omit this section silently}
```

## Avoid

- Testing internal component state (ref values, reactive properties)
- Module-level mocking (`vi.mock`) for API calls (use MSW for network-level mocking)
- Testing third-party library behavior (test your integration, not their code)
- Snapshot testing large or frequently changing component trees
- Tests that depend on execution order or share mutable state
- Skipping loading, error, and empty state tests for data-fetching components
- Testing style values or CSS classes (test visible behavior instead)
- Using `wrapper.vm` to access internal component state in tests
