---
name: rails-service-objects
description: Rails service objects: .call + Result, transaction boundaries, external-API ordering, idempotency keys, compensating actions, composition.
metadata:
  category: backend
  tags: [ruby, rails, service-objects, architecture, patterns]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Extracting business logic spanning multiple models or external APIs
- Multi-step mutations with transactions
- Refactoring fat controllers / models
- Wrapping external API calls with idempotency

Extraction bar - either limb is sufficient on its own: (a) the operation spans 2+ models or an external API **and** owns a transaction boundary, or (b) it has 3+ call sites. One call site is no objection under (a). A single-call-site, single-model operation meeting neither stays in the model or controller.

## Rules

- One service, one responsibility, verb-named (`FulfillOrder`, `ChargeCustomer`); place in `app/services/`, nest by domain when count grows. Entrypoint is instance `#call` - not class-method `run`/`execute`; a `def self.call(...) = new(...).call` shim is compliant (naming is the rule, not the shim).
- `call` returns `Result` for expected failures; raise only for programmer errors / unexpected state. `RecordNotFound` on user-supplied IDs is expected (Result); on internal IDs it's a bug (raise).
- Validate inputs in `initialize` (`ArgumentError` on invariants); authorization stays in controllers (Pundit).
- DB writes inside `ActiveRecord::Base.transaction`; external API calls outside; Sidekiq dispatch after commit.
- On partial failure after an external call succeeds, enqueue a reconciliation job - never inline refund / undo.

## Patterns

### `.call` + Result

```ruby
# app/services/result.rb
class Result
  attr_reader :value, :errors, :code

  def initialize(success:, value: nil, errors: [], code: nil)
    @success, @value, @errors, @code = success, value, Array(errors), code
  end

  def success? = @success
  def failure? = !@success

  def self.success(value = nil)       = new(success: true, value: value)
  def self.failure(errors, code: nil) = new(success: false, errors: errors, code: code)
end
```

`code:` drives HTTP status mapping in controllers (`:out_of_stock` -> 409, `:payment_declined` -> 402). String-matching `errors` is fragile.

### Service Body

```ruby
class FulfillOrder
  def initialize(order:, fulfilled_by: nil)
    @order, @fulfilled_by = order, fulfilled_by
    raise ArgumentError, "Order required" unless @order   # nil/type invariants only
  end

  def call
    # requires_new: inside a caller's transaction a savepoint, so the rescue below rolls back only this work
    outcome = ActiveRecord::Base.transaction(requires_new: true) do
      @order.lock!                                     # re-read under FOR UPDATE: two concurrent runs can't both pass
      next :replay if @order.processing? || @order.fulfilled?   # a previous run got here: skip the work, not the dispatch
      next :not_confirmed unless @order.confirmed?     # the full precondition, checked under the lock
      @order.update!(status: :processing, processing_started_at: Time.current)
      decrement_inventory
      :done
    end
    return Result.failure(["Order must be confirmed"], code: :not_confirmed) if outcome == :not_confirmed

    # Post-commit even inside a caller's transaction (runs at once when none is open); the job is idempotent
    ActiveRecord.after_all_transactions_commit { ShipmentNotificationJob.perform_async(@order.id) }
    Result.success(@order.reload)
  rescue Inventory::InsufficientStockError => e
    Result.failure([e.message], code: :out_of_stock)
  end

  private

  def decrement_inventory
    products = Product.where(id: @order.order_items.map(&:product_id))
                      .order(:id).lock("FOR UPDATE").index_by(&:id)
    @order.order_items.each do |item|
      product = products.fetch(item.product_id)
      raise Inventory::InsufficientStockError, "#{product.name} short" if product.available_stock < item.quantity
      product.decrement!(:available_stock, item.quantity)
    end
  end
end
```

`FOR UPDATE` prevents oversell; the `ORDER BY id` in the same locking query (chain order is irrelevant - the SQL is identical) kills the A->B/B->A deadlock two orders sharing products would otherwise hit. A service that locks two rows of one table by id (a transfer) rejects equal ids before any lock (a `Failure` code when the ids are user input; `ArgumentError` in `initialize` only when equal ids are a caller bug) - locking one row twice is not a transfer. For lock semantics, see `rails-db-locking-patterns`.

### External API Ordering + Compensating Action

Network calls inside a transaction hold the DB connection across the round-trip and invert failure modes. Correct order: validate -> charge (outside txn) -> open transaction with the payment ID -> commit -> dispatch jobs.

