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

- Every finding cites the specific constraint making the code redundant: FK name, NOT NULL column, unique index, CHECK constraint, enum, framework guarantee - or, for Categories 3 and 4, fewer call sites, types or consumers than the pattern's bar (one call site, a second type or implementer, or 3+ where the pattern says so) or no behaviour the layer adds. No citation, no finding.
- Default intent is `[Recommend]`. Escalate to `[Must]` only when there is measurable cost: extra SELECT on a hot path, blanket `rescue` masking real bugs, a service hiding a transaction boundary its caller cannot see (the caller wraps or rescues around it without knowing it opens one), silent data corruption (racing uniqueness with no index, a missing NOT NULL / FK / CHECK behind a validation), an incidental correctness bug, or - on a proposal only - a whole speculative layer that would be paid for at merge.
- Use `[Recommend]` with the open assumption stated when justification is plausible but not evidenced. Facts supplied alongside the diff (schema, call-site counts, form usage) count as evidence - don't re-ask what the requester already answered. When the config that decides a finding is not in evidence, the code goes in the category footer as `config not in evidence`, or into a `[Recommend]` entry that states the assumption.
- Cite locations as the diff presents them (hunk/line), or as `file:line` of the file read when reviewing existing code; never invent file paths.
- Don't flag redundancy with a legitimate reason: form-level error messages, system-boundary validation on untrusted input, an interface stabilized across 3+ call sites, intentional `touch:` side effects, a guard enforcing a legal state transition (the usual justification for a state-machine class), uniqueness validation paired with a unique index as advisory UX, or a `rescue_from` at the application boundary that reports before rendering. A validation with no DB backing shown (numericality, format, inclusion on a plain string column with no enum or CHECK) is not redundant - leave it.
- Rules win over Patterns where they disagree. The don't-flag list above is unconditional; a Pattern's narrower framing ("keep it if a form needs the message") explains the common case, it does not reopen the rule.

## Patterns

### Category 1: Redundant Validation vs DB Constraints

App-side validations cost a SELECT (an explicit `belongs_to` presence validation loads the parent on every validation; the built-in check, under `belongs_to_required_validates_foreign_key = false` - the 7.1 default - loads it only when the foreign key changed) or CPU. When the DB enforces the rule, the validation adds load without adding safety - but removing it is never free, and the cost is bigger than a lost error message. With the validation gone, non-bang `save`/`update` stops returning `false` and the DB raises instead (in strict SQL mode, the Rails MySQL default; with `strict: false` a single-row INSERT of NULL still raises, but an UPDATE or a multi-row write such as `insert_all` coerces it to `''`/0 silently, and then the validation is the only check): `ActiveRecord::NotNullViolation`, `StatementInvalid`. Every caller whose only check was that validation changes failure mode, not just form paths - bang callers too, since a `rescue ActiveRecord::RecordInvalid` stops matching `NotNullViolation` (a `StatementInvalid`). Recommend removal only where those callers are ready to rescue the `StatementInvalid` subclasses; a duplicate of a check that stays (`belongs_to` presence) changes nothing but the duplicate `:blank` message - check that no form or test asserts on it - and under 7.1+ defaults removing it also drops a SELECT per save on updates that leave the foreign key alone. A uniqueness validation paired with a unique index stays (Rules).

Note also what "the DB enforces it" means: FK, NOT NULL, UNIQUE and CHECK (enforced from MySQL 8.0.16) are DB constraints; a Rails integer-backed `enum` is not - it is a framework guarantee with no database enforcement at all, so raw SQL (`update_all` with a SQL string, `connection.execute`) or an out-of-band writer stores any value it likes.

#### Presence on `belongs_to`

