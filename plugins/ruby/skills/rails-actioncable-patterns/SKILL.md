---
name: rails-actioncable-patterns
description: "ActionCable Rails 7.2 - channel auth, subscription authz (IDOR), turbo_stream_from scope, Redis/PG adapter, fan-out batching, channel tests."
metadata:
  category: backend
  tags: [ruby, rails, actioncable, websocket, hotwire, turbo]
user-invocable: false
---

> Load `Use skill: stack-detect` first for framework and version. The broadcast adapter, app server and Hotwire usage are not stack-detect fields - read them here from `config/cable.yml`, the Puma/Falcon config, and the Gemfile, unless the project declares them under `## Tech Stack`.

## When to Use

- Adding a channel or `turbo_stream_from` subscription
- Reviewing channel authentication and subscription authorization
- Choosing the broadcast adapter (Redis vs PostgreSQL vs async)
- Diagnosing slow broadcasts, fan-out spikes, or IDOR over WebSocket
- Testing channels and broadcasts

## Rules

- `identified_by :current_user` in `ApplicationCable::Connection`; `reject_unauthorized_connection` on missing/invalid identity. Anonymous capability access (an emailed tracking link, no session) adds a second identifier rather than weakening the first: `identified_by :current_user, :verified_resource`, `connect` sets whichever the request carries and rejects when neither verifies, and the resource identifier comes from a signed, expiring token (`find_signed!`) - never a raw id
- Every channel `subscribed` authorizes the requested resource - never `stream_from` a client-supplied identifier without an ownership check
- `turbo_stream_from` scope is a capability; pass model objects, not public IDs. Per-user data: `turbo_stream_from current_user, :orders`. Shared resources: `turbo_stream_from project, :comments` - authorization is the controller only rendering the tag for permitted viewers
- Keep `allowed_request_origins` strict in production and never set `disable_request_forgery_protection` - cookie-authenticated connections are Cross-Site WebSocket Hijacking targets otherwise
- Redis (two conns per process) or Solid Cable in production; PostgreSQL adapter only for low-volume (LISTEN/NOTIFY caps throughput and payload); `async` in development, `adapter: test` in test - the broadcast matchers require it
- Broadcast from `after_commit`, not `after_save` - subscribers querying mid-broadcast see uncommitted state otherwise
- Fan-out to > 100 *distinct targets* goes through Sidekiq (`broadcast_render_later_to` / `broadcast_replace_later_to`, or a batched job), not inline in the request thread. One broadcast to a stream many subscribers share is a single publish regardless of subscriber count - that cost is the adapter's, not the request thread's, so viewer count alone never triggers this rule
- Channel actions are RPC over a socket - rate-limit per connection and validate params like any HTTP endpoint

## Patterns

### Connection Identification

```ruby
module ApplicationCable
  class Connection < ActionCable::Connection::Base
    identified_by :current_user

    def connect
      self.current_user = User.find_by(id: cookies.encrypted[:user_id]) || reject_unauthorized_connection
    end
  end
end
```

For JWT/API apps, prefer the `Sec-WebSocket-Protocol` subprotocol header for the token - headers don't land in access logs; in `connect`, read `request.headers["Sec-WebSocket-Protocol"]` and take the entry that isn't `actioncable-v1-json`. Query params are acceptable only for short-lived single-use tickets minted per connection. Never put the long-lived JWT itself in a URL. Devise apps can identify via `env["warden"].user` instead of the cookie lookup.

### Subscription Authorization (IDOR Prevention)

```ruby
# Bad - trusts client-supplied id
class OrderChannel < ApplicationCable::Channel
  def subscribed
    stream_for Order.find(params[:order_id])
  end
end

# Good - ownership + policy gate
class OrderChannel < ApplicationCable::Channel
  def subscribed
    order = current_user.orders.find_by(id: params[:order_id])
    return reject unless order && OrderPolicy.new(current_user, order).show?

    stream_for order
  end
end
```

