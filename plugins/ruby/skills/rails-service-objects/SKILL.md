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
- New features with multi-step mutations + transactions
- Refactoring fat controllers / models
- Orchestrating multi-service flows (checkout, fulfillment)
- Wrapping external API calls with idempotency and error handling

## Rules

- One service, one responsibility - verb-named (`FulfillOrder`, `ChargeCustomer`)
- Always return `Result`; never raw values or exceptions for expected failures
- Multi-model mutations in `ActiveRecord::Base.transaction`
- External API calls (Stripe, S3, HTTP) live outside the transaction
- Dispatch Sidekiq jobs after the transaction commits
- Validate inputs in `initialize` (`ArgumentError` on invariants)
- Authorization in controllers (Pundit), not services
- Decompose services >100 lines

## Patterns

### `.call` + Result Object

```ruby
# app/services/result.rb
class Result
  attr_reader :value, :errors, :code

  def initialize(success:, value: nil, errors: [], code: nil)
    @success, @value, @errors, @code = success, value, Array(errors), code
  end

  def success? = @success
  def failure? = !@success

  def self.success(value = nil)          = new(success: true, value: value)
  def self.failure(errors, code: nil)    = new(success: false, errors: errors, code: code)
end
```

`code:` is the controller's branch for HTTP status mapping (`:out_of_stock` -> 409, `:payment_declined` -> 402). String-matching `errors` is fragile.

### Naming and Placement

Verb + domain noun. Place in `app/services/`, nest by domain when the count grows:

```
app/services/
  checkout.rb                # orchestrator
  charge_customer.rb
  create_order.rb
  inventory/
    decrement.rb
```

Top-level for orchestrators; subdirectory for sub-services owned by one orchestrator.

### Service Body

```ruby
class FulfillOrder
  def initialize(order:, fulfilled_by: nil)
    @order, @fulfilled_by = order, fulfilled_by
    raise ArgumentError, "Order required"           unless @order
    raise ArgumentError, "Order must be confirmed"  unless @order.confirmed?
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
    product_ids = @order.order_items.map(&:product_id)
    products = Product.where(id: product_ids).lock("FOR UPDATE").index_by(&:id)
    @order.order_items.each do |item|
      product = products.fetch(item.product_id)
      raise Inventory::InsufficientStockError, "#{product.name} short" if product.available_stock < item.quantity
      product.decrement!(:available_stock, item.quantity)
    end
  end
end
```

Stock decrement under concurrency requires row locking - `lock("FOR UPDATE")` prevents oversell.

### External API Calls and Compensating Actions

Network calls inside `Model.transaction` hold the connection across the round-trip and produce inversions:

- Stripe call inside transaction + transaction rollback after success = "paid but no order"
- Stripe call outside transaction + Stripe success + DB write fails = same inversion, but now you control it

Correct order: validate -> charge (outside txn) -> open transaction with the resulting payment ID -> commit -> dispatch jobs. If the DB write fails after charging, enqueue a reconciliation job (the compensating action) - inline refund compounds failure:

```ruby
def call
  payment = ChargeCustomer.new(cart: @cart, idempotency_key: @key).call
  return payment if payment.failure?

  order_result = CreateOrder.new(cart: @cart, payment: payment.value).call
  if order_result.failure?
    PaymentReconciliationJob.perform_async(payment.value.id, "order_write_failed")
    return order_result
  end

  ShipmentNotificationJob.perform_async(order_result.value.id)
  Result.success(order_result.value)
end
```

### Idempotency Keys

For mutating services callable via "at-least-once" paths (HTTP retry, Sidekiq retry, double-click):

