---
name: rails-overengineering-review
description: Rails necessity review: validations duplicating DB constraints, guards on impossible states, services/Result/base classes wrapping trivial logic.
metadata:
  category: backend
  tags: [ruby, rails, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

Reviewing a Rails diff that adds validations, `rescue` blocks, service objects, or new abstractions. Composed into `task-rails-review` Step 7 (Code Hygiene) to catch code that is correct, performant, safe - and unnecessary.

## Rules

- Every finding cites the specific constraint making the code redundant: FK name, NOT NULL column, unique index, enum, framework guarantee - or, for Category 3, the absence of a second call site/type/consumer. No citation, no finding.
- Default intent is `[Recommend]`. Escalate to `[Must]` only when there is measurable cost: extra SELECT on a hot path, blanket `rescue` masking real bugs, a service hiding a transaction boundary the call site should see, or silent data corruption (racing uniqueness with no index).
- Use `[Recommend]` with the open assumption stated when justification is plausible but not evidenced. Facts supplied alongside the diff (schema, call-site counts, form usage) count as evidence - don't re-ask what the requester already answered.
- Cite locations as the diff presents them (hunk/line); never invent file paths.
- Don't flag redundancy with a legitimate reason: form-level error messages, system-boundary validation on untrusted input, an interface stabilized across 3+ call sites, intentional `touch:` side effects, a guard enforcing a legal state transition (the usual justification for a state-machine class), or uniqueness validation paired with a unique index as advisory UX.
- Rules win over Patterns where they disagree. The don't-flag list above is unconditional; a Pattern's narrower framing ("keep it if a form needs the message") explains the common case, it does not reopen the rule.

## Patterns

### Category 1: Redundant Validation vs DB Constraints

App-side validations cost a SELECT (uniqueness, `belongs_to` presence) or CPU. When the DB enforces the rule, the validation adds load without adding safety - but removing it is never free, and the cost is bigger than a lost error message. With the validation gone, non-bang `save`/`update` stops returning `false` and the DB raises instead: `ActiveRecord::NotNullViolation`, `RecordNotUnique`, `StatementInvalid`. **Every** caller changes failure mode, not just form paths. Recommend removal only where the callers are ready to rescue - or where the code already uses the bang methods.

Note also what "the DB enforces it" means: FK, NOT NULL, UNIQUE and CHECK are DB constraints; a Rails integer-backed `enum` is not - it is a framework guarantee with no database enforcement at all, so raw SQL or `update_column` writes any value it likes.

#### Presence on `belongs_to`

`belongs_to` is required by default under `config.load_defaults 5.0`+ (via `belongs_to_required_by_default`), so it already adds a presence validation and the duplicate is dead. Confirm that flag before flagging: it is config-gated, not a hard version default, so an app upgraded from 4.x that never bumped `load_defaults` still has optional `belongs_to` - there the explicit validation is the only check. The DB-level backstop is a `NOT NULL` column, not the FK: a foreign key permits NULL on both PostgreSQL and MySQL.

```ruby
# Bad
belongs_to :user
validates :user, presence: true

# Good
belongs_to :user
```

#### Uniqueness validation as the only enforcement

Without a unique index, two concurrent requests pass the SELECT, both insert, and the duplicate lands. The DB must enforce uniqueness; the validation is at best advisory UX.

```ruby
# Bad - races
validates :email, uniqueness: true

# Good - DB-enforced; validation kept only if form needs the pre-submit error
validates :email, uniqueness: { case_sensitive: false } # advisory; index is authoritative
# MySQL (case-insensitive collation): add_index :users, :email, unique: true
# PG functional index: add_index :users, "lower(email)", unique: true
# MySQL 8 functional index: add_index :users, "(lower(email))", unique: true
#   Rails wraps a String expression in its own parens, emitting ON users ((lower(email))) -
#   the double parens MySQL requires. Writing "((lower(email)))" yields three.
```

This is the *inverted* finding the review must still emit: nothing is redundant - a constraint is missing. Use `Unsafe because:` in place of `Redundant because:`, recommend adding the index (note the migration), and keep the validation when a form consumes the error.

#### Inclusion on an enum

`Order.new(status: "invalid")` raises `ArgumentError` on assignment - the validation never runs. (With `enum ..., validate: true` (7.1+), assignment doesn't raise; the enum validates itself - the inclusion validation is still redundant, cite the enum's own validation instead.)

```ruby
# Bad
enum :status, { pending: 0, confirmed: 1 }
validates :status, inclusion: { in: statuses.keys }

# Good
enum :status, { pending: 0, confirmed: 1 }
```

#### Presence on NOT NULL with no form path

Internal table fed by Sidekiq, no controller form - DB constraint suffices for *correctness*. Flag only after confirming no form/controller consumes `errors.full_messages` for this attribute, and note the failure-mode change: the job now raises `NotNullViolation` where it used to get `save => false`, so a permanently invalid payload retries until the budget is spent instead of being rejected once. That is acceptable when the job treats a raise as dead-letter-worthy, and a regression when it doesn't.

### Category 2: Defensive Code for Impossible States

Re-checking guarantees Rails or the DB already provides adds noise and hides regressions by swallowing the exception that would have surfaced them.

#### Nil guard on a non-nullable column

```ruby
# Bad - status is NOT NULL with default; guard never fires
return unless @order.status.present?
@order.update!(status: :processing)

# Good
@order.update!(status: :processing)
```

#### Catch-and-reraise of the only exception that could fire

```ruby
# Bad - rescue is dead code
def find_order
  Order.find(params[:id])
rescue ActiveRecord::RecordNotFound
  raise
end
```

Conversion to a 404 belongs in `ApplicationController`'s `rescue_from`, not in every action.

#### `present?` on a guaranteed-present user

```ruby
# Bad - authenticate_user! already halted on missing user
before_action :authenticate_user!
def index
  return head :unauthorized unless current_user.present?
  @orders = current_user.orders
end
```

#### Blanket `rescue StandardError` masking real bugs

```ruby
# Bad - swallows NoMethodError, ArgumentError, ConnectionNotEstablished
rescue StandardError => e
  Rails.logger.error(e)
  Result.failure(["something went wrong"])

# Good - name the failures the call can actually raise
rescue ActiveRecord::RecordInvalid, Inventory::InsufficientStockError => e
  Result.failure([e.message])
```

### Category 3: Premature Abstraction

#### Service object wrapping a one-line operation

```ruby
# Bad - service exists to wrap create! in a Result
class CreateComment
  def call
    Result.success(@post.comments.create!(user: @user, body: @body))
  rescue ActiveRecord::RecordInvalid => e
    Result.failure(e.record.errors.full_messages)
  end
end

# Good - controller calls create directly, and consumes the result
@comment = @post.comments.build(comment_params.merge(user: current_user))
if @comment.save
  redirect_to @post
else
  render :new, status: :unprocessable_entity
end
```

The `if @comment.save` is not decoration. The wrapper being deleted returned `Result.failure(errors)`, so replacing it with a bare `create` discards the return value and swallows every validation failure silently - a worse bug than the one being fixed.

Justified when the operation has 3+ call sites, or when it spans 2+ models or an external API and owns a transaction boundary. `rails-service-objects` states the same bar. Concretely planned growth (a scheduled second caller, not "we might") argues for `[Recommend]` over `[Must]` on an otherwise-premature abstraction; it does not by itself justify one.

#### `Result` where a boolean suffices

```ruby
# Bad
return unless CheckEligibility.new(user: u).call.success?

# Good
return unless u.verified?
```

Keep `Result` when the caller needs structured errors, or when the same call returns success-with-payload in one branch and failure-with-errors in another.

#### Base service class with one subclass

```ruby
# Bad - ApplicationService exists to save `.new(...).call` at the call site
class ApplicationService
  def self.call(...) = new(...).call
  def call; raise NotImplementedError; end
end
class FulfillOrder < ApplicationService; end

# Good - skip the base class until 3+ services share real cross-cutting behavior
class FulfillOrder
  def call; ...; end
end
```

#### `**options` with unused keys

```ruby
# Bad - audit_tag and source are speculative; never passed
def fulfill(order, **options)
  notify    = options.fetch(:notify, true)
  audit_tag = options.fetch(:audit_tag, nil)
  source    = options.fetch(:source, "web")
end

# Good
def fulfill(order, notify: true); end
```

#### Polymorphic association with one concrete type

```ruby
# Bad - only Post uses commentable; costs _type column, no FK constraint
belongs_to :commentable, polymorphic: true

# Good
belongs_to :post
```

Justified when a second type is already designed and lands in the same release.

## Output Format

Findings contribute to the consuming workflow's unified output. Each entry:

```
### [Must | Recommend] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction | Redundant Indirection (a layer that only forwards - repository, wrapper, alias)} (append "(inverted)" for missing-constraint findings)
- Code: {one-line citation, e.g., `validates :user, presence: true`}
- Redundant because: {FK name | NOT NULL column | unique index | enum | framework guarantee | speculative - no second call site/type/consumer, or a consumer that discards the value}   (or `Unsafe because:` for inverted findings)
- Cost: {extra SELECT per save | masked exception | hidden transaction boundary | silent duplicates | speculative surface area}   (required for [Must]; optional context otherwise)
- Recommendation: {concrete edit}
- Justified when: {one-line note, if a legitimate reason might apply; otherwise omit}
```

`file:line` takes a range (`app/services/pricing/engine.rb:1-27`) when one entry covers a merged set. Reviewing a proposal rather than a diff: the target is the design, so write `file:line` as `<proposed path> (new file)`, read `Code:` as the proposed shape, and let `[Must]` mean "do not build this" - the escalation bar is the cost the code *would* carry once merged. An incidental correctness bug noticed while gathering evidence gets its own entry under the category it belongs to, not a footnote inside another finding.

A line that fits two categories gets one entry under the dominant category, with the second concern folded into the Recommendation. Several findings resolved by one fix (delete the class) merge into a single entry citing all of them.

When a category has no findings, state it explicitly (`No redundant validations detected.`), followed by one-line justification bullets for candidates that matched a don't-flag rule - reviewers and re-reviews need to see what was considered and why it passed.

## Avoid

- Flagging validations on user-submitted models without checking whether the form consumes the error message
- Recommending removal of uniqueness validation without confirming a unique index exists. The validation races and does not *prevent* duplicates, but it is often the only thing keeping them rare and visible - removing it makes them silent
- Reading "no index in the migrations I was shown" as "no index exists" - say which schema evidence you had
- Flagging a controller's `rescue ActiveRecord::RecordNotFound` before checking `ApplicationController`'s `rescue_from` config
- Recommending changes that require a migration without saying so
- Confusing "duplicated" with "defense in depth" - validation + unique index is correct for form UX
