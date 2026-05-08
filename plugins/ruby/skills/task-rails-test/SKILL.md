---
name: task-rails-test
description: Rails-specific test strategy and scaffolding using RSpec, FactoryBot, Shoulda-matchers, Pundit policy specs, and Sidekiq job specs. Use when designing a Rails test plan, assessing coverage gaps, or scaffolding model/request/service/job/policy specs. Stack-specific override of task-code-test, invoked when stack-detect resolves to Ruby/Rails.
agent: rails-test-engineer
metadata:
  category: backend
  tags: [ruby, rails, rspec, factorybot, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `Satisfies: AC<N>` mapping in test names), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Rails Test

## Purpose

Rails-aware test strategy and scaffolding using RSpec idioms, FactoryBot, Shoulda-matchers, Pundit policy specs, Sidekiq job testing, and the Rails test pyramid (model / request / system / service / job / policy). Replaces the generic backend test patterns with Rails-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for Ruby/Rails. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a Rails test strategy for a new service or module
- Assessing test coverage gaps across model / request / service / policy / job specs
- Scaffolding RSpec specs for under-covered controllers or services
- Reviewing test pyramid balance for a Rails app
- Adding boundary tests (validation, authorization, edge cases) to existing happy-path specs

**Not for:**

- Test failure debugging (use `task-rails-debug`)
- General code review (use `task-code-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Ruby / Rails. If the detected stack is not Rails, stop and tell the user to invoke `/task-code-test` instead.

### Step 2 - Rails Test Pyramid

The Rails test pyramid maps to RSpec spec types:

| Layer       | RSpec spec types                                             | What belongs here                                                                  |
| ----------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Unit        | model specs, service specs, policy specs, job specs          | Validations, scopes, business rules, Pundit policies, idempotent job behavior      |
| Integration | request specs, system specs (subset)                         | Routing, controller -> service -> model -> DB end-to-end; authorization end-to-end |
| E2E         | system specs with `js: true` (Capybara + Selenium / Cuprite) | Critical user journeys only - checkout, signup, payment, data export               |

**Many** unit specs, **some** request specs, **few** system specs. System specs with JS are slow and brittle - use sparingly.

### Step 3 - Apply Rails Test Patterns

Use skill: `rails-testing-patterns` for the canonical patterns referenced below.

**Model specs (`spec/models/`):**

- Validations via shoulda-matchers: `it { should validate_presence_of(:email) }`
- Associations via shoulda-matchers: `it { should belong_to(:user) }`
- Scopes: arrange records that match and don't match; assert the scope returns the right set
- Custom methods: behavior-focused names (`describe '#full_name'`, `it 'concatenates first and last'`)
- **No mocking of ActiveRecord** in model specs - use FactoryBot to create real records

**Service specs (`spec/services/`):**

- Test the public interface (`.call` returning a Result object) - one example per outcome (success, validation failure, external failure)
- Stub external HTTP calls with WebMock/VCR; do **not** stub ActiveRecord
- Verify post-conditions: records created, emails enqueued, jobs scheduled

**Request specs (`spec/requests/`):**

- One example per `(action, role, outcome)` triple - covers routing, controller, serializer, auth, authz end-to-end
- Authentication: helper that signs in a user (`sign_in user` for Devise, or set JWT header)
- Authorization: a separate example for "user without permission gets 403/404" per protected action
- Strong params: a "rejects unpermitted attributes" example for any controller using `permit`
- Response shape: assert key fields, status, and Content-Type - not the full body

**Policy specs (`spec/policies/`, when using Pundit):**

- Use `pundit-matchers` or hand-rolled `permissions :action? do ... end` blocks
- One example per `(role, action, allow|deny)` triple
- Cover every action defined in the policy - no implicit allows

**Job specs (`spec/jobs/`, `spec/sidekiq/`):**

- Test `perform` directly with the right arguments
- Idempotency: call `perform` twice with the same args; assert the side effect happened once
- Retry behavior: stub the dependency to raise; assert the job is retried (or marked dead) per `sidekiq_options retry: N`
- Use `Sidekiq::Testing.inline!` for end-to-end "controller enqueues -> job runs -> side effect" tests in request specs

**System specs (`spec/system/`):**

- One per critical user journey
- Use Capybara with Cuprite (faster than Selenium) when JS is needed
- Avoid CSS selectors; query by role, label, or text

### Step 4 - Test Boundaries (Rails-Specific)

**What deserves a unit (model/service/policy/job) spec:**

- Model validations, scopes, custom methods, callbacks
- Service objects (one example per `Result.success` / `Result.failure` outcome)
- Pundit policies (one example per role x action)
- Sidekiq job idempotency, argument handling, retry behavior

**What deserves a request spec:**

- Every controller action, with at least: happy path, unauthorized path, validation-error path
- Auth flows (login, logout, password reset)
- API contract assertions (response shape, status code, headers)

**What deserves a system spec:**

- Critical journeys: signup, checkout, payment, core data export
- Anything that spans multiple pages with stateful UI behavior
- **Not**: form-field validation, button states, individual component behavior - test those at lower layers

**What does NOT need a test:**

- Rails-provided behavior: `belongs_to` association loading, `has_many` association building, default routing, default Devise endpoints (test that you wired them up correctly via request specs, not that they work)
- Generated boilerplate: `app/channels/application_cable/connection.rb` defaults
- Trivial delegation: `delegate :name, to: :user` (the framework guarantees it)

### Step 5 - FactoryBot and Test Data

- One factory per model under `spec/factories/`
- Use **traits** for variations: `:admin`, `:with_orders`, `:archived` - never define separate factories for variants
- Default factory builds a valid record with minimum attributes - no associations unless required for validity
- Use `build_stubbed` for unit specs that don't need DB persistence (much faster)
- Use `build` when associations matter but DB hit is unnecessary
- Use `create` only when DB persistence is required (request specs, association queries, integration tests)
- **Avoid `create_list(:foo, 100)`** in unit specs - signals the test belongs at integration layer

### Step 6 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ specs to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go unspec'd while plumbing controllers get full coverage.

When starting from low test coverage, prioritize by Rails-specific risk:

**Priority 1 - Authorization and authentication:**

- Pundit policy specs for every model exposed via API
- Request specs asserting unauthorized users get 403/404 on every protected action
- Devise/JWT authentication flow specs

**Priority 2 - Data integrity:**

- Model validations and unique-constraint enforcement
- Service objects performing writes (one happy path + one failure per write)
- Sidekiq jobs that mutate data (idempotency + retry behavior)

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- Multi-step state machines (`AASM` / `StateMachines` gem)

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"` to identify)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through controllers, simple CRUD - lower risk, can wait

