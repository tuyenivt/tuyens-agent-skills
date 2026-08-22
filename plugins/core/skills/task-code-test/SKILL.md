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

`/task-code-test [<file or path>]`

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and `Stack Type`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to         |
| -------------------- | ------------------- |
| Java / Spring Boot   | `task-spring-test`  |
| Python               | `task-python-test`  |
| Ruby / Rails         | `task-rails-test`   |
| Node.js / TypeScript | `task-node-test`    |
| Go / Gin             | `task-go-test`      |
| React / Next.js      | `task-react-test`   |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework. When the ask targets pasted or out-of-repo code whose language differs from the detected stack, skip dispatch - noting it in one line (`Pasted code is Python - scaffolding directly.`) - and run Step 4 with the snippet's inferred language. When the matched row's workflow resolves, announce the dispatch in one line (`Dispatching to task-rails-test.` - substitute the target name), then forward the user's invocation unchanged - path argument and ask. The announcement is the router's only output; the detection block stays internal. The dispatched workflow owns the output. **If matched and available, stop. Skip Step 4.** If the matched workflow is unavailable (plugin not installed), name the plugin that provides it, then run Step 4 using the detected stack's idioms. When no row matches at all, note it in one line (`No stack test workflow for <stack> - generic fallback.`) and run Step 4.

### Step 4 - Generic Fallback (no dispatch match)

**Ground the assessment first** (in-repo targets only - pasted code has no tree to map). Locate the test tree and map it against the target path (or, when no path was given, the highest-risk modules - risk per the prioritization list below); every coverage gap cites a specific untested surface - never pyramid theory alone.

**Pyramid.** Unit (many) > Integration (some) > E2E (few). Unit covers pure logic, validation, branch-heavy domain code, isolated error handling. Integration covers DB queries against a real schema, HTTP endpoints end-to-end, external service clients (stubs or contract tests), auth filters. E2E covers only critical business flows (checkout, login, data export) - keep this layer small. For `Stack Type: frontend` or `fullstack` targets, Use skill: `frontend-testing-patterns`.

**Prioritization when coverage is low** (do not chase a coverage number):

1. Business-critical paths (revenue, data integrity, auth)
2. Error-prone areas (recent bug history, complex branching, integration points)
3. High-change areas (git churn, shared utilities)
4. Plumbing and glue code last

**Untestable legacy code.** Budget a testability refactor (extract dependencies behind interfaces, isolate I/O from logic) before adding tests. Pin current behavior with characterization tests before any refactor.

**Contract tests are mandatory for:** HTTP APIs consumed by independently-deployed teams; event/message schemas with separate producer/consumer deploys; shared client libraries imported by other services. Cover happy path, provider error (4xx/5xx), and forward-compatible schema evolution. A client consuming an external third party needs stub-based tests; a contract suite only when that provider publishes a verifiable contract.

For test scaffolds, use the project's existing test framework when it matches the scaffold's language, else that language's conventional one. For pasted code with no project context, infer the language from the snippet.

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran, produce every templated section the ask maps to (coverage ask -> Test Coverage Assessment; strategy ask -> Test Strategy; a two-part ask covering both produces both, as does an ask naming no deliverable). A scaffolding ask produces neither templated section - output the test files as fenced code blocks in chat (nothing written to disk), the line `**Assumed framework:** <language> / <test framework>`, and an `Assumptions:` list covering behavior and environment inferred (raise types, rounding, import path, framework choice).

```markdown
## Test Coverage Assessment

**Stack:** {detected stack or unknown} (generic fallback applied)

**Covered today:** [1-2 lines - what the existing test tree already covers]

**Coverage gaps:**

- [Layer / component]: [what is missing and why it matters]

## Test Strategy

**Objective:** [what this strategy achieves]

**Pyramid balance (target):** Unit {x}% / Integration {y}% / E2E {z}% (default 70/20/10 unless the codebase's risk profile justifies otherwise - state why)

**Contract testing:** [required / not required - rationale]

**Gaps to close (prioritized):**

1. [Highest-risk gap]
2. ...
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched and available, stack workflow ran with invocation forwarded and Step 4 skipped - unless the pasted-code override fired, in which case dispatch was skipped and Step 4 ran
- [ ] Step 4: if not dispatched, output covers pyramid balance + prioritized gaps (or scaffolds with a stated framework), matching the user's ask

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Producing findings when a stack workflow was dispatched
- Falling through to Step 4 when a table row matched and its workflow is available - the table is authoritative for in-repo targets (pasted out-of-repo code follows the Step 3 override)
- Chasing a coverage number instead of prioritizing by risk
- Treating the fallback as equivalent to a stack workflow
