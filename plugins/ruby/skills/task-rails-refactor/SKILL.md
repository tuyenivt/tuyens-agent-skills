---
name: task-rails-refactor
description: Plan a Rails refactor - fat models/controllers, callback abuse, scope sprawl, concern soup - as committable steps with RSpec gates.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

## When to Use

- Rails code-smell identification and resolution on a specific target
- Safe refactor of a controller / model / service / concern / job into committable steps
- Pre-merge "this PR grew the fat-controller problem - what's the cleanup?"

Not for: deciding which debt to tackle first (`task-debt-prioritize`), feature changes (`task-rails-implement`), cross-cutting architecture change (`task-design-architecture`), bug fixes (`task-rails-debug`).

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Rails, redirect to `/task-code-refactor`.

### Step 3 - Inputs

Required: target scope (file/class/path), goal (what the refactor achieves). Recommended: existing RSpec coverage status, whether target crosses module/engine/team boundaries.

### Step 4 - Coverage Gate

Refactoring without test coverage is a rewrite with extra steps.

1. Identify the RSpec specs covering the target.
2. Assess: **Adequate** / **Thin (boundary tests missing)** / **Inadequate**.
3. If Inadequate, stop and recommend `task-rails-test` to fill gaps. Do not proceed.
4. If Thin, add boundary-test prerequisite as the first refactor step.

### Step 5 - Identify Smells

Use judgment - these are signals, not hard rules.

**Controller:**

| Smell                    | Signal                                                                                | Risk   |
| ------------------------ | ------------------------------------------------------------------------------------- | ------ |
| Fat Controller           | Action > 10 lines of orchestration (multi-model writes, conditional dispatch)         | High   |
| Logic in Controller      | Business rules, calculations, domain decisions inside the action                      | High   |
| Direct AR in Controller  | `Model.create!`/`find_each`/multi-step queries instead of a service                   | Medium |
| `before_action` chain    | > 3 deep with conditional skips and shared instance state                             | Medium |
| AR-in-API response       | `render json: @model` without serializer; full attribute exposure                     | High   |

**Model:**

| Smell                    | Signal                                                                                | Risk   |
| ------------------------ | ------------------------------------------------------------------------------------- | ------ |
| Fat Model                | > 300 lines; mixes persistence, business rules, queries, presentation                 | High   |
| Callback Abuse           | `after_create`/`after_save` orchestrating cross-aggregate work (mail, jobs, APIs)     | High   |
| Callback Mid-Transaction | Sidekiq enqueue or HTTP inside `after_save` (not `after_commit`)                      | High   |
| Scope Sprawl             | > 8 scopes; argument-accepting scopes drifting into query-objects                     | Medium |
| Validation Spaghetti     | > 5 conditional validations with `if:`/`unless:` lambdas                              | Medium |
| Polymorphic Sprawl       | Polymorphic with > 4 concrete types; type-specific branching in the model             | Medium |
| `default_scope`          | Filters records by default; surprises every query                                     | High   |

**Service / orchestration:**

| Smell                          | Signal                                                                  | Risk   |
| ------------------------------ | ----------------------------------------------------------------------- | ------ |
| Missing Service Object         | Multi-step write across controller + callbacks + job dispatch           | High   |
| Inconsistent Service Interface | Mix of `.call`/`.execute`/`.run`/`.perform` in `app/services/`          | Medium |
| Service Returns Boolean        | Caller can't distinguish failure cases                                  | Medium |
| Orchestration in Concern       | Multi-step work in a concern mixed into the model                       | Medium |

**Concern / module:**

| Smell                  | Signal                                                                                  | Risk   |
| ---------------------- | --------------------------------------------------------------------------------------- | ------ |
| Concern Soup           | Concerns named after the host model (`UserMethods`) - dumping ground                    | High   |
| Stateful Concern       | Defines instance variables; couples to host internals                                   | High   |
| Cross-Cutting Concern  | Does > 1 thing (`Auditable` also handling soft delete + slug)                           | Medium |

**Sidekiq:**

| Smell                     | Signal                                                                       | Risk   |
| ------------------------- | ---------------------------------------------------------------------------- | ------ |
| Job Doing Too Much        | Single `perform` orchestrating 4+ business steps without sub-jobs            | Medium |
| Job Receiving Records     | `perform(user, order)` instead of ids                                        | High   |
| Missing Idempotency Guard | Re-runs side effects when called twice with same args                        | High   |
| Job Without Retry Bound   | No `sidekiq_options retry:` - default 25 on a non-idempotent job             | High   |

For general OO smells: use skill `backend-coding-standards`.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. Rails signals to weigh:

- Model used in `render json:` somewhere - refactor risks API contract change
- Target in a Rails engine consumed by others
- Concern shared across models - affects every host
- `default_scope` on a heavily-queried model - silent result changes
- Polymorphic association - affects every concrete type
- Callback removal - specs, console scripts, rake tasks may rely on it

