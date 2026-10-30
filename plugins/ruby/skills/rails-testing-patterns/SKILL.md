---
name: rails-testing-patterns
description: RSpec on Rails 8.1+ - model/request/system/service/policy/job/rake specs, FactoryBot traits, shoulda-matchers, Sidekiq, Pundit, VCR/WebMock.
metadata:
  category: backend
  tags: [ruby, rails, rspec, testing, factorybot]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing tests for a new feature (models, services, requests, policies, jobs)
- Setting up FactoryBot factories with state traits
- Testing Sidekiq jobs, Pundit policies, Turbo Stream endpoints
- Mocking external HTTP at the boundary (VCR / WebMock)
- Reviewing for mystery guests, over-mocking, missing edge cases

## Rules

- Request specs, never controller specs (a controller spec moves to `spec/requests/<route path>_spec.rb`)
- Test through the public interface; no private-method specs
- FactoryBot only - no fixtures; use state traits, not inline attribute overrides
- `build_stubbed` by default; `build` in-memory; `create` only when the example needs persistence: DB reads (scopes, `reload`, uniqueness), code under test that performs real writes or reads them back, request specs, policy Scope resolution. Pure attribute/permission checks don't.
- Every Pundit policy spec covers every role and the `Scope`; roles that resolve identically for an action share one example (or a shared example group) rather than repeating it.
- Mock at boundaries (HTTP, third-party SDKs); never mock internal code - except a rake wiring spec, which stubs the one service the task delegates to
- `travel` / `freeze_time`, never `Time.now =` stubs
- One canonical `auth_headers` helper per suite, shaped for its surface (Devise session, generated-authentication session, or JWT bearer); a project with a session and a bearer surface names them apart (`session_headers`, `bearer_headers`) and never uses both on one endpoint

## Patterns

### Test Type Map

| Type          | Speed   | Covers                                   |
| ------------- | ------- | ---------------------------------------- |
| Model specs   | Fastest | Validations, scopes, associations, enums |
| Service specs | Fast    | `Result` success/failure + side effects  |
| Policy specs  | Fast    | Pundit rules per role                    |
| Request specs | Medium  | Endpoints, status, response bodies, authz|
| Job specs     | Fast    | Job behavior + idempotency               |
| Mailer specs  | Fast    | Headers, body; `have_enqueued_mail` at `deliver_later` call sites |
| Channel specs | Fast    | `subscribed` authorization, streams, rejected connections |
| Client specs  | Fast    | HTTP wrapper translation (WebMock)       |
| Rake specs    | Fast    | Wiring (ENV, args, exit, delegation)     |
| System specs  | Slowest | Critical user flows (Capybara)           |

System specs: `driven_by :rack_test` by default (no JS), `driven_by :selenium, using: :headless_chrome` only for the flows that need it, in a `before` of that file; one example per critical flow, asserting on visible text and the URL, never on markup structure.

### Model Specs

```ruby
RSpec.describe Order, type: :model do
  describe "associations" do
    it { is_expected.to belong_to(:user).counter_cache(true) }
    it { is_expected.to have_many(:order_items).dependent(:destroy) }
  end

  describe "validations" do
    it { is_expected.to validate_numericality_of(:total).is_greater_than(0) }
    it { is_expected.to define_enum_for(:status).with_values(pending: 0, confirmed: 1, processing: 2, shipped: 3) }
  end

  describe ".fulfillable" do
    it "returns only confirmed orders" do
      confirmed = create(:order, :confirmed)
      create(:order)                            # base factory already defaults to :pending
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
    # Drive the failure through data, not by stubbing internal classes (Rules: mock boundaries only)
    before { order.order_items.first.product.update!(available_stock: 0) }

    it "returns failure and does not transition" do
      result = described_class.new(order: order).call
      expect(result).to be_failure
      expect(order.reload.status).to eq("confirmed")
    end
  end
end
```

### Pundit Policy Specs

`permit_action` comes from the `pundit-matchers` gem (add to `:test` group):

