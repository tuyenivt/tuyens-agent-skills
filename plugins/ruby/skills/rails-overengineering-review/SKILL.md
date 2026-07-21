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
- Don't flag redundancy with a legitimate reason: form-level error messages, system-boundary validation on untrusted input, an interface stabilized across 3+ call sites, intentional `touch:` side effects, or uniqueness validation paired with a unique index as advisory UX.

## Patterns

### Category 1: Redundant Validation vs DB Constraints

App-side validations cost a SELECT (uniqueness, `belongs_to` presence) or CPU. When the DB enforces the rule via FK / NOT NULL / UNIQUE / CHECK / enum, the validation adds load without adding safety - unless a form path needs the error message before the DB roundtrip.

#### Presence on `belongs_to`

`belongs_to` defaults to `optional: false` since Rails 5.1, so it already adds a presence validation; the FK rejects null inserts. The duplicate validation is dead.

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
# MySQL 8 / PG functional index: add_index :users, "lower(email)", unique: true
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

Internal table fed by Sidekiq, no controller form - DB constraint suffices. Flag only after confirming no form/controller consumes `errors.full_messages` for this attribute.

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

# Good - controller calls create directly
@post.comments.create(comment_params.merge(user: current_user))
```

Justified when the operation has 3+ call sites or growth is concretely planned (not "we might"). See `rails-service-objects` for extraction criteria.

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

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction} (append "(inverted)" for missing-constraint findings)
- Code: {one-line citation, e.g., `validates :user, presence: true`}
- Redundant because: {FK name | NOT NULL column | unique index | enum | framework guarantee | speculative - no second call site/type/consumer}   (or `Unsafe because:` for inverted findings)
- Cost: {extra SELECT per save | masked exception | silent duplicates | speculative surface area}   (required for [Must]; optional context otherwise)
- Recommendation: {concrete edit}
- Justified when: {one-line note, if a legitimate reason might apply; otherwise omit}
```

A line that fits two categories gets one entry under the dominant category, with the second concern folded into the Recommendation. Several findings resolved by one fix (delete the class) merge into a single entry citing all of them.

When a category has no findings, state it explicitly (`No redundant validations detected.`), followed by one-line justification bullets for candidates that matched a don't-flag rule - reviewers and re-reviews need to see what was considered and why it passed.

## Avoid

- Flagging validations on user-submitted models without checking whether the form consumes the error message
- Recommending removal of uniqueness validation without confirming a unique index exists - the validation may be the only thing preventing silent duplicates
- Flagging a controller's `rescue ActiveRecord::RecordNotFound` before checking `ApplicationController`'s `rescue_from` config
- Recommending changes that require a migration without saying so
- Confusing "duplicated" with "defense in depth" - validation + unique index is correct for form UX