- Mail and notifications are Sidekiq jobs, not External API entries. Multiple external systems: the call whose failure must abort the flow goes before the transaction (before the finalize transaction in the claim/finalize shape); deferrable or flaky systems go after commit as Sidekiq jobs. The test is one question - *if this call fails, is the local write still correct?* No means it gates, so it goes first (charge, refund, inventory reservation at a third party). Yes means it is deferrable, so it goes after commit with a reconciliation path (ERP sync, notifications, search indexing, carrier booking that can be retried against an order that already exists). A post-commit external failure degrades to its reconciliation path - it never fails the Result.
- Contended resource (slot, seat, stock): the canonical order above assumes the mutation isn't claiming a contended resource. The test here is also one question - *could a concurrent run take the same thing?* A finite pool that two requests can exhaust (seats, stock, a unique slug) is contended and wants the two-transaction claim below. A single row only this request's key can touch is not contended, however much retry-safety it needs - idempotency alone is the second carve-out (below), not this one. When it is, prefer the two-transaction variant: txn 1 claims under row lock (pending state) -> charge -> txn 2 finalizes. Releasing your own pending claim on charge failure is a compensating write against a row only you own, not the forbidden inline undo (which refers to reversing a *succeeded* external call). Because txn 1 has already committed, that release can itself fail - so a scheduled sweep of stale pending rows is mandatory, not optional, or a crash between claim and finalize orphans the resource forever. The sweep is the reconciliation job below, never a blind TTL: a claim can be stale precisely because the charge *succeeded* and txn 2 never committed, and expiring that one releases the seat while the customer stays charged. Query ground truth first, finalize if the charge landed, release only if it did not.
- Idempotency-key rows are the second carve-out: the key row is persisted in its own transaction *before* the external call, because a durable record of an in-flight call is what makes the retry safe. Only mutations referencing the external result go in the post-call transaction. Those rows need the same sweep for the same reason - a crash between `create!` and the status write leaves `pending` forever, and a replay that answers "in flight" indefinitely is a charge that never becomes an order. When the resource row is itself the keyed record (a document, an upload), the key column lives on it and the row's own state column is the in-flight marker.
- An Active Storage `attach` is a local write inside the transaction (the upload runs in `after_commit`); an upload that must *gate* the flow runs first via `ActiveStorage::Blob.create_and_upload!` - `rails-active-storage-patterns` owns the orphan sweep.
- Orchestrators are replay-safe at the top, but a replay guard skips the *work*, not the post-commit dispatch. Returning early on the whole method drops the job on every replay, so a crash in the window between commit and dispatch loses it permanently - the guard has to sit around the transaction, with the dispatch after it and the job itself idempotent. (An outbox row written inside the transaction is the stronger form when losing the job is unacceptable.) Result stays binary - deferred post-commit work pending is still Success, with the job listed in the output block.
- A reconciliation job re-checks ground truth (was the charge captured? does the row exist?) and completes or reverses; it alerts after exhausting retries.

If the DB write fails after a successful charge, enqueue a reconciliation job:

```ruby
# Stock here is made to order, not a contended pool - a contended one takes the
# two-transaction claim above instead of charge-first. CreateOrder closes the cart by state and never
# mutates its lines: ChargeCustomer's fingerprint reads cart.total_cents on every replay, so an emptied
# cart would answer :idempotency_conflict instead of replaying the order.
def call
  payment = ChargeCustomer.new(cart: @cart, payment_method_id: @payment_method_id, idempotency_key: @key).call
  return payment if payment.failure?

  existing = Order.find_by(payment_id: payment.value.id)   # replay: the charge replayed, so may the order
  return succeed(existing) if existing                     # (orders.payment_id is unique; CreateOrder maps
                                                           #  RecordNotUnique to the existing order)
  begin
    order = CreateOrder.new(cart: @cart, payment: payment.value).call
  rescue StandardError                                   # raise path needs it too
    PaymentReconciliationJob.perform_async(payment.value.id, "order_write_failed")
    raise
  end

  if order.failure?
    PaymentReconciliationJob.perform_async(payment.value.id, "order_write_failed")
    return order
  end

  succeed(order.value)
end

def succeed(order)
  ActiveRecord.after_all_transactions_commit { ShipmentNotificationJob.perform_async(order.id) }   # idempotent job
  Result.success(order)
end
```

