---
name: rails-service-objects
description: Rails service objects: .call + Result, transaction boundaries, external-API ordering, idempotency keys, compensating actions, composition.
metadata:
  category: backend
  tags: [ruby, rails, service-objects, architecture, patterns]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Extracting business logic spanning multiple models or external APIs
- Multi-step mutations with transactions
- Refactoring fat controllers / models
- Wrapping external API calls with idempotency

Extraction bar - either limb is sufficient on its own: (a) the operation spans 2+ models or an external API **and** owns a transaction boundary, or (b) it has 3+ call sites. One call site is no objection under (a). A single-call-site, single-model operation meeting neither stays in the model or controller.

## Rules

- One service, one responsibility, verb-named (`FulfillOrder`, `ChargeCustomer`); place in `app/services/`, nest by domain when count grows. Entrypoint is instance `.call` - not class-method `run`/`execute`; a `def self.call(...) = new(...).call` shim is compliant (naming is the rule, not the shim).
- `call` returns `Result` for expected failures; raise only for programmer errors / unexpected state. `RecordNotFound` on user-supplied IDs is expected (Result); on internal IDs it's a bug (raise).
- Validate inputs in `initialize` (`ArgumentError` on invariants); authorization stays in controllers (Pundit).
- DB writes inside `ActiveRecord::Base.transaction`; external API calls outside; Sidekiq dispatch after commit.
- On partial failure after an external call succeeds, enqueue a reconciliation job - never inline refund / undo.

## Patterns

### `.call` + Result

```ruby
# app/services/result.rb
class Result
  attr_reader :value, :errors, :code

  def initialize(success:, value: nil, errors: [], code: nil)
    @success, @value, @errors, @code = success, value, Array(errors), code
  end

  def success? = @success
  def failure? = !@success

  def self.success(value = nil)       = new(success: true, value: value)
  def self.failure(errors, code: nil) = new(success: false, errors: errors, code: code)
end
```

`code:` drives HTTP status mapping in controllers (`:out_of_stock` -> 409, `:payment_declined` -> 402). String-matching `errors` is fragile.

### Service Body

```ruby
class FulfillOrder
  def initialize(order:, fulfilled_by: nil)
    @order, @fulfilled_by = order, fulfilled_by
    raise ArgumentError, "Order required" unless @order   # nil/type invariants only
  end

  def call
    return Result.failure(["Order must be confirmed"], code: :not_confirmed) unless replayable?

    unless @order.processing? || @order.fulfilled?          # skip the work, not the dispatch
      ActiveRecord::Base.transaction do
        @order.update!(status: :processing, fulfilled_at: Time.current)
        decrement_inventory
      end
    end
    ShipmentNotificationJob.perform_async(@order.id)   # post-commit; the job is idempotent
    Result.success(@order.reload)
  rescue Inventory::InsufficientStockError => e
    Result.failure([e.message], code: :out_of_stock)
  end

  private

  # Confirmed is the entry state; processing/fulfilled mean a previous run already
  # got here. Both are replayable - only anything else is a real precondition failure.
  def replayable?
    @order.confirmed? || @order.processing? || @order.fulfilled?
  end

  def decrement_inventory
    products = Product.where(id: @order.order_items.map(&:product_id))
                      .order(:id).lock("FOR UPDATE").index_by(&:id)
    @order.order_items.each do |item|
      product = products.fetch(item.product_id)
      raise Inventory::InsufficientStockError, "#{product.name} short" if product.available_stock < item.quantity
      product.decrement!(:available_stock, item.quantity)
    end
  end
end
```

`order(:id)` before `lock("FOR UPDATE")` prevents oversell *and* kills the A->B/B->A deadlock two carts sharing products would otherwise hit. For lock semantics, use skill: `rails-db-locking-patterns`.

### External API Ordering + Compensating Action

Network calls inside a transaction hold the DB connection across the round-trip and invert failure modes. Correct order: validate -> charge (outside txn) -> open transaction with the payment ID -> commit -> dispatch jobs.

