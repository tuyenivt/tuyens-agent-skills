---
name: task-code-test
description: Test entry point: strategy, scaffolding, coverage review. Detects stack and dispatches to stack-specific test workflow.
metadata:
  category: review
  tags: [testing, test-strategy, unit-test, integration-test, multi-stack, router]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles` and propagate the spec context to the dispatched stack workflow.

# Code Test (Router)

This skill is a thin dispatcher. It detects the project stack and delegates the entire workflow to the matching stack-specific skill (e.g., `task-spring-test`, `task-rails-test`, `task-react-test`). The stack workflow names ecosystem idioms (RSpec, JUnit, pytest, Vitest, etc.) and applies framework-aware test patterns directly.

For unknown or unrecognized stacks, this skill falls back to a minimal generic protocol so any project can still use the command.

## When to Use

- Test coverage evaluation, test strategy design, generating test scaffolds, test pyramid balance review.
- Use this entry point when you want one command that adapts to the project. If you already know the stack, calling the stack-specific workflow directly (e.g., `/task-spring-test`) skips the routing layer.

**Not for:** General code quality review (use `task-code-review`), performance review (use `task-code-review-perf`), security review (use `task-code-review-security`).

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and `Stack Type`.

### Step 2 - Dispatch to Stack Workflow

If the detected stack matches the table below, delegate the full workflow to the named skill, propagate any spec context, and stop. The dispatched workflow owns the output.

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

If a match is found, do not run Step 3.

### Step 3 - Generic Fallback (unknown stack only)

Run only when Step 2 finds no match. This is a minimum-viable test strategy that works for any language.

**Testing pyramid:** Unit (many) → Integration (some) → E2E (few). Most tests should be fast unit tests; integration tests cover boundaries; E2E covers only critical user flows.

**Boundary guidance:**

- **Unit:** pure logic, validation rules, branch-heavy domain code, error handling in isolation.
- **Integration:** database queries against a real schema, HTTP endpoints end-to-end, external service clients (use stubs or contract tests), auth/authorization filters.
- **E2E:** critical business flows only (checkout, login, data export). Each E2E test is expensive to maintain - keep this layer small.

**Prioritization when coverage is low** (do not chase a coverage number):

1. Business-critical paths (revenue, data integrity, auth).
2. Error-prone areas (recent bug history, complex branching, integration points).
3. High-change areas (high git churn, shared utilities).
4. Plumbing and glue code last.

**Untestable legacy code:** budget a testability refactor (extract dependencies behind interfaces, isolate I/O from logic) before adding tests. Characterization tests pin current behavior before any refactor.

**Contract tests** are mandatory for: HTTP APIs consumed by independently-deployed teams, event/message schemas with separate producer/consumer deploys, shared client libraries imported by other services. Cover happy path, provider error (4xx/5xx handling), and forward-compatible schema evolution.

## Output Format

When dispatched (Step 2 matched): the stack-specific workflow owns the output format. This skill produces no output of its own.

When fallback runs (Step 3): produce the section that matches the user's ask:

```markdown
## Test Coverage Assessment

**Stack:** unknown (generic fallback applied)
**Coverage gaps:**

- [Layer / component]: [what is missing and why it matters]

## Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Integration {y}% / E2E {z}%
**Contract testing:** [required / not required - rationale]
**Gaps to close (prioritized):**

1. [Highest risk gap]
2. ...
```

For test scaffolds, produce ready-to-run files using the project's existing test framework if one is detectable; otherwise state the assumed framework explicitly.

## Self-Check

- [ ] `behavioral-principles` loaded before any other step
- [ ] Spec-aware preamble loaded when `--spec` was passed or `.specs/<slug>/` exists
- [ ] `stack-detect` ran at Step 1
- [ ] If a stack matched, the dispatched workflow ran and Step 3 was skipped
- [ ] If no stack matched, Step 3 fallback ran and produced a Strategy Doc / Coverage Assessment / Scaffolds appropriate to the user's ask
- [ ] Spec context (if any) was propagated to the dispatched workflow

## Avoid

- Running both Step 2 dispatch and Step 3 fallback (one or the other, never both)
- Producing your own findings when a stack workflow was dispatched - that workflow owns the output
- Falling through to Step 3 when stack-detect returned a known stack but the dispatch table entry feels imperfect; the table is authoritative
- Treating the fallback as a full equivalent of a stack workflow - it is a temporary bridge for unsupported stacks; the user should install the matching language plugin when one exists
