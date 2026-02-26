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

### Step 1 — Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 — Testing Pyramid (All Stacks)

```
    /\      E2E (few)
   /--\     Integration (some)
  /----\    Unit (many)
```

### Step 3 — Framework-Specific Test Patterns

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

### Step 4 — Frontend (React)

**Component Test:**

- Test user interactions with Testing Library
- Verify loading/error states
- Use accessibility-first query selectors

**Hook Test:**

- Use renderHook for custom hook testing

### React Query Priority

1. `getByRole` - Accessible
2. `getByLabelText` - Forms
3. `getByText` - Content
4. `getByTestId` - Last resort

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

## Frontend-Specific Checklist

- [ ] User interactions tested
- [ ] Loading/error states verified
- [ ] Accessibility assertions
- [ ] No implementation details tested

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
- Do not aim for 100% coverage as a goal — focus on business value
- Consider maintenance cost of each test

## Output

```markdown
## Assessment

**Coverage:** [X%]
**Pyramid Balance:** [status]
**Stack Detected:** [language / framework]

## Gaps

| Area | Missing Tests | Priority |

## Recommended Tests

[Test cases to add with framework-specific scaffolds]
```

## Avoid

- Testing implementation details instead of behavior
- Flaky tests that depend on timing or external state
- Over-mocking (test nothing meaningful)
- Ignoring test maintenance cost
- Applying test patterns from one framework to another
