---
name: rails-testing-patterns
description: RSpec testing patterns for Rails 7+/8. Covers the test type hierarchy (model, request, system, service specs), FactoryBot with traits, shoulda-matchers, Sidekiq job testing, Pundit policy specs, VCR/WebMock for external APIs, and shared examples.
metadata:
  category: backend
  tags: [ruby, rails, rspec, testing, factorybot]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing tests for a new feature (models, services, request specs, policies)
- Setting up FactoryBot factories with traits for different model states
- Testing Sidekiq jobs with fake/inline modes
- Testing Pundit policies for role-based access control
- Mocking external API calls with VCR or WebMock
- Reviewing test quality: checking for mystery guests, excessive mocking, or missing edge cases

## Rules

- Never use controller specs - use request specs instead (full HTTP stack)
- Test through the public interface - never test private methods directly
- Use FactoryBot for test data, not fixtures - factories are more flexible and explicit
- Use `build_stubbed` when no DB hit is needed, `build` for in-memory, `create` only when persistence is required
- Mock at boundaries (external APIs, third-party services), not internal code
- Every model spec must cover associations, validations, scopes, and enum definitions
- Every request spec must cover happy path, error cases, and authorization
- Every service spec must assert Result object success/failure states

## Patterns

### Test Type Hierarchy

| Type          | Speed   | Scope           | Use For                                  |
| ------------- | ------- | --------------- | ---------------------------------------- |
| Model specs   | Fastest | Single model    | Validations, scopes, associations, enums |
| Service specs | Fast    | Business logic  | Service objects with Result assertions   |
| Policy specs  | Fast    | Authorization   | Pundit policy rules per role             |
| Request specs | Medium  | Full HTTP stack | Endpoints, status codes, response bodies |
| Job specs     | Fast    | Background work | Sidekiq job behavior and idempotency     |
| System specs  | Slowest | Browser-driven  | Critical user flows (Capybara)           |

### Model Specs

Bad - testing implementation details:

```ruby
it "calls calculate_total internally" do
  expect(order).to receive(:calculate_total) # testing private method
  order.save
end
```

Good - testing behavior through public interface:

```ruby
# spec/models/order_spec.rb
RSpec.describe Order, type: :model do
  describe "associations" do
    it { is_expected.to belong_to(:user).counter_cache(true) }
    it { is_expected.to have_many(:order_items).dependent(:destroy) }
    it { is_expected.to have_many(:products).through(:order_items) }
  end

  describe "validations" do
    it { is_expected.to validate_presence_of(:status) }
    it { is_expected.to validate_numericality_of(:total).is_greater_than(0) }
    it { is_expected.to define_enum_for(:status).with_values(pending: 0, confirmed: 1, processing: 2, shipped: 3, delivered: 4, cancelled: 5) }
  end

  describe "scopes" do
    describe ".fulfillable" do
      it "returns only confirmed orders" do
        confirmed = create(:order, :confirmed)
        create(:order, :pending)
        create(:order, :shipped)
        expect(described_class.fulfillable).to eq([confirmed])
      end
    end
  end
end
```

### Service Specs

Bad - not testing Result object contract:

```ruby
it "fulfills the order" do
  FulfillOrder.new(order: order).call
  expect(order.reload.status).to eq("processing")
end
```

Good - asserting Result success/failure and side effects:

```ruby
# spec/services/fulfill_order_spec.rb
RSpec.describe FulfillOrder do
  let(:order) { create(:order, :confirmed, :with_order_items) }

  describe "#call" do
    context "when order is confirmed with sufficient inventory" do
      it "returns a success result" do
        result = described_class.new(order: order).call
        expect(result).to be_success
        expect(result.value).to eq(order)
      end

      it "transitions order to processing" do
        described_class.new(order: order).call
        expect(order.reload.status).to eq("processing")
      end

      it "sets fulfilled_at timestamp" do
        freeze_time do
          described_class.new(order: order).call
          expect(order.reload.fulfilled_at).to eq(Time.current)
        end
      end

      it "enqueues a shipment notification job" do
        expect {
          described_class.new(order: order).call
        }.to change(ShipmentNotificationJob.jobs, :size).by(1)
      end
    end

    context "when order is not confirmed" do
      let(:order) { create(:order, :pending) }

      it "raises ArgumentError" do
        expect {
          described_class.new(order: order)
        }.to raise_error(ArgumentError, /must be confirmed/)
      end
    end

    context "when inventory is insufficient" do
      before { allow(InventoryService).to receive(:new).and_raise(Inventory::InsufficientStockError) }

      it "returns a failure result" do
        result = described_class.new(order: order).call
        expect(result).to be_failure
        expect(result.errors).to include(/insufficient/i)
      end

      it "does not transition order status" do
        described_class.new(order: order).call
        expect(order.reload.status).to eq("confirmed")
      end
    end
  end
end
```

