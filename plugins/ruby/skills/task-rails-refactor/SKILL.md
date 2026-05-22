---
name: task-rails-refactor
description: Rails refactor plan: fat models/controllers, callback abuse, missing services, scope sprawl, concern soup; phased committable steps.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing.

# Rails Refactor

Safe, step-by-step refactoring plan for a Rails target (controller, model, service, concern, job). Identifies Rails smells - fat models, fat controllers, callback abuse, missing service objects, scope sprawl, concern soup - and proposes independently-committable steps with RSpec gates between each.

Stack-specific delegate of `task-code-refactor` for Ruby/Rails.

## When to Use

- Rails code-smell identification and resolution
- Technical-debt reduction with a concrete plan
- Safe refactoring of a controller / model / service / concern / job
- Pre-merge "this PR grew the fat-controller problem - what's the cleanup?"

**Not for:** deciding which debt first (`task-debt-prioritize`), feature changes (`task-rails-implement`), architecture restructure across many files (`task-design-architecture`), bug fixes (`task-rails-debug`).

## Inputs

| Input                 | Required    | Description                                                                                            |
| --------------------- | ----------- | ------------------------------------------------------------------------------------------------------ |
| Target scope          | Yes         | File, class, module, or path to refactor                                                               |
| Goal                  | Yes         | What the refactoring achieves (e.g., extract OrderFulfillment service, kill `after_save` chain)        |
| Test coverage status  | Recommended | Whether RSpec coverage exists for the target area                                                      |
| Shared/public surface | Recommended | Whether the target is used across module / engine / team boundaries                                    |

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Rails, redirect to `/task-code-refactor`.

### Step 2 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps.

1. Identify the RSpec specs covering the target
2. Assess coverage - if missing or thin, **stop and require coverage first**. Recommend `task-rails-test` to fill gaps
3. If coverage is happy-path-only, flag boundary-test gap as a prerequisite step

**Output:** explicit coverage status - `Adequate` / `Thin (boundary tests missing)` / `Inadequate (refuse to proceed)`. Do not proceed past Step 3 if inadequate.

### Step 3 - Identify Rails Smells

Use judgment - these are signals, not hard rules.

**Controller smells:**

| Smell                    | Signal                                                                                                | Risk   |
| ------------------------ | ----------------------------------------------------------------------------------------------------- | ------ |
| Fat Controller           | Action > 10 lines of orchestration (multi-model writes, conditional dispatch, response shaping)       | High   |
| Logic in Controller      | Business rules, validation beyond strong params, calculation, domain decisions inside the action      | High   |
| Direct AR in Controller  | Calls `Model.create!`, `Model.find_each`, multi-step queries instead of going through a service       | Medium |
| Callback chain in update | `before_action` chain > 3 deep with conditional skips and shared instance state                       | Medium |
| AR-in-API response       | `render json: @model` without serializer; full attribute exposure including internal flags            | High   |

**Model smells:**

| Smell                                | Signal                                                                                                | Risk   |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------- | ------ |
| Fat Model                            | > 300 lines; mixes persistence, business rules, query logic, presentation                             | High   |
| Callback Abuse                       | `after_create`/`after_save` orchestrating cross-aggregate work (emails, jobs, external APIs)          | High   |
| Callback Mid-Transaction             | Sidekiq enqueue or HTTP call inside `after_save` (not `after_commit`)                                 | High   |
| Scope Sprawl                         | > 8 scopes; some accept arguments and grow into mini-query-objects                                    | Medium |
| Validation Spaghetti                 | > 5 conditional validations with `if:` / `unless:` lambdas                                            | Medium |
| Polymorphic Sprawl                   | Polymorphic with > 4 concrete types; type-specific branching inside the model                         | Medium |
| Self-referential `default_scope`     | `default_scope` excluding records, surprising queries                                                 | High   |
| `attr_accessor` mixed with attributes| Virtual attributes mixed with persisted without naming convention                                     | Low    |

**Service / orchestration smells:**

