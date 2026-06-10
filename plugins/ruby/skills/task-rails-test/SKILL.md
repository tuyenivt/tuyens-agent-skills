---
name: task-rails-test
description: Plan Rails test strategy and scaffold RSpec/FactoryBot/Shoulda/Pundit/Sidekiq specs; assess coverage gaps by risk.
agent: rails-test-engineer
metadata:
  category: backend
  tags: [ruby, rails, rspec, factorybot, testing, workflow]
  type: workflow
user-invocable: true
---

# Rails Test Strategy

Stack-specific delegate of `task-code-test`. Risk-prioritized test planning, coverage assessment, and RSpec scaffolding for Rails apps.

## When to Use

- Test strategy for a new service or module
- Coverage-gap assessment across model / request / service / policy / job / system
- Scaffolding RSpec specs for under-covered controllers or services
- Adding boundary tests (authorization, validation, edge cases) to happy-path specs
- Reviewing test pyramid balance

Not for: test failure debugging (`task-rails-debug`), general code review (`task-code-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Behavioral Principles
Use skill: `behavioral-principles`.

### Step 2 - Stack Detect
Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-test`.

### Step 3 - Spec-Aware Mode
If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the code under test: use skill `spec-aware-preamble`. Generate one example per acceptance criterion (`Satisfies: AC<N>` in test names), cover every NFR via `plan.md` verification steps, refuse tests for out-of-scope behavior. Never edit `spec.md`/`plan.md`/`tasks.md`; surface coverage gaps as proposed amendments.

### Step 4 - Pyramid

| Layer       | RSpec types                                          | What belongs                                                                  |
| ----------- | ---------------------------------------------------- | ----------------------------------------------------------------------------- |
| Unit        | model, service, policy, job                          | Validations, scopes, rules, Pundit policies, idempotent job behavior          |
| Integration | request, system (subset)                             | Controller -> service -> model -> DB; authorization end-to-end                |
| E2E         | system with `js: true` (Capybara + Cuprite/Selenium) | Critical journeys only - checkout, signup, payment, data export               |

**Many** unit, **some** request, **few** system. System with JS are slow and brittle.

### Step 5 - Strategy per Spec Type

Use skill: `rails-testing-patterns` for recipes (FactoryBot traits, shoulda-matchers, Pundit/Sidekiq idioms). Strategy rules on top:

- **Model**: real FactoryBot records, no AR mocking; behavior-focused names
- **Service**: one example per Result outcome (success / validation failure / external failure); stub HTTP at the boundary, never AR
- **Request**: one example per `(action, role, outcome)`; "rejects unpermitted attributes" for any `permit`; assert key fields + status + Content-Type, not full body
- **Policy**: one example per `(role, action, allow|deny)` - cover every action, no implicit allows
- **Job**: idempotency (call `perform` twice, side effect once); bounded retry per `sidekiq_options retry:`
- **System**: one per critical journey; Cuprite over Selenium; query by role/label/text, not CSS

### Step 6 - Boundaries

**Needs a test:** model validations/scopes/methods/callbacks; service Result branches; Pundit `(role x action)`; Sidekiq idempotency / arg shape / retry; every controller action (happy + unauthorized + validation-error); auth flows; API contract (shape, status, headers); critical journeys.

**Does NOT need a test:** Rails-provided behavior (default routing, `belongs_to` loading, default Devise endpoints - test you wired them up, not that they work); generated boilerplate; trivial delegation (`delegate :name, to: :user`).

### Step 7 - Prioritize by Risk (coverage < ~50%)

Run **before scaffolding**. Alphabetical is wrong when authorization holes go unspec'd while plumbing gets full coverage.

1. **Authorization/authentication** - Pundit policy specs for every API-exposed model; request specs asserting 403/404 on every protected action; Devise/JWT flow specs; inbound webhook signature verification (invalid/missing signature -> 401)
2. **Data integrity** - model validations + unique-constraint enforcement; write services (one happy + one failure); Sidekiq mutating jobs (idempotency + retry)
3. **Business-critical flows** - revenue (checkout, billing, subscription transitions); multi-step state machines (AASM, `state_machines`)
4. **High-churn code** - frequent recent commits (`git log --since="3 months ago"`); bug-fix history (`git log --grep=fix`)
5. **Plumbing** - pass-through controllers, simple CRUD - lower risk, can wait

### Step 8 - API Contract (public/partner APIs)

Plain request specs don't catch drift (renamed key, status 200->204, new required parameter). Pick one:

| Tool        | Approach                                                                       |
| ----------- | ------------------------------------------------------------------------------ |
| `rswag`     | Declare OpenAPI inline; `rake rswag:specs:swaggerize` exports `swagger.yaml`   |
| `committee` | Validate request/response against existing OpenAPI schema                      |
| Hand-rolled | `match_schema(...)` with `json-schema`                                         |

Skip for internal/admin apps with a single frontend consumer where drift is caught by frontend tests.

### Step 9 - Infrastructure Hygiene

When `rails_helper.rb`/CI config isn't in evidence, emit this as a confirm-checklist - don't claim items verified.

- [ ] DB isolation: transactional fixtures (default; matches `rails-testing-patterns`) or `database_cleaner-active_record` truncation only for cross-connection state
- [ ] `Sidekiq::Testing` defaults to `:fake`; `:inline` per-spec when end-to-end needed. A global `inline!` is a finding, not a pass
- [ ] `WebMock.disable_net_connect!(allow_localhost: true)` in `rails_helper.rb`; existing live third-party calls migrate to boundary stubs (WebMock on the client) or VCR cassettes
- [ ] **Verify HTTP stubs intercept.** WebMock matches `Net::HTTP` and adapter shims. Faraday with `:typhoeus`/`:em_http`/`:patron`, custom `aws-sdk-*` handlers, and gRPC bypass WebMock silently. Write one stubbed test, assert `expect(stub).to have_been_requested` - if not, install the matching adapter, switch Faraday to `:net_http` in test, or stub the SDK client. Silent passthrough leaks production credentials into CI
- [ ] `example_status_persistence_file_path` for `--only-failures`
- [ ] `--order random` - tests pass in any order
- [ ] CI runs full suite; local default runs fast unit + request (use `slow:`/`system:` tags)
- [ ] Parallelism: `parallel_tests` or RSpec built-in for suites > 5 minutes

### Step 10 - Choose Output

| Request                                              | Output                       |
| ---------------------------------------------------- | ---------------------------- |
| "What tests are missing?" / "review coverage"        | Coverage Assessment          |
| "Write tests for X" / "scaffold specs"               | Test Scaffolds               |
| "Test strategy" / "test plan" / coverage < 50%       | Strategy Doc (+ Assessment)  |
| Reviewing existing specs                             | Review Checklist (below)     |

When several rows match, produce the most comprehensive (Strategy Doc subsumes Assessment). Review mode emits checklist findings + Step 9 infra findings; add an Assessment block only when coverage gaps are visible in the evidence. Policy/source files not shown: scaffold the known roles and mark unknowns `# TODO: confirm role`.

**Review Checklist (existing specs):**

- [ ] Spec types match (model -> model spec, controller -> request spec; no deprecated controller specs)
- [ ] Every controller action: happy + unauthorized + validation-error
- [ ] Every Pundit policy: every action x every role
- [ ] Every mutating Sidekiq job: idempotency spec
- [ ] FactoryBot uses traits (not duplicated factories); default builds a valid record with minimum attributes
- [ ] `build_stubbed` for unit, `build` when associations matter without DB, `create` only when persistence required
- [ ] No `allow(SomeModel).to receive(:find)...` - mocking AR is a smell
- [ ] No `it { should ... }` chains > 5 deep (split into describes)
- [ ] System specs minimal; critical journeys only

## Output Format

**Coverage Assessment:**

```markdown
## Rails Test Coverage Assessment

**Stack:** Ruby <version> / Rails <version>
**Framework:** RSpec <version>, FactoryBot, Shoulda-matchers
**Gaps:**
- **Model:** [uncovered models]
- **Request:** [uncovered actions; missing unauthorized examples]
- **Policy:** [uncovered Pundit policies]
- **Service:** [uncovered services]
- **Job:** [Sidekiq jobs without idempotency specs]
- **System:** [critical journeys not covered]

**Pyramid target:** Unit {x}% / Request {y}% / System {z}%
```

**Review (existing specs):** numbered findings tagged `[Critical | High | Medium]`, infra findings (Step 9) first, spec findings (checklist) after; when the user reported a symptom ("CI green, staging breaks"), open with one line tying the top findings to it. Append the Assessment block only when coverage gaps are visible in the evidence.

**Test Scaffolds:** ready-to-run RSpec files using project conventions. Each scaffold:

- Correct spec type (`type: :model | :request | :policy | :job | :system`)
- FactoryBot with traits (not `Model.new`)
- Model: shoulda-matchers for validations and associations
- Request: happy + unauthorized + validation-error
- Policy: every `(role, action)` pair
- Job: idempotency + retry behavior
- Inline comments only for non-obvious setup

**Strategy Doc:**

```markdown
## Rails Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid:** Unit {x}% / Request {y}% / System {z}%
**Tooling:** RSpec, FactoryBot (traits), Shoulda-matchers, pundit-matchers, WebMock/VCR, Cuprite
**Sidekiq:** default `:fake`, `:inline` per-spec for end-to-end
**DB isolation:** [transactional fixtures | database_cleaner truncation]
**Parallelism:** [parallel_tests | none]
**Gaps to close (prioritized):**
1. [Highest risk - typically authorization or data integrity]
2. [...]
```

## Self-Check

- [ ] Step 1-2: behavioral-principles loaded; stack confirmed
- [ ] Step 3: spec-aware mode honored when applicable
- [ ] Step 4: pyramid mapped to spec types
- [ ] Step 5: `rails-testing-patterns` consulted; per-type strategy applied
- [ ] Step 6: boundaries defined; no duplicated assertions across layers
- [ ] Step 7: risk prioritization applied when coverage is low
- [ ] Step 8: API contract approach chosen (or skip rationale stated)
- [ ] Step 9: infra hygiene confirmed - HTTP stubs verified to intercept
- [ ] Step 10: output type matches request; Review Checklist applied when reviewing

## Avoid

- Chasing a coverage number instead of prioritizing by risk
- Mocking AR in model or service specs - use FactoryBot and real DB
- Deprecated controller specs - use request specs
- Duplicating factories instead of traits
- `create` everywhere when `build_stubbed` would do - slow tests are abandoned tests
- System specs for things that belong at the request layer (form validation, error rendering)
- Testing Rails internals - test your wiring, not the framework
- Happy-path-only request specs - boundary tests catch the regressions that matter
- Skipping policy specs because the controller has request specs - policies are unit-tested separately
