---
name: task-code-test
description: Test strategy, test scaffolding, and test coverage review. Use when coverage is low and you need a plan, when adding tests to untested code, when scaffolding a new test suite, when reviewing what test types are missing (unit vs integration vs contract), or when designing the testing pyramid for a service.
metadata:
  category: review
  tags: [testing, test-strategy, unit-test, integration-test, multi-stack]
  type: workflow
user-invocable: true
---

# Code Test

## Purpose

Design test strategy, assess coverage gaps, and generate test scaffolds for a module or service. Prioritizes testing by business risk rather than coverage numbers. Adapts test patterns to the detected stack's ecosystem.

## When to Use

- Test coverage evaluation
- Testing strategy design
- Test quality review
- Test pyramid balance assessment
- Generating test scaffolds

**Not for:** General code quality review (use `task-code-review`), performance testing (use `task-code-perf-review`), security testing (use `task-code-secure`).

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Testing Pyramid (All Stacks)

**Unit (many)** → **Integration (some)** → **E2E (few)**. Most tests should be fast unit tests; integration tests cover boundaries; E2E tests cover only critical user flows.

### Step 3 - Framework-Specific Test Patterns

After loading stack-detect, apply test patterns using the idioms of the detected ecosystem and `Stack Type`.

#### Backend Test Patterns (when Stack Type is `backend` or `fullstack`)

**Unit Tests:**

- Use the ecosystem's standard test framework and assertion library
- Follow the Arrange-Act-Assert (Given-When-Then) pattern
- Use the framework's mock/stub mechanism for isolating dependencies
- Name tests to describe behavior: `should_X_when_Y` or equivalent naming convention

**Integration Tests:**

- Use the framework's standard integration test setup (test server, test client, test database)
- Apply transaction rollback or database cleanup between tests for isolation
- Use container-based testing (e.g., Testcontainers or equivalent) for database and service dependencies
- Test HTTP endpoints through the framework's test client

**Test Data:**

- Use the ecosystem's standard test data mechanism (factories, fixtures, builders, etc.)
- Prefer factory-based test data over static fixtures for flexibility
- Keep test data minimal and focused on the scenario being tested

#### Frontend Test Patterns (when Stack Type is `frontend` or `fullstack`)

Use skill: `frontend-testing-patterns` for component testing, MSW mocking, and E2E patterns.

**Component Tests:**

- Test user-visible behavior, not implementation details (query by role/label, not by class/test-id)
- Cover all render states: loading, error, empty, and populated
- Test user interactions (click, type, submit) and verify resulting UI changes
- Use MSW (Mock Service Worker) for API mocking in component tests

**Integration Tests:**

- Test multi-component flows (form submission -> success message, navigation -> page load)
- Verify data fetching and state management work together correctly
- Test error boundaries and fallback UI

**E2E Tests:**

- Cover only critical user flows (login, checkout, core CRUD operations)
- Use the project's E2E framework (Playwright, Cypress, or equivalent)
- Keep E2E count minimal - these are expensive to maintain

#### Common Patterns (all Stack Types)

**Test Organization:**

- Follow the project's existing test organization conventions
- Use the ecosystem's standard approach for skipping slow tests (integration, E2E) in fast feedback loops

If the detected stack is unfamiliar, apply the universal testing pyramid and Arrange-Act-Assert pattern.

### Step 4 - Test Boundary Guidance

Before writing or recommending tests, determine what deserves each layer:

**What belongs in unit tests:**

- Pure functions and domain logic with no I/O
- Validation rules and business rules with many branches
- Error handling and edge cases in isolation
- Anything that would be slow or brittle if integration-tested

**What belongs in integration tests:**

- Database queries - verify real SQL executes correctly against a real schema
- HTTP endpoints - verify routing, serialization, and status codes end to end
- External service clients - verify request/response mapping (use contract tests or stubs)
- Authentication and authorization logic - verify the whole filter/middleware chain

**What belongs in E2E tests:**

- Critical business flows (checkout, login, data export) only
- Flows that span multiple services or UI + API together
- **Frontend**: critical user journeys that span multiple pages/routes
- Keep this layer small - each test is expensive to write and maintain

**The "test or not" decision:**

- If it's a framework behavior (e.g., Spring autowiring, Rails routing), don't test it - trust the framework
- If it's configuration you wrote, test that configuration works
- If a bug could only be caught at a higher layer, write the test there - not at both layers