### Idempotency Keys

For mutating services on at-least-once paths (HTTP retry, Sidekiq retry, double-click), thread one key through the chain and back it with a unique DB index (`add_index :payments, :idempotency_key, unique: true`). Key source by trigger: client `Idempotency-Key` header when the client cooperates; otherwise derive deterministically from intent (`"book-#{user_id}-#{slot_id}"`) for double-click/UI paths, or from job args for Sidekiq retries. The key names the attempt, never only the payload: two legitimate equal partial refunds carry two client keys, and a payload hash alone would collapse them. With no client key and nothing to derive one from, reject the request (400) - a random key defeats the retry it exists for; the rejection is the service's `Failure(:idempotency_key_missing)`, mapped to 400 by the controller. A replay carrying the same key with a different payload is a conflict, never a silent replay: store a payload fingerprint beside the key and return `Failure(:idempotency_conflict)` (409).

```ruby
class ChargeCustomer
  def initialize(cart:, payment_method_id:, idempotency_key:)
    @cart, @payment_method_id, @key = cart, payment_method_id, idempotency_key
  end

  def call
    return Result.failure([:idempotency_key_missing], code: :idempotency_key_missing) if @key.blank?   # nil key would match any NULL row
    existing = Payment.find_by(idempotency_key: @key)                # assign on its own line - see below
    return replay(existing) if existing                              # replay compares request_fingerprint first - a mismatch is :idempotency_conflict

    payment = Payment.create!(cart_id: @cart.id, amount_cents: @cart.total_cents, idempotency_key: @key,
                              request_fingerprint: fingerprint, status: :pending)  # durable before the call
    intent  = BillingClient.new.create_intent(amount_cents: payment.amount_cents,          # the client confirms the intent
                                              payment_method_id: @payment_method_id, idempotency_key: @key)
    payment.update!(gateway_payment_id: intent.id, gateway_status: intent.status, status: status_for(intent.status))
    settle(payment)
  rescue ActiveRecord::RecordNotUnique
    replay(Payment.find_by!(idempotency_key: @key))                  # race loser; runs in autocommit, outside any caller
                                                                     # transaction, so the winner's row is visible - inside a caller's
                                                                     # REPEATABLE READ transaction the snapshot can predate the winner (RecordNotFound)
  rescue BillingError::Declined => e
    payment&.update!(status: :declined)          # terminal, or the key wedges until reconciliation
    Result.failure([e.message], code: :payment_declined)
  rescue BillingError::Unavailable                # timeout or dropped connection: unknown outcome, never a decline
    PaymentReconciliationJob.perform_async(payment.id, "charge_in_flight") if payment   # the row stays pending; reconciliation asks the gateway
    raise
  end

  private

  def fingerprint = Digest::SHA256.hexdigest([@cart.id, @cart.total_cents, @payment_method_id].join(":"))

  # Three outcomes, not two: "not captured" is not the same as "failed".
  def status_for(intent_status)
    case intent_status
    when "succeeded"                            then :captured
    when "canceled", "requires_payment_method" then :declined
    else :pending   # requires_action (3DS), processing, requires_capture - not terminal
    end
  end

  def settle(payment)
    return Result.success(payment) if payment.captured?
    return Result.failure(["payment declined"], code: :payment_declined) if payment.declined?

    PaymentReconciliationJob.perform_async(payment.id, "charge_in_flight")
    # 3DS needs the customer - handing back the client secret (a value on the failure, or a
    # follow-up fetch) is the controller contract's job, out of scope here; processing /
    # requires_capture need only time
    code = payment.gateway_status == "requires_action" ? :requires_action : :payment_processing
    Result.failure(["payment incomplete"], code: code)
  end

  # A row alone proves nothing - only a terminal row does.
  def replay(payment)
    return Result.failure(["key reused with a different request"], code: :idempotency_conflict) if payment.request_fingerprint != fingerprint
    return Result.success(payment)                                    if payment.captured?
    return Result.failure(["payment declined"], code: :payment_declined) if payment.declined?
    # Payment#fresh? = pending? && created_at > CHARGE_TIMEOUT.ago; a 3DS replay answers as the first call did
    return Result.failure(["charge in flight"], code: { "requires_action" => :requires_action, nil => :idempotency_conflict }.fetch(payment.gateway_status, :payment_processing)) if payment.fresh?

    # A pending row older than the charge timeout is not "in flight" - it is unknown.
    # Ask the gateway by key before answering; never expire it blind.
    PaymentReconciliationJob.perform_async(payment.id, "pending_expired")
    Result.failure(["payment state unknown - reconciling"], code: :idempotency_conflict)
  end
end
```