### Pundit Policy Specs

Bad - testing authorization only in request specs (slow, indirect):

```ruby
# Only testing authorization through HTTP - misses edge cases
it "returns 403 for non-admin" do
  get "/api/v1/orders/#{order.id}", headers: user_headers
  expect(response).to have_http_status(:forbidden)
end
```

Good - dedicated policy specs covering each role:

```ruby
# spec/policies/order_policy_spec.rb
RSpec.describe OrderPolicy do
  subject { described_class.new(user, order) }

  let(:order) { create(:order, user: owner) }
  let(:owner) { create(:user) }

  context "when user is the order owner" do
    let(:user) { owner }

    it { is_expected.to permit_action(:show) }
    it { is_expected.not_to permit_action(:fulfill) }
  end

  context "when user is an admin" do
    let(:user) { create(:user, :admin) }

    it { is_expected.to permit_action(:show) }
    it { is_expected.to permit_action(:fulfill) }
  end

  context "when user is another user" do
    let(:user) { create(:user) }

    it { is_expected.not_to permit_action(:show) }
    it { is_expected.not_to permit_action(:fulfill) }
  end

  describe OrderPolicy::Scope do
    let(:admin) { create(:user, :admin) }
    let(:regular_user) { create(:user) }
    let!(:user_order) { create(:order, user: regular_user) }
    let!(:other_order) { create(:order) }

    it "returns all orders for admin" do
      scope = described_class.new(admin, Order).resolve
      expect(scope).to include(user_order, other_order)
    end

    it "returns only own orders for regular user" do
      scope = described_class.new(regular_user, Order).resolve
      expect(scope).to contain_exactly(user_order)
    end
  end
end
```

### Request Specs

```ruby
# spec/requests/api/v1/orders_spec.rb
RSpec.describe "Api::V1::Orders", type: :request do
  let(:user) { create(:user) }
  let(:admin) { create(:user, :admin) }

  describe "GET /api/v1/orders" do
    it "returns paginated orders for the current user" do
      create_list(:order, 3, user: user)
      create(:order) # another user's order
      get "/api/v1/orders", headers: auth_headers(user)

      expect(response).to have_http_status(:ok)
      expect(json_response["data"].size).to eq(3)
    end
  end

  describe "POST /api/v1/orders/:id/fulfill" do
    let(:order) { create(:order, :confirmed, :with_order_items) }

    context "as admin" do
      it "fulfills the order" do
        post "/api/v1/orders/#{order.id}/fulfill", headers: auth_headers(admin)

        expect(response).to have_http_status(:ok)
        expect(order.reload.status).to eq("processing")
      end
    end

    context "as order owner" do
      it "returns forbidden" do
        post "/api/v1/orders/#{order.id}/fulfill", headers: auth_headers(order.user)
        expect(response).to have_http_status(:forbidden)
      end
    end

    context "when order is not confirmed" do
      let(:order) { create(:order, :pending) }

      it "returns unprocessable entity" do
        post "/api/v1/orders/#{order.id}/fulfill", headers: auth_headers(admin)
        expect(response).to have_http_status(:unprocessable_entity)
      end
    end
  end
end
```

### FactoryBot

Bad - minimal factory without traits (forces inline overrides everywhere):

```ruby
factory :order do
  total { 99.99 }
  status { :pending }
end
# Usage: create(:order, status: :confirmed, fulfilled_at: Time.current)
```

Good - factory with traits for each state:

