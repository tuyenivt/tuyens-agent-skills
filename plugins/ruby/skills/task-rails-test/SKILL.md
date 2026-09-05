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

Risk-prioritized test planning, coverage assessment, and RSpec scaffolding for Rails apps.

## When to Use

- Test strategy for a new service or module
- Coverage-gap assessment across model / request / service / policy / job / system
- Scaffolding RSpec specs for under-covered controllers or services
- Adding boundary tests (authorization, validation, edge cases) to happy-path specs
- Reviewing test pyramid balance

Not for: test failure debugging, general code review (`task-code-review`).

## Workflow

### Step 1 - Behavioral Principles
Use skill: `behavioral-principles`.

### Step 2 - Stack Detect
Use skill: `stack-detect`. Accept pre-confirmed stack. If not Rails, stop and name the detected stack so the user can invoke that stack's test workflow.

### Step 3 - Pyramid

| Layer       | RSpec types                                          | What belongs                                                                  |
| ----------- | ---------------------------------------------------- | ----------------------------------------------------------------------------- |
| Unit        | model, service, policy, job                          | Validations, scopes, rules, Pundit policies, idempotent job behavior          |
| Integration | request, system (subset)                             | Controller -> service -> model -> DB; authorization end-to-end                |
| E2E         | system with `js: true` (Capybara + Cuprite/Selenium) | Critical journeys only - checkout, signup, payment, data export               |

**Many** unit, **some** request, **few** system. System with JS are slow and brittle.

Default pyramid target (by example count): ~70% unit / ~25% request / ~5% system. Adjust to app shape - API-only apps fold the system share into request; JS-heavy UIs may need more system. State the adjustment when you deviate.

### Step 4 - Strategy per Spec Type

Use skill: `rails-testing-patterns` for recipes (FactoryBot traits, shoulda-matchers, Pundit/Sidekiq idioms). Strategy rules on top:

- **Model**: real FactoryBot records, no AR mocking; behavior-focused names
- **Service**: one example per Result outcome (success / validation failure / external failure); stub HTTP at the boundary, never AR
- **Request**: one example per `(action, role, outcome)`; "rejects unpermitted attributes" for any `permit`; assert key fields + status + Content-Type, not full body. Signed webhooks: invalid/missing signature is the unauthorized example, malformed payload the validation-error one
- **Policy**: one example per distinct policy *outcome*, not per role - cover every action, no implicit allows; roles that resolve identically share one example or a shared example group (`rails-testing-patterns`)
- **Job**: idempotency (call `perform` twice, side effect once); bounded retry per `sidekiq_options retry:`
- **System**: one per critical journey; Cuprite over Selenium; query by role/label/text, not CSS

### Step 5 - Boundaries

**Needs a test:** model validations/scopes/methods/callbacks; service Result branches; Pundit: every action, one example per distinct outcome; Sidekiq idempotency / arg shape / retry; every controller action (happy + unauthorized + validation-error); auth flows; API contract (shape, status, headers); critical journeys.

**Does NOT need a test:** Rails-provided behavior (default routing, `belongs_to` loading, default Devise endpoints - test you wired them up, not that they work); generated boilerplate; trivial delegation (`delegate :name, to: :user`).

Assert each behavior at the lowest layer that can catch it; upper layers verify wiring, not re-assert logic (a request spec checks the 422, not every validation message).

### Step 6 - Prioritize by Risk (coverage < ~50% or unknown)

Run **before scaffolding**. Coverage for this trigger: SimpleCov's line-coverage figure when configured; otherwise the per-layer ratio of specced to total units - files for models, services, policies and jobs, actions for controllers - summed into one figure across the layers, and scoped to the surface the request named (app-wide only when the request is app-wide); say which scope was used; when neither is computable from the evidence, state `basis: none available` and apply the risk order to the gaps that are in evidence. Always state which basis was used. Alphabetical is wrong when authorization holes go unspec'd while plumbing gets full coverage.

1. **Authorization/authentication** - Pundit policy specs for every API-exposed model; request specs asserting 403/404 on every protected action; Devise/JWT flow specs; inbound webhook signature verification (invalid/missing signature -> 401)
2. **Data integrity** - model validations + unique-constraint enforcement; write services (one happy + one failure); Sidekiq mutating jobs (idempotency + retry)
3. **Business-critical flows** - revenue (checkout, billing, subscription transitions); multi-step state machines (AASM, `state_machines`); public/partner API contract drift (covered by the Step 7 tool)
4. **High-churn code** - frequent recent commits (`git log --since="3 months ago"`); bug-fix history (`git log --grep=fix`)
5. **Plumbing** - pass-through controllers, simple CRUD - lower risk, can wait

### Step 7 - API Contract (public/partner APIs)

Plain request specs don't catch drift (renamed key, status 200->204, new required parameter). Pick one:

| Tool        | Approach                                                                       |
| ----------- | ------------------------------------------------------------------------------ |
| `rswag`     | Declare OpenAPI inline; `rake rswag:specs:swaggerize` exports `swagger.yaml`   |
| `committee` | Validate request/response against existing OpenAPI schema                      |
| Hand-rolled | `match_schema(...)` with `json-schema`                                         |

