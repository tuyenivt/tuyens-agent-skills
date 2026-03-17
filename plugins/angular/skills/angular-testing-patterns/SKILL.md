---
name: angular-testing-patterns
description: Angular testing patterns - Vitest/Jest + Angular Testing Library, component harnesses, service testing, HttpTestingController, and Playwright e2e for Angular 21+.
metadata:
  category: frontend
  tags: [angular, testing, vitest, angular-testing-library, component-harness, playwright, httptestingcontroller]
user-invocable: false
---

# Angular Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing tests for Angular components, services, and pipes
- Setting up testing infrastructure for an Angular project
- Reviewing test quality and coverage
- Choosing between component, integration, and e2e test approaches
- Testing services with HttpClient and dependency injection

## Rules

- Test behavior, not implementation - assert what the user sees and does
- Use Angular Testing Library queries by role, label, and text - not CSS selectors as primary strategy
- Mock HTTP at the network boundary (HttpTestingController or MSW) - not service methods
- Every data-fetching component must have tests for loading, success, and error states
- Services must be tested with TestBed and proper DI setup
- Tests must be independent - no shared mutable state, no order dependencies
- Colocate tests with source: `component-name.component.spec.ts` next to `component-name.component.ts`

## Patterns

### Component Testing with Angular Testing Library

```typescript
import { render, screen } from "@testing-library/angular";
import userEvent from "@testing-library/user-event";
import { UserCardComponent } from "./user-card.component";

describe("UserCardComponent", () => {
  const defaultUser: User = {
    id: "1",
    name: "Alice",
    email: "alice@example.com",
  };

  it("renders user name and email", async () => {
    await render(UserCardComponent, {
      inputs: { user: defaultUser },
    });

    expect(screen.getByRole("heading", { name: "Alice" })).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("emits edit event when edit button is clicked", async () => {
    const user = userEvent.setup();
    const editSpy = jest.fn();

    await render(UserCardComponent, {
      inputs: { user: defaultUser },
      on: { edit: editSpy },
    });

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(editSpy).toHaveBeenCalled();
  });
});
```

### Component Testing with TestBed

```typescript
describe("ProductListComponent", () => {
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

  afterEach(() => {
    httpMock.verify(); // ensure no outstanding requests
  });

  it("renders products after loading", () => {
    fixture.detectChanges(); // triggers ngOnInit

    const req = httpMock.expectOne("/api/products");
    req.flush([
      { id: "1", name: "Widget", price: 9.99 },
      { id: "2", name: "Gadget", price: 19.99 },
    ]);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain("Widget");
    expect(fixture.nativeElement.textContent).toContain("Gadget");
  });

  it("shows error message when API fails", () => {
    fixture.detectChanges();

    const req = httpMock.expectOne("/api/products");
    req.flush("Server error", {
      status: 500,
      statusText: "Internal Server Error",
    });
    fixture.detectChanges();

    const errorEl = fixture.nativeElement.querySelector('[role="alert"]');
    expect(errorEl.textContent).toContain("Failed to load products");
  });
});
```

### Service Testing

```typescript
describe("UserService", () => {
  let service: UserService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [UserService, provideHttpClient(), provideHttpClientTesting()],
    });

    service = TestBed.inject(UserService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it("fetches users with filters", () => {
    const mockUsers: User[] = [
      { id: "1", name: "Alice", email: "alice@test.com" },
    ];

    service.getUsers({ role: "admin" }).subscribe((users) => {
      expect(users).toEqual(mockUsers);
    });

    const req = httpMock.expectOne(
      (r) => r.url === "/api/users" && r.params.get("role") === "admin",
    );
    expect(req.request.method).toBe("GET");
    req.flush(mockUsers);
  });

  it("creates a user", () => {
    const newUser: CreateUserDto = { name: "Bob", email: "bob@test.com" };
    const createdUser: User = { id: "2", ...newUser };

    service.createUser(newUser).subscribe((user) => {
      expect(user).toEqual(createdUser);
    });

    const req = httpMock.expectOne("/api/users");
    expect(req.request.method).toBe("POST");
    expect(req.request.body).toEqual(newUser);
    req.flush(createdUser);
  });
});
```

### Signal-Based Service Testing

```typescript
describe("CartService", () => {
  let service: CartService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [CartService],
    });
    service = TestBed.inject(CartService);
  });

  it("starts with empty cart", () => {
    expect(service.items()).toEqual([]);
    expect(service.count()).toBe(0);
    expect(service.total()).toBe(0);
  });

  it("adds item to cart", () => {
    service.addItem({ id: "1", name: "Widget", price: 9.99 } as Product);

    expect(service.count()).toBe(1);
    expect(service.items()[0].name).toBe("Widget");
    expect(service.total()).toBeCloseTo(9.99);
  });

  it("increments quantity for duplicate item", () => {
    const product = { id: "1", name: "Widget", price: 9.99 } as Product;
    service.addItem(product);
    service.addItem(product);

    expect(service.count()).toBe(1);
    expect(service.items()[0].quantity).toBe(2);
    expect(service.total()).toBeCloseTo(19.98);
  });

  it("removes item from cart", () => {
    service.addItem({ id: "1", name: "Widget", price: 9.99 } as Product);
    service.removeItem("1");

    expect(service.isEmpty()).toBe(true);
  });
});
```

### Three-State Testing for Data Components

