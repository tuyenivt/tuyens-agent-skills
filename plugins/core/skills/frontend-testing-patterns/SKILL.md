---
name: frontend-testing-patterns
description: Frontend testing patterns - component testing, integration testing, e2e with Playwright/Cypress, API mocking with MSW, snapshot discipline. Adapts to detected stack and test framework.
metadata:
  category: frontend
  tags: [frontend, testing, playwright, cypress, msw, vitest, jest, multi-stack]
user-invocable: false
---

# Frontend Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Planning test strategy for frontend features
- Reviewing existing test coverage and quality
- Setting up testing infrastructure for a frontend project
- Choosing between testing approaches for a specific component or feature

## Rules

- Test behavior, not implementation - tests should assert what the user sees and does, not internal component state
- Use Testing Library queries that reflect how users find elements (by role, label, text) - not test IDs or CSS selectors as primary strategy
- Every test must be independent - no shared mutable state between tests, no order dependencies
- Mock at the network boundary (MSW or HTTP interceptors), not at the module level - module mocks hide integration bugs. **Exception:** Module-level mocking is appropriate for third-party SDKs that render their own UI in iframes (Stripe Elements, Google Maps, reCAPTCHA) and for browser APIs without test equivalents (IntersectionObserver, ResizeObserver, navigator.geolocation)
- Snapshot tests are only for regression detection on stable, leaf components - never snapshot large component trees or frequently changing UI
- E2E tests cover critical user journeys only - do not duplicate unit/integration coverage in e2e

---

## Patterns

### Testing Pyramid for Frontend

| Level       | What It Tests                       | Tools                                      | Speed  | Count    |
| ----------- | ----------------------------------- | ------------------------------------------ | ------ | -------- |
| Unit        | Pure functions, utilities, hooks    | Vitest / Jest                              | Fast   | Many     |
| Component   | Single component rendering + events | Testing Library + Vitest/Jest              | Fast   | Many     |
| Integration | Multi-component flows with state    | Testing Library + MSW + Vitest/Jest        | Medium | Moderate |
| E2E         | Full user journeys in browser       | Playwright (primary) / Cypress (secondary) | Slow   | Few      |

### Component Testing

**Bad** - Testing implementation details:

```
// Testing internal state and method calls
const wrapper = mount(UserCard)
expect(wrapper.vm.isExpanded).toBe(false)
wrapper.vm.toggleExpand()
expect(wrapper.vm.isExpanded).toBe(true)
```

Problem: Test breaks when internal implementation changes, even if behavior is identical.

**Good** - Testing user-visible behavior:

```
// Testing what the user sees and does
render(<UserCard user={mockUser} />)
expect(screen.getByRole("heading", { name: "Alice" })).toBeInTheDocument()

await userEvent.click(screen.getByRole("button", { name: "Show details" }))
expect(screen.getByText("alice@example.com")).toBeVisible()
```

### Query Priority

Use queries that most closely resemble how users interact with the UI:

| Priority | Query Type             | When to Use                                    |
| -------- | ---------------------- | ---------------------------------------------- |
| 1        | `getByRole`            | Any element with an ARIA role (buttons, links) |
| 2        | `getByLabelText`       | Form inputs                                    |
| 3        | `getByPlaceholderText` | Inputs without visible labels (last resort)    |
| 4        | `getByText`            | Non-interactive elements                       |
| 5        | `getByDisplayValue`    | Filled form inputs                             |
| 6        | `getByTestId`          | Only when no semantic query works              |

### API Mocking with MSW

Mock at the network layer so components use real fetch/axios code paths:

**Bad** - Module-level mocking:

```
// Mocking the fetch function directly
jest.mock("../api/users", () => ({
  getUsers: jest.fn().mockResolvedValue([{ id: 1, name: "Alice" }])
}))
```

Problem: Skips HTTP client configuration, interceptors, error handling, serialization.

**Good** - Network-level mocking with MSW:

```
// MSW handler - intercepts actual network requests
const handlers = [
  http.get("/api/users", () => {
    return HttpResponse.json([{ id: 1, name: "Alice" }])
  }),
  http.get("/api/users/:id", ({ params }) => {
    return HttpResponse.json({ id: params.id, name: "Alice" })
  }),
]

// Test uses real component code paths
render(<UserList />)
expect(await screen.findByText("Alice")).toBeInTheDocument()
```

### Error and Loading State Testing

Every component that fetches data must test three states:

1. **Loading**: Verify loading indicator appears
2. **Success**: Verify data renders correctly
3. **Error**: Verify error message and retry mechanism

```
// Error state test
server.use(
  http.get("/api/users", () => {
    return HttpResponse.json({ message: "Server error" }, { status: 500 })
  })
)
render(<UserList />)
expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load users")
expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument()
```

### Snapshot Discipline

**When snapshots are appropriate:**

- Stable, leaf UI components (icons, badges, formatted display values)
- Regression detection after a component is finalized

