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
- Testing Sidekiq jobs (`fake` / `inline`)
- Pundit policy tests for role-based access
- Mocking external API calls (VCR / WebMock)
- Reviewing for mystery guests, over-mocking, missing edge cases

## Rules

- Never use controller specs - use request specs
- Test through the public interface, never private methods
- FactoryBot for test data, not fixtures
- `build_stubbed` when no DB needed; `build` for in-memory; `create` only when persistence is required
- Mock at boundaries (external APIs), not internal code
- Model specs cover associations, validations, scopes, enums
- Request specs cover happy path, errors, authorization
- Service specs assert `Result.success?` / `failure?` and side effects
- Rake specs cover wiring (ENV, exit, forwarding); behavioral coverage on the underlying service

## Patterns

### Test Type Map

| Type          | Speed   | Scope           | Use For                                  |
| ------------- | ------- | --------------- | ---------------------------------------- |
| Model specs   | Fastest | Single model    | Validations, scopes, associations, enums |
| Service specs | Fast    | Business logic  | `Result` success/failure + side effects  |
| Policy specs  | Fast    | Authorization   | Pundit rules per role                    |
| Request specs | Medium  | Full HTTP stack | Endpoints, status, response bodies       |
| Job specs     | Fast    | Background      | Job behavior + idempotency               |
| Rake specs    | Fast    | Task wiring     | ENV, exit behavior, delegation           |
| System specs  | Slowest | Browser         | Critical user flows (Capybara)           |

### Model Specs

```ruby
RSpec.describe Order, type: :model do
  describe "associations" do
    it { is_expected.to belong_to(:user).counter_cache(true) }
    it { is_expected.to have_many(:order_items).dependent(:destroy) }
  end

  describe "validations" do
    it { is_expected.to validate_presence_of(:status) }
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

  describe "#call" do
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
    it { is_expected.to permit_action(:show) }
    it { is_expected.to permit_action(:fulfill) }
  end

  describe OrderPolicy::Scope do
    let(:admin) { create(:user, :admin) }
    let!(:own_order) { create(:order, user: admin) }
    let!(:other) { create(:order) }

    it "admin sees all" do
      expect(described_class.new(admin, Order).resolve).to include(own_order, other)
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
      create(:order)
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
      expect(order.reload.status).to eq("processing")
    end

    it "owner gets 403" do
      post "/api/v1/orders/#{order.id}/fulfill", headers: auth_headers(order.user)
      expect(response).to have_http_status(:forbidden)
    end
  end
end
```

### FactoryBot

State traits avoid inline overrides:

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

# Use
build_stubbed(:order)                          # no DB
build(:order, :confirmed)                      # in-memory
create(:order, :confirmed, :with_order_items)  # hits DB
```

### shoulda-matchers

```ruby
# spec/support/shoulda_matchers.rb
Shoulda::Matchers.configure do |c|
  c.integrate { |w| w.test_framework :rspec; w.library :rails }
end
```

### Test Database Isolation

Prefer Rails transactional fixtures over `database_cleaner`. System specs share the connection between test thread and Capybara server thread, so one transaction works:

```ruby
RSpec.configure { |c| c.use_transactional_fixtures = true }
```

Reach for `database_cleaner-active_record` with `:truncation` only for legitimate cross-connection state (separate analytics DB).

### Sidekiq

```ruby
require "sidekiq/testing"
Sidekiq::Testing.fake!  # default - jobs pushed to array

RSpec.describe ShipmentNotificationJob, type: :job do
  let(:order) { create(:order, :processing) }

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

> See `rails-rake-task-patterns` for the task design rules these specs verify.

Tasks are thin shells over services - service spec owns behavioral coverage; rake spec verifies wiring (ENV, args, exit, prod gate). `Rails.application.load_tasks` once per suite; `task.reenable` after each example. `climate_control` for per-example ENV.

