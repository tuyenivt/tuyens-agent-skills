---
name: rails-actioncable-patterns
description: "ActionCable Rails 7.2+ - channel auth, subscription authz (IDOR), turbo_stream_from scope, Redis/Solid Cable adapters, fan-out, channel tests."
metadata:
  category: backend
  tags: [ruby, rails, actioncable, websocket, hotwire, turbo]
user-invocable: false
---

> Load `Use skill: stack-detect` first for framework and version. The broadcast adapter and Hotwire usage are not stack-detect fields - read them here from `config/cable.yml` and the Gemfile, unless the project declares them under `## Tech Stack`.

## When to Use

- Adding a channel or `turbo_stream_from` subscription
- Reviewing channel authentication and subscription authorization
- Choosing the broadcast adapter (Redis vs Solid Cable vs async)
- Diagnosing slow broadcasts, fan-out spikes, or IDOR over WebSocket
- Testing channels and broadcasts

## Rules

- `identified_by :current_user` in `ApplicationCable::Connection`; `reject_unauthorized_connection` on missing/invalid identity. Anonymous capability access (an emailed tracking link, no session) adds a second identifier rather than weakening the first: `identified_by :current_user, :verified_resource`, `connect` sets whichever the request carries and rejects when neither verifies, and the resource identifier comes from a signed, expiring token (`find_signed` - the non-bang form returns nil on a bad or expired token, so the reject branch runs) - never a raw id
- Every channel `subscribed` authorizes the requested resource - never `stream_from` a client-supplied identifier without an ownership check
- `turbo_stream_from` scope is a capability; pass model objects, not public IDs. Per-user data: `turbo_stream_from current_user, :orders`. Shared resources: `turbo_stream_from project, :comments` - authorization is the controller only rendering the tag for permitted viewers
- Keep `allowed_request_origins` strict in production and never set `disable_request_forgery_protection` - cookie-authenticated connections are Cross-Site WebSocket Hijacking targets otherwise
- Redis or Solid Cable in production (table below); `async` in development, `adapter: test` in test - the broadcast matchers require it
- Broadcast from `after_commit`, not `after_save` - subscribers re-querying mid-broadcast see the pre-commit state otherwise, and a rolled-back write is still announced
- Fan-out to > 100 *distinct targets* goes through one batched background job that enumerates the targets and broadcasts from the job - calling `broadcast_*_later_to` once per target still loops in the request thread and enqueues N jobs. When every target receives the same payload, the fix is one shared stream scoped to the resource they share (`stream_for warehouse`, authorized in `subscribed`), not batching. One broadcast to a stream many subscribers share is a single publish regardless of subscriber count - that cost is the adapter's, not the request thread's, so viewer count alone never triggers this rule
- Channel actions are RPC over a socket - rate-limit per identity (`connection.connection_identifier`, shared by every socket of one user) and validate params like any HTTP endpoint

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

For JWT/API apps, prefer the `Sec-WebSocket-Protocol` subprotocol header for the token - headers don't land in access logs; the client adds it with `consumer.addSubProtocol(token)` (Rails 7.1+), and in `connect` you split `request.headers["Sec-WebSocket-Protocol"]` on `,`, strip each entry, and take the one that is neither `actioncable-v1-json` nor `actioncable-unsupported`. Query params are acceptable only for short-lived single-use tickets minted per connection. Never put the long-lived JWT itself in a URL. A mailed capability token lives as long as the link must work (`expires_in:` on the signed id, days for a shipment); the cable ticket minted per page load stays short-lived, and an expired identifier is refused on the next reconnect rather than by dropping live sockets. Devise apps can identify via `env["warden"].user` instead of the cookie lookup.

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

Two roles on one resource (owner + support agent): look the record up unscoped (`Order.find_by(id: params[:order_id])`) and let the policy decide (`OrderPolicy.new(current_user, order).show?` covers both) - the owner-scoped lookup above returns nil for the agent and rejects before the policy runs. Both stream `stream_for order`.

Same rule for Turbo Stream scope:

```erb
<%# Bad - every viewer receives the identical signed tag - leaks across tenants %>
<%= turbo_stream_from "orders" %>

<%# Good - per-user, signed by Rails %>
<%= turbo_stream_from current_user, :orders %>
```