Skip for internal/admin apps with a single frontend consumer where drift is caught by frontend tests.

### Step 8 - Infrastructure Hygiene

Judge evidence per item, not per file set: an item whose config is in evidence is verified (file findings when broken); an item not in evidence goes to the confirm-checklist - never claimed verified. The checklist lands in the deliverable's `## Infra To Confirm` section (Output Format).

- [ ] DB isolation: transactional fixtures (default; matches `rails-testing-patterns`) or `database_cleaner-active_record` truncation only for cross-connection state
- [ ] `Sidekiq::Testing` defaults to `:fake`; `:inline` per-spec when end-to-end needed. A global `inline!` is a finding, not a pass
- [ ] `WebMock.disable_net_connect!(allow_localhost: true)` in `rails_helper.rb`; existing live third-party calls migrate to boundary stubs (WebMock on the client) or VCR cassettes
- [ ] **Verify HTTP stubs intercept.** WebMock hooks `Net::HTTP` and the major adapters (Typhoeus, Patron, em-http, Excon, http.rb, Curb) - Faraday on those adapters is intercepted. What bypasses it silently: gRPC, raw sockets, shell-outs (`curl`), SDKs with custom non-Ruby transports, and WebMock simply not required in `rails_helper.rb`. Write one stubbed test, assert `expect(stub).to have_been_requested` - if unmatched, wire WebMock in or stub at the SDK client boundary. Silent passthrough leaks production credentials into CI. No runnable environment: the one-test recipe becomes an `## Infra To Confirm` item, not an emitted scaffold
- [ ] `example_status_persistence_file_path` for `--only-failures`
- [ ] `--order random` - tests pass in any order
- [ ] CI runs full suite; local default runs fast unit + request (use `slow:`/`system:` tags)
- [ ] Parallelism for suites > 5 minutes: `parallel_tests` or `turbo_tests` - rspec-core ships no parallel runner, and Rails' `parallelize` is Minitest-only

### Step 9 - Choose Output

| Request                                              | Output                       |
| ---------------------------------------------------- | ---------------------------- |
| "What tests are missing?" / "review coverage"        | Coverage Assessment          |
| "Write tests for X" / "scaffold specs"               | Test Scaffolds               |
| "Test strategy" / "test plan" / coverage < 50%       | Strategy Doc (+ Assessment)  |
| Reviewing existing specs                             | Review Checklist (below)     |

When several rows match, emit the union of the matched rows' outputs - the requested deliverable is always among them, never replaced (a scaffold request at low coverage matches the Scaffolds row and the Strategy row, so it emits scaffolds, the Strategy Doc and the Assessment). Merging rule: `Strategy Doc (+ Assessment)` means both blocks, carrying **one** prioritized gap list - it lives in the Strategy Doc's `Gaps to close`, and the Assessment's `Close first` block is omitted. A `coverage < 50%` row matches only on an established figure - `basis: none available` does not escalate the mode. Review mode emits checklist findings + Step 8 infra findings; add an Assessment block only when the evidence shows coverage gaps beyond those already filed as findings (the same test as the Review paragraph below).

**Any mode, unseen source:** a file shown to be absent from a fully listed repo is evidence, not an unknown - treat it as verified-missing and file it. When a policy or source file simply isn't shown, work from the roles and actions in evidence plus the conventional set (`guest`/`member`/`admin`), mark unknowns `# TODO: confirm role`, and label invented file or example names as placeholders.

**Review Checklist (existing specs):**

- [ ] Spec types match (model -> model spec, controller -> request spec; no deprecated controller specs)
- [ ] Every controller action: happy + unauthorized + validation-error
- [ ] Every Pundit policy: every action, and every role that produces a distinct outcome
- [ ] Every mutating Sidekiq job: idempotency spec
- [ ] FactoryBot uses traits (not duplicated factories); default builds a valid record with minimum attributes
- [ ] `build_stubbed` for unit (fake id from 1001, `persisted?` true, and factory-declared associations resolved DB-free; it raises on the persistence methods - `save`, `update`, `reload`, `destroy`, `touch` - but a `has_many` load or a scope on a stubbed record still issues real SQL silently), `build` when the test needs a genuine unsaved record, `create` only when persistence is required
- [ ] No `allow(SomeModel).to receive(:find)...` - mocking AR is a smell
- [ ] No `it { should ... }` chains > 5 deep (split into describes)
- [ ] System specs minimal; critical journeys only

## Output Format

Every mode's deliverable ends with these two sections, which the per-mode templates below do not repeat (Review mode carries its infra findings in its own numbered list instead, so only `## Infra To Confirm` follows it):

`## Infra Findings` - Step 8 items that **are** in evidence and are broken (a global `Sidekiq::Testing.inline!`, WebMock absent from `rails_helper.rb`), one line each, `file:line` + what breaks. Omit when none. In Review mode these are the Step 8 findings already ordered first in the numbered list; do not repeat them here.

