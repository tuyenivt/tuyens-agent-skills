---
name: task-code-test
description: Test strategy, scaffolds, and quality review. Auto-detects project stack from CLAUDE.md and adapts test patterns to the detected language and framework.
metadata:
  category: review
  tags: [testing, test-strategy, unit-test, integration-test, multi-stack]
  type: workflow
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

## Key Skills Reference

- Use skill: `coding-standards` for test naming and structure
- Use skill: `api-guidelines` for API test patterns

## Principles

- Test behavior, not implementation
- Fast feedback is essential
- Tests are specifications
- Pyramid over ice cream cone

## Rules

- Every test must have a clear purpose
- Use Arrange-Act-Assert consistently
- No test interdependencies
- Do not aim for 100% coverage as a goal - focus on business value
- Consider maintenance cost of each test

## Output

```markdown
## Assessment

**Stack Detected:** [language / framework]
**Coverage:** [X% or "not measured"]
**Pyramid Balance:** [unit-heavy / balanced / integration-heavy / inverted]
**Contract Testing:** [present / absent / not applicable]

## Test Boundary Analysis

| Layer       | Current State  | Recommendation          |
| ----------- | -------------- | ----------------------- |
| Unit        | [count/status] | [what to add or remove] |
| Integration | [count/status] | [what to add or remove] |
| E2E         | [count/status] | [what to add or remove] |
| Contract    | [count/status] | [what to add or remove] |

## Gaps

| Area   | Missing Tests    | Layer                     | Priority     |
| ------ | ---------------- | ------------------------- | ------------ |
| [area] | [what's missing] | Unit/Integration/Contract | High/Med/Low |

## Recommended Tests

[Test cases to add with framework-specific scaffolds - describe behavior, not method names]

## What NOT to Test

[Framework behaviors, configuration that can't be misconfigured, implementation details that should be free to change]
```

## Success Criteria

A well-executed test review or strategy passes all of these. Use as a self-check before presenting.

### Completeness

- [ ] Test pyramid balance is assessed - unit, integration, and E2E split is evaluated
- [ ] Framework-specific test patterns for the detected stack are applied
- [ ] Coverage gaps table lists specific areas and their priority - not a generic coverage percentage goal
- [ ] Error paths and edge cases are checked, not just the happy path

### Quality

- [ ] Recommended tests describe behavior, not implementation details
- [ ] Every recommended test scaffold uses the detected stack's current framework and idioms
- [ ] Test isolation is verified - no shared state between tests
- [ ] Test names describe the behavior being verified, not the method being called

### Staff-Level Signal (for tech lead review)

- [ ] The highest-value test gaps are identified and prioritized - not an exhaustive list of everything missing
- [ ] Integration test coverage of critical business flows is explicitly assessed
- [ ] The review distinguishes between test quantity and test quality - coverage % is not the sole signal
- [ ] Any deprecated test utilities or annotations in the detected stack are flagged
- [ ] "What not to test" guidance is provided - over-testing is as much a problem as under-testing
- [ ] Contract testing is assessed for any multi-service boundary in scope

## Avoid

- Testing implementation details instead of behavior
- Flaky tests that depend on timing or external state
- Over-mocking (test nothing meaningful)
- Ignoring test maintenance cost
- Applying test patterns from one framework to another

## After This Skill

If the output needed significant adjustment - wrong test strategy recommended, coverage gaps were missed, or scaffolds used outdated patterns for the stack - run `/task-skill-feedback` to log what changed and why.
