---
name: rails-testing-patterns
description: RSpec testing patterns for Rails 7.2+: model/request/system/service specs, FactoryBot traits, shoulda-matchers, Sidekiq, Pundit, VCR.
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
- Rake specs cover wiring only (ENV parsing, exit behavior, argument forwarding) - put behavioral coverage on the underlying service spec

## Patterns

### Test Type Hierarchy

| Type          | Speed   | Scope           | Use For                                  |
| ------------- | ------- | --------------- | ---------------------------------------- |
| Model specs   | Fastest | Single model    | Validations, scopes, associations, enums |
| Service specs | Fast    | Business logic  | Service objects with Result assertions   |
| Policy specs  | Fast    | Authorization   | Pundit policy rules per role             |
| Request specs | Medium  | Full HTTP stack | Endpoints, status codes, response bodies |
| Job specs     | Fast    | Background work | Sidekiq job behavior and idempotency     |
| Rake specs    | Fast    | Task wiring     | ENV parsing, exit behavior, delegation   |
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

### Test Database Isolation

Prefer Rails' built-in transactional fixtures over the `database_cleaner` gem. System specs share the connection between the test thread and the Capybara server thread, so a single transaction works for JS-driven tests too:

```ruby
# spec/rails_helper.rb
RSpec.configure do |config|
  config.use_transactional_fixtures = true
end
```

Only reach for `database_cleaner-active_record` with the `:truncation` strategy if you have legitimate cross-connection state (e.g., a separate analytics DB written to inside the test) - and document why. Adding it preemptively trades speed for nothing on a modern Rails app.

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

### Rake Task Specs

> See `rails-rake-task-patterns` for the task design rules these specs verify.

Rake tasks are thin shells over services. The service spec carries the behavioral coverage; the rake spec only proves the wiring is correct - ENV parsing, argument forwarding, exit behavior on failure.

Setup: load tasks once per suite, reenable per example so invocations are independent. Use `climate_control` (or similar) to scope ENV mutations to one example.

Bad - re-implements service coverage and leaves the task in a "already invoked" state for sibling specs:

```ruby
RSpec.describe "orders:fulfill_pending" do
  it "fulfills every pending order" do
    create_list(:order, 3, :pending)
    Rails.application.load_tasks
    Rake::Task["orders:fulfill_pending"].invoke
    expect(Order.pending.count).to eq(0)
  end
end
```

Good - asserts wiring, isolates ENV, reenables the task:

```ruby
# spec/tasks/orders_rake_spec.rb
require "rails_helper"
require "rake"

RSpec.describe "orders:fulfill_pending" do
  before(:all) { Rails.application.load_tasks }

  let(:task) { Rake::Task["orders:fulfill_pending"] }
  after { task.reenable }

  it "forwards DRY_RUN and BATCH_SIZE from ENV to the service" do
    expect(FulfillPendingOrders).to receive(:call)
      .with(dry_run: true, batch_size: 250)
      .and_return(Result.success(processed: 0, skipped: 0))

    ClimateControl.modify(DRY_RUN: "1", BATCH_SIZE: "250") { task.invoke }
  end

  it "uses documented defaults when ENV is unset" do
    expect(FulfillPendingOrders).to receive(:call)
      .with(dry_run: false, batch_size: 500)
      .and_return(Result.success(processed: 0, skipped: 0))

    ClimateControl.modify(DRY_RUN: nil, BATCH_SIZE: nil) { task.invoke }
  end

  it "propagates service failures so cron sees a non-zero exit" do
    allow(FulfillPendingOrders).to receive(:call).and_raise(StandardError, "boom")
    expect { task.invoke }.to raise_error(StandardError, "boom")
  end
end
```

For tasks with a production confirmation gate, assert the gate fires:

```ruby
RSpec.describe "sessions:purge_stale" do
  before(:all) { Rails.application.load_tasks }
  let(:task) { Rake::Task["sessions:purge_stale"] }
  after { task.reenable }

  it "aborts in production without CONFIRM=yes" do
    allow(Rails).to receive(:env).and_return(ActiveSupport::StringInquirer.new("production"))
    ClimateControl.modify(CONFIRM: nil) do
      expect { task.invoke }.to raise_error(SystemExit) # `abort` raises SystemExit
    end
  end
end
```

Notes:

- `Rake::Task#invoke` runs prerequisites; `#execute` skips them. Prefer `invoke` so `:environment` actually loads.
- `task.reenable` only re-enables that single task. If a task has chained `invoke` calls, reenable each one.
- A failing rake task raises - `expect { ... }.to raise_error` is the right matcher. `abort` raises `SystemExit`, not `RuntimeError`.

### Test Helpers - `auth_headers` and `json_response`

Request specs above reference `auth_headers(user)` and `json_response`. Define these once in `spec/support/request_helpers.rb` so every request spec uses the same setup:

```ruby
# spec/support/request_helpers.rb
module RequestHelpers
  def auth_headers(user)
    token = Warden::JWTAuth::UserEncoder.new.call(user, :user, nil).first
    { "Authorization" => "Bearer #{token}", "Content-Type" => "application/json" }
  end

  def json_response
    JSON.parse(response.body)
  end
end

RSpec.configure do |config|
  config.include RequestHelpers, type: :request
end
```

Adapt `auth_headers` to the project's auth strategy (Devise session, JWT, API key in header). The point is one helper, one canonical shape.

### Time Helpers

Use Rails' built-in time helpers (no `timecop` gem needed). They auto-reset after each example when `ActiveSupport::Testing::TimeHelpers` is included:

```ruby
# spec/rails_helper.rb
RSpec.configure do |config|
  config.include ActiveSupport::Testing::TimeHelpers
end

# Usage
it "expires after 7 days" do
  token = create(:reset_token)
  travel 8.days
  expect(token).to be_expired
end

it "stamps fulfilled_at" do
  freeze_time do
    described_class.call(order)
    expect(order.reload.fulfilled_at).to eq(Time.current)
  end
end
```

`travel`, `travel_to`, `travel_back`, and `freeze_time` cover all common time-test cases. Avoid `Time.now = ...` style stubs - they leak between examples.

### N+1 Assertions in Specs

Catch N+1 regressions at test time, not in production logs. Two approaches:

```ruby
# Bullet (raises in dev/test on detected N+1)
# spec/rails_helper.rb
config.before(:each) do
  Bullet.enable = true
  Bullet.raise = true
  Bullet.start_request
end
config.after(:each) { Bullet.end_request }

# Assert exact query count for a hot endpoint
require "active_record/query_recorder"

it "loads index in 2 queries regardless of order count" do
  create_list(:order, 10, :with_order_items, user: user)
  queries = ActiveRecord::QueryRecorder.new do
    get "/api/v1/orders", headers: auth_headers(user)
  end
  expect(queries.count).to be <= 4 # one per: count, orders, items, products
end
```

Pin the query count; raising it requires an explicit decision in code review.

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