### Step 5 - Prioritization (when coverage is low)

When starting from low test coverage, prioritize by risk rather than trying to reach a coverage number:

**Priority 1 - Business-critical paths:**

- Revenue-impacting flows (checkout, billing, payments)
- Data integrity logic (writes, migrations, state transitions)
- Authentication and authorization checks

**Priority 2 - Error-prone areas:**

- Code with recent bug history (check git log for fix commits)
- Complex conditional logic with many branches
- Integration points with external services

**Priority 3 - High-change areas:**

- Code that changes frequently (high churn in git history)
- Shared utilities used across many modules

**Priority 4 - Plumbing and glue code:**

- Simple CRUD, pass-through controllers, configuration
- These are lower risk and can wait

**Testability refactoring:** Untested legacy code often needs structural changes before tests can be added (extracting dependencies behind interfaces, breaking god classes, isolating I/O from logic). Budget time for these refactors - they are part of the testing work, not separate from it.

### Step 6 - Contract Testing (for service-to-service APIs)

When the detected stack involves multiple services or the project exposes/consumes HTTP/messaging APIs:

**Consumer-Driven Contracts:**

- The API consumer defines the contract (what fields and status codes it depends on)
- The API provider verifies it satisfies all consumer contracts before deploy
- Use the ecosystem's standard contract testing tool (e.g., Pact, Spring Cloud Contract, msw, nock, WireMock)

**When contract tests are mandatory:**

- Any HTTP API consumed by a team that deploys independently
- Event/message schemas where producers and consumers deploy separately
- Any shared client library that other services import

**Minimum contract test coverage:**

- Happy path: expected request shape gets expected response shape
- Provider error: consumer handles 4xx/5xx gracefully
- Schema evolution: consumer tolerates new fields (Postel's law)

## Review Checklist

Quick-reference checklist consolidating the key checks from above:

- [ ] Test names describe behavior, not implementation
- [ ] Arrange-Act-Assert pattern used consistently
- [ ] Each testable unit has: happy path + error path + edge case
- [ ] No test interdependencies (tests pass in any order)
- [ ] Test framework and mocks follow current ecosystem recommendations
- [ ] Integration tests have proper isolation (transactions, cleanup, containers)
- [ ] Contract tests exist for independently-deployed service dependencies
- [ ] Slow tests (integration, E2E) can be skipped in fast feedback loops

## Output Format

**Which output to produce:**
- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% -> Strategy Doc (optionally include Coverage Assessment)
- If unclear, produce Strategy Doc as the default.

Produce one or more of the following depending on what was requested:

**Coverage Assessment:**

```markdown
## Test Coverage Assessment

**Stack:** [language / framework]
**Coverage gaps:**

- [Layer / component]: [what is missing and why it matters]

**Recommended testing pyramid:**

- Unit: [what belongs here]
- Integration: [what belongs here]
- E2E: [what belongs here, if anything]
```

**Test Scaffolds** (when generating boilerplate):
Produce ready-to-run test files using the detected stack's test framework. Include:

- Arrange-Act-Assert structure with descriptive test names
- At least one happy path, one not-found/empty case, and one validation/error case per unit
- Inline comments explaining non-obvious setup

**Strategy Doc** (when designing a test strategy):

```markdown
## Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Integration {y}% / E2E {z}%
**Tooling:** [test framework, mocking library, container strategy]
**Contract testing:** [required / not required - rationale]
**Gaps to close (prioritized):**

1. [Highest risk gap]
2. ...
```

## Self-Check

- [ ] Stack detected and framework-specific test patterns applied
- [ ] Testing pyramid balance assessed - not just unit tests or just integration tests
- [ ] Prioritization by risk applied when coverage is low (not chasing a coverage number)
- [ ] Test boundaries clearly defined - each test layer covers what it does best
- [ ] Contract testing assessed for service-to-service APIs
- [ ] Test scaffolds (if generated) include happy path, error path, and edge case
- [ ] Review checklist items all addressed

## Avoid

- Chasing a coverage number instead of prioritizing by risk
- Testing framework internals (trust the framework, test your configuration)
- Writing brittle tests that break on implementation changes (test behavior, not implementation)
- Duplicating assertions across test layers (if an integration test covers it, don't unit test the same thing)
- Generating tests without understanding what the code does - characterization tests first for unfamiliar code
- Recommending E2E tests for things that can be caught at the unit or integration level
