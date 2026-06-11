---
name: frontend-testing-patterns
description: Guide frontend testing: component, integration, e2e (Playwright/Cypress), MSW API mocking, snapshot discipline. Adapts to stack.
metadata:
  category: frontend
  tags: [frontend, testing, playwright, cypress, msw, vitest, jest, multi-stack]
user-invocable: false
---

# Frontend Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Planning test strategy for frontend features
- Reviewing existing coverage and quality
- Setting up testing infrastructure
- Choosing the right testing level for a component or flow

## Rules

- Test user-visible behavior, not implementation details (internal state, method calls)
- Prefer Testing Library queries that mirror user perception (role, label, text) over selectors or test IDs
- Tests are independent: no shared mutable state, no order dependencies
- Mock at the network boundary (MSW or HTTP interceptors), not at the module level for your own code
- Snapshots only for stable leaf components used as regression detection; never large trees or churning UI
- E2E covers critical user journeys only; do not duplicate unit/integration coverage there

Module-level mocking is acceptable only for third-party SDKs that render in iframes (Stripe, Maps, reCAPTCHA) and browser APIs without test equivalents (IntersectionObserver, ResizeObserver, geolocation).

---

## Patterns

### Testing Pyramid

| Level       | Tests                              | Tools                          | Count    |
| ----------- | ---------------------------------- | ------------------------------ | -------- |
| Unit        | Pure functions, hooks, utilities   | Vitest / Jest                  | Many     |
| Component   | Single component render + events   | Testing Library + Vitest/Jest  | Many     |
| Integration | Multi-component flows with state   | Testing Library + MSW          | Moderate |
| E2E         | Full user journeys in a browser    | Playwright (preferred)         | Few      |

### Test Behavior, Not Implementation

```
// Bad: probes internal state - breaks on refactor even if UX is identical
const wrapper = mount(UserCard)
expect(wrapper.vm.isExpanded).toBe(false)
wrapper.vm.toggleExpand()

// Good: tests what the user sees and does
render(<UserCard user={mockUser} />)
await userEvent.click(screen.getByRole("button", { name: "Show details" }))
expect(screen.getByText("alice@example.com")).toBeVisible()
```

### Query Priority

| Priority | Query                  | When                                          |
| -------- | ---------------------- | --------------------------------------------- |
| 1        | `getByRole`            | Anything with an ARIA role (buttons, links)   |
| 2        | `getByLabelText`       | Form inputs                                   |
| 3        | `getByPlaceholderText` | Inputs without visible labels (last resort)   |
| 4        | `getByText`            | Non-interactive elements                      |
| 5        | `getByDisplayValue`    | Filled form inputs                            |
| 6        | `getByTestId`          | Only when no semantic query works             |

### API Mocking with MSW

Mock at the network layer so components exercise real fetch/HTTP code paths (interceptors, error handling, serialization):

```
// Bad: jest.mock on your own API module skips your real HTTP wiring
jest.mock("../api/users", () => ({ getUsers: jest.fn().mockResolvedValue([...]) }))

// Good: MSW intercepts the actual request
const handlers = [
  http.get("/api/users", () => HttpResponse.json([{ id: 1, name: "Alice" }])),
  http.get("/api/users/:id", ({ params }) => HttpResponse.json({ id: params.id, name: "Alice" })),
]

render(<UserList />)
expect(await screen.findByText("Alice")).toBeInTheDocument()
```

### Loading and Error State Tests

Every data-fetching component tests three states: loading, success, error.

```
// Error state
server.use(http.get("/api/users", () => HttpResponse.json({ message: "Server error" }, { status: 500 })))
render(<UserList />)
expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load users")
expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument()
```

### Snapshot Discipline

Snapshots are appropriate for stable leaf components (icons, badges, formatted values) as regression detection after the component is finalized. They are harmful for large trees (any change anywhere breaks them), dynamic content (dates, IDs, random values), and components under active development.

If a snapshot breaks, read the diff. If developers reflexively run `--update-snapshot`, the test is worthless.

### E2E Strategy

Cover critical revenue/blocking paths only:

| Category       | Examples                                        |
| -------------- | ----------------------------------------------- |
| Authentication | Sign up, sign in, password reset, sign out      |
| Core workflows | Create order, process payment, submit form      |
| Navigation     | Landing to checkout, deep link resolution       |
| Error recovery | Network failure during checkout, session expiry |