```ruby
RSpec.describe "orders:fulfill_pending" do
  before(:all) { Rails.application.load_tasks }
  let(:task) { Rake::Task["orders:fulfill_pending"] }
  after { task.reenable }

  it "forwards DRY_RUN and BATCH_SIZE to the service" do
    expect(FulfillPendingOrders).to receive(:call)
      .with(dry_run: true, batch_size: 250)
      .and_return(Result.success(processed: 0))
    ClimateControl.modify(DRY_RUN: "1", BATCH_SIZE: "250") { task.invoke }
  end

  it "propagates service failures so cron sees non-zero exit" do
    allow(FulfillPendingOrders).to receive(:call).and_raise(StandardError, "boom")
    expect { task.invoke }.to raise_error(StandardError, "boom")
  end
end
```

For production-gate tasks, stub `Rails.env` to `"production"` and assert `task.invoke` raises `SystemExit` when `CONFIRM` is unset (which is what `abort` raises).

`invoke` runs prerequisites; `execute` skips them. `reenable` is per-task.

### Request Helpers

```ruby
# spec/support/request_helpers.rb
module RequestHelpers
  def auth_headers(user)
    token = Warden::JWTAuth::UserEncoder.new.call(user, :user, nil).first
    { "Authorization" => "Bearer #{token}", "Content-Type" => "application/json" }
  end

  def json_response = JSON.parse(response.body)
end

RSpec.configure { |c| c.include RequestHelpers, type: :request }
```

Adapt `auth_headers` to the project's auth strategy. One helper, one canonical shape.

### Time Helpers

Built-in `ActiveSupport::Testing::TimeHelpers` auto-resets after each example. No `timecop` gem needed.

```ruby
RSpec.configure { |c| c.include ActiveSupport::Testing::TimeHelpers }

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

### N+1 Assertions

```ruby
# Bullet: raise in dev/test on detected N+1
config.before(:each) { Bullet.enable = true; Bullet.raise = true; Bullet.start_request }
config.after(:each)  { Bullet.end_request }

# Pin a query count
require "active_record/query_recorder"
it "loads index in 2 queries regardless of order count" do
  create_list(:order, 10, :with_order_items, user: user)
  queries = ActiveRecord::QueryRecorder.new { get "/api/v1/orders", headers: auth_headers(user) }
  expect(queries.count).to be <= 4
end
```

Pinning the count means raising it requires an explicit decision in review.

### VCR / WebMock

```ruby
VCR.configure do |c|
  c.cassette_library_dir = "spec/cassettes"
  c.hook_into :webmock
  c.configure_rspec_metadata!
  c.filter_sensitive_data("<API_KEY>") { ENV["API_KEY"] }
end

it "fetches data", vcr: { cassette_name: "api/fetch_data" } do
  expect(ExternalApi.fetch_data).to be_present
end
```

Use one or the other per spec - cassettes + stubs interact confusingly. Default: WebMock for client unit specs, VCR for service/request specs that exercise the integration.

### Shared Examples

```ruby
RSpec.shared_examples "a paginated endpoint" do
  it "returns pagination metadata" do
    expect(json_response).to include("meta" => include("total", "page", "per_page"))
  end
end

it_behaves_like "a paginated endpoint"
```

### `let` vs `let!`

`let` is lazy (evaluates on first reference). `let!` is eager (before each example). Use `let!` when the record must exist even if not referenced in the test.

## Output Format

```
Test Type: {Model | Service | Policy | Request | Job | System | Rake}
File: spec/{type}/{path}_spec.rb
Contexts: {happy path, not found, forbidden, validation failure, ...}
Factories: {name with traits}
Assertions: {count} examples
```

## Avoid

- Fixtures - use FactoryBot
- Testing private methods
- `sleep` in tests - use `have_enqueued_job` / `Sidekiq::Testing`
- Mystery guests - explicit test data, not hidden in shared setup
- Mocking internal code - mock boundaries only
- Controller specs - use request specs
- Missing policy specs (authorization bugs are among the most dangerous)
- Factories without traits for status fields - inline overrides obscure intent
- `Time.now =` stubs - leak between examples; use `travel` / `freeze_time`
