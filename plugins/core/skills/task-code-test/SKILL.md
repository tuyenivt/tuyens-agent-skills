---
name: task-code-test
description: Test strategy, test scaffolding, and test coverage review. Use when coverage is low and you need a plan, when adding tests to untested code, when scaffolding a new test suite for a feature, when reviewing what test types are missing (unit vs integration vs contract), or when designing the testing pyramid for a service. Not for general code quality review (use task-code-review), not for performance testing (use task-code-perf-review), and not for security testing (use task-code-secure).
metadata:
  category: review
  tags: [testing, test-strategy, unit-test, integration-test, multi-stack]
  type: workflow
user-invocable: true
---

# Code Test

## When to Use

- Test coverage evaluation
- Testing strategy design
- Test quality review
- Test pyramid balance assessment
- Generating test scaffolds

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Testing Pyramid (All Stacks)

```
    /\      E2E (few)
   /--\     Integration (some)
  /----\    Unit (many)
```

### Step 3 - Framework-Specific Test Patterns

After loading stack-detect, apply test patterns using the idioms of the detected ecosystem:

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
- Keep this layer small - each test is expensive to write and maintain

**The "test or not" decision:**

- If it's a framework behavior (e.g., Spring autowiring, Rails routing), don't test it - trust the framework
- If it's configuration you wrote, test that configuration works
- If a bug could only be caught at a higher layer, write the test there - not at both layers

### Step 5 - Contract Testing (for service-to-service APIs)

When the detected stack involves multiple services or the project exposes/consumes HTTP/messaging APIs:

**Consumer-Driven Contracts:**

- The API consumer defines the contract (what fields and status codes it depends on)
- The API provider verifies it satisfies all consumer contracts before deploy
- Recommended tooling: Pact (most stacks), Spring Cloud Contract (Java)

**When contract tests are mandatory:**

- Any HTTP API consumed by a team that deploys independently
- Event/message schemas where producers and consumers deploy separately
- Any shared client library that other services import

**Minimum contract test coverage:**

- Happy path: expected request shape gets expected response shape
- Provider error: consumer handles 4xx/5xx gracefully
- Schema evolution: consumer tolerates new fields (Postel's law)

## Universal Checklist

- [ ] Clear test names (describe behavior)
- [ ] Arrange-Act-Assert pattern
- [ ] Edge cases covered
- [ ] Error paths tested
- [ ] No test interdependencies
- [ ] Fast feedback (tests run quickly)

## Stack-Specific Checklist

After loading stack-detect, verify the ecosystem's specific testing best practices:

- [ ] Test framework is current (no deprecated test utilities or annotations)
- [ ] Mock/stub mechanism follows current framework recommendations
- [ ] Integration test isolation is properly configured (transactions, cleanup, containers)
- [ ] Test data setup uses the ecosystem's recommended approach
- [ ] Parallel test execution is enabled where safe

## Contract Testing Checklist

- [ ] Service-to-service APIs have consumer-driven contracts or stub-verified tests
- [ ] Message/event schemas are tested for producer-consumer compatibility
- [ ] Consumer tolerates additive schema changes (new optional fields don't break it)
- [ ] Provider CI verifies contracts before deploy

## Output Format

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