**When snapshots are harmful:**

- Large component trees (any change anywhere breaks the snapshot)
- Components with dynamic content (dates, IDs, random values)
- Components under active development (constant meaningless snapshot updates)

**Rule:** If a snapshot test breaks, developers must read and understand the diff before updating. If they blindly run `--update-snapshot`, the test provides zero value.

### E2E Testing Strategy

E2E tests cover critical paths only - the happy paths that generate revenue or block users:

| Test Category  | Examples                                        |
| -------------- | ----------------------------------------------- |
| Authentication | Sign up, sign in, password reset, sign out      |
| Core workflows | Create order, process payment, submit form      |
| Navigation     | Landing to checkout flow, deep link resolution  |
| Error recovery | Network failure during checkout, session expiry |

E2E tests should:

- Use Playwright (preferred) with page object pattern
- Run against a stable test environment with seeded data
- Avoid testing visual details covered by component tests
- Use realistic but deterministic test data

### Testing Third-Party Integrations

Third-party SDKs that render their own UI (Stripe Elements, PayPal buttons, Google Maps, reCAPTCHA) operate outside your component tree - often in iframes. You cannot query their inputs with Testing Library.

**Bad** - Trying to interact with Stripe Elements via Testing Library:

```
// Stripe Elements renders in an iframe - this will fail
const cardInput = screen.getByLabelText("Card number")
await userEvent.type(cardInput, "4242424242424242")
```

**Good** - Mock the SDK at the module level, test your integration boundary:

```
// Mock the third-party SDK module
jest.mock("@stripe/react-stripe-js", () => ({
  CardElement: ({ onChange }) => (
    <input data-testid="mock-card" onChange={() => onChange({ complete: true })} />
  ),
  useStripe: () => ({ createPaymentMethod: jest.fn().mockResolvedValue({ paymentMethod: { id: "pm_test" } }) }),
  useElements: () => ({ getElement: jest.fn() }),
}))

// Test YOUR code's behavior when the SDK reports success/failure
await userEvent.click(screen.getByRole("button", { name: "Pay" }))
expect(await screen.findByText("Payment successful")).toBeInTheDocument()
```

**Testing strategy for third-party integrations:**

1. **Component tests**: Mock the SDK at the module level - test that your code reacts correctly to SDK success, failure, and loading states
2. **Integration boundary tests**: Unit-test the functions that call SDK methods (e.g., your `processPayment()` wrapper) with a mocked SDK client
3. **E2E tests**: Use the provider's test mode (Stripe test keys, Google Maps test environment) for full integration validation in Playwright

### Test Data Factories

For complex domain objects, create factory functions rather than inline object literals:

```
// Factory with sensible defaults and overrides
function createMockProduct(overrides = {}) {
  return { id: "prod_1", name: "Widget", price: 999, currency: "USD", inStock: true, ...overrides }
}

// Usage in tests - only specify what matters for this test
const expensiveProduct = createMockProduct({ price: 99999 })
const outOfStock = createMockProduct({ inStock: false })
```

## Stack-Specific Guidance

After loading stack-detect, apply testing patterns using the libraries and idioms of the detected ecosystem:

- **React**: Vitest + React Testing Library, `renderHook` for custom hooks, MSW for API mocking, Playwright for e2e
- **Vue**: Vitest + Vue Test Utils (or Testing Library Vue), `@nuxt/test-utils` for Nuxt-specific testing, MSW for API mocking, Playwright for e2e
- **Angular**: Vitest or Jest + Angular Testing Library, component harnesses for Material components, `HttpTestingController` for HTTP mocking, Playwright for e2e

If the detected stack is unfamiliar, apply the universal patterns above and recommend the user consult their framework's testing documentation.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## Frontend Testing Assessment

**Stack:** {detected language / framework}
**Test framework:** {detected or recommended test framework}

### Test Strategy

| Level       | Coverage Target | Tools                        |
| ----------- | --------------- | ---------------------------- |
| Unit        | {target %}      | {tool}                       |
| Component   | {target %}      | {tool}                       |
| Integration | {target %}      | {tool}                       |
| E2E         | {critical paths}| {tool}                       |

### Tests to Write

- {component/feature}: {test description} ({level})

### Issues Found

- [Severity: High | Medium | Low] {description of testing issue}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if testing is adequate - do not omit this section silently}
```

---

## Avoid

- Testing implementation details (internal state, method calls, component internals)
- Using CSS selectors or test IDs as primary query strategy (brittle, not user-centric)
- Module-level mocking for your own API calls (hides integration bugs) - use MSW instead. Module mocking is acceptable only for third-party SDKs with iframe-based UIs and browser APIs
- Snapshot testing large or frequently changing component trees (meaningless churn)
- Duplicating component-level assertions in e2e tests (slow, redundant)
- Tests that depend on execution order or shared mutable state (flaky)
- Testing third-party library behavior instead of your integration with it
- Skipping error and loading state tests for data-fetching components
