---
name: rails-service-objects
description: "Service object patterns for Rails. When to extract, naming (verb-based), Result objects, input validation, error handling, composition, and anti-patterns."
user-invocable: false
---

## When to Extract

- Business logic > 10 lines in a controller or model
- Multi-model operations (create order + update inventory + notify)
- External API interactions
- Complex calculations or transformations
- Logic that needs independent testing

## Naming Convention

Verb-based, singular purpose. Place in `app/services/`.

```
app/services/
  create_order.rb
  process_payment.rb
  sync_inventory.rb
  orders/
    calculate_total.rb
    apply_discount.rb
```

## .call Interface

```ruby
# app/services/create_order.rb
class CreateOrder
  def initialize(customer:, items:, coupon_code: nil)
    @customer = customer
    @items = items
    @coupon_code = coupon_code
  end

  def call
    ActiveRecord::Base.transaction do
      order = build_order
      apply_discount(order) if @coupon_code
      order.save!
      enqueue_confirmation(order)
      Result.success(order)
    end
  rescue ActiveRecord::RecordInvalid => e
    Result.failure(e.record.errors.full_messages)
  rescue Coupon::ExpiredError
    Result.failure(["Coupon code has expired"])
  end

  private

  def build_order
    Order.new(
      customer: @customer,
      line_items: @items.map { |item| LineItem.new(item) },
      total: calculate_total
    )
  end

  def apply_discount(order)
    coupon = Coupon.find_by!(code: @coupon_code)
    order.total *= (1 - coupon.discount_percentage / 100.0)
  end

  def calculate_total
    @items.sum { |item| item[:price] * item[:quantity] }
  end

  def enqueue_confirmation(order)
    OrderConfirmationJob.perform_async(order.id)
  end
end
```

## Result Object

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

## Controller Usage

```ruby
class OrdersController < ApplicationController
  def create
    result = CreateOrder.new(
      customer: current_user,
      items: order_params[:items],
      coupon_code: order_params[:coupon_code]
    ).call

    if result.success?
      render json: result.value, status: :created
    else
      render json: { errors: result.errors }, status: :unprocessable_entity
    end
  end
end
```

## Input Validation at Boundary

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

## Composition (Orchestrator Services)

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
    NotifyWarehouse.new(order: result.value).call

    Result.success(result.value)
  end
end
```

## Anti-Patterns

- ❌ Wrapper around a single ActiveRecord method — just call the method directly
- ❌ God services — >100 lines means you need to decompose
- ❌ Services that only call other services — unnecessary indirection
- ❌ Services without a clear single responsibility
- ❌ Using service objects for simple CRUD — controllers handle that fine
- ❌ Returning raw exceptions — use Result objects for expected failures