```ruby
RSpec.describe OrderPolicy do
  subject { described_class.new(user, order) }
  let(:order) { build_stubbed(:order, user: owner) }  # pure permission checks: no DB needed
  let(:owner) { build_stubbed(:user) }

  context "owner" do
    let(:user) { owner }
    it { is_expected.to     permit_action(:show) }
    it { is_expected.not_to permit_action(:fulfill) }
  end

  context "admin" do
    let(:user) { build_stubbed(:user, :admin) }
    it { is_expected.to permit_action(:fulfill) }
  end

  context "another user" do
    let(:user) { build_stubbed(:user) }
    it { is_expected.to forbid_actions(%i[show fulfill]) }
  end

  describe OrderPolicy::Scope do
    it "admin sees all orders" do  # Scope resolution queries the DB - create required
      admin = create(:user, :admin)
      own, other = create(:order, user: admin), create(:order)
      expect(described_class.new(admin, Order).resolve).to include(own, other)
    end

    it "owner sees only their own" do   # the case the Scope exists to enforce
      owner = create(:user)
      own, other = create(:order, user: owner), create(:order)
      resolved = described_class.new(owner, Order).resolve
      expect(resolved).to include(own)
      expect(resolved).not_to include(other)
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

State traits replace inline overrides so intent stays explicit:

```ruby
FactoryBot.define do
  factory :order do
    user
    total  { 99.99 }
    status { :pending }

    # `trait :x { }` is a syntax error - a brace block cannot attach to a paren-less
    # command call with arguments. Use do...end (or parenthesise: `trait(:x) { }`).
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
      transient { items_count { 3 } }
      after(:create) { |order, ctx| create_list(:order_item, ctx.items_count, order: order) }
    end
  end
end

build_stubbed(:order)
create(:order, :confirmed, :with_order_items)
```

Factory defaults must satisfy the model's callbacks - a `before_validation` that recomputes from an association needs the association present before save (`after(:build) { |o| o.order_items << build(:order_item, order: o) }`, not `after(:create)` - and `order: o`, or the item factory's own `order` builds a second order whose hook builds another item, forever), or the default is overwritten and the record fails validation; under `before_save` the same recompute runs after validation, so the record persists with the overwritten value and nothing raises.

### Jobs - Sidekiq and Active Job

Two distinct assertions, two call shapes: *enqueueing* uses `perform_async` under `fake!` (jobs pushed to an array - assert size and `jobs.last["args"]`); *behavior* calls `described_class.new.perform(...)` directly, no Sidekiq involved.

```ruby
# rails_helper.rb, once: Sidekiq.testing!(:fake)   (Sidekiq 8.1.1+; below it require "sidekiq/testing"; Sidekiq::Testing.fake! - jobs pushed to an array)

RSpec.describe ShipmentNotificationJob, type: :job do
  let(:order) { create(:order, :confirmed) }

  it "enqueues with the order id" do
    expect { described_class.perform_async(order.id) }.to change(described_class.jobs, :size).by(1)
    expect(described_class.jobs.last["args"]).to eq([order.id])
  end

  # The negative assertion needs the positive control beside it: alone it passes if
  # `perform` is deleted, if the job never mails, or if the mailer uses deliver_later.
  # The job mails with deliver_now (a Sidekiq::Job is already the async boundary);
  # a job that uses deliver_later is asserted with have_enqueued_mail instead (needs the :test
  # Active Job adapter - the railtie picks it in the test env when no queue_adapter is set;
  # a :sidekiq adapter that reaches the test env makes it raise).
  it "is idempotent - a second run on the same order does not mail again" do
    expect { described_class.new.perform(order.id) }
      .to change { ActionMailer::Base.deliveries.count }.by(1)

    expect { described_class.new.perform(order.id) }
      .not_to change { ActionMailer::Base.deliveries.count }
  end