`belongs_to` is required by default under `config.load_defaults 5.0`+ (via `belongs_to_required_by_default`), so it already adds a presence validation and the duplicate is redundant - and from `load_defaults 7.1` (`belongs_to_required_validates_foreign_key = false`) it is also the more expensive of the two, since the built-in check skips the association load unless the FK changed. Confirm that flag before flagging: it is config-gated, not a hard version default. An explicit `belongs_to_required_by_default` in `config/application.rb`, any `config/environments/*.rb` or an initializer overrides `load_defaults`, often for one environment only, and an app upgraded from 4.x that never bumped `load_defaults` still has optional `belongs_to` - wherever it is false, the explicit validation is the only check and is not redundant; a flag that differs per environment makes the finding conditional - name the environment it holds in and keep `[Recommend]`. The DB-level backstop is a `NOT NULL` column, not the FK: a foreign key permits NULL.

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
# MySQL 8.0.13+ functional index: add_index :users, "(lower(email))", unique: true
#   Rails wraps a String expression in its own parens, emitting ON users ((lower(email))) -
#   the double parens MySQL requires. Writing "((lower(email)))" yields three.
```

This is the *inverted* finding the review must still emit: nothing is redundant - a constraint is missing. Use `Unsafe because:` in place of `Redundant because:`, recommend adding the index (note the migration), and keep the validation when a form consumes the error.

#### Inclusion on an enum

`Order.new(status: "invalid")` raises `ArgumentError` on assignment - the validation never runs for a bad value. It is still the nil check: enum assignment accepts `nil`, which is not in `statuses.keys`, so the inclusion is redundant only when the column is NOT NULL or presence is validated elsewhere. (With `enum ..., validate: true` (7.1+), assignment doesn't raise; the enum validates itself - cite the enum's own validation instead.)

```ruby
# Bad - orders.status is NOT NULL
enum :status, { pending: 0, confirmed: 1 }
validates :status, inclusion: { in: statuses.keys }

# Good
enum :status, { pending: 0, confirmed: 1 }
```

#### Presence on NOT NULL with no form path

Internal table fed by Sidekiq, no controller form - DB constraint suffices for *correctness*. One entry per column. Flag only after confirming no form/controller consumes `errors.full_messages` for this attribute, and note the failure-mode change. On a string column `presence` also rejects `""` and whitespace, which NOT NULL admits - there it is redundant only with a CHECK or format validation keeping blanks out:

```ruby
# Bad - invoices.amount_cents is NOT NULL; only ImportInvoiceJob writes it
validates :amount_cents, presence: true

# Good - drop the validation; the job dead-letters a payload the DB rejects
def perform(payload)
  Invoice.create!(payload)
rescue ActiveRecord::NotNullViolation => e
  DeadLetter.record!(payload, e)   # rejected once, not retried until the budget is spent
end
```

The failure-mode change: a job that checked `save => false` (or rescued `RecordInvalid`) now sees `NotNullViolation` escape `perform`, so a permanently invalid payload retries until the budget is spent instead of being rejected once (a job that already let `create!` raise retried before too - nothing changes for it). That is acceptable when the job treats a raise as dead-letter-worthy, and a regression when it doesn't.

### Category 2: Defensive Code for Impossible States

Re-checking guarantees Rails or the DB already provides adds noise and hides regressions by swallowing the exception that would have surfaced them.

#### Nil guard on a non-nullable column

```ruby
# Bad - status is a NOT NULL integer enum column only Rails writes; guard never fires (an unmapped integer from an
# out-of-band writer reads back as nil, and a NOT NULL string column still admits "")
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

Rails already maps an uncaught `RecordNotFound` to 404 through `config.action_dispatch.rescue_responses`; a `rescue_from` in `ApplicationController` is only for custom rendering, and never in every action.

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

# Good - controller builds and saves directly, and consumes the result
@comment = @post.comments.build(comment_params.merge(user: current_user))
if @comment.save
  redirect_to @post
else
  render :new, status: :unprocessable_content   # Rack 3.1+ name for 422 (write 422 on older Rack)
end
```

The `if @comment.save` is not decoration. The wrapper being deleted returned `Result.failure(errors)`, so replacing it with a bare `create` discards the return value and swallows every validation failure silently - a worse bug than the one being fixed.

Justified when the operation has 3+ call sites, or when it spans 2+ models or an external API and owns a transaction boundary. `rails-service-objects` states the same bar. Concretely planned growth (a scheduled second caller, not "we might") keeps the finding at `[Recommend]` with the plan stated; it does not by itself justify the abstraction.

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
  def call
    # ...
  end
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

# Good - a migration (drop commentable_type, rename to post_id, add the FK) and a rename for every caller
belongs_to :post
```

Justified when a second type lands in the same release - shipped, not planned, which is the same bar as for services.

### Category 4: Redundant Indirection