- Multiple external systems: the call whose failure must abort the flow goes before the transaction; deferrable or flaky systems go after commit as Sidekiq jobs. The test is one question - *if this call fails, is the local write still correct?* No means it gates, so it goes first (charge, refund, inventory reservation at a third party). Yes means it is deferrable, so it goes after commit with a reconciliation path (ERP sync, notifications, search indexing, carrier booking that can be retried against an order that already exists). A post-commit external failure degrades to its reconciliation path - it never fails the Result.
- Contended resource (slot, seat, stock): the canonical order above assumes the mutation isn't claiming a contended resource. The test here is also one question - *could a concurrent run take the same thing?* A finite pool that two requests can exhaust (seats, stock, a unique slug) is contended and wants the two-transaction claim below. A single row only this request's key can touch is not contended, however much retry-safety it needs - idempotency alone is the first carve-out, not this one. When it is, prefer the two-transaction variant: txn 1 claims under row lock (pending state) -> charge -> txn 2 finalizes. Releasing your own pending claim on charge failure is a compensating write against a row only you own, not the forbidden inline undo (which refers to reversing a *succeeded* external call). Because txn 1 has already committed, that release can itself fail - so a scheduled sweep of stale pending rows is mandatory, not optional, or a crash between claim and finalize orphans the resource forever. The sweep is the reconciliation job below, never a blind TTL: a claim can be stale precisely because the charge *succeeded* and txn 2 never committed, and expiring that one releases the seat while the customer stays charged. Query ground truth first, finalize if the charge landed, release only if it did not.
- Idempotency-key rows are the second carve-out: the key row is persisted in its own transaction *before* the external call, because a durable record of an in-flight call is what makes the retry safe. Only mutations referencing the external result go in the post-call transaction. Those rows need the same sweep for the same reason - a crash between `create!` and the status write leaves `pending` forever, and a replay that answers "in flight" indefinitely is a charge that never becomes an order.
- Orchestrators are replay-safe at the top, but a replay guard skips the *work*, not the post-commit dispatch. Returning early on the whole method drops the job on every replay, so a crash in the window between commit and dispatch loses it permanently - the guard has to sit around the transaction, with the dispatch after it and the job itself idempotent. (An outbox row written inside the transaction is the stronger form when losing the job is unacceptable.) Result stays binary - deferred post-commit work pending is still Success, with the job listed in the output block.
- A reconciliation job re-checks ground truth (was the charge captured? does the row exist?) and completes or reverses; it alerts after exhausting retries.

If the DB write fails after a successful charge, enqueue a reconciliation job:

```ruby
def call
  payment = ChargeCustomer.new(cart: @cart, idempotency_key: @key).call
  return payment if payment.failure?

  begin
    order = CreateOrder.new(cart: @cart, payment: payment.value).call
  rescue StandardError                                   # raise path needs it too
    PaymentReconciliationJob.perform_async(payment.value.id, "order_write_failed")
    raise
  end

  if order.failure?
    PaymentReconciliationJob.perform_async(payment.value.id, "order_write_failed")
    return order
  end

  ShipmentNotificationJob.perform_async(order.value.id)
  Result.success(order.value)
end
```

### Idempotency Keys

For mutating services on at-least-once paths (HTTP retry, Sidekiq retry, double-click), thread one key through the chain and back it with a unique DB index (`add_index :payments, :idempotency_key, unique: true`). Key source by trigger: client `Idempotency-Key` header when the client cooperates; otherwise derive deterministically from intent (`"book-#{user_id}-#{slot_id}"`) for double-click/UI paths, or from job args for Sidekiq retries.

```ruby
class ChargeCustomer
  def initialize(cart:, idempotency_key:)
    @cart, @key = cart, idempotency_key
    raise ArgumentError, "idempotency_key required" if @key.blank?   # nil key would match any NULL row
  end

  def call
    existing = Payment.find_by(idempotency_key: @key)                # assign on its own line - see below
    return replay(existing) if existing

    payment = Payment.create!(cart_id: @cart.id, amount_cents: @cart.total_cents,
                              idempotency_key: @key, status: :pending)  # durable before the call
    intent  = BillingClient.new.create_intent(amount_cents: payment.amount_cents,
                                              idempotency_key: @key)
    payment.update!(stripe_id: intent.id, status: status_for(intent.status))
    settle(payment)
  rescue ActiveRecord::RecordNotUnique
    replay(Payment.find_by!(idempotency_key: @key))                  # race loser
  rescue BillingError::Declined => e
    payment&.update!(status: :declined)          # terminal, or the key wedges forever
    Result.failure([e.message], code: :payment_declined)
  end

  private

  # Three outcomes, not two: "not captured" is not the same as "failed".
  def settle(payment)
    return Result.success(payment) if payment.captured?
    return Result.failure(["payment declined"], code: :payment_declined) if payment.declined?

    PaymentReconciliationJob.perform_async(payment.id, "charge_in_flight")
    Result.failure(["payment incomplete"], code: :requires_action)
  end

  # A row alone proves nothing - only a terminal row does.
  def replay(payment)
    return Result.success(payment)                                    if payment.captured?
    return Result.failure(["payment declined"], code: :payment_declined) if payment.declined?
    return Result.failure(["charge in flight"], code: :idempotency_conflict) if payment.fresh?

    # A pending row older than the charge timeout is not "in flight" - it is unknown.
    # Ask the gateway by key before answering; never expire it blind.
    PaymentReconciliationJob.perform_async(payment.id, "pending_expired")
    Result.failure(["payment state unknown - reconciling"], code: :idempotency_conflict)
  end
end
```