```ruby
class ChargeCustomer
  def initialize(cart:, idempotency_key:)
    @cart, @idempotency_key = cart, idempotency_key
  end

  def call
    if existing = Payment.find_by(idempotency_key: @idempotency_key)
      return replay(existing)
    end

    payment = Payment.create!(
      cart_id: @cart.id, amount_cents: @cart.total_cents,
      idempotency_key: @idempotency_key, status: :pending     # column has unique index
    )
    intent = Stripe::PaymentIntent.create(
      { amount: payment.amount_cents, ... },
      idempotency_key: @idempotency_key                       # forward upstream
    )
    payment.update!(stripe_id: intent.id, status: :authorized)
    Result.success(payment)
  rescue ActiveRecord::RecordNotUnique
    Result.success(Payment.find_by!(idempotency_key: @idempotency_key))
  rescue Stripe::CardError => e
    Result.failure([e.message], code: :payment_declined)
  end

  private

  def replay(payment)
    case payment.status
    when "authorized", "captured" then Result.success(payment)
    when "declined"               then Result.failure([payment.failure_reason], code: :payment_declined)
    else                               Result.failure(["in-flight"], code: :conflict)
    end
  end
end
```

Unique index on `idempotency_key` turns a race into `RecordNotUnique` we recover cleanly. The orchestrator threads the key through all child services so a replay produces consistent results across the chain.

### Transaction Discipline

For full transaction boundary rules - nested transactions, `requires_new`, `after_commit` vs `after_save`, `after_commit_everywhere` for nested dispatch, isolation levels, and deadlock retry - use skill: `rails-transaction-patterns`. The service-object specific summary:

- Outer service owns the transaction; inner services either don't open one (called from one place) or use `requires_new: true` (called from many).
- External calls outside; DB writes inside; Sidekiq dispatch after commit via `after_commit_everywhere` when nested.

### Composition (Orchestrator)

```ruby
class Checkout
  def initialize(cart:, payment_method_id:, idempotency_key:)
    @cart, @pm, @key = cart, payment_method_id, idempotency_key
  end

  def call
    if existing = Order.joins(:payment).find_by(payments: { idempotency_key: @key })
      return Result.success(existing)
    end

    validation = ValidateCart.new(cart: @cart).call
    return validation if validation.failure?

    payment = ChargeCustomer.new(cart: @cart, payment_method_id: @pm, idempotency_key: @key).call
    return payment if payment.failure?

    order = CreateOrder.new(cart: @cart, payment: payment.value).call
    if order.failure?
      PaymentReconciliationJob.perform_async(payment.value.id, "order_failed")
      return order
    end

    ShipmentNotificationJob.perform_async(order.value.id)
    InvoiceEmailJob.perform_async(order.value.id)
    Result.success(order.value)
  end
end
```

### Controller Usage

Authorize, call, branch on `result.code`:

```ruby
def create
  @cart = current_user.cart
  authorize @cart, :checkout?

  result = Checkout.new(
    cart: @cart,
    payment_method_id: params.require(:payment_method_id),
    idempotency_key: request.headers["Idempotency-Key"] || "cart-#{@cart.id}-#{@cart.updated_at.to_i}"
  ).call

  if result.success?
    render json: OrderSerializer.new(result.value), status: :created
  else
    render json: { errors: result.errors, code: result.code }, status: status_for(result.code)
  end
end

private

def status_for(code)
  { cart_invalid: :unprocessable_entity, out_of_stock: :conflict,
    payment_declined: :payment_required, conflict: :conflict }.fetch(code, :unprocessable_entity)
end
```

## Output Format

```
Service: {class name}
Location: app/services/{file}.rb
Responsibility: {one sentence}
Transaction: {Yes - models mutated | No}
External API: {provider, called outside transaction? compensating action if so}
Idempotency: {key source and propagation; unique constraint location}
Sidekiq Jobs: {job names dispatched after commit, or "None"}
Result: Success({value type}) | Failure({code enum: out_of_stock | payment_declined | ...})
```

## Avoid

- Wrapper around a single AR method - call the method directly
- Services that only call other services without adding logic - unnecessary indirection
- Raw exceptions for expected failures - use Result
- `.perform_async` or external API call inside a DB transaction
- Authorization inside a service - belongs in the controller
- Inline refund / undo on partial failure - enqueue a reconciliation job
- Stock decrement without `lock("FOR UPDATE")` - races oversell
- Inner `transaction` rescued by outer service - savepoint commits partial writes
