---
name: rails-actioncable-patterns
description: "ActionCable Rails 7.2 - channel auth, subscription authz (IDOR), turbo_stream_from scope, Redis/PG adapter, fan-out batching, channel tests."
metadata:
  category: backend
  tags: [ruby, rails, actioncable, websocket, hotwire, turbo]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the broadcast adapter (Redis/PG), server (Puma/Falcon), and whether Hotwire is in use.

## When to Use

- Adding a channel or `turbo_stream_from` subscription
- Reviewing channel authentication and subscription authorization
- Choosing the broadcast adapter (Redis vs PostgreSQL vs async)
- Diagnosing slow broadcasts, fan-out spikes, or IDOR over WebSocket
- Testing channels and broadcasts

## Rules

- `identified_by :current_user` in `ApplicationCable::Connection`; `reject_unauthorized_connection` on missing/invalid identity
- Every channel `subscribed` authorizes the requested resource - never `stream_from` a client-supplied identifier without an ownership check
- `turbo_stream_from` scope is a capability; pass the user-scoped object (`turbo_stream_from current_user, :orders`), not a public ID
- Redis adapter in production; PostgreSQL adapter only for low-volume (LISTEN/NOTIFY caps throughput, one DB conn per process); `async` for tests only
- Broadcast from `after_commit`, not `after_save` - subscribers querying mid-broadcast see uncommitted state otherwise
- Fan-out > 100 recipients goes through Sidekiq (`broadcast_later_to` or a batched job), not inline in the request thread
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

For JWT/API apps, prefer the `Sec-WebSocket-Protocol` subprotocol header for the token - headers don't land in access logs. Query params are acceptable only for short-lived single-use tickets minted per connection. Never put the long-lived JWT itself in a URL. Devise apps can identify via `env["warden"].user` instead of the cookie lookup.

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
<%# Bad - guessable scope leaks across tenants %>
<%= turbo_stream_from "orders" %>

<%# Good - per-user, signed by Rails %>
<%= turbo_stream_from current_user, :orders %>
```

`turbo_stream_from` signs the scope so the signature proves the server emitted it - **not** that the current viewer is entitled. Authorization is the scope the controller chooses to render. For a user-owned resource, scope as `[current_user, record]` (and broadcast to the identical array) - including the owner makes the scope unguessable even if a signed tag leaks.

### Broadcast Adapters

| Adapter      | Use when                              | Trade-off                                  |
| ------------ | ------------------------------------- | ------------------------------------------ |
| `redis`      | Production, >1 app process            | One Redis conn per process; default        |
| `postgresql` | Single-process dev or low-volume only | LISTEN/NOTIFY caps throughput; DB pool hit |
| `async`      | Test / single-process dev             | No cross-process broadcast                 |

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
  after_commit -> { broadcast_replace_to [user, :orders], target: dom_id(self, :card) }, on: :update
end
```

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

Per-connection rate limiting for channel actions - a minimal Redis fence:

```ruby
def send_message(data)
  key = "cable:rl:#{connection.connection_identifier}:send_message"
  return transmit(error: "rate limited") if Sidekiq.redis { |r| r.incr(key).tap { r.expire(key, 10) } } > 20
  ...
end
```

`broadcast_later_to` enqueues rendering + broadcast to Active Job when the model has a Turbo `broadcasts` directive.

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

# From a model/service spec
it "broadcasts the updated card" do
  expect { order.update!(status: :paid) }.to have_broadcasted_to([order.user, :orders])
end
```

`turbo_stream_from` subscriptions ride `Turbo::StreamsChannel` - there is no custom channel to spec; the broadcast assertion plus a request/system test covering the rendered `turbo_stream_from` tag is full coverage. For Turbo Stream HTTP-side assertions (`text/vnd.turbo-stream.html`), see `rails-testing-patterns`.

## Output Format

In review mode, precede the block with numbered findings citing the violated rule; any field may carry `- GAP` with the observed non-compliant value (`Broadcast adapter: async - GAP`).

```
Channel: <name>
Identified by: <current_user | session token | JWT (transport)>
Stream scope: <per-user | per-resource | global - reason>
Authorization in subscribed: <Yes - policy/ownership check | No - GAP>
Broadcast adapter: <redis | postgresql | async>
Broadcast hook: <after_commit | service explicit | broadcast_later_to>
Fan-out volume: <recipients per event - sync or batched>
Tests: <channel spec | broadcast assertion | both>
```

## Avoid

- `stream_from "scope_#{params[:id]}"` without an ownership check - IDOR over WebSocket
- `turbo_stream_from "scope"` with a guessable name - cross-tenant leak
- Broadcasting from `after_save` - subscribers race the commit
- Sharing one Redis instance between ActionCable and Sidekiq under load
- Inline `broadcast_to` in a loop over many recipients
- PostgreSQL adapter in production with >2 app processes
- Treating `turbo_stream_from`'s signed scope as authorization