Five things this shape gets right, each a live bug in its absence: `existing` assigned on its own line (a modifier-`if` body parses before its condition, so `return ... if (existing = ...)` raises `NameError` on exactly the replay path); the replay gated on terminal state (a pending or declined row returned as success creates an order against money never captured); the key required (`find_by(idempotency_key: nil)` matches an arbitrary NULL-key row - MySQL's unique index admits unlimited NULLs); the status derived three ways from the response (`requires_action`, `processing` and `requires_capture` are neither captured nor declined, so they fail *and* enqueue reconciliation; a gateway timeout is the same unknown, never a decline - the `Unavailable` rescue leaves the row pending and enqueues reconciliation, since nothing else runs on a raise); and every rescued exit writing a terminal state or enqueuing reconciliation, any other raise leaving the row `pending` for the stale-pending sweep (a declined charge left pending answers `:idempotency_conflict` until reconciliation resolves it - one declined card wedges the key).

The SDK call sits behind `BillingClient`, not in the service: services never name a vendor error class (`Stripe::CardError`) - the client translates at the boundary. For the client and its idempotency header, see `rails-http-client-patterns`; for the error taxonomy, `rails-exception-handling`.

### Transaction Discipline

For nested transactions, `requires_new`, `after_commit` vs `after_save`, isolation levels, and deadlock retry, see `rails-transaction-patterns`. Service-specific:

- Outer service owns the transaction; inner services either don't open one or use `requires_new: true`.
- Post-commit dispatch via `ActiveRecord.after_all_transactions_commit` - it waits for every open transaction on every pool and runs at once when none is open (`Model.current_transaction.after_commit` is the single-connection form: it climbs to that connection's outermost transaction only), so a bare `perform_async` after a service's own block is wrong whenever a caller may wrap it. `after_commit_everywhere` only where it is already in the Gemfile.
- `return`, `break` or `throw` inside the transaction block commits the writes made before it: an exit that means failure raises, or `raise ActiveRecord::Rollback`; `next :code` out of the block, as `FulfillOrder` does, is the deliberate commit-and-report exit (`rails-transaction-patterns`).
- An inner service that opens a transaction uses `requires_new: true` and returns a `Result` - its own rescue rolls back only its savepoint. A composing caller that must abort the whole unit checks `failure?` inside its block and raises.

### Controller Usage

```ruby
def create
  authorize @cart, :checkout?
  result = Checkout.new(cart: @cart, payment_method_id: params.require(:payment_method_id),
                        idempotency_key: request.headers["Idempotency-Key"].presence || "checkout-#{current_user.id}-#{@cart.id}-#{params[:payment_method_id]}").call   # derive when the client sends none; a new card is a new attempt
  if result.success?
    render json: OrderSerializer.new(result.value), status: :created
  else
    render json: { errors: result.errors, code: result.code }, status: status_for(result.code)
  end
end   # an HTML controller redirects on success and re-renders the form with status: :unprocessable_content on failure

private

def status_for(code)
  # Every code any composed service can emit needs an entry - an orchestrator that
  # returns a child's Result verbatim leaks the child's codes to this mapping, and
  # fetch without a default makes a missing entry fail in tests, not ship as a 422.
  { cart_invalid: :unprocessable_content, out_of_stock: :conflict,
    payment_declined: :payment_required, requires_action: :payment_required,
    payment_processing: :accepted, idempotency_conflict: :conflict,
    idempotency_key_missing: :bad_request, not_confirmed: :unprocessable_content
  }.fetch(code)   # :unprocessable_content is 422; Rails 8.1 maps it on Rack < 3.1 too
end
```

## Output Format

One block per service (orchestrator and each child; plain jobs don't get blocks - a job's own idempotency or retry defect is a numbered finding naming `rails-sidekiq-patterns`). A unit outside the read set that the reviewed code or its design depends on (a webhook handler, a reconciliation job named in a doc) is one numbered finding naming the file, not a `(proposed)` block. In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no service around a controller's inline mutation) gets a block for the unit the fix introduces, its name suffixed `(proposed)`; a vendor client (`StripeGateway`, `AmsClient`) is not a service - findings only, naming `rails-http-client-patterns`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to add code, or to change code the request does not ask you to judge, is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding. A request that names existing code to assess, even when it also asks for the fix, is review mode. A service recommended for deletion, or a class in `app/services/` that is not a service at all (a calculator, a strategy, a value object), gets findings only and no block, with one line saying which it is. Controller-level findings (a missing `authorize`, an unmapped code, mass-assigned or client-priced params feeding the service), a model callback that dispatches inside the transaction, a project `Result` lacking a reader this contract uses, and two services implementing one responsibility without composing (name the survivor) are numbered findings with no block. A scheduled sweep is listed on the block of the service it backs. A project with no `Result` class gets the contract block below; the contract block also appears when the request asks for the Result API itself ("design the Result contract"), while a `result.rb` that is merely listed among the files to review gets findings only. A service that finalizes on a partner's confirmation webhook is its own block; webhook dedupe is `rails-http-client-patterns`' concern, and out-of-order delivery takes `rails-sidekiq-patterns`' monotonic guard.

The job backend comes from the Gemfile (`sidekiq` or `solid_queue`), not from stack-detect. An Active Job class (`ApplicationJob`, any backend) retries through `retry_on` / `discard_on` and enqueues with `perform_later`; a `Sidekiq::Job` retries through `sidekiq_options retry:` + `sidekiq_retry_in` and enqueues with `perform_async`. A slot named for Sidekiq (`Sidekiq retry`, `sidekiq only`) takes the channel of whichever backend runs the job. A `rescue` inside `perform` for a class the retry channel owns wins and silently disables that retry - one channel per class. `perform_later` inside a transaction is deferred to commit only when the job class sets `self.enqueue_after_transaction_commit = true` (default false), so the post-commit rule above binds both backends.

```
Service: {ClassName}

Location: app/services/{file}.rb

Responsibility: {one sentence}

Transaction: {Yes - models mutated | Yes - two: claim, then finalize | Yes - key row first, result row after the call | joins the caller's (requires_new: true | fused - GAP if the service or its caller rescues between the inner and outer block) | No}

External API: {none | provider; placement: before the transaction (gating) | between the key-row and result transactions (idempotency-key shape) | between the claim and finalize transactions (contended resource) | after commit via job (deferrable) | inside - GAP; compensating action: <job name | pending-claim release + sweep | absent - GAP | N/A> - one entry per provider}

Idempotency: {key source; unique index column (`not in evidence - db/schema.rb` when the schema is unread) | row lock on a state column (claim/finalize), or a unique index on the contended resource | state replay (a re-run skips completed work, no key) | gateway-side only - no local index | none - GAP if the path is at-least-once - list all that apply}

Sidekiq Jobs: {jobs dispatched after commit | mailer deliver_later after commit | dispatched inside the transaction - GAP | dispatched on a failure branch only (name it) | scheduled sweep: <job> | absent - GAP when a pending or claim row exists | None}

Result: Success({value}) | Failure({code enum}) | Failure with no code (errors or a message only) - GAP -> Failure({code enum}) | <observed non-Result return (false, a record, nil) - GAP -> Result>
```

When the deliverable is the shared `Result` contract itself rather than one service, emit this block once (plus per-service blocks for services already in scope), and list the failure codes the project registers, grouped by owning service; a reconciliation job takes `perform(record_id, reason)` with the reason drawn from the same registry:

```
Result API: success({value}) / failure({errors}, code:) - readers: value, errors, code, success?, failure?

Codes: {the project's registry, designed here when none exists; synchronous codes and job-side reconciliation reasons listed separately}

Consumed by: {controller: code -> HTTP status | job: retry on <codes>, drop (mark resolved and report) on <codes> | service: return early on failure?}
```

These fields take ` - GAP` by the same rule (a job whose `perform` receives no reason; a service that returns nothing).

## Avoid

- Wrapper around a single AR method - call the method directly
- Pure delegation services adding no logic - unnecessary indirection
- A `rescue` attached to the `transaction do ... end` block itself - it runs inside the transaction, so a rescued `InsufficientStockError` still commits the writes made before it (`rails-transaction-patterns`)
- Check-then-decrement on stock with neither a row lock nor a guarded atomic UPDATE (`... SET stock = stock - ? WHERE id = ? AND stock >= ?`, affected rows checked) - races oversell
