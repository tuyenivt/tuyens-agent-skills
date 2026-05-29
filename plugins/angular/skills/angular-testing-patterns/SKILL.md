---
name: angular-testing-patterns
description: Angular testing - Vitest/Jest, Angular Testing Library, TestBed, HttpTestingController, functional guard/interceptor, Playwright.
metadata:
  category: frontend
  tags: [angular, testing, vitest, angular-testing-library, component-harness, playwright, httptestingcontroller]
user-invocable: false
---

# Angular Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing tests for components, services, pipes, guards, resolvers, interceptors
- Setting up testing infrastructure or choosing between unit, component, and e2e levels

## Rules

- Test behavior, not implementation. Assert what the user sees and does, not signal values or private methods.
- Query by role, label, or text. CSS selectors only when no accessible name exists.
- Mock HTTP at the network boundary with `HttpTestingController`. Never stub service methods to bypass HTTP.
- Every data-fetching component tests loading, success, error, and empty states.
- Call `httpMock.verify()` in `afterEach` to catch unmatched requests.
- Tests are independent: no shared mutable state, no order dependencies.

### Component test choice

| Use                 | When                                                 |
| ------------------- | ---------------------------------------------------- |
| Angular Testing Library (ATL) `render` | Default. User-centric queries, `userEvent`. |
| `TestBed` + `ComponentFixture`         | Manual CD timing, harness loader, `setInput` on OnPush. |

For Vitest, replace `jest.fn()` with `vi.fn()` and `jest.mock` with `vi.mock`. APIs are otherwise identical.

## Patterns

### Component test (ATL)

```typescript
import { render, screen } from "@testing-library/angular";
import userEvent from "@testing-library/user-event";

it("emits edit when button clicked", async () => {
  const user = userEvent.setup();
  const editSpy = vi.fn();

  await render(UserCardComponent, {
    inputs: { user: { id: "1", name: "Alice", email: "a@x.com" } },
    on: { edit: editSpy },
  });

  await user.click(screen.getByRole("button", { name: "Edit" }));
  expect(editSpy).toHaveBeenCalled();
});
```

### Four-state coverage for data components

```typescript
const setup = async () => {
  const r = await render(UserListComponent, {
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  return { ...r, http: TestBed.inject(HttpTestingController) };
};

afterEach(() => TestBed.inject(HttpTestingController).verify());

it("loading", async () => {
  await setup();
  expect(screen.getByRole("status")).toBeInTheDocument();
});

it("success", async () => {
  const { http } = await setup();
  http.expectOne("/api/users").flush([{ id: "1", name: "Alice" }]);
  expect(await screen.findByText("Alice")).toBeInTheDocument();
});

it("error", async () => {
  const { http } = await setup();
  http.expectOne("/api/users").flush(null, { status: 500, statusText: "x" });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

it("empty", async () => {
  const { http } = await setup();
  http.expectOne("/api/users").flush([]);
  expect(await screen.findByText("No users found")).toBeInTheDocument();
});
```

### Service (HTTP)

```typescript
it("fetches users with filters", () => {
  service.list({ role: "admin", page: 2 }).subscribe((page) => {
    expect(page.items).toEqual(mockUsers);
  });
  const req = httpMock.expectOne(
    (r) => r.url === "/api/users" && r.params.get("role") === "admin" && r.params.get("page") === "2",
  );
  expect(req.request.method).toBe("GET");
  req.flush({ items: mockUsers, total: 1 });
});
```

### Signal-based service

Read signals as function calls; no `detectChanges` needed for pure service signals.

```typescript
it("adds item and updates derived signals", () => {
  service.add({ id: "1", name: "Widget", price: 9.99 });
  expect(service.count()).toBe(1);
  expect(service.total()).toBeCloseTo(9.99);
});
```

### OnPush signal-input component

```typescript
fixture.componentRef.setInput("product", { id: "1", name: "Updated", price: 19.99 });
fixture.detectChanges();
expect(screen.getByText("Updated")).toBeInTheDocument();
```

### Functional guard

```typescript
TestBed.configureTestingModule({
  providers: [
    { provide: AuthService, useValue: { isAuthenticated: () => false } },
    { provide: Router, useValue: router },
  ],
});

const result = TestBed.runInInjectionContext(() =>
  authGuard({} as ActivatedRouteSnapshot, { url: "/dashboard" } as RouterStateSnapshot),
);

expect(router.createUrlTree).toHaveBeenCalledWith(["/auth/login"], {
  queryParams: { returnUrl: "/dashboard" },
});
```

### Functional interceptor

```typescript
beforeEach(() => {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: { getToken: () => "abc123" } },
    ],
  });
});

it("attaches bearer token to same-origin requests", () => {
  const http = TestBed.inject(HttpClient);
  const httpMock = TestBed.inject(HttpTestingController);

  http.get("/api/users").subscribe();
  const req = httpMock.expectOne("/api/users");
  expect(req.request.headers.get("Authorization")).toBe("Bearer abc123");
  req.flush({});
});
```

### Functional resolver

```typescript
const result = TestBed.runInInjectionContext(() =>
  teamResolver({ paramMap: convertToParamMap({ teamId: "42" }) } as ActivatedRouteSnapshot,
    {} as RouterStateSnapshot),
);
```

### Debounced search input

```typescript
it("debounces search and fires one request", fakeAsync(() => {
  const user = userEvent.setup({ delay: null });
  // ... typing
  user.type(screen.getByRole("searchbox"), "alice");
  tick(300);
  httpMock.expectOne((r) => r.url === "/api/search" && r.params.get("q") === "alice");
}));
```

### Material harness

For Angular Material components, use CDK harnesses (`TestbedHarnessEnvironment.loader(fixture)` + per-component harness) instead of `By.css('mat-...')` selectors.

### Playwright e2e

```typescript
test("user can sign in", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("Email").fill("user@example.com");
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).toHaveURL("/dashboard");
});
```

## Output Format

```
## Angular Testing Plan

**Test framework:** {Vitest | Jest | Karma}
**Component testing:** {Angular Testing Library | TestBed}
**API mocking:** {HttpTestingController | MSW}
**E2E:** {Playwright | none}

### Test Coverage

| Component/Service | Unit  | Component | Integration | E2E   |
| ----------------- | ----- | --------- | ----------- | ----- |
| {name}            | {Y/N} | {Y/N}     | {Y/N}       | {Y/N} |

### Tests to Write

- {component}: {description} ({Unit | Component | Integration | E2E})

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

State "No issues found" when coverage is adequate.

## Avoid

- Asserting on internal state (signal values directly, private methods, child component instances)
- Snapshot testing large or frequently changing component trees
- Testing framework behavior (router internals, change detection scheduling)
- Skipping `httpMock.verify()` - unmatched requests go undetected
- Omitting empty-state tests for list components
- Raw `By.css('mat-...')` selectors when CDK harnesses exist