State: **Narrow** / **Moderate** / **Wide** / **Critical**.

### Step 7 - Propose Step Sequence

Each step must be:

1. **Independently committable** - suite passes after each
2. **Behaviorally invariant** - no behavior change unless that's the step
3. **Reversible** - rollback is one revert
4. **Tested** - existing RSpec passes; new specs added when extracting new units

**Transaction-boundary watch.** Extracting orchestration that runs inside `ActiveRecord::Base.transaction` - the extracted unit inherits transaction context. If it makes HTTP calls or enqueues Sidekiq, they now happen mid-transaction (regression). State the transaction stance per step.

**Recipe: extract service from fat controller**

1. Add `app/services/<verb>_<noun>.rb` returning `Result`; copy logic; controller still does original work
2. Add service spec - one example per outcome (success, validation failure, external failure)
3. Controller calls the service; preserve response shape; request specs pass
4. Remove original logic from controller
5. Add request-spec example asserting service failure surfaces as expected error

**Recipe: move side effects out of an open transaction**

Pick **one** option per event - mixing is a red flag.

- **A. Post-commit dispatch.** `after_commit` callback or `transaction.after_commit { ... }` at the dispatch site. Cheapest. Risk: process crash between commit and `after_commit` drops the side effect.
- **B. Transactional outbox.** Inside the transaction, `OutboxMessage.create!`. A relay job (`FOR UPDATE SKIP LOCKED`) dispatches and marks processed. Handlers must be idempotent. Use when at-least-once delivery is required across crashes.

**Recipe: untangle fat controller + callback orchestration**

Do **not** use thread-local "skip from service" flags - they leak across requests on threaded servers.

1. Pin behavior with a request spec asserting every observable side effect
2. Promote `after_save` to `after_commit` if callbacks enqueue jobs or send mail mid-transaction
3. Audit call sites (`grep` `Model.create`, `record.save`, console scripts, rake tasks) - every caller goes through the new service. Done *before* step 4
4. Introduce the service and delete the callbacks in the same commit
5. Remove dead code: callback methods, helper concerns, callback-behavior tests

**Recipe: split fat model into model + service + query object**

1. Extract query object first (lowest risk - new file, model methods delegate)
2. Extract service - move orchestration; model methods delegate
3. Update callers; remove model delegators
4. Model retains only validations, associations, simple scopes, small instance methods

**Recipe: replace concern soup with role-based concerns**

1. Categorize methods into roles (`Auditable`, `SoftDeletable`, `Sluggable`)
2. Create role concerns one at a time; move methods; update host
3. Remove original soup concern when empty

**Recipe: make Sidekiq job idempotent**

1. Spec asserting side effect happens once when `perform` is called twice
2. Idempotency guard at top of `perform`
3. Verify transient-failure retries still complete
4. Bound `sidekiq_options retry:` to actual budget

## Output Format

```markdown
## Rails Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this achieves]
**Stack:** Ruby <version> / Rails <version>

## Coverage Gate
**Status:** Adequate | Thin | Inadequate
[If Inadequate: what coverage must exist; recommend `task-rails-test`]

## Smells Identified
| Smell  | Location  | Risk | Notes                          |
| ------ | --------- | ---- | ------------------------------ |
| [name] | file:line | High | [one-sentence why]             |

## Blast Radius
[Narrow | Moderate | Wide | Critical] - [rationale citing callers, specs, public surface]

## Step Sequence
### Step 1 - [Action verb + noun]
- **Change:** [what is added/extracted/moved]
- **Transaction stance:** [inherits caller tx | defers via after_commit | runs outside]
- **Risk:** [Low | Medium | High]
- **Test gate:** [which specs must pass]
- **Rollback:** [single revert path]

### Step 2 - [...]

## Out of Scope
[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed
- [ ] Step 3: target and goal recorded
- [ ] Step 4: coverage status stated; refused to proceed if Inadequate
- [ ] Step 5: smells identified using catalog
- [ ] Step 6: blast radius stated before steps
- [ ] Step 7: each step independently committable, behaviorally invariant, reversible, with test gate and transaction stance; ordered low-risk first; no bundled cleanup; goal mapped to end state

## Avoid

- Proposing a refactor without a coverage gate
- Bundling behavior changes with refactoring steps
- "While we're here" unrelated cleanups
- Renaming during a refactor (rename PRs are separate)
- Removing callbacks without a spec pinning original behavior
- Extracting an abstraction with one user - wait for the second use case
- Replacing concerns with inheritance hierarchies (composition or role-based concerns are usually right)
- Skipping blast radius on "small" refactors - polymorphic associations and `default_scope` are deceptively wide
- Refactoring code with no current bug, change, or pain
