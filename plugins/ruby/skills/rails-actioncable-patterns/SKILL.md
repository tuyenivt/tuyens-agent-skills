---
name: rails-actioncable-patterns
description: "ActionCable for Rails 7.2: channel auth, subscription authz, Turbo Streams scope security, broadcast adapters, fan-out batching, channel testing."
metadata:
  category: backend
  tags: [ruby, rails, actioncable, websocket, hotwire, turbo]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the broadcast adapter (Redis/PG), server (Puma/Falcon), and whether Hotwire is in use.

## When to Use

- Adding a new ActionCable channel or Turbo Stream subscription
- Reviewing channel authentication and subscription authorization
- Choosing the broadcast adapter (Redis vs PostgreSQL)
- Diagnosing slow broadcasts, fan-out spikes, or IDOR via channel join
- Testing channels and broadcasts

## Rules

- `identified_by :current_user` in `ApplicationCable::Connection`; reject the connection (`reject_unauthorized_connection`) when the session/JWT is invalid.
- Every channel `subscribed` method authorizes the requested resource - never `stream_from` a client-supplied identifier without an ownership check.
- `turbo_stream_from` interpolates user data into the channel name - the channel name is a capability; treat it as an authorization decision, never a public ID.
- Redis adapter for production fan-out; PostgreSQL adapter only for low-volume apps (uses `LISTEN/NOTIFY` - one DB connection per process, throughput-limited).
- Broadcast from `after_commit`, not `after_save` - subscribers reading the DB on the broadcast see a committed row.
- Batch fan-out for >100 recipients - `broadcast_later_to` (Sidekiq) instead of inline `broadcast_to`.
- Channel actions are RPC over a long-lived socket; rate-limit per connection and validate params like any HTTP endpoint.
- One subscription per resource per tab. Repeated `subscribed` from the same client signals reconnect storms or client-side bugs.

## Patterns

### Connection Identification

```ruby
module ApplicationCable
  class Connection < ActionCable::Connection::Base
    identified_by :current_user

    def connect
      self.current_user = find_verified_user
    end

    private

    def find_verified_user
      User.find_by(id: cookies.encrypted[:user_id]) || reject_unauthorized_connection
    end
  end
end
```

For API/JWT apps, decode the token from the `Authorization` header passed via the upgrade request (forwarded as `Sec-WebSocket-Protocol` or query param - never put raw tokens in URLs that hit logs).

### Subscription Authorization (IDOR prevention)

Bad - trusts client-supplied ID:

```ruby
class OrderChannel < ApplicationCable::Channel
  def subscribed
    stream_for Order.find(params[:order_id])   # any authenticated user can subscribe to any order
  end
end
```

Good - enforce ownership/policy:

```ruby
class OrderChannel < ApplicationCable::Channel
  def subscribed
    order = current_user.orders.find_by(id: params[:order_id])
    return reject unless order && OrderPolicy.new(current_user, order).show?

    stream_for order
  end
end
```

For Turbo Streams, the same rule applies to the **scope** passed to `turbo_stream_from`:

```erb
<%# Bad - exposes other tenants' updates if the scope is guessable %>
<%= turbo_stream_from "orders" %>

<%# Good - per-user scope, enforced by the channel %>
<%= turbo_stream_from current_user, :orders %>
```

`turbo_stream_from` signs the scope and Turbo's `Turbo::StreamsChannel` verifies the signature - but the signature only proves the server emitted the scope, not that the *current viewer* should receive it. Authorization happens by what scope the controller chooses to render.

### Broadcast Adapters

| Adapter        | Use when                                | Trade-off                                 |
| -------------- | --------------------------------------- | ----------------------------------------- |
| `redis`        | Production with >1 app process          | One Redis connection per process; default |
| `postgresql`   | Single-process dev or low-volume only   | LISTEN/NOTIFY caps throughput; DB pool hit|
| `async`        | Test/single-process dev                 | No cross-process broadcast                |

Configure in `config/cable.yml`:

```yaml
production:
  adapter: redis
  url: <%= ENV.fetch("REDIS_CABLE_URL") %>
  channel_prefix: app_production
```

Run a dedicated Redis instance for ActionCable when broadcast volume is high - sharing with Sidekiq/cache causes head-of-line blocking on either workload.

### Broadcast from `after_commit`

```ruby
class Order < ApplicationRecord
  after_commit -> { broadcast_replace_to [user, :orders], target: dom_id(self, :card) }, on: :update
end
```

`after_save` fires inside the transaction - subscribers re-querying see the pre-commit state (or nothing, if the txn rolls back).

### Fan-Out Batching

For high-cardinality broadcasts (notifications to thousands of users), do not call `broadcast_to` in a tight loop on the request thread:

```ruby
# Bad - blocks the request, holds the DB connection
followers.find_each { |f| NotificationChannel.broadcast_to(f, payload) }

# Good - hand off to Sidekiq, broadcast in chunks
followers.in_batches(of: 500) do |batch|
  BroadcastNotificationJob.perform_async(batch.pluck(:id), payload)
end
```

Use `broadcast_later_to` when the model has a Turbo `broadcasts` directive - it enqueues the rendering and broadcast to Active Job.

### Testing Channels and Broadcasts

```ruby
# Channel spec - subscription + actions
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
    other = create(:order)
    subscribe(order_id: other.id)
    expect(subscription).to be_rejected
  end
end

# Broadcast assertion from a model/service spec
it "broadcasts the updated card" do
  expect { order.update!(status: :paid) }
    .to have_broadcasted_to([order.user, :orders])
end
```

See `rails-testing-patterns` for the Turbo Stream HTTP-side assertion (`text/vnd.turbo-stream.html`).

## Output Format

When reviewing or designing a channel:

```
Channel: <name>
Identified by: <current_user | session token>
Stream scope: <per-user | per-resource | global - reason>
Authorization in subscribed: <Yes - policy/ownership check | No - GAP>
Broadcast adapter: <redis | postgresql | async>
Broadcast hook: <after_commit | service explicit | broadcast_later_to>
Fan-out volume: <recipients per event - sync or batched>
Tests: <channel spec | broadcast assertion | both>
```

## Avoid

- `stream_from "scope_#{params[:id]}"` without an ownership check - IDOR over WebSocket
- `turbo_stream_from "scope"` with a global or guessable scope name - cross-tenant leak
- Broadcasting from `after_save` - subscribers race the commit
- Sharing Redis instance between ActionCable and Sidekiq under load - head-of-line blocking
- Inline `broadcast_to` in a loop over many recipients - blocks the request, holds DB conn
- PostgreSQL adapter in production with >2 app processes - LISTEN/NOTIFY throughput ceiling
- Trusting `turbo_stream_from`'s signed scope as authorization - it only proves the server signed it, not that the recipient is entitled