```ruby
# spec/factories/orders.rb
FactoryBot.define do
  factory :order do
    user
    total { 99.99 }
    status { :pending }

    trait :confirmed do
      status { :confirmed }
    end

    trait :processing do
      status { :processing }
      fulfilled_at { Time.current }
    end

    trait :shipped do
      status { :shipped }
      fulfilled_at { 1.day.ago }
    end

    trait :with_order_items do
      transient do
        items_count { 3 }
      end

      after(:create) do |order, ctx|
        create_list(:order_item, ctx.items_count, order: order)
      end
    end
  end
end

# Usage
order = build_stubbed(:order)                          # fastest, no DB
order = build(:order, :confirmed)                      # in-memory
order = create(:order, :confirmed, :with_order_items)  # hits DB
```

### shoulda-matchers

```ruby
# spec/support/shoulda_matchers.rb
Shoulda::Matchers.configure do |config|
  config.integrate do |with|
    with.test_framework :rspec
    with.library :rails
  end
end
```

### DatabaseCleaner

```ruby
# spec/support/database_cleaner.rb
RSpec.configure do |config|
  config.before(:suite) { DatabaseCleaner.clean_with(:truncation) }
  config.before(:each) { DatabaseCleaner.strategy = :transaction }
  config.before(:each, js: true) { DatabaseCleaner.strategy = :truncation }
  config.before(:each) { DatabaseCleaner.start }
  config.after(:each) { DatabaseCleaner.clean }
end
```

### Sidekiq Testing

Bad - testing job execution without idempotency check:

```ruby
it "processes the order" do
  Sidekiq::Testing.inline! do
    described_class.perform_async(order.id)
  end
end
```

Good - testing both enqueue and execution with idempotency:

```ruby
# spec/support/sidekiq.rb
require "sidekiq/testing"
Sidekiq::Testing.fake! # default - jobs pushed to array

# spec/jobs/shipment_notification_job_spec.rb
RSpec.describe ShipmentNotificationJob, type: :job do
  let(:order) { create(:order, :processing) }

  it "enqueues the job" do
    expect {
      described_class.perform_async(order.id)
    }.to change(described_class.jobs, :size).by(1)
  end

  it "sends shipment notification email" do
    expect {
      described_class.new.perform(order.id)
    }.to change { ActionMailer::Base.deliveries.count }.by(1)
  end

  it "is idempotent - skips already-shipped orders" do
    shipped_order = create(:order, :shipped)
    expect {
      described_class.new.perform(shipped_order.id)
    }.not_to change { ActionMailer::Base.deliveries.count }
  end
end
```

### VCR / WebMock

```ruby
# spec/support/vcr.rb
VCR.configure do |config|
  config.cassette_library_dir = "spec/cassettes"
  config.hook_into :webmock
  config.configure_rspec_metadata!
  config.filter_sensitive_data("<API_KEY>") { ENV["API_KEY"] }
end

# Usage
it "fetches data from API", vcr: { cassette_name: "api/fetch_data" } do
  result = ExternalApi.fetch_data
  expect(result).to be_present
end
```

### Shared Examples

```ruby
RSpec.shared_examples "a paginated endpoint" do
  it "returns pagination metadata" do
    expect(json_response).to include("meta" => include("total", "page", "per_page"))
  end
end

# Usage
it_behaves_like "a paginated endpoint"
```

### let vs let!

```ruby
# let - lazy evaluated (only when referenced)
let(:user) { create(:user) }

# let! - eager evaluated (runs before each example)
# Use when the record must exist even if not referenced in the test
let!(:admin) { create(:user, :admin) }
```

## Output Format

When generating tests, document coverage:

```
Test Type: {Model | Service | Policy | Request | Job | System}
File: spec/{type}/{path}_spec.rb
Contexts: {list of context blocks - e.g., "happy path, not found, forbidden, validation failure"}
Factories: {factory name with traits used}
Assertions: {count} examples
```

## Avoid

- Fixtures - use FactoryBot instead (more flexible, explicit)
- Testing private methods - test through the public interface
- `sleep` in tests - use `have_enqueued_job` or `Sidekiq::Testing`
- Mystery guests - make test data explicit, not hidden in shared setup
- Excessive mocking - mock boundaries (external APIs), not internal code
- Controller specs - deprecated, use request specs (full stack, more realistic)
- Missing policy specs - authorization bugs are among the most dangerous
- Factories without traits for status fields - forces inline overrides that obscure test intent
