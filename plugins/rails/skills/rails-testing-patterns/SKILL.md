---
name: rails-testing-patterns
description: "RSpec testing patterns for Rails 7+/8. Model specs, request specs (not controller specs), system specs, FactoryBot, shoulda-matchers, Sidekiq testing, VCR/WebMock."
user-invocable: false
---

## Test Type Hierarchy

1. **Model specs** — fastest, test validations, scopes, methods
2. **Request specs** — test full HTTP stack (replaces controller specs)
3. **System specs** — browser-driven, test user flows (Capybara)
4. **Service specs** — test business logic in isolation

**NEVER use controller specs** — they're deprecated. Use request specs instead.

## Model Specs

```ruby
# spec/models/order_spec.rb
RSpec.describe Order, type: :model do
  describe "associations" do
    it { is_expected.to belong_to(:customer) }
    it { is_expected.to have_many(:line_items).dependent(:destroy) }
    it { is_expected.to have_many(:products).through(:line_items) }
  end

  describe "validations" do
    it { is_expected.to validate_presence_of(:total) }
    it { is_expected.to validate_numericality_of(:total).is_greater_than(0) }
    it { is_expected.to define_enum_for(:status).with_values(pending: 0, active: 1, completed: 2) }
  end

  describe "scopes" do
    describe ".active" do
      it "returns only active orders" do
        active = create(:order, status: :active)
        create(:order, status: :pending)
        expect(described_class.active).to eq([active])
      end
    end
  end
end
```

## Request Specs

```ruby
# spec/requests/api/v1/orders_spec.rb
RSpec.describe "Api::V1::Orders", type: :request do
  let(:customer) { create(:customer) }

  describe "GET /api/v1/orders" do
    it "returns paginated orders" do
      create_list(:order, 3, customer: customer)
      get "/api/v1/orders", headers: auth_headers

      expect(response).to have_http_status(:ok)
      expect(json_response["data"].size).to eq(3)
    end
  end

  describe "POST /api/v1/orders" do
    let(:valid_params) { { order: { total: 99.99, customer_id: customer.id } } }

    it "creates an order" do
      expect {
        post "/api/v1/orders", params: valid_params, headers: auth_headers
      }.to change(Order, :count).by(1)

      expect(response).to have_http_status(:created)
    end

    it "returns errors for invalid params" do
      post "/api/v1/orders", params: { order: { total: -1 } }, headers: auth_headers
      expect(response).to have_http_status(:unprocessable_entity)
    end
  end
end
```

## FactoryBot

```ruby
# spec/factories/orders.rb
FactoryBot.define do
  factory :order do
    customer
    total { 99.99 }
    status { :pending }

    # ✅ Traits for variations
    trait :active do
      status { :active }
    end

    trait :completed do
      status { :completed }
      completed_at { Time.current }
    end

    trait :with_line_items do
      transient do
        line_items_count { 3 }
      end

      after(:create) do |order, ctx|
        create_list(:line_item, ctx.line_items_count, order: order)
      end
    end
  end
end

# ✅ build_stubbed — fastest, no DB hit
order = build_stubbed(:order)

# ✅ build — in-memory, no DB
order = build(:order)

# create — hits DB, use only when needed
order = create(:order, :active, :with_line_items)
```

## shoulda-matchers

```ruby
# spec/support/shoulda_matchers.rb
Shoulda::Matchers.configure do |config|
  config.integrate do |with|
    with.test_framework :rspec
    with.library :rails
  end
end
```

## DatabaseCleaner

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

## Sidekiq Testing

```ruby
# spec/support/sidekiq.rb
require "sidekiq/testing"
Sidekiq::Testing.fake! # default — jobs are pushed to array

# spec/jobs/process_order_job_spec.rb
RSpec.describe ProcessOrderJob, type: :job do
  it "enqueues the job" do
    expect {
      described_class.perform_async(order.id)
    }.to change(described_class.jobs, :size).by(1)
  end

  it "processes the order" do
    Sidekiq::Testing.inline! do
      expect { described_class.perform_async(order.id) }
        .to change { order.reload.status }.to("completed")
    end
  end
end
```

## VCR / WebMock

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

## Shared Examples

```ruby
RSpec.shared_examples "a paginated endpoint" do
  it "returns pagination metadata" do
    expect(json_response).to include("meta" => include("total", "page", "per_page"))
  end
end

# Usage
it_behaves_like "a paginated endpoint"
```

## let vs let!

```ruby
# let — lazy evaluated (only when referenced)
let(:user) { create(:user) }

# let! — eager evaluated (runs before each example)
# Use when the record must exist even if not referenced
let!(:admin) { create(:user, :admin) }
```

## Anti-Patterns

- ❌ Fixtures — use FactoryBot instead (more flexible, explicit)
- ❌ Testing private methods — test through public interface
- ❌ `sleep` in tests — use `have_enqueued_job` or Sidekiq::Testing
- ❌ Mystery guests — make test data explicit, not hidden in shared setup
- ❌ Excessive mocking — mock boundaries (external APIs), not internal code
- ❌ Controller specs — use request specs (full stack, more realistic)
