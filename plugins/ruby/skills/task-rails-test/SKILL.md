---
name: task-rails-test
description: Rails test plan and scaffolding: RSpec, FactoryBot, Shoulda-matchers, Pundit policy specs, Sidekiq job specs; coverage gap analysis.
agent: rails-test-engineer
metadata:
  category: backend
  tags: [ruby, rails, rspec, factorybot, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing.
>
> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble`. When a spec is loaded, generate one test per acceptance criterion (use `Satisfies: AC<N>` mapping in test names), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md`; surface coverage gaps as proposed amendments.

# Rails Test

Rails-aware test strategy and scaffolding using RSpec, FactoryBot, Shoulda-matchers, Pundit policy specs, Sidekiq testing, and the Rails test pyramid (model / request / system / service / job / policy).

Stack-specific delegate of `task-code-test` for Ruby/Rails.

## When to Use

- Designing a test strategy for a new service or module
- Assessing coverage gaps across model / request / service / policy / job specs
- Scaffolding RSpec specs for under-covered controllers or services
- Reviewing test pyramid balance
- Adding boundary tests (validation, authorization, edge cases) to existing happy-path specs

**Not for:** test failure debugging (`task-rails-debug`), general review (`task-code-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-test`.

### Step 2 - Rails Test Pyramid

| Layer       | RSpec spec types                                            | What belongs here                                                                  |
| ----------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Unit        | model specs, service specs, policy specs, job specs         | Validations, scopes, business rules, Pundit policies, idempotent job behavior      |
| Integration | request specs, system specs (subset)                        | Routing, controller -> service -> model -> DB end-to-end; authorization end-to-end |
| E2E         | system specs with `js: true` (Capybara + Selenium/Cuprite)  | Critical journeys only - checkout, signup, payment, data export                    |

**Many** unit, **some** request, **few** system. System specs with JS are slow and brittle.

### Step 3 - Apply Test Patterns

Use skill: `rails-testing-patterns` for canonical recipes. Strategy-side rules on top:

- **Model specs**: no AR mocking - FactoryBot real records; behavior-focused names
- **Service specs**: one example per Result outcome (success / validation failure / external failure); stub HTTP at the boundary, never AR
- **Request specs**: one example per `(action, role, outcome)`; "rejects unpermitted attributes" for any controller using `permit`; assert key fields + status + Content-Type, not full body
- **Policy specs**: one example per `(role, action, allow|deny)` - cover every action, no implicit allows
- **Job specs**: idempotency assertion (call `perform` twice, side effect once); bounded retry per `sidekiq_options retry: N`
- **System specs**: one per critical journey; Cuprite over Selenium; query by role/label/text, not CSS

### Step 4 - Test Boundaries

**Unit (model/service/policy/job):**
- Model validations, scopes, custom methods, callbacks
- Service objects (one example per Result outcome)
- Pundit policies (one per role x action)
- Sidekiq idempotency, argument handling, retry

**Request spec:**
- Every controller action: happy + unauthorized + validation-error
- Auth flows (login, logout, password reset)
- API contract assertions (response shape, status, headers)

**System spec:**
- Critical journeys: signup, checkout, payment, core data export
- Multi-page stateful UI behavior
- **Not**: form-field validation, button states, individual component behavior - test those at lower layers

**Does NOT need a test:**
- Rails-provided behavior: `belongs_to` association loading, default routing, default Devise endpoints (test you wired them up via request specs, not that they work)
- Generated boilerplate
- Trivial delegation: `delegate :name, to: :user` (framework guarantees it)

### Step 5 - FactoryBot

See `rails-testing-patterns` for shape. Strategy:

- One factory per model; **traits** for variations - never duplicated factories
- Default factory builds *valid record with minimum attributes* (no associations unless required for validity)
- `build_stubbed` for unit (fastest), `build` when associations matter without DB, `create` only when persistence is required
- `create_list(:foo, 100)` in a unit spec signals the test belongs at integration layer

### Step 6 - Prioritization (when coverage is low)

If line coverage is below ~50%, run this **before scaffolding** - it determines which specs to scaffold first. Scaffolding alphabetically is wrong when authorization holes go unspec'd while plumbing controllers get full coverage.

1. **Authorization and authentication**: Pundit policy specs for every API-exposed model; request specs asserting unauthorized -> 403/404 on every protected action; Devise/JWT flow specs
2. **Data integrity**: model validations + unique-constraint enforcement; services performing writes (one happy + one failure per write); Sidekiq jobs that mutate data (idempotency + retry)
3. **Business-critical flows**: revenue paths (checkout, billing, subscription state transitions); multi-step state machines (`AASM` / `StateMachines`)
4. **High-churn code**: files with frequent recent commits (`git log --since="3 months ago"`); files with bug-fix history (`git log --grep="fix"`)
5. **Plumbing**: pass-through controllers, simple CRUD - lower risk, can wait

### Step 6.5 - API Contract Testing

For Rails apps with public or partner APIs, plain request specs assert "this endpoint returned 200 with these fields today" - they don't catch contract drift (renamed key, status 200->204, new required parameter).

| Tool         | Approach                                                                                       | Tradeoff                                          |
| ------------ | ---------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `rswag`      | Specs declare OpenAPI schema inline; `rake rswag:specs:swaggerize` exports `swagger.yaml`      | Docs + contract test in one. Verbose DSL          |
| `committee`  | Specs validate request and response against existing `swagger.yaml`/OpenAPI                    | Source of truth in schema file; specs assert      |
| Hand-rolled  | `expect(json_response).to match_schema(...)` with `json-schema`                                | Explicit. Fine for small APIs                     |

Pick one - drift catches latent client breakage. Skip for internal/admin-only apps where the API has one consumer (the frontend) and contract drift is caught by the frontend's tests.

### Step 7 - Test Infrastructure Hygiene

- [ ] `database_cleaner-active_record` configured (or `use_transactional_fixtures = true` for unit + request)
- [ ] `Sidekiq::Testing` configured (default `:fake`; `:inline` per-spec when end-to-end needed)
- [ ] WebMock/VCR disable real HTTP (`WebMock.disable_net_connect!(allow_localhost: true)` in `rails_helper.rb`)
- [ ] **Faraday adapter / SDK clients that bypass WebMock**: WebMock intercepts at `Net::HTTP` (and `http`/`excon`/`patron`/`typhoeus`/`curb` via adapter shims). A Faraday connection with `:typhoeus` / `:em_http` / `:patron` uses that transport directly; unless WebMock's matching adapter is loaded, real HTTP escapes. `aws-sdk-*` uses `Net::HTTP` by default but can be configured with custom handlers; gRPC uses its own C-extension. Confirm by writing one stubbed test and asserting the stub fired (`expect(stub).to have_been_requested`); if not, install the matching WebMock adapter, switch the Faraday adapter back to `:net_http` in test, or stub the SDK client directly. Silent passthrough is how production credentials leak into CI
- [ ] `example_status_persistence_file_path` for `--only-failures`
- [ ] `bin/rspec --order random` - tests pass in any order
- [ ] CI runs full suite; local default runs fast unit + request (use `slow:`, `system:` tags to skip)
- [ ] Parallelism: `parallel_tests` or RSpec built-in for suites > 5 minutes

## Review Checklist

For existing specs:

- [ ] Spec types match what's being tested (model -> model spec, controller -> request spec, not deprecated controller spec)
- [ ] Every controller action has request spec with happy + unauthorized + validation-error
- [ ] Every Pundit policy has policy spec covering every action x every role
- [ ] Every Sidekiq job has an idempotency spec
- [ ] FactoryBot uses traits, not duplicated factories
- [ ] No `allow(SomeModel).to receive(:find).and_return(...)` - mocking AR is a smell
- [ ] No `it { should ... }` chains > 5 deep (split into describe blocks)
- [ ] System specs minimal; critical journeys only

## Output Format

Which output to produce:
- "What tests are missing?" / "review our test coverage" -> Coverage Assessment
- "Write tests for X" / "scaffold specs" -> Test Scaffolds
- "Test strategy" / "test plan" / coverage below 50% -> Strategy Doc (optionally with Coverage Assessment)
- Unclear: Strategy Doc

**Coverage Assessment:**

```markdown
## Rails Test Coverage Assessment

**Stack:** Ruby <version> / Rails <version>
**Test framework:** RSpec <version>, FactoryBot, Shoulda-matchers
**Coverage gaps:**

- **Model specs:** [models without coverage]
- **Request specs:** [controllers without coverage; missing unauthorized-path examples]
- **Policy specs:** [Pundit policies without coverage]
- **Service specs:** [services without coverage]
- **Job specs:** [Sidekiq jobs without idempotency specs]
- **System specs:** [critical journeys without coverage]

**Recommended pyramid balance:**

- Unit (model/service/policy/job): [target count]
- Integration (request): [target count]
- E2E (system): [target count - keep small]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run RSpec files using project conventions. Each scaffold includes:

- Right spec type (`type: :model`, `type: :request`, `type: :policy`, `type: :job`, `type: :system`)
- FactoryBot calls (with traits) instead of `Model.new(...)`
- Model specs: shoulda-matchers for validations and associations
- Request specs: happy path + unauthorized + validation-error
- Policy specs: every `(role, action)` pair
- Job specs: idempotency + retry-behavior
- Inline comments explaining non-obvious setup

**Strategy Doc:**

```markdown
## Rails Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit (model/service/policy/job) {x}% / Request {y}% / System {z}%
**Tooling:** RSpec, FactoryBot (traits), Shoulda-matchers, pundit-matchers, WebMock/VCR, Cuprite
**Sidekiq testing:** default `:fake`, `:inline` per-spec for end-to-end
**Database isolation:** [transactional fixtures | database_cleaner truncation]
**Parallelism:** [parallel_tests | none]
**Gaps to close (prioritized):**

1. [Highest risk - typically authorization or data integrity]
2. [...]
```

## Self-Check

- [ ] Stack confirmed
- [ ] `rails-testing-patterns` consulted for canonical patterns
- [ ] Pyramid mapped to RSpec spec types (model/service/policy/job at unit, request at integration, system minimal at E2E)
- [ ] Boundaries defined: each layer covers what it does best; no duplicated assertions
- [ ] Prioritization by risk applied when coverage is low - auth and data integrity first, plumbing last
- [ ] FactoryBot: traits over duplicated factories; `build_stubbed` vs `build` vs `create` choice explicit
- [ ] Sidekiq approach explicit (`:fake` default, `:inline` per-spec)
- [ ] Test scaffolds (if generated): happy + unauthorized + validation-error; idempotency for jobs; per-role for policies
- [ ] Spec-aware mode honored when `--spec` passed (one example per AC, NFR coverage from plan.md, no out-of-scope)
- [ ] Review checklist applied when reviewing existing specs

## Avoid

- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no policy specs misses the bigger threat
- Mocking AR in model or service specs - use FactoryBot and real DB
- Controller specs (deprecated) - use request specs
- Duplicating factories instead of using traits
- `create` everywhere when `build_stubbed` would do - slow tests are abandoned tests
- System specs for things that should be request specs (form validation, error message rendering)
- Testing Rails internals - test your wiring, not the framework
- Happy-path-only request specs - boundary tests catch the regressions that matter
- Skipping policy specs because the controller has request specs - policies are unit-tested separately
