---
name: rails-testing-patterns
description: RSpec for Rails 7.2+: model/request/system/service/policy/job/rake specs, FactoryBot traits, shoulda-matchers, Sidekiq, Pundit, VCR.
metadata:
  category: backend
  tags: [ruby, rails, rspec, testing, factorybot]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing tests for a new feature (models, services, requests, policies, jobs)
- Setting up FactoryBot factories with state traits
- Testing Sidekiq jobs and Pundit policies
- Mocking external HTTP at the boundary (VCR / WebMock)
- Reviewing for mystery guests, over-mocking, missing edge cases

## Rules

- Request specs, never controller specs
- Test through the public interface; no private-method specs
- FactoryBot only - no fixtures
- `build_stubbed` by default; `build` for in-memory; `create` only when persistence is required
- Mock at boundaries (HTTP, third-party SDKs), never internal code
- Every Pundit policy gets a spec covering each role
- `travel` / `freeze_time`, never `Time.now =` stubs

## Patterns

### Test Type Map

| Type          | Speed   | Covers                                   |
| ------------- | ------- | ---------------------------------------- |
| Model specs   | Fastest | Validations, scopes, associations, enums |
| Service specs | Fast    | `Result` success/failure + side effects  |
| Policy specs  | Fast    | Pundit rules per role                    |
| Request specs | Medium  | Endpoints, status, response bodies, authz|
| Job specs     | Fast    | Job behavior + idempotency               |
| Rake specs    | Fast    | Wiring (ENV, args, exit, delegation)     |
| System specs  | Slowest | Critical user flows (Capybara)           |

### Model Specs

```ruby
RSpec.describe Order, type: :model do
  describe "associations" do
    it { is_expected.to belong_to(:user).counter_cache(true) }
    it { is_expected.to have_many(:order_items).dependent(:destroy) }
  end

  describe "validations" do
    it { is_expected.to validate_numericality_of(:total).is_greater_than(0) }
    it { is_expected.to define_enum_for(:status).with_values(pending: 0, confirmed: 1, shipped: 2) }
  end

  describe ".fulfillable" do
    it "returns only confirmed orders" do
      confirmed = create(:order, :confirmed)
      create(:order, :pending)
      expect(described_class.fulfillable).to eq([confirmed])
    end
  end
end
```

### Service Specs

```ruby
RSpec.describe FulfillOrder do
  let(:order) { create(:order, :confirmed, :with_order_items) }

  it "returns success and transitions status" do
    result = described_class.new(order: order).call
    expect(result).to be_success
    expect(order.reload.status).to eq("processing")
  end

  it "enqueues a shipment job" do
    expect { described_class.new(order: order).call }
      .to change(ShipmentNotificationJob.jobs, :size).by(1)
  end

  context "when inventory is insufficient" do
    before { allow(InventoryService).to receive(:new).and_raise(Inventory::InsufficientStockError) }

    it "returns failure and does not transition" do
      result = described_class.new(order: order).call
      expect(result).to be_failure
      expect(order.reload.status).to eq("confirmed")
    end
  end
end
```

### Pundit Policy Specs

```ruby
RSpec.describe OrderPolicy do
  subject { described_class.new(user, order) }
  let(:order) { create(:order, user: owner) }
  let(:owner) { create(:user) }

  context "owner" do
    let(:user) { owner }
    it { is_expected.to     permit_action(:show) }
    it { is_expected.not_to permit_action(:fulfill) }
  end

  context "admin" do
    let(:user) { create(:user, :admin) }
    it { is_expected.to permit_action(:fulfill) }
  end

  describe OrderPolicy::Scope do
    it "admin sees all orders" do
      admin = create(:user, :admin)
      own, other = create(:order, user: admin), create(:order)
      expect(described_class.new(admin, Order).resolve).to include(own, other)
    end
  end
end
```

### Request Specs

```ruby
RSpec.describe "Api::V1::Orders", type: :request do
  let(:user)  { create(:user) }
  let(:admin) { create(:user, :admin) }

  describe "GET /api/v1/orders" do
    it "returns paginated orders for the current user" do
      create_list(:order, 3, user: user)
      create(:order) # belongs to another user
      get "/api/v1/orders", headers: auth_headers(user)
      expect(response).to have_http_status(:ok)
      expect(json_response["data"].size).to eq(3)
    end
  end

  describe "POST /api/v1/orders/:id/fulfill" do
    let(:order) { create(:order, :confirmed) }

    it "admin can fulfill" do
      post "/api/v1/orders/#{order.id}/fulfill", headers: auth_headers(admin)
      expect(response).to have_http_status(:ok)
    end

    it "owner gets 403" do
      post "/api/v1/orders/#{order.id}/fulfill", headers: auth_headers(order.user)
      expect(response).to have_http_status(:forbidden)
    end
  end
end
```

### FactoryBot

State traits avoid inline overrides hiding intent:

```ruby
FactoryBot.define do
  factory :order do
    user
    total  { 99.99 }
    status { :pending }

    trait :confirmed  { status { :confirmed } }
    trait :processing { status { :processing }; fulfilled_at { Time.current } }
    trait :shipped    { status { :shipped };    fulfilled_at { 1.day.ago } }

    trait :with_order_items do
      transient { items_count { 3 } }
      after(:create) { |order, ctx| create_list(:order_item, ctx.items_count, order: order) }
    end
  end
end

build_stubbed(:order)                          # no DB
create(:order, :confirmed, :with_order_items)  # DB + associated rows
```

### Sidekiq