### Step 6.5 - API Contract Testing (when the project exposes an API)

For Rails apps with public or partner APIs, plain request specs assert "this endpoint returned 200 with these fields today" - they do not catch silent contract drift (a renamed JSON key, a status changed from 200 to 204, a new required parameter). Two common Rails approaches:

| Tool         | Approach                                                                              | Tradeoff                                                                              |
| ------------ | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `rswag`      | Specs declare the OpenAPI schema inline; `rake rswag:specs:swaggerize` exports `swagger.yaml` | Generates docs and acts as a contract test in one. Verbose DSL.                       |
| `committee`  | Specs validate request and response against an existing `swagger.yaml` / OpenAPI file | Source of truth lives in the schema file; specs assert conformance.                   |
| Hand-rolled  | `expect(json_response).to match_schema(...)` with `json-schema` gem                   | No generator, but explicit. Fine for small APIs.                                      |

Use one - drift catches latent client breakage long before integration partners notice. Skip this step for internal/admin-only Rails apps where the API has one consumer (the same team's frontend) and contract drift is caught by the frontend's own tests.

### Step 7 - Test Infrastructure Hygiene

- [ ] `database_cleaner-active_record` configured (or `use_transactional_fixtures = true` for unit + request specs)
- [ ] `Sidekiq::Testing` configured (default `:fake`; switch to `:inline` per-spec when end-to-end coverage is needed)
- [ ] WebMock/VCR configured to disable real HTTP in tests
- [ ] `RSpec.configure { |c| c.example_status_persistence_file_path = ... }` for `--only-failures` workflows
- [ ] `bin/rspec --order random` enabled - tests pass in any order
- [ ] CI runs full suite; local dev runs fast unit + request specs by default (use spec tags `slow:`, `system:` to skip)
- [ ] Parallelism: `parallel_tests` gem or RSpec built-in `--seed` parallelism for suites > 5 minutes

## Rails Review Checklist

Quick-reference checklist for reviewing existing Rails specs:

- [ ] Spec types match what is being tested (model -> model spec, controller -> request spec, not the deprecated controller spec)
- [ ] Every controller action has a request spec with at least happy + unauthorized + validation-error
- [ ] Every Pundit policy has a policy spec covering every action x every role
- [ ] Every Sidekiq job has an idempotency spec
- [ ] FactoryBot uses traits, not duplicated factories
- [ ] No `allow(SomeModel).to receive(:find).and_return(...)` patterns - mocking ActiveRecord is a smell
- [ ] No `it { should ... }` chains > 5 deep (split into describe blocks)
- [ ] System specs minimal; reserved for critical journeys

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold specs" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% -> Strategy Doc (optionally include Coverage Assessment)
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Rails Test Coverage Assessment

**Stack:** Ruby <version> / Rails <version>
**Test framework:** RSpec <version>, FactoryBot, Shoulda-matchers
**Coverage gaps:**

- **Model specs:** [models without spec coverage]
- **Request specs:** [controllers without spec coverage; controllers missing unauthorized-path examples]
- **Policy specs:** [Pundit policies without spec coverage]
- **Service specs:** [services without spec coverage]
- **Job specs:** [Sidekiq jobs without idempotency specs]
- **System specs:** [critical user journeys without coverage]

**Recommended pyramid balance:**

- Unit (model/service/policy/job): [count target]
- Integration (request): [count target]
- E2E (system): [count target - keep small]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run RSpec spec files using project conventions. Each scaffold must include:

- The right spec type (`type: :model`, `type: :request`, `type: :policy`, `type: :job`, `type: :system`)
- FactoryBot calls (with traits) instead of `Model.new(...)`
- For model specs: shoulda-matchers for validations and associations
- For request specs: happy path + unauthorized + validation-error examples
- For policy specs: every `(role, action)` pair
- For job specs: idempotency + retry-behavior examples
- Inline comments explaining non-obvious setup (e.g., why `Sidekiq::Testing.inline!` is needed for a particular request spec)

**Strategy Doc** (when designing a test strategy):

```markdown
## Rails Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit (model/service/policy/job) {x}% / Request {y}% / System {z}%
**Tooling:** RSpec, FactoryBot (traits-based), Shoulda-matchers, pundit-matchers, WebMock/VCR, Cuprite (system specs)
**Sidekiq testing:** default `:fake`, `:inline` per-spec for end-to-end
**Database isolation:** [transactional fixtures | database_cleaner truncation]
**Parallelism:** [parallel_tests | none]
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or data integrity]
2. [...]
```

## Self-Check

- [ ] Stack confirmed as Rails before any Rails-specific guidance applied
- [ ] `rails-testing-patterns` consulted for canonical RSpec/FactoryBot/Shoulda patterns
- [ ] Test pyramid mapped to RSpec spec types (model/service/policy/job at unit, request at integration, system minimal at E2E)
- [ ] Boundaries clearly defined: each spec layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - authorization and data integrity first, plumbing last
- [ ] FactoryBot guidance includes traits over duplicated factories; `build_stubbed` vs `build` vs `create` choice explicit
- [ ] Sidekiq testing approach explicit (`:fake` default, `:inline` per-spec)
- [ ] Test scaffolds (if generated) include happy path + unauthorized path + validation-error path; idempotency spec for jobs; per-role examples for policies
- [ ] Spec-aware mode honored when `--spec` was passed (one example per AC, NFR coverage from plan.md, no out-of-scope tests)
- [ ] Review checklist items addressed when reviewing existing specs

## Avoid

- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no policy specs misses the bigger threat
- Mocking ActiveRecord in model or service specs - use FactoryBot and a real database
- Writing controller specs (deprecated since Rails 5) - use request specs
- Duplicating factories instead of using traits (`UserFactoryAdmin` vs `:user, :admin`)
- Using `create` everywhere when `build_stubbed` would do - slow tests are abandoned tests
- System specs for things that should be request specs (form validation, error message rendering)
- Testing Rails internals (e.g., that `belongs_to` works, that routes resolve to controllers) - test your wiring, not the framework
- Writing happy-path-only request specs - boundary tests (unauthorized, invalid, not-found) catch the regressions that matter
- Skipping policy specs because the controller has request specs - policies are unit-tested separately so they can be reused