Use Playwright with a page object pattern, run against a stable seeded environment, and skip visual details covered by component tests.

**E2E stability.** Flaky tests erode trust faster than missing tests:

- Never use fixed sleeps (`waitForTimeout`, hard-coded delays) - they race network timing. Use auto-retrying assertions that wait for the UI state itself: `await expect(page.getByText("Order confirmed")).toBeVisible()`
- Wait on user-visible outcomes (spinner gone, data rendered), never on timers or network internals
- Each test creates or seeds its own data; never reuse state left by a previous test
- Do not raise retry counts to mask flakiness - retries hide real race conditions; fix the wait or the data setup instead

### Third-Party SDK Integrations

SDKs that render in their own iframe (Stripe Elements, PayPal, Maps, reCAPTCHA) cannot be queried with Testing Library. Mock them at the module level and test your integration boundary:

```
// Mock the SDK
jest.mock("@stripe/react-stripe-js", () => ({
  CardElement: ({ onChange }) => <input data-testid="mock-card" onChange={() => onChange({ complete: true })} />,
  useStripe: () => ({ createPaymentMethod: jest.fn().mockResolvedValue({ paymentMethod: { id: "pm_test" } }) }),
  useElements: () => ({ getElement: jest.fn() }),
}))

// Test YOUR code reacting to the SDK's success/failure paths
await userEvent.click(screen.getByRole("button", { name: "Pay" }))
expect(await screen.findByText("Payment successful")).toBeInTheDocument()
```

Layer the strategy:
1. Component tests: mock the SDK, assert your code's reactions
2. Boundary unit tests: unit-test wrappers (e.g., `processPayment()`) with a mocked SDK client
3. E2E: use the provider's test mode (Stripe test keys, etc.) for true integration validation

### Test Data Factories

For complex domain objects, prefer factories over inline literals so tests only declare what matters:

```
function createMockProduct(overrides = {}) {
  return { id: "prod_1", name: "Widget", price: 999, currency: "USD", inStock: true, ...overrides }
}

const expensive = createMockProduct({ price: 99999 })
const outOfStock = createMockProduct({ inStock: false })
```

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms:

- **React**: Vitest + React Testing Library; `renderHook` for hooks; MSW; Playwright
- **Vue**: Vitest + Vue Test Utils (or Testing Library Vue); `@nuxt/test-utils` for Nuxt; MSW; Playwright
- **Angular**: Vitest or Jest + Angular Testing Library; component harnesses for Material; `HttpTestingController`; Playwright

For unknown stacks, apply universal patterns and point the user to the framework's testing docs.

---

## Output Format

Consuming workflow skills depend on this structure. Include exactly one of `Issues Found` / `No Issues Found`. When the project defines no coverage norms, default targets to 80% for unit and component, key flows for integration, critical paths for e2e.

```
## Frontend Testing Assessment

**Stack:** {detected language / framework}
**Test framework:** {detected or recommended test framework}

### Test Strategy

| Level       | Coverage Target  | Tools  |
| ----------- | ---------------- | ------ |
| Unit        | {target %}       | {tool} |
| Component   | {target %}       | {tool} |
| Integration | {target %}       | {tool} |
| E2E         | {critical paths} | {tool} |

### Tests to Write

- {component/feature}: {test description} ({level})

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if testing is adequate - do not omit this section silently}
```

Severity calibration: High = false confidence (implementation-detail assertions, reflexively updated snapshots, own code mocked out at module level); Medium = fragile or incomplete (brittle selectors, missing error/loading states, order dependence, fixed sleeps); Low = maintainability (inline literals over factories, naming, duplication).

---

## Avoid

- Asserting on internal state, method calls, or component internals
- CSS selectors or test IDs as the primary query strategy
- Module-level mocking for your own API code (use MSW); allowed only for iframe SDKs and untestable browser APIs
- Snapshots on large or fast-moving component trees
- Duplicating component-level assertions in e2e
- Order-dependent or shared-state tests
- Fixed sleeps or raised retry counts in e2e instead of auto-retrying assertions
- Testing third-party library behavior instead of your integration with it
- Skipping error/loading state tests on data-fetching components