Same rule for Turbo Stream scope:

```erb
<%# Bad - every viewer receives the identical signed tag - leaks across tenants %>
<%= turbo_stream_from "orders" %>

<%# Good - per-user, signed by Rails %>
<%= turbo_stream_from current_user, :orders %>
```

`turbo_stream_from` signs the scope so the signature proves the server emitted it - **not** that the current viewer is entitled. Authorization is the scope the controller chooses to render. For a user-owned resource, scope as `[current_user, record]` (and broadcast to the identical array) - including the owner makes the scope unguessable even if a signed tag leaks. For a shared resource (project, team, room), scope as `[record, :collection]` and gate access in the controller/policy before rendering the tag - every holder of the signed tag can read the stream. A singleton scope with no record (admin dashboard, site status) follows the same shared-resource rule: a bare symbol scope is acceptable exactly when the controller renders the tag only to the entitled audience - the audience gate, not the scope name, is the control.

### Broadcast Adapters

| Adapter      | Use when                              | Trade-off                                  |
| ------------ | ------------------------------------- | ------------------------------------------ |
| `redis`      | Production, >1 app process            | Two Redis conns per process (one blocked in SUBSCRIBE, one publishing) - budget `maxclients` accordingly; default in the Rails 7.2 generated `cable.yml` |
| `solid_cable`| Production, Rails 8 default           | DB-backed and polled (`polling_interval`), not LISTEN/NOTIFY - so no payload cap, but delivery is only as fast as the poll |
| `postgresql` | Single-process dev or low-volume only | LISTEN/NOTIFY caps throughput and payload (8000 bytes - an oversized broadcast raises `PG::InvalidParameterValue` in the broadcasting thread, it does not truncate); DB pool hit |
| `async`      | Development, single process           | No cross-process broadcast                 |
| `test`       | Test env                              | Records broadcasts instead of delivering; `have_broadcasted_to` requires it and raises under any other adapter |

```yaml
# config/cable.yml
production:
  adapter: redis
  url: <%= ENV.fetch("REDIS_CABLE_URL") %>
  channel_prefix: app_production
```

Use a dedicated Redis instance for ActionCable in high-volume apps - sharing with Sidekiq/cache causes head-of-line blocking.

### Broadcast from `after_commit`

```ruby
class Order < ApplicationRecord
  after_commit -> { broadcast_replace_later_to [user, :orders], target: ActionView::RecordIdentifier.dom_id(self, :card) }, on: :update
end
```

`dom_id` is a view helper - in model context call it module-qualified as above (or `include ActionView::RecordIdentifier`); bare `dom_id` raises NoMethodError.

`after_save` fires inside the transaction; subscribers re-querying see the pre-commit state, or nothing if the txn rolls back.

One canonical broadcast source per message: the model `after_commit` (or an explicit service call) owns it - channel actions that also broadcast what the callback already broadcasts double-deliver. Persist in the action, let the callback announce.

### Fan-Out Batching

```ruby
# Bad - blocks the request, holds the DB connection
followers.find_each { |f| NotificationChannel.broadcast_to(f, payload) }

# Good - hand off to Sidekiq in chunks; filter (mutes, prefs) in the enumeration query
followers.merge(Follow.where(muted: false)).in_batches(of: 500) do |batch|
  BroadcastNotificationJob.perform_async(batch.pluck(:id), payload)
end
```

Per-identity rate limiting for channel actions. `connection_identifier` is built from the declared `identified_by` values, so every socket for the same user - two tabs, a reconnect - shares one counter. That is the stronger control (a client cannot buy quota by opening more sockets); if you genuinely want per-socket limits, append a suffix minted in `subscribed`. A minimal Redis fence (any Redis pool works; counter keys are tiny, so borrowing `Sidekiq.redis` here does not conflict with keeping broadcast pub/sub on its own instance):

