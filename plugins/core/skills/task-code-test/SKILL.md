---
name: task-code-test
description: Test entry point: strategy, scaffolding, coverage review. Detects stack and dispatches to stack-specific test workflow.
metadata:
  category: review
  tags: [testing, test-strategy, unit-test, integration-test, multi-stack, router]
  type: workflow
user-invocable: true
---

# Code Test (Router)

Detects the project stack and delegates to the matching stack-specific test workflow (`task-{stack}-test`). When no stack workflow matches, runs a minimal generic test-pyramid protocol.

## When to Use

- Test coverage evaluation, test strategy design, test scaffolding, pyramid balance review.
- If you already know the stack, call the stack workflow directly (e.g., `/task-spring-test`) to skip routing.

**Not for:** General code review (`task-code-review`), performance (`task-code-review-perf`), security (`task-code-review-security`).

## Invocation

`/task-code-test [<file or path>] [--spec <slug>]`

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Spec-Aware Preamble (conditional)

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the code under test, use skill: `spec-aware-preamble` (from the `spec` plugin) and propagate spec context to the dispatched workflow.

### Step 3 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and `Stack Type`.

### Step 4 - Dispatch to Stack Workflow

| Detected stack       | Delegate to         |
| -------------------- | ------------------- |
| Java / Spring Boot   | `task-spring-test`  |
| Kotlin / Spring Boot | `task-kotlin-test`  |
| Python               | `task-python-test`  |
| Ruby / Rails         | `task-rails-test`   |
| Node.js / TypeScript | `task-node-test`    |
| Go / Gin             | `task-go-test`      |
| Rust / Axum          | `task-rust-test`    |
| .NET / ASP.NET Core  | `task-dotnet-test`  |
| PHP / Laravel        | `task-laravel-test` |
| React                | `task-react-test`   |
| Vue                  | `task-vue-test`     |
| Angular              | `task-angular-test` |

Forward the user's invocation and spec context. The dispatched workflow owns the output. **If matched and available, stop. Skip Step 5.** If the matched workflow is unavailable (plugin not installed), name the plugin that provides it, then run Step 5 using the detected stack's idioms.

### Step 5 - Generic Fallback (no dispatch match)

**Pyramid.** Unit (many) > Integration (some) > E2E (few). Unit covers pure logic, validation, branch-heavy domain code, isolated error handling. Integration covers DB queries against a real schema, HTTP endpoints end-to-end, external service clients (stubs or contract tests), auth filters. E2E covers only critical business flows (checkout, login, data export) - keep this layer small.

**Prioritization when coverage is low** (do not chase a coverage number):

1. Business-critical paths (revenue, data integrity, auth)
2. Error-prone areas (recent bug history, complex branching, integration points)
3. High-change areas (git churn, shared utilities)
4. Plumbing and glue code last

**Untestable legacy code.** Budget a testability refactor (extract dependencies behind interfaces, isolate I/O from logic) before adding tests. Pin current behavior with characterization tests before any refactor.

**Contract tests are mandatory for:** HTTP APIs consumed by independently-deployed teams; event/message schemas with separate producer/consumer deploys; shared client libraries imported by other services. Cover happy path, provider error (4xx/5xx), and forward-compatible schema evolution.

For test scaffolds, use the project's existing test framework if detectable, else the detected language's conventional one. For pasted code with no project context, infer the language from the snippet. Always state assumed language and framework.

## Output Format

When Step 4 dispatched: the stack workflow owns the output. When fallback ran, produce the section matching the user's ask:

```markdown
## Test Coverage Assessment

**Stack:** {detected stack or unknown} (generic fallback applied)
**Coverage gaps:**

- [Layer / component]: [what is missing and why it matters]

## Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Integration {y}% / E2E {z}%
**Contract testing:** [required / not required - rationale]
**Gaps to close (prioritized):**

1. [Highest-risk gap]
2. ...
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: spec-aware preamble loaded iff `--spec` or `.specs/<slug>/` present
- [ ] Step 3: `stack-detect` ran
- [ ] Step 4: if matched and available, stack workflow ran with invocation and spec context forwarded; Step 5 skipped
- [ ] Step 5: if not dispatched, output covers pyramid balance + prioritized gaps (or scaffolds with a stated framework), matching the user's ask

## Avoid

- Running both Step 4 dispatch and Step 5 fallback
- Producing findings when a stack workflow was dispatched
- Falling through to Step 5 when a table row matched and its workflow is available - the table is authoritative
- Chasing a coverage number instead of prioritizing by risk
- Treating the fallback as equivalent to a stack workflow