`turbo_stream_from` signs the scope so the signature proves the server emitted it - **not** that the current viewer is entitled. Authorization is the scope the controller chooses to render. For a user-owned resource, scope as `[current_user, record]` (and broadcast to the identical array) - including the owner narrows what a leaked tag grants to one user's view of one record. For a shared resource (project, team, room), scope as `[record, :collection]` and gate access in the controller/policy before rendering the tag - every holder of the signed tag can read the stream. A singleton scope with no record (admin dashboard, site status) follows the same shared-resource rule: a bare symbol scope is acceptable exactly when the controller renders the tag only to the entitled audience - the audience gate, not the scope name, is the control.

### Broadcast Adapters

| Adapter      | Use when                              | Trade-off                                  |
| ------------ | ------------------------------------- | ------------------------------------------ |
| `redis`      | Production, >1 app process            | Two Redis conns per process (one blocked in SUBSCRIBE, one publishing) - budget `maxclients` accordingly; default in the Rails 7.2 generated `cable.yml` |
| `solid_cable`| Production, Rails 8 default; the app already runs the Solid stack and poll latency is acceptable | Table-backed (works on MySQL) and polled (`polling_interval`; the generated `cable.yml` sets 0.1s) - delivery is only as fast as the poll; every cable-serving process polls, so give it its own database or budget the connections |
| `async`      | Development, single process           | No cross-process broadcast                 |
| `test`       | Test env                              | Records broadcasts (and still delivers in-process, like async); `have_broadcasted_to` requires it and raises under any other adapter |

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

`after_save` fires inside the transaction; subscribers re-querying see the pre-commit state, and if the transaction rolls back they have already received an update for a write that never happened.

One canonical broadcast source per message: the model `after_commit` (or an explicit service call) owns it - channel actions that also broadcast what the callback already broadcasts double-deliver. Persist in the action, let the callback announce. The stream a page subscribes to and the stream the model broadcasts on must be the same computed name, and the broadcast `target:` must be a DOM id the page renders (`dom_id(record)` on both sides) - a mismatch in either is a numbered finding, since the update is published and never shown.

Presence and typing indicators are ephemeral channel-action broadcasts, not model callbacks: `subscribed` / `appear` increment a Redis counter per `connection_identifier` and refresh its TTL (heartbeat every ~30 s from the client, so a dropped socket expires rather than lingering), `unsubscribed` decrements it and removes it at zero - several tabs share one identifier, so a plain key deleted on one tab's unsubscribe would drop a user whose other tabs are open - and a late joiner reads the current set from Redis on `subscribed` instead of waiting for the next event. The roster broadcast carries ids and display names only, never the user record.

### Fan-Out Batching

```ruby
# Bad - blocks the request, holds the DB connection
followers.find_each { |f| NotificationChannel.broadcast_to(f, payload) }

# Good - one job per event; the job enumerates off the request thread, filtering
# (mutes, prefs) in the query
BroadcastNotificationJob.perform_async(author.id, payload.as_json)   # Sidekiq strict args: JSON-native, string keys

# BroadcastNotificationJob#perform(author_id, payload)
User.joins(:follows).merge(Follow.where(author_id: author_id, muted: false))
    .find_each { |follower| NotificationChannel.broadcast_to(follower, payload) }
```

Per-identity rate limiting for channel actions. `connection_identifier` is built from the declared `identified_by` values, so every socket for the same user - two tabs, a reconnect - shares one counter. That is the stronger control (a client cannot buy quota by opening more sockets); per-socket limits need a second identifier (`identified_by :current_user, :socket_id`, with `self.socket_id = SecureRandom.uuid` in `connect`) - which also changes the key `ActionCable.server.remote_connections.where` matches on. A minimal Redis fence (any Redis pool works; counter keys are tiny, so borrowing `Sidekiq.redis` here does not conflict with keeping broadcast pub/sub on its own instance):

```ruby
def send_message(data)
  key = "cable:rl:#{connection.connection_identifier}:send_message"
  count = Sidekiq.redis { |r| r.incr(key).tap { |n| r.expire(key, 10) if n == 1 } }
  return transmit({ error: "rate limited" }) if count > 20   # braces required: transmit(data, via:)
  # ... handle the message
end
```

A loop publishing the same payload N times to one stream is a GAP - replace it with one broadcast; a value that changes hundreds of times a minute (a live counter) is coalesced - a short-interval job broadcasts the current value - rather than broadcast per event.

Non-`later` broadcast helpers render the partial in the caller's thread. Use the `_later_to` variants (`broadcast_replace_later_to`) from model callbacks and request-path code so rendering happens on Active Job; inline variants are fine from jobs, which already run off-thread. The Turbo directive form (`broadcasts_to ->(o) { [o.user, :orders] }`) wires the `later` variants for create and update; removal on destroy stays inline (`broadcast_remove_to` renders nothing).

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