```ruby
def send_message(data)
  key = "cable:rl:#{connection.connection_identifier}:send_message"
  count = Sidekiq.redis { |r| r.incr(key).tap { |n| r.expire(key, 10) if n == 1 } }
  return transmit({ error: "rate limited" }) if count > 20   # braces required: transmit(data, via:)
  ...
end
```

Non-`later` broadcast helpers render the partial in the caller's thread. Use the `_later_to` variants (`broadcast_replace_later_to`) from model callbacks and request-path code so rendering happens on Active Job; inline variants are fine from jobs, which already run off-thread. The Turbo directive form (`broadcasts_to ->(o) { [o.user, :orders] }`) wires the `later` variants by default.

### Testing

```ruby
RSpec.describe OrderChannel, type: :channel do
  let(:user)  { create(:user) }
  let(:order) { create(:order, user: user) }
  before { stub_connection current_user: user }

  it "subscribes when the user owns the order" do
    subscribe(order_id: order.id)
    expect(subscription).to be_confirmed
    expect(subscription).to have_stream_for(order)
  end

  it "rejects when the order belongs to someone else" do
    subscribe(order_id: create(:order).id)
    expect(subscription).to be_rejected
  end
end

# From a model/service spec. Pass the computed stream-name string - a non-string
# target makes have_broadcasted_to raise "Broadcasting channel can't be inferred".
# perform_enqueued_jobs (ActiveJob::TestHelper) runs the _later_to render job.
it "broadcasts the updated card" do
  expect { perform_enqueued_jobs { order.update!(status: :paid) } }
    .to have_broadcasted_to("#{order.user.to_gid_param}:orders")
end
```

`turbo_stream_from` subscriptions ride `Turbo::StreamsChannel` - there is no custom channel to spec; the broadcast assertion plus a request/system test covering the rendered `turbo_stream_from` tag is full coverage. For Turbo Stream HTTP-side assertions (`text/vnd.turbo-stream.html`), see `rails-testing-patterns`.

## Output Format

In review or diagnosis mode, precede the block with numbered findings citing the violated rule; the block describes the corrected channel, so target state lives there rather than in a separate section. Any field may carry `- GAP` with the observed non-compliant value (`Broadcast adapter: async - GAP`), and any field whose evidence is outside the reviewed files is `not in evidence` plus the file to read. Emit one block per channel. Pure `turbo_stream_from` flows have no custom channel: write `Channel: Turbo::StreamsChannel (turbo_stream_from)` and pick the signed-scope authorization value.

```
Channel: <name | Turbo::StreamsChannel (turbo_stream_from)>

Identified by: <current_user | session token | JWT (transport) | signed resource ticket (anonymous) | not in evidence>

Stream scope: <per-user | per-tenant | per-resource | global - reason>

Authorization in subscribed: <Yes - policy/ownership check | Signed scope + controller gate (turbo_stream_from) | No - GAP>

Authorization in actions: <per-action check + rate limit | no receiving actions | No - GAP>

Broadcast adapter: <redis | solid_cable | postgresql | async | not in evidence>

Broadcast hook: <after_commit (inline | later) | service explicit | broadcasts directive>

Fan-out volume: <distinct targets per event - sync or batched | single shared stream (subscriber count is not fan-out) | not enumerable from the reviewed files>

Tests: <channel spec | broadcast assertion | both | none - GAP>
```

## Avoid

- `stream_from "scope_#{params[:id]}"` without an ownership check - IDOR over WebSocket
- One shared `turbo_stream_from` scope for per-user or per-tenant data - every viewer holds the identical signed tag
- Broadcasting from `after_save` - subscribers race the commit
- Sharing one Redis instance between ActionCable and Sidekiq under load
- Inline `broadcast_to` in a loop over many recipients
- PostgreSQL adapter in production with >2 app processes
- Treating `turbo_stream_from`'s signed scope as authorization