`## Infra To Confirm` - Step 8 items **not** in evidence, plus any step skip rationale other than Step 7's. Omit when there are none.

A code defect that is not a Step 8 item but blocks the specs being written - a scope referencing a column the schema lacks, a body read twice, an auth hole the coverage analysis walked into - is reported, never dropped and never silently designed around: one line under `## Blocking Defects`, giving `file:line`, what it breaks, and the workflow that owns the fix. Scaffold against the corrected behaviour and say so.

The Step 7 API-contract decision - the tool chosen, or `skipped - <reason>` - is stated exactly once: in the Strategy Doc's `**API contract:**` slot when that block ships, otherwise as one line under `## Infra To Confirm`.
Assessment or Strategy rows with no matching surface fill as `N/A (<reason>)` - never dropped; a folded pyramid share renders as `0%`.

**Coverage Assessment:**

```markdown
## Rails Test Coverage Assessment

**Stack:** Ruby <version> / Rails <version>

**Framework:** <the test gems present in the `Gemfile`, with versions only where the Gemfile or lockfile states them; name any of RSpec / FactoryBot / shoulda-matchers that is absent>

**Basis:** {SimpleCov line coverage <n>% | per-layer file ratio <n>/<n> | none available}

**Gaps:**
- **Model:** [uncovered models]
- **Request:** [uncovered actions; missing unauthorized examples]
- **Policy:** [uncovered Pundit policies]
- **Service:** [uncovered services]
- **Job:** [Sidekiq jobs without idempotency specs]
- **System:** [critical journeys not covered]

**Close first (Step 6 risk order):**
1. [highest-risk gap - typically authorization or data integrity]
2. [...]

**Pyramid target:** Unit {x}% / Request {y}% / System {z}%
```

**Review (existing specs):** numbered findings tagged `[Critical | High | Medium]`, each citing `file:line` (file alone when the line isn't in evidence). Assign by consequence: Critical = tests can pass while auth or data-integrity is broken (missing policy or unauthorized-example coverage, HTTP stubs not intercepting); High = green-but-broken risk outside auth (global `Sidekiq::Testing.inline!`, missing validation-error/edge examples, mocked AR); Medium = maintainability (duplicated factories, deep chains, wrong layer). A happy-path-only protected action files two findings: its missing-unauthorized facet at Critical, its missing-validation-error facet at High. Infra findings (Step 8) first, spec findings (checklist) after, severity-ordered within each group; when the user reported a symptom ("CI green, staging breaks"), open with one line tying the top findings to it. Append the Assessment block only when the evidence shows coverage gaps beyond those already filed as findings - a gap is stated once.

**Test Scaffolds:** a `**Stack:** / **Basis:**` header line - here **Basis** names the evidence the scaffolds derive from - a different contract from the Assessment's coverage-figure `Basis`; when the union rule ships both blocks, each keeps its own `Basis` inside its own block and neither is hoisted (source files shown; inventions labeled placeholders per the unseen-source rule) - then ready-to-run RSpec files using project conventions. Each scaffold:

- Correct spec type (`type: :model | :request | :policy | :job | :system`)
- FactoryBot with traits (not `Model.new`); missing factories ship as files alongside the specs
- Model: shoulda-matchers for validations and associations
- Request: happy + unauthorized + validation-error
- Policy: every action, one example per distinct outcome
- Job: idempotency + retry behavior
- Inline comments only for non-obvious setup

Run `bundle exec rspec <scaffolded files>` and fix failures before presenting. If the environment can't execute, say so, list the command for the user, and report "[N] specs written, not executed" - never claim passes.

**Strategy Doc:**

```markdown
## Rails Test Strategy

**Objective:** [what this strategy achieves]

**Pyramid:** Unit {x}% / Request {y}% / System {z}%

**Tooling:** RSpec, FactoryBot (traits), shoulda-matchers + what the app shape needs (pundit-matchers, WebMock/VCR; Cuprite only when system specs exist)

**API contract:** [rswag | committee | hand-rolled match_schema | skipped - <reason>]

**Sidekiq:** default `:fake`, `:inline` per-spec for end-to-end

**DB isolation:** [transactional fixtures | database_cleaner truncation]

**Parallelism:** [parallel_tests | none]

**Gaps to close (prioritized):**
1. [Highest risk - typically authorization or data integrity]
2. [...]
```

## Self-Check

- [ ] Step 1-2: behavioral-principles loaded; stack confirmed
- [ ] Step 3: pyramid mapped to spec types
- [ ] Step 4: `rails-testing-patterns` consulted; per-type strategy applied
- [ ] Step 5: boundaries defined; no duplicated assertions across layers
- [ ] Step 6: risk prioritization applied when coverage is low
- [ ] Step 7: API contract approach chosen (or skip rationale stated)
- [ ] Step 8: infra items verified from evidence or routed to `## Infra To Confirm`; stub interception addressed
- [ ] Step 9: output type matches request; Review Checklist applied when reviewing

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