end
```

An Active Job class (`class OrderConfirmationJob < ApplicationJob`, run by the Sidekiq or Solid Queue adapter) asserts enqueueing with `have_enqueued_job(OrderConfirmationJob).with(order.id)` under the `:test` adapter and behaviour with `described_class.perform_now(order.id)`; `perform_enqueued_jobs { ... }` runs the enqueued ones inline once `rails_helper.rb` has `config.include ActiveJob::TestHelper, type: :job`.

Services with idempotency keys get the same two-call test at the service layer: call twice with one key, assert the side effect happened once and the second Result replays the first. A service that calls `deliver_later` is asserted with `have_enqueued_mail(OrderMailer, :shipped)` under the `:test` adapter, always on a created record: the matcher deserializes the job's GlobalID args, so on a `build_stubbed` record `.with(order)` raises `ActiveJob::DeserializationError` and the bare matcher fails with a wrong-number-of-arguments error. A mailer spec (`type: :mailer`) builds the mail (`OrderMailer.shipped(order)`) and asserts `mail.to`, `mail.subject` and `mail.body.encoded`; a mailer with no template raises `ActionView::MissingTemplate` on first access (`mail.to`), but one missing format of several builds silently from the formats found - a multipart mailer asserts `mail.html_part.body` and `mail.text_part.body`, or declares its formats in a `mail(...) { |f| f.text; f.html }` block, which raises on the missing one.

### Rake Task Specs

> See `rails-rake-task-patterns` for task design.

Tasks are thin shells; service spec owns behavior, rake spec verifies wiring. A task with inline logic gets a review finding (extract the service) before a wiring spec. `Rails.application.load_tasks` once; `task.reenable` after each example; `climate_control` for per-example ENV.

```ruby
RSpec.describe "orders:fulfill_pending" do
  # `require "rake"` belongs in rails_helper.rb: load_tasks is what requires it, so
  # touching Rake::Task first raises NameError under `bundle exec rspec`.
  before(:all) { Rails.application.load_tasks if Rake::Task.tasks.empty? }  # re-loading appends duplicate task bodies
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

For production-gate tasks, stub `Rails.env` with a StringInquirer - `allow(Rails).to receive(:env).and_return("production".inquiry)` (a plain string breaks `Rails.env.production?`) - and assert `task.invoke` raises `SystemExit` when `CONFIRM` is unset.

### Suite Speed

Slow CI is a data problem before it's a parallelism problem:

- Profile first: `rspec --profile 20`. Usual culprits: `create` cascades (`after(:create)` chains), request specs testing what a model spec covers.
- `create` costs 10-100x `build_stubbed`; apply the persistence criterion from Rules suite-wide.
- Parallelize (`parallel_tests` / `turbo_tests`) only after per-spec hygiene - it multiplies waste otherwise.
- `bin/ci` (`config/ci.rb`, 8.1) runs setup, RuboCop, `bundler-audit`, importmap audit, Brakeman, the tests and a seed replant locally; an RSpec suite replaces the generated `Tests: Rails` step (`bin/rails test`) with `bundle exec rspec`, and since the generated `.github/workflows/ci.yml` runs its own jobs rather than `bin/ci`, a workflow whose steps differ from `config/ci.rb` is a finding, and an 8.1 app with no `config/ci.rb` gets a `[Recommend]` finding, not a proposed file.

### Database Isolation

Use transactional fixtures, not `database_cleaner`. System specs share the connection between test thread and Capybara server thread, so one transaction works:

```ruby
RSpec.configure { |c| c.use_transactional_fixtures = true }
```

Transactional fixtures roll back the database, and nothing else. State living outside it leaks between examples in random order and produces the classic "passes alone, fails in suite": Sidekiq's `fake!` job array (`Sidekiq::Job.clear_all` in a `before`), any `Singleton` or class-level memo the app fills lazily (reset it through its own API, or `instance_variable_set(:@memo, nil)` when it has none, or freeze it at boot), `Rails.cache` (only when test.rb overrides the generated `:null_store` with a real store - then `Rails.cache.clear`), constants mutated by hand (`const_set`; rspec-mocks' `stub_const` resets itself), and Active Storage blobs on the disk service (`tmp/storage` - clear it in an `after(:suite)`). Put the resets in `rails_helper.rb` once rather than per file.