Four things this shape gets right, each a live bug in its absence:

- **Assign on its own line.** `return ... if (existing = Payment.find_by(...))` raises `NameError`: Ruby binds locals at parse time in textual order, and a modifier-`if` body parses before its condition, so `existing` in the body compiles as a method call. It fails on exactly the replay path the guard exists for.
- **Gate the replay on terminal state.** Returning Success for any row with the key hands the caller a success while the winner's charge is still in flight - or was declined - and the orchestrator creates an order against money never captured.
- **Require the key.** `find_by(idempotency_key: nil)` returns an arbitrary NULL-key row, and the unique index does not backstop it: both PostgreSQL and MySQL permit unlimited NULLs in a unique index.
- **Derive the status from the response, and branch three ways.** Creating a payment intent does not authorize funds - it can land in `requires_payment_method`, `requires_action` (3DS), or `processing`. Marking it authorized on the mere existence of an id ships goods for free. But mapping everything non-captured to a plain failure is the mirror bug: `processing` may still capture, and a bare failure makes the orchestrator abandon a live charge with no reconciliation. Captured succeeds, declined fails, anything in between fails *and* enqueues reconciliation.
- **Write a terminal state on every exit.** The rescue must mark the row `declined` before returning; otherwise the pending row it created is never resolved, `replay` can never reach its declined branch, and every later request with that key gets `:idempotency_conflict` forever - one declined card wedges the key permanently.

The SDK call sits behind `BillingClient`, not in the service: services never name a vendor error class (`Stripe::CardError`) - the client translates at the boundary. For the client and its idempotency header, use skill: `rails-http-client-patterns`; for the error taxonomy, `rails-exception-handling`.

### Transaction Discipline

For nested transactions, `requires_new`, `after_commit` vs `after_save`, isolation levels, and deadlock retry, use skill: `rails-transaction-patterns`. Service-specific:

- Outer service owns the transaction; inner services either don't open one or use `requires_new: true`.
- Post-commit dispatch via `after_commit_everywhere` when nested.

### Controller Usage

```ruby
def create
  authorize @cart, :checkout?
  result = Checkout.new(cart: @cart, payment_method_id: params.require(:payment_method_id),
                        idempotency_key: request.headers["Idempotency-Key"]).call
  if result.success?
    render json: OrderSerializer.new(result.value), status: :created
  else
    render json: { errors: result.errors, code: result.code }, status: status_for(result.code)
  end
end

def status_for(code)
  # Every code any composed service can emit needs an entry - an orchestrator that
  # returns a child's Result verbatim leaks the child's codes to this mapping.
  { cart_invalid: :unprocessable_entity, out_of_stock: :conflict,
    payment_declined: :payment_required, requires_action: :payment_required,
    idempotency_conflict: :conflict, not_confirmed: :unprocessable_entity
  }.fetch(code, :unprocessable_entity)
end
```

## Output Format

One block per service (orchestrator and each child; plain jobs don't get blocks). In review mode, precede the blocks with a numbered findings list, each finding citing the violated rule; the block describes the corrected service - that is where target state lives, so no separate remediation section is written. A service recommended for deletion, or a class in `app/services/` that is not a service at all (a calculator, a strategy, a value object), gets findings only and no block, with one line saying which it is.

```
Service: {ClassName}

Location: app/services/{file}.rb

Responsibility: {one sentence}

Transaction: {Yes - models mutated | No}

External API: {provider; outside transaction? compensating action: <job name | absent - GAP | N/A>}

Idempotency: {key source; unique index column | row lock on a state column (claim/finalize) | gateway-side only - no local index | none - GAP if the path is at-least-once}

Sidekiq Jobs: {jobs dispatched after commit | dispatched on a failure branch only (name it) | None}

Result: Success({value}) | Failure({code enum})
```

When the deliverable is the shared `Result` contract itself rather than one service, emit this block once instead, and list the failure codes the project registers:

```
Result API: success({value}) / failure({errors}, code:) - readers: value, errors, code, success?, failure?

Codes: {the project's registry, or "none - define one" }

Consumed by: {controller: code -> HTTP status | job: retry on <codes>, drop on <codes> | service: return early on failure?}
```

## Avoid

- Wrapper around a single AR method - call the method directly
- Pure delegation services adding no logic - unnecessary indirection
- Raw exceptions for expected failures - use Result
- `.perform_async` or external API call inside a DB transaction
- Authorization inside a service - belongs in the controller
- Inline refund / undo on partial failure - enqueue a reconciliation job
- Stock decrement without `lock("FOR UPDATE")` - races oversell