```ruby
require "sidekiq/testing"
Sidekiq::Testing.fake!  # default - jobs pushed to array

RSpec.describe ShipmentNotificationJob, type: :job do
  it "enqueues" do
    expect { described_class.perform_async(order.id) }
      .to change(described_class.jobs, :size).by(1)
  end

  it "is idempotent - skips already-shipped orders" do
    shipped = create(:order, :shipped)
    expect { described_class.new.perform(shipped.id) }
      .not_to change { ActionMailer::Base.deliveries.count }
  end
end
```

### Rake Task Specs

> See `rails-rake-task-patterns` for task design.

Tasks are thin shells - the service spec owns behavior; the rake spec verifies wiring. `Rails.application.load_tasks` once; `task.reenable` after each example; `climate_control` for per-example ENV.

```ruby
RSpec.describe "orders:fulfill_pending" do
  before(:all) { Rails.application.load_tasks }
  let(:task) { Rake::Task["orders:fulfill_pending"] }
  after { task.reenable }

  it "forwards DRY_RUN and BATCH_SIZE to the service" do
    expect(FulfillPendingOrders).to receive(:call)
      .with(dry_run: true, batch_size: 250).and_return(Result.success(processed: 0))
    ClimateControl.modify(DRY_RUN: "1", BATCH_SIZE: "250") { task.invoke }
  end

  it "propagates failures so cron sees non-zero exit" do
    allow(FulfillPendingOrders).to receive(:call).and_raise(StandardError, "boom")
    expect { task.invoke }.to raise_error(StandardError, "boom")
  end
end
```

Production-gate tasks: stub `Rails.env` to `"production"` and assert `task.invoke` raises `SystemExit` when `CONFIRM` is unset.

### Database Isolation

Transactional fixtures, not `database_cleaner`. System specs share the connection between test thread and Capybara server thread, so one transaction works:

```ruby
RSpec.configure { |c| c.use_transactional_fixtures = true }
```

`database_cleaner-active_record` with `:truncation` only for cross-connection state (separate analytics DB).

### Request Helpers

One canonical `auth_headers` helper per project; shape depends on the auth strategy. Two common forms:

```ruby
# Devise session (cookie-based, server-rendered apps)
module RequestHelpers
  def auth_headers(user)
    sign_in(user)
    { "Content-Type" => "application/json" }
  end

  def json_response = JSON.parse(response.body)
end

# JWT bearer (API-only apps; adjust encoder to the project's gem)
module RequestHelpers
  def auth_headers(user)
    token = JwtEncoder.encode(user_id: user.id) # or Warden::JWTAuth, Devise-JWT, etc.
    { "Authorization" => "Bearer #{token}", "Content-Type" => "application/json" }
  end
end

RSpec.configure { |c| c.include RequestHelpers, type: :request }
```

Pick one shape - mixing session and bearer auth in the same spec helper hides which path the endpoint actually exercises.

### Time Helpers

```ruby
RSpec.configure { |c| c.include ActiveSupport::Testing::TimeHelpers }

it "expires after 7 days" do
  token = create(:reset_token)
  travel 8.days
  expect(token).to be_expired
end
```

Built-in - no `timecop` needed; auto-resets after each example.

### N+1 Assertions

Pin the query count so raising it requires an explicit review decision:

```ruby
require "active_record/query_recorder"
it "index runs ≤ 4 queries regardless of order count" do
  create_list(:order, 10, :with_order_items, user: user)
  queries = ActiveRecord::QueryRecorder.new { get "/api/v1/orders", headers: auth_headers(user) }
  expect(queries.count).to be <= 4
end
```

### Turbo Stream and Broadcast Assertions

For Hotwire-driven endpoints, assert the stream shape, not the HTML body:

```ruby
# Request spec - response is text/vnd.turbo-stream.html
it "appends a row to the orders frame" do
  post "/orders", params: { order: attributes_for(:order) },
       headers: { "Accept" => "text/vnd.turbo-stream.html" }
  expect(response.media_type).to eq("text/vnd.turbo-stream.html")
  expect(response.body).to include('<turbo-stream action="append" target="orders">')
end

# ActionCable broadcast from a model/service
it "broadcasts to the user's stream" do
  expect { service.call }
    .to have_broadcasted_to("orders_#{user.id}")
    .with(a_hash_including("action" => "update"))
end
```

`turbo-rails` ships `Turbo::Broadcastable::TestHelper` for `assert_turbo_stream_broadcasts` in Minitest; RSpec uses `have_broadcasted_to` from `action-cable-testing`.

### VCR / WebMock

```ruby
VCR.configure do |c|
  c.cassette_library_dir = "spec/cassettes"
  c.hook_into :webmock
  c.configure_rspec_metadata!
  c.filter_sensitive_data("<API_KEY>") { ENV["API_KEY"] }
end
```

WebMock for client unit specs; VCR for service/request specs hitting the integration. Use one per spec - cassettes + ad-hoc stubs interact confusingly.

## Output Format

```
Test Type: {Model | Service | Policy | Request | Job | System | Rake}
File: spec/{type}/{path}_spec.rb
Contexts: {happy path, not found, forbidden, validation failure, ...}
Factories: {name with traits}
Examples: {count}
```

## Avoid

- Mystery guests - data set up in shared `before` blocks far from the example
- Factories without state traits - inline status overrides obscure intent
- `sleep` waiting on async work - use `have_enqueued_job` / `Sidekiq::Testing`
- Missing policy specs (authorization bugs are among the most damaging)
- Mocking internal code - mock boundaries only