Attachments: upload with `fixture_file_upload("spec/fixtures/files/contract.pdf", "application/pdf")` (the `test` service in `config/storage.yml` is Disk), assert `record.files.attached?` and `blob.content_type`, and stub nothing - the magic-byte sniff and URL rules are `rails-active-storage-patterns`'. Greenfield suites first run `bin/rails g rspec:install` (`.rspec`, `spec_helper.rb`, `rails_helper.rb`) and add the `:test` gems before any spec is written.

`database_cleaner-active_record` with `:truncation` only for writes from a connection the test process does not own (a separate process, a pool built outside the handler) - a second database in `database.yml` is already rolled back, since transactional fixtures open a transaction on every pool in the handler.

### Request Auth Helpers

Pick one shape per surface (one helper name per shape). Devise session:

```ruby
module RequestHelpers
  def auth_headers(user)
    sign_in(user)
    { "Content-Type" => "application/json" }
  end

  def json_response = JSON.parse(response.body)
end

RSpec.configure do |c|
  c.include RequestHelpers, type: :request
  # `sign_in` is Devise's, not rspec-rails' - without this the Devise variant raises NoMethodError
  c.include Devise::Test::IntegrationHelpers, type: :request
end
```

JWT bearer (Warden::JWTAuth / Devise-JWT / custom encoder) - the configure block includes `RequestHelpers` only:

```ruby
module RequestHelpers
  def auth_headers(user)
    token = JwtEncoder.encode(user_id: user.id)
    { "Authorization" => "Bearer #{token}", "Content-Type" => "application/json" }
  end

  def json_response = JSON.parse(response.body)   # every shape defines it; specs call it
end
```

Generated authentication (`bin/rails generate authentication`) - the integration session keeps the signed cookie, so the helper signs in and returns the content-type hash; the configure block includes `RequestHelpers` only:

```ruby
module RequestHelpers
  def auth_headers(user)
    post session_path, params: { email_address: user.email_address, password: "password" }   # the factory's password
    { "Content-Type" => "application/json" }
  end

  def json_response = JSON.parse(response.body)
end
```

Mixing shapes behind one helper name hides which path the endpoint actually exercises.

### Time Helpers

```ruby
RSpec.configure { |c| c.include ActiveSupport::Testing::TimeHelpers }

it "expires after 7 days" do
  token = create(:reset_token)
  travel 8.days
  expect(token).to be_expired
end
```

