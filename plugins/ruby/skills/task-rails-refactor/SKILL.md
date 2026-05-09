---
name: task-rails-refactor
description: Rails-specific refactor planning for fat models, fat controllers, callback abuse, missing service objects, scope sprawl, polymorphic-association sprawl, and concern soup. Produces a step-by-step sequence of independently-committable Rails refactoring steps with a test-coverage gate. Stack-specific override of task-code-refactor for Ruby/Rails.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rails Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Rails target (controller, model, service, concern, job). Identifies Rails-specific smells (fat models, fat controllers, callback abuse, missing service objects, scope sprawl, concern soup) and proposes independently-committable refactoring steps with RSpec coverage gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Ruby/Rails.

## When to Use

- Rails code-smell identification and resolution
- Rails technical-debt reduction with a concrete plan
- Safe refactoring of a controller / model / service / concern / job
- Pre-merge "this PR grew the fat-controller problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-rails-implement`)
- Architecture-level restructuring across many files (use `task-design-architecture`)
- Bug fixes (use `task-rails-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                |
| --------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, class, module, or path to refactor (e.g., `app/controllers/orders_controller.rb`, `app/models/user.rb`)              |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract OrderFulfillment service, kill `after_save` chain, split User concerns) |
| Test coverage status  | Recommended | Whether RSpec coverage exists for the target area (`rspec spec/<area>/` passes)                                            |
| Shared/public surface | Recommended | Whether the target is used across module / engine / team boundaries                                                        |

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Ruby / Rails. If invoked as a subagent of a Rails-aware parent, accept the pre-confirmed stack. If the detected stack is not Rails, stop and tell the user to invoke `/task-code-refactor` instead.

### Step 2 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Before proposing any refactor:

1. Identify the RSpec specs covering the target (`spec/models/<model>_spec.rb`, `spec/requests/<controller>_spec.rb`, `spec/services/<service>_spec.rb`, etc.)
2. Run coverage assessment - if coverage is missing or thin, **stop and require coverage first** before proposing refactor steps. Recommend `task-rails-test` to fill gaps.
3. If coverage exists but is happy-path-only, flag the boundary-test gap as a prerequisite step in the plan (refactor must not silently change error / unauthorized / not-found behavior).

**Output of this step:** explicit coverage status - `Adequate` / `Thin (boundary tests missing)` / `Inadequate (refuse to proceed without coverage)`. Do not proceed past Step 3 if coverage is inadequate.

### Step 3 - Identify Rails Smells

Inspect the target for these Rails-specific smells. Use judgment - these are signals, not hard rules.

**Controller smells:**

| Smell                    | Signal                                                                                                        | Risk   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Controller           | Controller action > 10 lines of orchestration (multiple model writes, conditional dispatch, response shaping) | High   |
| Logic in Controller      | Business rules, validation beyond strong params, calculation, or domain decisions inside the action           | High   |
| Direct AR in Controller  | Controllers call `Model.create!`, `Model.find_each`, multi-step queries instead of going through a service    | Medium |
| Callback chain in update | `before_action` chain > 3 deep with conditional skips and shared instance state                               | Medium |
| AR-in-API response       | `render json: @model` without a serializer; full attribute exposure including timestamps and internal flags   | High   |

**Model smells:**

| Smell                                 | Signal                                                                                                                   | Risk   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------ |
| Fat Model                             | Model > 300 lines; mixes persistence, business rules, query logic, presentation logic                                    | High   |
| Callback Abuse                        | `after_create` / `after_save` orchestrating cross-aggregate work (sending emails, enqueuing jobs, calling external APIs) | High   |
| Callback Mid-Transaction              | Sidekiq enqueue or HTTP call inside `after_save` (not `after_commit`) - races commit                                     | High   |
| Scope Sprawl                          | Model has > 8 scopes; some scopes accept arguments and grow into mini-query-objects                                      | Medium |
| Validation Spaghetti                  | Conditional validations with `if:` / `unless:` lambdas; > 5 conditional validations on one model                         | Medium |
| Polymorphic Sprawl                    | Polymorphic association with > 4 concrete types; type-specific branching inside the model                                | Medium |
| Self-referential `default_scope`      | `default_scope` that excludes records and surprises queries; rarely the right tool                                       | High   |
| `attr_accessor` Mixed With Attributes | Virtual attributes mixed with persisted ones without naming convention                                                   | Low    |

**Service / orchestration smells:**

| Smell                          | Signal                                                                                          | Risk   |
| ------------------------------ | ----------------------------------------------------------------------------------------------- | ------ |
| Missing Service Object         | Multi-step write spread across controller + model callbacks + job dispatch                      | High   |
| Inconsistent Service Interface | Mix of `.call`, `.execute`, `.run`, `.perform` interfaces in `app/services/`                    | Medium |
| Service Returning Boolean      | Service returns `true` / `false`; caller cannot distinguish failure cases                       | Medium |
| Service Hidden in Concern      | Orchestration logic lives in a concern that's mixed into the model rather than a service object | Medium |

**Concern / module smells:**

| Smell                 | Signal                                                                                                | Risk   |
| --------------------- | ----------------------------------------------------------------------------------------------------- | ------ |
| Concern Soup          | `app/models/concerns/` files named after the model they're for (e.g., `UserMethods`) - dumping ground | High   |
| Concern with State    | Concern that defines instance variables; coupling depends on host class internals                     | High   |
| Cross-Cutting Concern | Concern doing > 1 thing (e.g., `Auditable` that also handles soft delete and slug generation)         | Medium |

**Sidekiq job smells:**

| Smell                     | Signal                                                                        | Risk   |
| ------------------------- | ----------------------------------------------------------------------------- | ------ |
| Job Doing Too Much        | Single `perform` orchestrating 4+ business steps without sub-jobs or services | Medium |
| Job Receiving Records     | `perform(user, order)` instead of `perform(user_id, order_id)`                | High   |
| Missing Idempotency Guard | `perform` that re-runs side effects when called twice with the same args      | High   |
| Job Without Retry Bound   | No `sidekiq_options retry: <N>` - default 25 retries on a non-idempotent job  | High   |

**General OO smells (apply with Rails judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog. Apply Rails judgment - a 25-line method with one clear responsibility is fine; a 10-line method doing three things is not.

### Step 4 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, specs, and deployments are affected by the refactor.

Rails-specific blast-radius signals:

- [ ] **Public API surface**: target is a model used in `render json:` somewhere - refactor risks API contract change
- [ ] **Engine boundary**: target is in a Rails engine consumed by other engines or the host app
- [ ] **Concern shared across models**: refactoring a concern affects every host class
- [ ] **Default scope on a heavily-queried model**: scope changes can silently change query results across the app
- [ ] **Polymorphic association**: refactoring the association affects every concrete type
- [ ] **Callback removal**: callbacks may be relied on by other code paths (specs, console scripts, rake tasks) not just the obvious caller

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single module, multiple callers) / **Wide** (cross-module, public API, default scope) / **Critical** (concern shared by 5+ models, public engine surface).

### Step 5 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing RSpec suite continues to pass; new specs added when extracting new units

**Transaction-boundary watch.** When extracting orchestration that runs inside `ActiveRecord::Base.transaction`, the extracted unit inherits the transaction context. If the extracted code makes HTTP calls or enqueues Sidekiq jobs, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's transaction" or "callee uses `after_commit` to defer side effects." Never silently move I/O across a transaction boundary.

**Common Rails refactor recipes:**

**Recipe: Extract service object from fat controller**

1. Add `app/services/<verb>_<noun>.rb` with `.call(input)` returning a `Result` (or `Success` / `Failure`); copy logic from controller; controller still does the original work
2. Add `spec/services/<verb>_<noun>_spec.rb` with one example per outcome (success, validation failure, external failure)
3. Update controller to call the service; preserve response shape; ensure request specs pass
4. Remove the original logic from the controller; verify request specs pass unchanged
5. Add a request-spec example asserting service failure surfaces as expected error response

**Recipe: Move side effects out of an open DB transaction**

When the smell is "Sidekiq enqueue / HTTP call / mailer delivery happens inside `ActiveRecord::Base.transaction` so the worker can race the commit (or the email goes out then the transaction rolls back)," pick **one** of these options per refactor; do not stack them.

- **Option A - Post-commit dispatch.** Move the side effect to `after_commit` on the model, or wrap the dispatch site in `transaction.after_commit { OrderMailer.welcome(order).deliver_later }`. With Sidekiq 7+, `Sidekiq.transactional_push!` (when configured with the `sidekiq-transactional` gem or built-in equivalent) defers `perform_async` until commit. Cheapest option; correct when the side-effect target is one queue/mailer and "fire-once when commit lands" is sufficient. Risk: process crash between commit and `after_commit` callback execution drops the side effect with no retry record.
- **Option B - Transactional outbox.** Add an `outbox_messages` table (`id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload jsonb`, `created_at`, `processed_at`). Inside the same DB transaction as the business write, `OutboxMessage.create!(...)` records the intent. A relay job (`OutboxRelayJob` running on a schedule via `sidekiq-cron` / `solid_queue` recurring tasks) selects unprocessed rows with `OutboxMessage.where(processed_at: nil).lock("FOR UPDATE SKIP LOCKED").limit(N)`, dispatches the real side effect, then sets `processed_at`. Side-effect handlers must be idempotent (use `outbox_id` as a Sidekiq `unique_for:` key or as the natural dedup key). Use this when at-least-once delivery is required across crashes, or when multiple consumers need the event. Cost: extra table, extra job, extra observability surface.

State which option per refactor step and why. Mixing them (post-commit dispatch + outbox for the same event) is a red flag - one of the two is dead code.

**Recipe: Convert `after_save` callback to `after_commit` (or remove)**

1. Add a request spec / job spec that reproduces the current observable behavior
2. Move the callback from `after_save` to `after_commit` (or `after_commit on: :create`); run specs - confirm pass
3. If callback is doing cross-aggregate work, extract it into a service object called by the relevant controller; remove the callback
4. Run the full suite; verify no orphan code paths still rely on the callback

**Recipe: Untangle fat controller + callback orchestration (combined case)**

The most common Rails refactor: a controller action triggers a model write whose `after_save` / `after_create` callbacks fan out (mailers, jobs, audit writes). Removing the callbacks and extracting a service must happen as one logical change, but in safe sub-steps so the suite stays green between commits.

1. **Pin behavior with a request spec** asserting every observable side effect (record created, mailer enqueued, job enqueued, audit row written) - this is the contract the refactor must preserve
2. **Promote `after_save` to `after_commit`** first if the callbacks enqueue jobs or send mail mid-transaction; specs still pass, but side effects now fire post-commit (closer to the eventual service-object behavior)
3. **Introduce a service object** (`app/services/<verb>_<noun>.rb`) that performs the write _and_ the side effects in one `.call`; controller calls the service _but the callbacks still run_ - this duplicates side effects intentionally and temporarily
4. **Make callbacks no-op when called from the service** via a thread-local or explicit flag (`Order.transaction { ... ; order.skip_callbacks_for_service = true }`), or `update_columns` to bypass; verify spec still passes with side effects firing exactly once
5. **Delete the callbacks entirely**; the service is now the single source of orchestration; remove the bypass flag; spec still green
6. **Audit other call sites** (`grep` for `Order.create`, `order.save`, console scripts, rake tasks, other controllers) - any caller relying on the old callbacks is now broken and must be updated to call the service or have the side effects re-derived

The intermediate "callbacks no-op when called from service" step is the safety net - it keeps the codebase shippable between the introduction of the service (step 3) and the deletion of the callbacks (step 5).

**Recipe: Split fat model into model + service + query object**

1. Identify three concerns: persistence (validations, associations) stays in the model; business orchestration moves to a service; complex queries move to a query object (`app/queries/`)
2. Extract query object first (lowest risk - new file, model methods delegate to it temporarily)
3. Extract service object - move orchestration; model methods delegate temporarily
4. Update callers to call services / query objects directly; remove model delegators
5. Final pass: model has only validations, associations, simple scopes, and small instance methods

**Recipe: Replace concern soup with role-based concerns or composition**

1. Categorize the concern's methods into clear roles (e.g., `Auditable`, `SoftDeletable`, `Sluggable`)
2. Create the new role-based concerns one at a time; move methods; update host model
3. Remove the original soup concern when empty; verify specs

**Recipe: Make Sidekiq job idempotent**

1. Add a job spec asserting the side effect happens exactly once when `perform` is called twice with the same args
2. Add an idempotency guard at the top of `perform` (re-fetch state, check whether work was done, return early)
3. Verify retries on transient failures still complete the work
4. Bound `sidekiq_options retry: <N>` based on the job's actual retry budget

### Step 6 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end)
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Rails Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Stack:** Ruby <version> / Rails <version>

## Coverage Gate

**Status:** Adequate | Thin (boundary tests missing) | Inadequate (cannot proceed)

[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-rails-test` first.]

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, specs, public surface]

## Step Sequence

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Test gate:** [which specs must pass after this step]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] RSpec passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

- [ ] Stack confirmed as Rails (or accepted from parent dispatcher)
- [ ] Coverage gate evaluated; refused to propose plan if coverage was inadequate
- [ ] Rails-specific smells identified using Step 3 catalog (controller, model, service, concern, Sidekiq)
- [ ] Cross-module risk (blast radius) stated before proposing steps
- [ ] Each step independently committable; test gate stated per step
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions)
- [ ] No step bundles unrelated cleanup
- [ ] Goal explicitly mapped to the end state of the sequence
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing callbacks without a spec asserting the original behavior is preserved (or intentionally changed)
- Extracting an abstraction with one user - wait for the second use case before generalizing
- Replacing concerns with inheritance hierarchies - composition or role-based concerns are usually right
- Skipping the blast-radius step on "small" refactors - polymorphic associations and default scopes are deceptively wide
- Refactoring code that has no current bug, no current change request, no current pain - if nobody is touching it, leave it alone
