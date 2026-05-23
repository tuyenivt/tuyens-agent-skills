---
name: angular-testing-patterns
description: Angular testing: Vitest/Jest, Angular Testing Library, component harnesses, service tests, HttpTestingController, Playwright e2e.
metadata:
  category: frontend
  tags: [angular, testing, vitest, angular-testing-library, component-harness, playwright, httptestingcontroller]
user-invocable: false
---

# Angular Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing tests for Angular components, services, pipes, guards, resolvers
- Setting up testing infrastructure or choosing between unit, component, and e2e levels
- Testing services with HttpClient and DI

## Rules

- Test behavior, not implementation. Assert what the user sees and does, not signal values or private methods.
- Query by role, label, or text. CSS selectors only when no accessible name exists.
- Mock HTTP at the network boundary with `HttpTestingController` (or MSW). Never stub service methods to bypass real HTTP flow.
- Every data-fetching component tests loading, success, error, and empty states.
- Call `httpMock.verify()` in `afterEach` to catch unmatched requests.
- Tests are independent: no shared mutable state, no order dependencies.
- Colocate `*.spec.ts` next to source. Prefer Angular Testing Library; drop to `TestBed` only when you need fixture-level control (change detection, harnesses, injector access).

## Patterns

### Component test with Angular Testing Library

```typescript
import { render, screen } from "@testing-library/angular";
import userEvent from "@testing-library/user-event";

it("emits edit when button clicked", async () => {
  const user = userEvent.setup();
  const editSpy = jest.fn();

  await render(UserCardComponent, {
    inputs: { user: { id: "1", name: "Alice", email: "a@x.com" } },
    on: { edit: editSpy },
  });

  await user.click(screen.getByRole("button", { name: "Edit" }));
  expect(editSpy).toHaveBeenCalled();
});
```

### Component test with TestBed + HttpTestingController

Use when you need fixture control or to flush HTTP responses manually.

```typescript
let fixture: ComponentFixture<ProductListComponent>;
let httpMock: HttpTestingController;

beforeEach(async () => {
  await TestBed.configureTestingModule({
    imports: [ProductListComponent],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  }).compileComponents();

  fixture = TestBed.createComponent(ProductListComponent);
  httpMock = TestBed.inject(HttpTestingController);
});

afterEach(() => httpMock.verify());

it("renders products after load", () => {
  fixture.detectChanges(); // ngOnInit fires the request
  httpMock.expectOne("/api/products").flush([{ id: "1", name: "Widget" }]);
  fixture.detectChanges();

  expect(fixture.nativeElement.textContent).toContain("Widget");
});
```

### Service test (HTTP)

```typescript
it("fetches users with filters", () => {
  service.getUsers({ role: "admin" }).subscribe((users) => {
    expect(users).toEqual(mockUsers);
  });

  const req = httpMock.expectOne(
    (r) => r.url === "/api/users" && r.params.get("role") === "admin",
  );
  expect(req.request.method).toBe("GET");
  req.flush(mockUsers);
});
```

### Signal-based service test

Assert signal outputs by invoking them as functions. No `detectChanges` needed for pure service signals.

```typescript
it("adds item and updates derived signals", () => {
  service.addItem({ id: "1", name: "Widget", price: 9.99 } as Product);

  expect(service.count()).toBe(1);
  expect(service.total()).toBeCloseTo(9.99);
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

it("loading", async () => {
  await setup();
  expect(screen.getByRole("status")).toBeInTheDocument();
});

it("success", async () => {
  const { fixture, http } = await setup();
  http.expectOne("/api/users").flush([{ id: "1", name: "Alice" }]);
  fixture.detectChanges();
  expect(screen.getByText("Alice")).toBeInTheDocument();
});

it("error", async () => {
  const { fixture, http } = await setup();
  http.expectOne("/api/users").flush(null, { status: 500, statusText: "x" });
  fixture.detectChanges();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

it("empty", async () => {
  const { fixture, http } = await setup();
  http.expectOne("/api/users").flush([]);
  fixture.detectChanges();
  expect(screen.getByText("No users found")).toBeInTheDocument();
});
```

### Material harness

```typescript
import { TestbedHarnessEnvironment } from "@angular/cdk/testing/testbed";
import { MatButtonHarness } from "@angular/material/button/testing";
import { MatInputHarness } from "@angular/material/input/testing";

const loader = TestbedHarnessEnvironment.loader(fixture);
const email = await loader.getHarness(
  MatInputHarness.with({ selector: '[formControlName="email"]' }),
);
const submit = await loader.getHarness(
  MatButtonHarness.with({ text: "Sign In" }),
);

await email.setValue("user@example.com");
await submit.click();
```

### OnPush components with signal inputs

Use `componentRef.setInput` to update an input and trigger change detection.

```typescript
fixture.componentRef.setInput("product", { id: "1", name: "Updated", price: 19.99 });
fixture.detectChanges();
expect(screen.getByText("Updated")).toBeInTheDocument();
```

### Guard / resolver

Functional guards run inside an injection context. Provide deps via TestBed and execute with `runInInjectionContext`.

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

Consuming workflow skills parse this structure.

```
## Angular Testing Plan

**Stack:** {detected framework}
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

### No Issues Found

{State explicitly when coverage is adequate.}
```

## Avoid

- Asserting on internal state (signal values directly, private methods, child component instances).
- Snapshot testing large or frequently changing component trees.
- Testing framework behavior (router internals, change detection scheduling).
- Skipping `httpMock.verify()` - unmatched requests go undetected.
- Omitting empty-state tests for list components.