Built-in - no `timecop` needed; auto-resets after each example in every group once Active Record is loaded (rspec-rails' `FixtureSupport` carries the Minitest lifecycle that runs `travel_back`) - only a suite without Active Record adds `config.after { travel_back }`.

### N+1 Assertions

Rails ships `ActiveRecord::Assertions::QueryAssertions` (7.2+) - `require "active_record/testing/query_assertions"` in `rails_helper.rb` (only Minitest's `rails/test_help` loads it), then `config.include ActiveRecord::Assertions::QueryAssertions, type: :request` (request groups carry `ActiveSupport::Testing::Assertions`, whose private `_assert_nothing_raised_or_warn` the assertions call, through the Action Mailer and Active Job railties; an app loading neither, and any model, service or untyped group, includes that module too) and `assert_queries_count(4) { get orders_path }` (also `assert_no_queries`, `assert_queries_match`). For a custom report, subscribe to `sql.active_record` (or use `rspec-sqlimit` / `n_plus_one_control`):

```ruby
it "index runs <= 4 queries regardless of order count" do
  create_list(:order, 10, :with_order_items, user: user)
  count = 0
  counter = ->(*, payload) { count += 1 unless payload[:name].in?(["SCHEMA", "TRANSACTION"]) }
  ActiveSupport::Notifications.subscribed(counter, "sql.active_record") do
    get "/api/v1/orders", headers: auth_headers(user)
  end
  expect(count).to be <= 4
end
```

Pin the count at the fixed behaviour so raising it requires an explicit review decision.

### Turbo Stream and Broadcast Assertions

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

`have_broadcasted_to` is built into rspec-rails 4+ (the standalone `action-cable-testing` gem was merged upstream - don't add it) and needs the `test` adapter in `cable.yml`'s test entry, whatever production uses. A Turbo `broadcast_*_to(user)` is asserted on its stream name, `have_broadcasted_to(user.to_gid_param)` (what Turbo's `stream_name_from` derives; an array target joins each part's `to_gid_param` - a symbol stays as is - with `:`); from a job, run `perform_now` inside the `expect` block. A channel spec (`type: :channel`) runs `stub_connection current_user: user`, `subscribe(order_id: order.id)`, then asserts `subscription` is `be_confirmed` with `have_stream_for(order)` or `be_rejected`; a connection spec calls `connect "/cable", headers: {...}` and asserts `connection.current_user` or `have_rejected_connection`. The full shape is in `rails-actioncable-patterns` Testing.

### VCR / WebMock

```ruby
VCR.configure do |c|
  c.cassette_library_dir = "spec/cassettes"
  c.hook_into :webmock
  c.configure_rspec_metadata!
  c.filter_sensitive_data("<API_KEY>") { ENV["API_KEY"] }
end
```

WebMock for client unit specs; VCR for service/request specs hitting the integration (with no credentials to record a cassette, WebMock stubs there too). One per spec file - cassettes + ad-hoc stubs interact confusingly. In a suite review each of these is a finding: `allow_any_instance_of(Client)` or an `instance_double` of the client in a request spec (stub HTTP instead); `match_requests_on` without `:body` for a keyed POST (cassette drift); `allow_http_connections_when_no_cassette`; a cassette holding unfiltered credentials.

Job specs follow the same boundary rule: the HTTP client wrapper (`app/clients/`) *is* the boundary, so either stub its class (`allow(EcbClient).to receive(...)`) or stub HTTP with WebMock - both comply with "never mock internal code"; pick by what the example asserts (translation logic -> WebMock on the client spec; orchestration -> class double in the job spec).

## Output Format

One block per file written or reviewed (a reviewed file with no finding still gets its block; a file the review adds is keyed on its path with `(proposed)`), each followed by that file's code - the whole file when new, the changed lines when it exists - including the support files, since a suite-wide rule (`Sidekiq.testing!(:fake)`, the Devise include, leak resets) is unenforceable if `rails_helper.rb` and the factories have nowhere to land. A Gemfile change (a missing `pundit-matchers`, a `timecop` to drop) is a numbered finding with no block. On a spec block `Factories:` names the factories the spec uses, with traits (the bare name when it uses none); on a Factory block it lists the factories and traits the file defines; on a Support block it is `n/a`. A gem that does I/O or detection (Marcel, an SDK) is a boundary: stub it, or feed it a real fixture file. In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no client class, no transaction, no channel class) gets a block for the unit the fix introduces, its name suffixed `(proposed)`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to add code, or to change code the request does not ask you to judge, is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding. A request that names existing code to assess, even when it also asks for the fix, is review mode. A finding with no single target file - suite runtime, a leak that spans examples - is a numbered finding with no block. In either mode, a bug in the code under test found while writing or reviewing the spec is a numbered finding too, and the spec pins the fixed behaviour - written against the fix and marked `pending "finding N"` as the first line of each example the fix unblocks when the fix is outside the run's scope. A file that moves (controller spec to request spec) is one block keyed on the target path, naming the old one. `Examples:` counts examples actually written, pending ones included (in review, the file's count after the fix).

```
Test Type: {Model | Service | Policy | Request | Job | Mailer | Channel | Client (HTTP wrapper unit spec) | System | Rake | Support (rails_helper, spec/support, config/environments/test.rb) | Factory}

File: {spec/{type}/{path}_spec.rb | spec/factories/{name}.rb (or the project's existing spec/factories.rb) | spec/rails_helper.rb | spec/support/{name}.rb | config/environments/test.rb}

Contexts: {happy path, not found, forbidden, validation failure, ... | n/a (Factory, Support)}

Factories: {name with traits | none defined yet - the ones this run writes, by name | model absent - GAP | the factories and traits this file defines (Factory) | n/a (Support)}

Examples: {count | n/a (Factory, Support)}
```


## Avoid

- Mystery guests - data set up in shared `before` blocks far from the example
- `sleep` waiting on async work - use `:fake` job assertions (`have_enqueued_job` is the ActiveJob equivalent)
- Missing policy specs - authorization bugs are among the most damaging
