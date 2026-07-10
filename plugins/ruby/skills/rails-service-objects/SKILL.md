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

## Rules

- One service, one responsibility, verb-named (`FulfillOrder`, `ChargeCustomer`); place in `app/services/`, nest by domain when count grows. Entrypoint is instance `.call` - not class-method `run`/`execute`.
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
    raise ArgumentError, "Order required"          unless @order
    raise ArgumentError, "Order must be confirmed" unless @order.confirmed?
  end

  def call
    ActiveRecord::Base.transaction do
      @order.update!(status: :processing, fulfilled_at: Time.current)
      decrement_inventory
    end
    ShipmentNotificationJob.perform_async(@order.id)   # post-commit
    Result.success(@order.reload)
  rescue Inventory::InsufficientStockError => e
    Result.failure([e.message], code: :out_of_stock)
  end

  private

  def decrement_inventory
    products = Product.where(id: @order.order_items.map(&:product_id))
                      .lock("FOR UPDATE").index_by(&:id)
    @order.order_items.each do |item|
      product = products.fetch(item.product_id)
      raise Inventory::InsufficientStockError, "#{product.name} short" if product.available_stock < item.quantity
      product.decrement!(:available_stock, item.quantity)
    end
  end
end
```

`lock("FOR UPDATE")` prevents oversell under concurrent fulfillment. For lock semantics, use skill: `rails-db-locking-patterns`.

### External API Ordering + Compensating Action

Network calls inside a transaction hold the DB connection across the round-trip and invert failure modes. Correct order: validate -> charge (outside txn) -> open transaction with the payment ID -> commit -> dispatch jobs.

- Multiple external systems: the call whose failure must abort the flow (charge, refund) goes before the transaction; deferrable or flaky systems (ERP sync, notifications) go after commit as Sidekiq jobs. A post-commit external failure degrades to its reconciliation path - it never fails the Result.
- Contended resource (slot, seat, stock): the canonical order above assumes the mutation isn't claiming a contended resource. When it is, prefer the two-transaction variant: txn 1 claims under row lock (pending state) -> charge -> txn 2 finalizes. On charge failure, releasing your own pending claim is normal rollback, not the forbidden inline undo (which refers to reversing a *succeeded* external call).
- Orchestrators are replay-safe at the top: first line of `call` returns `Result.success` if the operation already completed (`order.cancelled?`). Result stays binary - deferred post-commit work pending is still Success, with the job listed in the output block.
- A reconciliation job re-checks ground truth (was the charge captured? does the row exist?) and completes or reverses; it alerts after exhausting retries.

If the DB write fails after a successful charge, enqueue a reconciliation job:

```ruby
def call
  payment = ChargeCustomer.new(cart: @cart, idempotency_key: @key).call
  return payment if payment.failure?

  order = CreateOrder.new(cart: @cart, payment: payment.value).call
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
  def call
    return Result.success(existing) if (existing = Payment.find_by(idempotency_key: @key))  # replay: same key -> same outcome

    payment = Payment.create!(cart_id: @cart.id, amount_cents: @cart.total_cents,
                              idempotency_key: @key, status: :pending)
    intent  = Stripe::PaymentIntent.create({ amount: payment.amount_cents, ... },
                                           idempotency_key: @key) # forward upstream
    payment.update!(stripe_id: intent.id, status: :authorized)
    Result.success(payment)
  rescue ActiveRecord::RecordNotUnique
    Result.success(Payment.find_by!(idempotency_key: @key))      # race winner
  rescue Stripe::CardError => e
    Result.failure([e.message], code: :payment_declined)
  end
end
```

The unique index converts the race into `RecordNotUnique` we recover cleanly. The orchestrator passes the same key into every child so replays are consistent. For HTTP-side idempotency headers, use skill: `rails-http-client-patterns`.

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
  { cart_invalid: :unprocessable_entity, out_of_stock: :conflict,
    payment_declined: :payment_required }.fetch(code, :unprocessable_entity)
end
```

## Output Format

One block per service (orchestrator and each child; plain jobs don't get blocks). In review mode, precede the blocks with a numbered findings list, each finding citing the violated rule; the block describes the corrected service. A service recommended for deletion gets findings only, no block.

```
Service: {ClassName}
Location: app/services/{file}.rb
Responsibility: {one sentence}
Transaction: {Yes - models mutated | No}
External API: {provider; outside transaction? compensating action: <job name | N/A>}
Idempotency: {key source; unique index column}
Sidekiq Jobs: {jobs dispatched after commit | None}
Result: Success({value}) | Failure({code enum})
```

## Avoid

- Wrapper around a single AR method - call the method directly
- Pure delegation services adding no logic - unnecessary indirection
- Raw exceptions for expected failures - use Result
- `.perform_async` or external API call inside a DB transaction
- Authorization inside a service - belongs in the controller
- Inline refund / undo on partial failure - enqueue a reconciliation job
- Stock decrement without `lock("FOR UPDATE")` - races oversell