| Smell                          | Signal                                                                  | Risk   |
| ------------------------------ | ----------------------------------------------------------------------- | ------ |
| Missing Service Object         | Multi-step write across controller + model callbacks + job dispatch     | High   |
| Inconsistent Service Interface | Mix of `.call`, `.execute`, `.run`, `.perform` in `app/services/`       | Medium |
| Service Returning Boolean      | Returns `true`/`false`; caller can't distinguish failure cases          | Medium |
| Service Hidden in Concern      | Orchestration in a concern mixed into the model rather than a service   | Medium |

**Concern / module smells:**

| Smell                  | Signal                                                                                  | Risk   |
| ---------------------- | --------------------------------------------------------------------------------------- | ------ |
| Concern Soup           | `concerns/` files named after the model (`UserMethods`) - dumping ground                | High   |
| Concern with State     | Defines instance variables; coupling on host class internals                            | High   |
| Cross-Cutting Concern  | Does > 1 thing (`Auditable` also handling soft delete and slug generation)              | Medium |

**Sidekiq smells:**

| Smell                     | Signal                                                                       | Risk   |
| ------------------------- | ---------------------------------------------------------------------------- | ------ |
| Job Doing Too Much        | Single `perform` orchestrating 4+ business steps without sub-jobs            | Medium |
| Job Receiving Records     | `perform(user, order)` instead of `perform(user_id, order_id)`               | High   |
| Missing Idempotency Guard | `perform` re-runs side effects when called twice with same args              | High   |
| Job Without Retry Bound   | No `sidekiq_options retry:` - default 25 retries on a non-idempotent job     | High   |

**General OO smells:** use skill `backend-coding-standards`. Apply Rails judgment - a 25-line method with one clear responsibility is fine; a 10-line method doing three things is not.

### Step 4 - Cross-Module Risk

Use skill: `review-blast-radius`.

Rails-specific signals:

- [ ] Public API surface: target is a model used in `render json:` somewhere - refactor risks API contract change
- [ ] Engine boundary: target is in a Rails engine consumed by others
- [ ] Concern shared across models: affects every host
- [ ] `default_scope` on a heavily-queried model: scope changes silently change results across the app
- [ ] Polymorphic association: refactoring affects every concrete type
- [ ] Callback removal: callbacks may be relied on by specs, console scripts, rake tasks - not just obvious callers

State: **Narrow** (single file, single caller) / **Moderate** (single module, multiple callers) / **Wide** (cross-module, public API, default scope) / **Critical** (concern shared by 5+ models, public engine surface).

### Step 5 - Propose the Step Sequence

Each step must be:

1. **Independently committable** - codebase compiles and suite passes after each
2. **Behaviorally invariant** - no behavior change unless noted as a separate step
3. **Reversible** - rollback is one revert
4. **Tested** - existing RSpec passes; new specs added when extracting new units

**Transaction-boundary watch.** Extracting orchestration that runs inside `ActiveRecord::Base.transaction` - the extracted unit inherits transaction context. If it makes HTTP calls or enqueues Sidekiq jobs, they now happen mid-transaction (regression). State the transaction stance per step: "callee runs inside caller's transaction" or "callee uses `after_commit` to defer side effects."

**Common recipes:**

**Extract service from fat controller**

1. Add `app/services/<verb>_<noun>.rb` with `.call(input)` returning `Result`; copy logic from controller; controller still does original work
2. Add `spec/services/<verb>_<noun>_spec.rb` with one example per outcome (success, validation failure, external failure)
3. Update controller to call the service; preserve response shape; request specs pass
4. Remove original logic from controller; request specs pass unchanged
5. Add request-spec example asserting service failure surfaces as expected error

**Move side effects out of an open DB transaction**

Pick **one**, do not stack:

- **Option A - Post-commit dispatch.** Move side effect to `after_commit`, or wrap dispatch site in `transaction.after_commit { OrderMailer.welcome(order).deliver_later }`. Sidekiq 7+ `Sidekiq.transactional_push!` (with `sidekiq-transactional` or built-in) defers `perform_async` until commit. Cheapest; correct when one queue/mailer and "fire-once when commit lands" is sufficient. **Risk:** process crash between commit and `after_commit` drops the side effect with no retry
- **Option B - Transactional outbox.** Add `outbox_messages` table. Inside the same DB transaction, `OutboxMessage.create!(...)` records intent. A relay job (sidekiq-cron / solid_queue recurring) `SELECT ... FOR UPDATE SKIP LOCKED`s unprocessed rows, dispatches, then sets `processed_at`. Handlers must be idempotent (use `outbox_id` as Sidekiq `unique_for:` key). Use when at-least-once delivery is required across crashes, or multiple consumers need the event. Cost: extra table, job, observability surface