A layer that only forwards - `OrderRepository#find(id)` calling `Order.find(id)`, a wrapper returning the wrapped call's value unchanged, an alias method - adds a name and a file, not behaviour. Justified when it hides a real seam (a second data source, a vendor SDK). An interface module with one implementer, or a repository layer justified by "we can swap the database later", belongs here too: the seam is speculative until the second data source exists. A `Result` wrapper around one predicate (`CheckEligibility`) is Category 3, not this.

## Output Format

Findings contribute to the consuming workflow's unified output. Each entry:

```
### [Must | Recommend] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction | Redundant Indirection | Incidental (a correctness bug outside the four)}{ (inverted)}
- Code: {one-line citation, e.g., `validates :user, presence: true`}
- Redundant because: {FK name | NOT NULL column | unique index | CHECK constraint | enum | framework guarantee | swallows <classes> (a blanket rescue) | speculative | adds no behaviour | n/a - incidental}
- Evidence: {schema file (schema.rb / structure.sql) | migrations shown | call-site count supplied | call-site count by grep (state the pattern) | form usage supplied | Gemfile / lockfile | config read (sidekiq.yml, initializers) | code in diff | code read (existing files)}
- Cost: {extra SELECT per save or per row on a hot path | masked exception | hidden transaction boundary | silent duplicates | silent bad data (a missing NOT NULL, FK or CHECK) | incorrect behaviour (incidental) | speculative surface area | negligible (CPU only)}
- Recommendation: {concrete edit}
- Justified when: {one-line note} {only when a legitimate reason might apply}
```

An inverted (missing-constraint) finding appends ` (inverted)` to its Category and writes `Unsafe because: {missing unique index | missing NOT NULL | missing FK | missing CHECK}` in place of `Redundant because:` - the unique-index pattern above is the shape for all four: the validation exists, the constraint does not, so raw SQL or a second writer bypasses it; its Cost is `silent duplicates` for uniqueness and `silent bad data` for the rest. A blanket `rescue StandardError` takes `Redundant because: swallows <classes>`. `speculative` means fewer call sites, types or consumers than the pattern's bar (one call site, a second type or implementer, or 3+ for a service or base class), a consumer that discards the value, or a column no code reads, or a non-unique index no query uses and no foreign key needs (Category 3, bar: one reader); `adds no behaviour` is a pure pass-through (Category 4); a registry or singleton that only resolves names is Category 4, one built for consumers that do not exist is Category 3; a component or helper with no call site, or a row rendered by both a partial and a component, is Category 3 with `speculative`. A `[Must]` entry's `Cost` is any value except `negligible` (the Rules' escalation list); it is `speculative surface area` only on a proposal, at the scale of a new layer (a base class plus adapters plus config) - the cost is paid at merge. `file:line` takes a range (`app/services/pricing/engine.rb:1-27`) when one entry covers a merged set. Reviewing a proposal rather than a diff: the target is the design, so write `file:line` as `<proposed path> (new file)`, read `Code:` as the proposed shape, and let `[Must]` mean "do not build this". An incidental correctness bug noticed while gathering evidence (an HTTP call under a row lock, success returned on failure, a stacked retry channel, a queue nothing consumes, an N+1 inside a helper) gets its own `Incidental` entry, listed after the four categories and their footers and counted in no category footer, not a footnote inside another finding; it carries no `Justified when` line, and a security defect (injection, an unscoped lookup) is a one-line sibling pointer to `rails-security-patterns` instead.

A line that fits two categories gets one entry under the dominant category, with the second concern folded into the Recommendation. Several findings resolved by one fix (delete the class) merge into a single entry citing all of them. Entries run in category order, each category's entries directly above its footer, `[Must]` first within a category.

Every category ends with this footer, so reviewers and re-reviews see what was considered and why it passed. `N` counts the entries filed under that category; a concern folded into another category's entry, or a category with nothing to consider, gets one `Considered, not flagged` line saying so:

```
### {Category}: {N findings | no findings}

- Considered, not flagged: {code | none} - {the don't-flag rule it matched | config not in evidence | folded into <entry> | nothing in the reviewed code for this category} (several items on the one line, separated by `;`)
```

## Avoid

- Recommending removal of uniqueness validation without confirming a unique index exists. The validation races and does not *prevent* duplicates, but it is often the only thing keeping them rare and visible - removing it makes them silent
- Reading "no index in the migrations I was shown" as "no index exists" - say which schema evidence you had
- Recommending changes that require a migration without saying so
