---
name: frontend-testing-patterns
description: Guide frontend testing: component, integration, e2e, MSW API mocking, snapshot discipline, coverage ratchets. Adapts to stack.
metadata:
  category: frontend
  tags: [frontend, testing, playwright, e2e, msw, vitest, jest, multi-stack]
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

Module-level mocking is acceptable only for third-party SDKs you cannot drive from the DOM - those rendering in an iframe (Stripe Elements, reCAPTCHA) or on a canvas (Google Maps, which renders into the page, not an iframe). Browser APIs without test equivalents (IntersectionObserver, ResizeObserver, geolocation) are globals, not modules: stub them on `globalThis`/`navigator` in setup, which module mocking cannot do.

### Server-rendered components

A component that runs only on the server (React Server Components, Nuxt server components) has no client lifecycle to render into and often no network boundary to intercept - it calls the database or filesystem directly. The client-side rules do not transfer:

- Extract the data access and unit-test it directly against a test database or a fake repository; the component's own job is then shaped from that data.
- Test the rendered result through the framework's server-render path or E2E, not Testing Library's `render()`.
- MSW intercepts HTTP, so it applies only where the server component actually makes an HTTP call to another service.
- The Client Components beneath it follow every rule above - the boundary between them is where normal component testing resumes.

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
| 3        | `getByPlaceholderText` | Inputs without a visible label                |
| 4        | `getByText`            | Non-interactive elements                      |
| 5        | `getByDisplayValue`    | Filled form inputs                            |
| 6        | `getByAltText`         | Images and `area`/`input type=image`          |
| 7        | `getByTitle`           | Elements whose only name is a `title`         |
| 8        | `getByTestId`          | Last resort - only when no semantic query works |

### API Mocking with MSW

Mock at the network layer so components exercise real fetch/HTTP code paths (interceptors, error handling, serialization):

```
// Bad: jest.mock on your own API module skips your real HTTP wiring
jest.mock("../api/users", () => ({ getUsers: jest.fn().mockResolvedValue([...]) }))

// Good: MSW intercepts the actual request.
// handlers.ts
export const handlers = [
  http.get("/api/users", () => HttpResponse.json([{ id: 1, name: "Alice" }])),
  http.get("/api/users/:id", ({ params }) => HttpResponse.json({ id: params.id, name: "Alice" })),
]

// setup file - without this the handlers are never installed and nothing is intercepted
export const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// test
render(<UserList />)
expect(await screen.findByText("Alice")).toBeInTheDocument()
```

### Loading and Error State Tests

Every data-fetching component tests three states: loading, success, error.

```
// Error state - server.use is per-test; afterEach(resetHandlers) above undoes it
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

SDKs you cannot drive from your own DOM - those in an iframe (Stripe Elements, PayPal, reCAPTCHA) or on a canvas (Google Maps) - cannot be queried with Testing Library. Mock them at the module level and test your integration boundary:

```
// Hoist every spy the factory closes over - a hoisted factory cannot see module imports.
const { createPaymentMethod, getElement, h } = vi.hoisted(() => {
  const { createElement } = require("react")
  return { createPaymentMethod: vi.fn(), getElement: vi.fn(), h: createElement }
})

vi.mock("@stripe/react-stripe-js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@stripe/react-stripe-js")>()),
  CardElement: (props: { onChange: (e: { complete: boolean }) => void }) =>
    h("input", { "data-testid": "mock-card", onChange: () => props.onChange({ complete: true }) }),
  useStripe: () => ({ createPaymentMethod }),
  useElements: () => ({ getElement }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  createPaymentMethod.mockResolvedValue({ paymentMethod: { id: "pm_test" } })
})

// Test YOUR code reacting to the SDK's success/failure paths. Drive the mock element first,
// or a form gated on card completeness never enables its submit button.
await userEvent.click(screen.getByTestId("mock-card"))
await userEvent.click(screen.getByRole("button", { name: "Pay" }))
expect(createPaymentMethod).toHaveBeenCalled()
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

Consuming workflow skills depend on this structure. Include exactly one of `Issues Found` / `No Issues Found`. A clean run emits every header field, the Test Strategy table, `Tests to Write` when any apply, and `No Issues Found`; only the `Issues Found` blocks are omitted. Order Issues Found by severity, highest first; within a band, file order. When the project defines no coverage norms, default targets to 80% for unit and component, key flows for integration, critical paths for e2e.

On a codebase far below those targets, a global number is a wish, not a plan: write the Coverage Target cell as a ratchet with the baseline in it (`80% on changed files, baseline 12%`), or `80% on changed files, baseline unmeasured` when no coverage report exists - never invent a baseline number. Order `Tests to Write` as an adoption sequence - E2E over the one or two revenue-critical journeys first (largest safety net per test), then component tests at the files that change most often, then backfill. Say which step the project is on rather than listing 400 components.

```
## Frontend Testing Assessment

**Stack:** {detected language / framework}

**Test framework:** {detected or recommended test framework}

### Test Strategy

| Level       | Coverage Target  | Tools  |
| ----------- | ---------------- | ------ |
| Unit        | {target %}       | {tool} |
| Component   | {target %}       | {tool} |
| Integration | {target % or key flows} | {tool} |
| E2E         | {critical paths} | {tool} |

### Tests to Write

- {component/feature}: {test description} ({unit | component | integration | e2e})

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Location: {file}:{line}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

Notes: {defects in the code under test rather than the tests, each naming the concern that owns it; omit when none}

### No Issues Found

{State explicitly if testing is adequate - do not omit this section silently}
```

`Issues Found` covers the test code in scope, including its harness and config (a missing setup import, an unreset handler, a raised retry count). A defect in the code under test goes in one trailing `Notes:` line naming the owning concern, not in `Issues Found`.

Severity calibration: High = false confidence (implementation-detail assertions, reflexively updated snapshots, own code mocked out at module level, a harness defect that stops tests exercising what they claim - handlers never installed, a missing setup import, a raised retry count masking a race); Medium = fragile or incomplete (brittle selectors, missing error/loading states, order dependence, fixed sleeps); Low = maintainability (inline literals over factories, naming, duplication). A large-tree snapshot rates Medium as fragile; it escalates to High when the history shows reflexive updating (a snapshot regenerated alongside unrelated changes, or a script that passes the update flag - `-u`, `--updateSnapshot` on Jest, `--update` on Vitest) - rate the evidence, not the trajectory.

---

## Avoid

- Asserting on internal state, method calls, or component internals
- CSS selectors or test IDs as the primary query strategy
- Module-level mocking for your own API code (use MSW); allowed only for third-party SDKs you cannot drive from the DOM. Browser globals are stubbed on `globalThis`, not module-mocked
- Snapshots on large or fast-moving component trees
- Duplicating component-level assertions in e2e
- Order-dependent or shared-state tests
- Fixed sleeps or raised retry counts in e2e instead of auto-retrying assertions
- Testing third-party library behavior instead of your integration with it
- Skipping error/loading state tests on data-fetching components