# From a model/service spec. Pass the computed stream-name string (a Symbol also works) - a
# record or array target without `.from_channel(...)` raises "Broadcasting channel can't be
# inferred", and from_channel(Turbo::StreamsChannel) is wrong for Turbo streams anyway, because
# broadcasting_for prefixes the channel name. perform_enqueued_jobs runs the _later_to render job -
# it needs ActiveJob::TestHelper (request specs get it through the integration-test load hook;
# model and service specs do not: config.include ActiveJob::TestHelper, type: :model) and the :test queue adapter.
it "broadcasts the updated card" do
  expect { perform_enqueued_jobs { order.update!(status: :paid) } }
    .to have_broadcasted_to("#{order.user.to_gid_param}:orders")
end
```

`turbo_stream_from` subscriptions ride `Turbo::StreamsChannel` - there is no custom channel to spec; the broadcast assertion plus a request/system test covering the rendered `turbo_stream_from` tag is full coverage. For Turbo Stream HTTP-side assertions (`text/vnd.turbo-stream.html`), see `rails-testing-patterns`.

## Output Format

In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no client class, no transaction, no channel class) gets a block for the unit the fix introduces, its name suffixed `(proposed)`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to design or change code is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding. `Broadcast adapter` names the production adapter; a test environment on anything but `test` is a numbered finding. Emit one block per channel, and one per stream when streams on the same channel differ in scope or hook (an account balance stream and a global entries stream are two blocks). Pure `turbo_stream_from` flows have no custom channel: write `Channel: Turbo::StreamsChannel (turbo_stream_from)` and pick the signed-scope authorization value; when the controller rendering the tag is outside the read set, `Authorization in subscribed` is `not in evidence` plus the controller file. Connection-wide fields (`Identified by`, `Broadcast adapter`, `Request origins`) repeat in every block; the finding behind a connection-wide GAP is written once. An existing policy that cannot express the ownership rule (an admin-only `show?`) is a numbered finding owned by `rails-security-patterns`.

```
Channel: <name | Turbo::StreamsChannel (turbo_stream_from)>

Identified by: <current_user | current_user, no reject on a missing user - GAP | session token | unsigned cookie id - GAP (`cookies[:user_id]`, forgeable) | resource identifier from a raw id - GAP | JWT (transport) + the identifier it resolves to | signed resource ticket (anonymous) | not in evidence - list every identifier the Connection declares, joined with +>

Stream scope: <per-user | per-tenant | per-resource | global - reason (a reason is required; a global stream carrying per-user data is a GAP)>

Authorization in subscribed: <Yes - policy/ownership check | Yes - audience gate (a shared stream every authenticated role may read; the check is the role, not a record) | fixed at connect (the identifier is the resource) | Signed scope + controller gate (turbo_stream_from) | Signed scope, controller gate missing - GAP | No - GAP>

Authorization in actions: <per-action check + rate limit | per-action check, no rate limit - GAP | no receiving actions | No - GAP>

Broadcast adapter: <redis | solid_cable | async | not in evidence>

Request origins: <allowed_request_origins strict, forgery protection on | unset - same-origin only, plus localhost in development (framework default, compliant; a stated client on another origin makes it a GAP -> allowed_request_origins strict) | allowed_request_origins permissive - GAP | disable_request_forgery_protection - GAP | not in evidence>

Broadcast hook: <after_commit (later) | after_commit enqueuing a broadcasting job (the job broadcasts inline) | after_commit (inline, from a model callback) - GAP | service explicit (later, or inline from a job) | service explicit (inline, request path) - GAP | broadcasts directive | channel action broadcasting an ephemeral event (typing, presence) | channel action re-broadcasting what the callback announces - GAP (persist in the action, let the callback announce) | after_save - GAP | not in evidence - the broadcaster is outside the read set>

Fan-out volume: <distinct targets per event - batched job | <= 100 distinct targets broadcast inline | > 100 distinct targets broadcast inline - GAP | same payload published N times to one stream - GAP (one broadcast) | single shared stream (subscriber count is not fan-out; a shared stream carrying per-user data is an authorization GAP, not a cost) | not enumerable from the reviewed files | not in evidence>

Tests: <channel spec | channel spec, no rejection case - GAP | broadcast assertion | broadcast assertion + request/system test (turbo_stream_from flows - full coverage) | channel spec + broadcast assertion | none - GAP>
```

## Avoid

- `async` adapter in production - broadcasts never leave the process that sent them
- Treating `turbo_stream_from`'s signed scope as authorization
- A channel action that re-broadcasts what the model callback already announces - double delivery
