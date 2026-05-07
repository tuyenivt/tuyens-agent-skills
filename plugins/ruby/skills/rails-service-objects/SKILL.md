---
name: rails-service-objects
description: Service object design patterns for Rails. Covers extraction criteria, verb-based naming, the .call interface with Result objects, input boundary validation, error handling, and service composition.
metadata:
  category: backend
  tags: [ruby, rails, service-objects, architecture, patterns]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Extracting business logic that spans multiple models or external APIs
- Creating a new feature that involves multi-step mutations with transactions
- Refactoring fat controllers or models with >10 lines of business logic
- Composing multiple operations into an orchestrator (e.g., order fulfillment flow)
- Wrapping external API calls with error handling and Result objects

## Rules

- One service, one responsibility - name with a verb describing the action
- Always return a `Result` object, never raw values or exceptions for expected failures
- Wrap multi-model mutations in `ActiveRecord::Base.transaction`
- Dispatch Sidekiq jobs AFTER the transaction commits, never inside it - if the job fires before commit, the worker may read stale data or a row that does not exist yet
- Validate inputs at the boundary (in `initialize` or a `validate_inputs!` method)
- Place services in `app/services/`, namespaced by domain if needed
- Keep services under 100 lines - decompose into smaller services if larger

## Patterns

### When to Extract

Extract to a service when:

| Signal                                        | Example                                  |
| --------------------------------------------- | ---------------------------------------- |
| Business logic > 10 lines in controller/model | Order total calculation with discounts   |
| Multi-model operations                        | Create order + update inventory + notify |
| External API interactions                     | Payment gateway, shipping API            |
| Complex calculations                          | Tax calculation, pricing rules           |
| Logic needing independent testing             | Fulfillment eligibility checks           |

### Naming Convention

Verb-based, singular purpose. Place in `app/services/`:

```
app/services/
  fulfill_order.rb
  create_order.rb
  process_payment.rb
  orders/
    calculate_total.rb
    apply_discount.rb
```

### .call Interface with Result Object

Bad - returning raw values and raising for expected failures:

```ruby
class CreateOrder
  def call
    order = Order.create!(params) # raises on validation failure
    order # returns raw AR object
  end
end
```

Good - Result object with transaction and post-commit dispatch:

```ruby
# app/services/fulfill_order.rb
class FulfillOrder
  def initialize(order:, fulfilled_by: nil)
    @order = order
    @fulfilled_by = fulfilled_by
    validate_inputs!
  end

  def call
    ActiveRecord::Base.transaction do
      @order.update!(status: :processing, fulfilled_at: Time.current)
      decrement_inventory
    end
    # AFTER transaction commits - worker will find the committed row
    ShipmentNotificationJob.perform_async(@order.id)
    Result.success(@order.reload)
  rescue ActiveRecord::RecordInvalid => e
    Result.failure(e.record.errors.full_messages)
  rescue Inventory::InsufficientStockError => e
    Result.failure([e.message])
  end

  private

  def validate_inputs!
    raise ArgumentError, "Order is required" unless @order
    raise ArgumentError, "Order must be confirmed to fulfill" unless @order.confirmed?
  end

  def decrement_inventory
    @order.order_items.includes(:product).each do |item|
      InventoryService.new(product: item.product).decrement!(item.quantity)
    end
  end
end
```

### Result Object

```ruby
# app/services/result.rb
class Result
  attr_reader :value, :errors

  def initialize(success:, value: nil, errors: [])
    @success = success
    @value = value
    @errors = errors
  end

  def success?
    @success
  end

  def failure?
    !@success
  end

  def self.success(value = nil)
    new(success: true, value: value)
  end

  def self.failure(errors)
    new(success: false, errors: Array(errors))
  end
end
```

### Controller Usage

```ruby
class OrdersController < ApplicationController
  def fulfill
    order = Order.find(params[:id])
    authorize order
    result = FulfillOrder.new(order: order, fulfilled_by: current_user).call

    if result.success?
      render json: OrderSerializer.new(result.value), status: :ok
    else
      render json: { errors: result.errors }, status: :unprocessable_entity
    end
  end
end
```

### Input Validation at Boundary

```ruby
class ProcessPayment
  def initialize(order:, payment_method:, amount:)
    @order = order
    @payment_method = payment_method
    @amount = amount
    validate_inputs!
  end

  def call
    # business logic here
  end

  private

  def validate_inputs!
    raise ArgumentError, "Order is required" unless @order
    raise ArgumentError, "Amount must be positive" unless @amount&.positive?
    raise ArgumentError, "Invalid payment method" unless valid_payment_method?
  end

  def valid_payment_method?
    %w[card bank_transfer wallet].include?(@payment_method)
  end
end
```

### Composition (Orchestrator Services)

When a workflow composes multiple services, use early return on failure to short-circuit:

```ruby
# app/services/checkout.rb
class Checkout
  def initialize(cart:, payment_method:)
    @cart = cart
    @payment_method = payment_method
  end

  def call
    result = CreateOrder.new(customer: @cart.customer, items: @cart.items).call
    return result if result.failure?

    payment_result = ProcessPayment.new(
      order: result.value,
      payment_method: @payment_method,
      amount: result.value.total
    ).call
    return payment_result if payment_result.failure?

    ClearCart.new(cart: @cart).call
    Result.success(result.value)
  end
end
```

## Output Format

When generating a service object, document:

```
Service: {class name}
Location: app/services/{file_name}.rb
Responsibility: {one-sentence description of what it does}
Transaction: {Yes | No} - {which models are mutated}
Sidekiq Jobs: {job names dispatched after commit, or "None"}
Result: Success({value type}) | Failure({error scenarios})
```

## Avoid

- Wrapper around a single ActiveRecord method - just call the method directly
- God services >100 lines - decompose into smaller focused services
- Services that only call other services without adding logic - unnecessary indirection
- Services without a clear single responsibility
- Using service objects for simple CRUD - controllers handle that fine
- Returning raw exceptions - use Result objects for expected failures
- Dispatching Sidekiq jobs inside a transaction block - worker races the commit
- Missing input validation - fail fast with `ArgumentError` on invalid inputs