Every component that fetches data must test:

```typescript
describe("UserListComponent", () => {
  it("shows loading state initially", async () => {
    await render(UserListComponent, {
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders users on success", async () => {
    const { fixture } = await render(UserListComponent, {
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    const httpMock = TestBed.inject(HttpTestingController);
    httpMock.expectOne("/api/users").flush([
      { id: "1", name: "Alice" },
      { id: "2", name: "Bob" },
    ]);
    fixture.detectChanges();

    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("shows error state on failure", async () => {
    const { fixture } = await render(UserListComponent, {
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    const httpMock = TestBed.inject(HttpTestingController);
    httpMock
      .expectOne("/api/users")
      .flush(null, { status: 500, statusText: "Error" });
    fixture.detectChanges();

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("shows empty state when no users", async () => {
    const { fixture } = await render(UserListComponent, {
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    const httpMock = TestBed.inject(HttpTestingController);
    httpMock.expectOne("/api/users").flush([]);
    fixture.detectChanges();

    expect(screen.getByText("No users found")).toBeInTheDocument();
  });
});
```

### Component Harness Testing (Angular Material)

```typescript
import { HarnessLoader } from "@angular/cdk/testing";
import { TestbedHarnessEnvironment } from "@angular/cdk/testing/testbed";
import { MatButtonHarness } from "@angular/material/button/testing";
import { MatInputHarness } from "@angular/material/input/testing";

describe("LoginComponent", () => {
  let loader: HarnessLoader;

  beforeEach(async () => {
    const fixture = TestBed.createComponent(LoginComponent);
    loader = TestbedHarnessEnvironment.loader(fixture);
  });

  it("submits form with credentials", async () => {
    const emailInput = await loader.getHarness(
      MatInputHarness.with({ selector: '[formControlName="email"]' }),
    );
    const passwordInput = await loader.getHarness(
      MatInputHarness.with({ selector: '[formControlName="password"]' }),
    );
    const submitButton = await loader.getHarness(
      MatButtonHarness.with({ text: "Sign In" }),
    );

    await emailInput.setValue("user@example.com");
    await passwordInput.setValue("password123");
    await submitButton.click();

    // assert submission
  });
});
```

### Testing OnPush Components with Signal Inputs

OnPush components only re-render when inputs change or signals update. Use `componentRef.setInput()` to trigger change detection properly:

```typescript
describe("ProductCardComponent", () => {
  it("updates when input signal changes", async () => {
    const { fixture } = await render(ProductCardComponent, {
      inputs: { product: { id: "1", name: "Widget", price: 9.99 } },
    });

    expect(screen.getByText("Widget")).toBeInTheDocument();

    // Update input - triggers OnPush change detection
    fixture.componentRef.setInput("product", {
      id: "1",
      name: "Updated Widget",
      price: 19.99,
    });
    fixture.detectChanges();

    expect(screen.getByText("Updated Widget")).toBeInTheDocument();
  });
});
```

### Guard and Resolver Testing

```typescript
describe("authGuard", () => {
  it("allows authenticated users", () => {
    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: { isAuthenticated: () => true } },
      ],
    });

    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
    );

    expect(result).toBe(true);
  });

  it("redirects unauthenticated users to login", () => {
    const router = { createUrlTree: jest.fn().mockReturnValue("loginUrl") };

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: { isAuthenticated: () => false } },
        { provide: Router, useValue: router },
      ],
    });

    const result = TestBed.runInInjectionContext(() =>
      authGuard(
        {} as ActivatedRouteSnapshot,
        { url: "/dashboard" } as RouterStateSnapshot,
      ),
    );

    expect(router.createUrlTree).toHaveBeenCalledWith(["/auth/login"], {
      queryParams: { returnUrl: "/dashboard" },
    });
  });
});
```

### Playwright E2E

```typescript
// e2e/auth.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("user can sign in and see dashboard", async ({ page }) => {
    await page.goto("/auth/login");
    await page.getByLabel("Email").fill("user@example.com");
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page).toHaveURL("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible();
  });

  test("shows validation errors for empty form", async ({ page }) => {
    await page.goto("/auth/login");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText("Email is required")).toBeVisible();
    await expect(page.getByText("Password is required")).toBeVisible();
  });
});
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Angular Testing Plan

**Stack:** {detected framework}
**Test framework:** {Vitest | Jest | Karma}
**Component testing:** {Angular Testing Library | TestBed}
**API mocking:** {HttpTestingController | MSW}
**E2E:** Playwright

### Test Coverage

| Component/Service    | Unit | Component | Integration | E2E      |
| -------------------- | ---- | --------- | ----------- | -------- |
| {name}               | {Y/N}| {Y/N}    | {Y/N}       | {Y/N}    |

### Tests to Write

- {component}: {test description} ({level})
- {service}: {test description} ({level})

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if testing is adequate - do not omit this section silently}
```

## Avoid

- Testing internal component state (signal values directly, private methods)
- Using CSS selectors as primary query strategy (prefer role, label, text)
- Mocking service methods when HttpTestingController can test the real HTTP flow
- Testing Angular framework behavior (test your code, not the framework)
- Snapshot testing large or frequently changing component trees
- Tests that depend on execution order or share mutable state
- Skipping loading, error, and empty state tests for data-fetching components
- Forgetting `httpMock.verify()` in afterEach (unmatched requests go undetected)