State which option per step and why. Mixing them (post-commit + outbox for the same event) is a red flag - one is dead code.

**Convert `after_save` to `after_commit` (or remove)**

1. Add a spec reproducing current observable behavior
2. Move callback from `after_save` to `after_commit` (or `after_commit on: :create`); run specs
3. If callback does cross-aggregate work, extract into a service called by the controller; remove the callback
4. Run full suite; verify no orphan code paths still rely on the callback

**Untangle fat controller + callback orchestration**

Most common Rails refactor. **Do not use thread-local "skip from service" flags** - they leak across requests on threaded servers and produce silent test passes.

1. **Pin behavior with a request spec** asserting every observable side effect
2. **Promote `after_save` to `after_commit`** if callbacks enqueue jobs / send mail mid-transaction
3. **Audit call sites** (`grep` for `Order.create`, `order.save`, console scripts, rake tasks, other controllers). Every caller of the model's write path goes through the new service, or has side effects re-derived. Must be done *before* step 4
4. **Introduce the service** and **delete the callbacks in the same commit**. Service is now the single source of orchestration. Specs from step 1 still green
5. **Remove dead code**: callback methods, helper concerns, tests that asserted callback behavior directly

The "audit before delete" sequencing is the safety net.

**Split fat model into model + service + query object**

1. Identify three concerns: persistence (validations, associations) stays; orchestration to service; complex queries to query object (`app/queries/`)
2. Extract query object first (lowest risk - new file, model methods delegate temporarily)
3. Extract service - move orchestration; model methods delegate temporarily
4. Update callers; remove model delegators
5. Final: model has only validations, associations, simple scopes, small instance methods

**Replace concern soup with role-based concerns**

1. Categorize methods into roles (`Auditable`, `SoftDeletable`, `Sluggable`)
2. Create new role-based concerns one at a time; move methods; update host
3. Remove original soup concern when empty; verify specs

**Make Sidekiq job idempotent**

1. Spec asserting side effect happens once when `perform` called twice with same args
2. Idempotency guard at top of `perform`
3. Verify retries on transient failures still complete
4. Bound `sidekiq_options retry: <N>` based on actual retry budget

### Step 6 - Validate Plan

- [ ] Goal achieved at end of sequence
- [ ] Each step reviewable in < 30 minutes
- [ ] Test coverage runs between every step
- [ ] Steps ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes)
- [ ] Rollback is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Rails Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this achieves]
**Stack:** Ruby <version> / Rails <version>

## Coverage Gate

**Status:** Adequate | Thin (boundary tests missing) | Inadequate (cannot proceed)

[If Inadequate: state what coverage must exist before refactor begins; recommend `task-rails-test`.]

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [name]       | file:line | High | [Why this is the smell - one sentence] |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, specs, public surface]

## Step Sequence

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Test gate:** [which specs must pass]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] RSpec passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

- [ ] Stack confirmed (or accepted from parent)
- [ ] Coverage gate evaluated; refused to propose plan if coverage inadequate
- [ ] Rails smells identified using Step 3 catalog (controller, model, service, concern, Sidekiq)
- [ ] Blast radius stated before proposing steps
- [ ] Each step independently committable; test gate stated per step
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions)
- [ ] No step bundles unrelated cleanup
- [ ] Goal explicitly mapped to end state
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate
- Bundling behavior changes with refactoring steps
- "While we're here" unrelated cleanups
- Renaming during a refactor (rename PRs are separate)
- Removing callbacks without a spec asserting the original behavior is preserved
- Extracting an abstraction with one user - wait for the second use case
- Replacing concerns with inheritance hierarchies - composition or role-based concerns are usually right
- Skipping blast-radius on "small" refactors - polymorphic associations and default scopes are deceptively wide
- Refactoring code with no current bug, change request, or pain - leave it alone
