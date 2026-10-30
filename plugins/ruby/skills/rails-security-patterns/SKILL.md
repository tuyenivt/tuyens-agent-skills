---
name: rails-security-patterns
description: Rails security - strong params, Devise/JWT, Pundit, CSRF, SQLi, IDOR, open redirect, Rack::Attack, credentials, signed cookies, host auth.
metadata:
  category: backend
  tags: [ruby, rails, security, authentication, authorization]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

For template-layer XSS (`sanitize` allowlists, engine escape operators), see `rails-view-templates`. For upload validation / magic-byte sniffing and blob URL exposure or expiry, see `rails-active-storage-patterns`. A friendly-500 `rescue_from StandardError` that hides bugs is `rails-exception-handling`'s.

## When to Use

- Adding auth (Devise/JWT/`authenticate_by`) or authz (Pundit)
- Reviewing strong params for mass assignment / IDOR
- Implementing rate limiting (`Rack::Attack`)
- Setting up Rails credentials, signed cookies, host authorization
- Auditing `redirect_to` / SQL composition / CSRF posture
- Verifying inbound webhook signatures

## Rules

- Never `params.permit!` / `params.to_unsafe_h`; never permit ownership FKs (`:user_id`, `:account_id`, `:tenant_id`)
- Every resource action calls `authorize`; every index uses `policy_scope`; enforce with `after_action :verify_authorized` / `:verify_policy_scoped`
- Parameterized queries only - never string interpolation in `where`
- Secrets via Rails credentials (or an injected `ENV` read through a single config object); never hardcoded
- Validate `redirect_to` targets against an allowlist
- API-only controllers carry token/JWT auth; do not blanket `skip_before_action :verify_authenticity_token` on session controllers
- Secrets never reach a client payload: server-side keys stay out of rendered JS, JSON and HTML (`javascript:` blocks, `data-*`, serializers); only keys designed as publishable are rendered, scoped to the page
- Outbound calls to partners authenticate (bearer from credentials, HMAC-signed body) and pin the host; an unauthenticated outbound call is a finding
- Error responses carry no internal detail (backtrace, SQL, class names, file paths) - the ladder in `rails-exception-handling` renders typed responses
- `render json:` under `load_defaults 8.1` no longer escapes `<`, `>`, `&` (`escape_json_responses = false`) - fine for an API body; a `render json:` body that a script tag or `data-*` attribute embeds passes `escape: true`, which restores `<>&` only. On 8.1 neither that body nor template `to_json` escapes U+2028/9 (`escape_js_separators_in_json = false`), so JSON inlined into a script tag goes through `json_escape` on either path

## Patterns

### Strong Parameters

```ruby
# Bad - mass assignment, claims arbitrary user_id
params.require(:order).permit(:total, :user_id)
Order.new(order_params)

# Good - ownership server-side
params.expect(order: [:total, tag_ids: [], items: [[:product_id, :quantity]]])
current_user.orders.new(order_params)
```

Arrays need explicit brackets; omitting them silently drops input. When the client must reference a FK (e.g., `:product_id`), validate via `policy_scope` before save.

`params.expect` (8.0+) raises 400 on type mismatch and resists hash-confusion - a scalar where a hash is expected (`?order=x`) never reaches the model. An array of hashes takes the double-bracket form: a single bracket at the root is a 400 on every real request, and nested under a key it silently drops the array.

### Authentication

`authenticate_by` (Rails 7.1+) is constant-time and defeats user-enumeration timing. `find_by(email:)&.authenticate(...)` returns fast on a missing user - that delta is observable.

```ruby
class User < ApplicationRecord
  has_secure_password
  normalizes :email, with: ->(e) { e.strip.downcase }
end

User.authenticate_by(email: params[:email], password: params[:password])
```

`bin/rails generate authentication` (8.0+) is the session scaffold for an app without Devise: `User` with `has_secure_password` and `normalizes :email_address`, a `Session` row per login referenced by a signed, `httponly` cookie, `Current.session`, and `PasswordsMailer` with a `password_reset_token` valid 15 minutes by default (configurable on 8.1: `has_secure_password reset_token: { expires_in: 1.hour }`). It is generated app code - review it like any other: the generated `rate_limit to: 10, within: 3.minutes, only: :create` on both `SessionsController` and `PasswordsController` is IP-only, so key it on IP plus `email_address` (Rate Limiting), and check for enumeration through the reset flow's response. The reset token is a signed `generates_token_for` token, so `update` needs no guess throttle; the 8.1 generator ends every session after a reset (`@user.sessions.destroy_all` in `update`) - an app generated on 8.0 lacks that line, so add it.

JWT for APIs: default to Devise + `devise-jwt` (`:jwt_authenticatable` with `Devise::JWT::RevocationStrategies::Denylist` - a `jti` claim checked against a denylist table swept past the token TTL); secret from credentials; `expiration_time` <= 1 hour. Devise earns its weight whenever the account lifecycle (registration, reset, lockout) is needed - almost every email+password API; hand-roll `authenticate_by` plus a JWT gem only for minimal token auth, and then own encode/decode, `jti` revocation and refresh. Hand-rolled verification pins the algorithm: `JWT.decode(token, key, true, algorithms: ["HS256"])` - `false` as the third argument skips the signature check, and `alg: none` must be refused.

A mounted engine (`Sidekiq::Web`, `Flipper::UI`) inherits no authentication: wrap the mount in Devise's `authenticate :user, ->(u) { u.admin? } do ... end` or a `constraints` lambda - an unguarded mount is `Authentication`, Critical.

### Authorization - Pundit

```ruby
class OrderPolicy < ApplicationPolicy
  def show?    = user.admin? || record.user_id == user.id
  def fulfill? = user.admin?
  def update?  = record.user_id == user.id

  class Scope < Scope
    def resolve
      user.admin? ? scope.all : scope.where(user_id: user.id)
    end
  end
end

class ApplicationController < ActionController::API   # ActionController::Base for server-rendered apps
  include Pundit::Authorization
  # one callback branching on action_name: `except: :index` / `only: :index` on the base class raise
  # AbstractController::ActionNotFound in every subclass without an index action once
  # raise_on_missing_callback_actions is on (true in generated dev/test since 7.1)
  after_action :verify_pundit_authorization

  rescue_from Pundit::NotAuthorizedError do
    render json: { error: "Forbidden" }, status: :forbidden
  end

  private

  def verify_pundit_authorization = action_name == "index" ? verify_policy_scoped : verify_authorized
end
```

Policies that only check `user.admin?` (no owner clause) silently lock owners out. Missing `rescue_from` returns a 500 instead of a 403 (and a full trace in development; production renders the generic error page). Relationship-based access (trainer->trainee, manager->team) extends the same shape: the member check tests the relationship, the Scope unions the related owner IDs (`scope.where(user_id: [user.id, *user.trainee_ids])`).

IDOR: lookups on user-supplied IDs go through `policy_scope(Model).find(params[:id])` (404 on foreign records) or `find` + `authorize` (403). Never bare `Model.find(params[:id])` followed by render. Response exposure is part of authorization: render through a serializer field allowlist, never `render json: @record` raw.

The same rule governs an ActionCable `subscribed` block, which is a lookup on a client-supplied identifier by another name - stream from an authorized object, never from a raw `params[:id]`. Channel actions (`receive`, custom methods) are unauthenticated RPC unless you check them individually; `subscribed` authorizes the subscription, not what the socket may then ask for. An over-broad `allowed_request_origins` (`/.*/`, an unanchored regexp, a wildcard list) or `disable_request_forgery_protection = true` is the same `Channel Authorization` pattern, risk `cross-site request forgery`; left unset, Action Cable accepts same-origin only (`allow_same_origin_as_host`, plus localhost in development), which is compliant.

When the credential *is* the link (an emailed tracking URL, a document download), use Rails' signed ids: `record.signed_id(expires_in: 7.days, purpose: :tracking)` and `Model.find_signed!(token, purpose: :tracking)` - the purpose scopes the token to one use, the expiry bounds forwarding, and the token stays replayable until then (single use needs your own nonce table). The verification is the authorization - the one legitimate exception to the rule above: call `skip_authorization` (`skip_policy_scope` on an index) after `find_signed!`, or the base class's `after_action` raises.

### SQL Injection

```ruby
# Bad
User.where("email = '#{params[:email]}'")

# Good
User.where(email: params[:email])
User.where("name LIKE ?", "%#{User.sanitize_sql_like(params[:q])}%")
```

### CSRF

Session controllers: `protect_from_forgery with: :exception` (default). API-only (`ActionController::API`) does not include `RequestForgeryProtection` (nor the session middleware it needs) - use token/JWT auth. Never globally skip the token check on session controllers.

### Rate Limiting - `rate_limit` and Rack::Attack

Built-in `rate_limit` (7.2+) is the first choice for a per-action throttle - it runs after params parsing, so a JSON body is visible to `by:`, which Rack::Attack below has to re-parse:

```ruby
class SessionsController < ApplicationController
  rate_limit to: 5, within: 20.seconds, only: :create, scope: :login,          # scope: (8.1) shares one counter with any controller using the same scope: and by:
             by: -> { "#{request.remote_ip}:#{params[:email].to_s.downcase}" }  # IP plus identifier - never IP alone
end
```

A hit raises `ActionController::TooManyRequests` (a 429; `with:` names another handler) and counts in `config.action_controller.cache_store` - the shared-store rule below applies to it too (Solid Cache or Redis, never `:memory_store`). Rack::Attack stays for what no controller sees: a middleware-level IP throttle across every path, a blocklist, and the `Fail2Ban` pattern.

```ruby
Rack::Attack.throttle("api/ip", limit: 300, period: 5.minutes) { |req| req.ip if req.path.start_with?("/api/") }

Rack::Attack.throttle("logins/email_ip", limit: 5, period: 20.seconds) do |req|
  next unless req.path == "/api/v1/login" && req.post?
  parsed = (JSON.parse(req.body.read) rescue nil)   # req.params is blind to a JSON body
  req.body&.rewind                                   # Rack 3.1 allows a nil input
  email = parsed.is_a?(Hash) ? parsed["email"].to_s.downcase : ""
  "#{req.ip}:#{email}"
end
```

Login throttles must key on IP **and** the submitted identifier field, whatever its name (`email`, `name`, `login`; a form login reads it from `req.params`) - IP-only is bypassed by credential stuffing via rotating proxies. On a JSON endpoint `req.params['email']` is nil (`Rack::Request#params` reads only the query string and form bodies), so the key collapses to `"#{ip}:"` - hence the body parse above.

Counters are only as shared as the cache behind them (`rate_limit` and Rack::Attack alike). Inside Rails, Rack::Attack defaults its store to `Rails.cache`, so the failure is subtler than "per-process": a file store does not span hosts and `:memory_store` does not span processes. Point it somewhere genuinely shared, and pass an *instance* - `Rack::Attack.cache.store = Redis` assigns the class, which responds to none of the counter methods, so every throttled request raises `Rack::Attack::MisconfiguredStoreError` (a 500 across the app, not just a lost throttle):

```ruby
Rack::Attack.cache.store = ActiveSupport::Cache::RedisCacheStore.new(url: ENV["REDIS_URL"])
```

For a token-only endpoint with no email field, key on IP plus the token's *subject* once verified, and add a `Fail2Ban`-style blocklist on repeated signature failures so enumeration costs the attacker an IP ban rather than just a 429.

### Open Redirect

Rails rejects cross-host `redirect_to` with `UnsafeRedirectError` only when `config.action_controller.raise_on_open_redirects` is true - it defaults to false and is switched on by `load_defaults 7.0`+, so a 7.2 or 8.0 app upgraded on older defaults has no protection at all; on 8.1+ the setting is `action_on_open_redirect` (`:log` by default, which still redirects; `load_defaults 7.0`+ sets `:raise`) and `raise_on_open_redirects` is deprecated. `redirect_to url, allow_other_host: true` opts back out per call site. A path-relative target (`redirect_to "orders"` - no leading `/`, resolved by the browser against the current URL) is a separate 8.1 control, `config.action_controller.action_on_path_relative_redirect` (`:raise` under `load_defaults 8.1`, `:log` otherwise - still redirects), so an allowlist entry always carries its leading `/`. Same-origin open redirects pass either way. Use a path allowlist; exact-match comparison also kills protocol-relative bypasses (`//evil.com`) that naive prefix checks miss:

```ruby
ALLOWED = %w[/dashboard /orders /profile].freeze
def safe_return_to
  ALLOWED.include?(params[:return_to]) ? params[:return_to] : "/"
end
```

Dynamic in-app targets (`/orders/42`) that no enumerable list can express: require an app-relative path - `to.match?(%r{\A/(?![/\\])[^\x00-\x20\\]*\z})` (single leading `/`; rejecting a second `/` or `\` kills the protocol-relative `//evil.com` and browser-normalized `/\evil.com` bypasses, and rejecting control and whitespace characters anywhere kills `/\t/evil.com`, which browsers strip to `//evil.com`).

### Host Authorization and Transport

```ruby
config.hosts << "app.example.com"
config.hosts << ".example.com"        # leading dot = this host and one subdomain level
```

Rails anchors both forms and tolerates a port on both: `".example.com"` becomes `/\A(?:[a-z0-9-]+\.)?example\.com(?::\d+)?\z/i` - the apex plus exactly one label, so `a.b.example.com` is rejected (a bare `"app.example.com"` matches that host only), and a Regexp is wrapped by `sanitize_regexp` into `/\A...(?::\d+)?\z/` - case-sensitive unless you add `/i` yourself. So a trailing-garbage `Host: www.example.com.evil.com` is rejected either way. The trap runs the other direction - because the anchoring is automatic, a Regexp must match the *whole* hostname (`/example\.com/` will not match `www.example.com`; write `/.*\.example\.com/`), and one left open in the middle still matches too much: `/.*example\.com/` accepts `evilexample.com`. Prefer the String form for that reason, not for anchoring.

Blocks Host header injection; mismatched requests get 403. `config.hosts.clear` disables the protection entirely - it is never the fix for a host mismatch. `config.hosts` absent from `production.rb` means every Host is accepted (Medium); take the hostname from a deploy manifest or ingress, or write `Not in evidence:` naming it, and exclude the health path (`config.host_authorization = { exclude: ->(req) { req.path == "/up" } }`) so the load balancer's probe is not 403'd.

### Secrets in Client Payloads and Outbound Authentication

```erb
<%# Bad - a server-side key rendered into the page %>
<script>window.stripeSecret = "<%= Rails.application.credentials.dig(:stripe, :secret_key) %>"</script>

<%# Good - only the publishable key, and only on the page that needs it %>
<meta name="stripe-key" content="<%= Rails.application.credentials.dig(:stripe, :publishable_key) %>">
```

```ruby
# Bad - an unauthenticated outbound call to a partner, host from user input
Faraday.get("#{params[:callback_url]}/status")

# Good - pinned host, bearer from credentials, HMAC over the body when the partner verifies one
PartnerClient.new.status(ref)   # Faraday.new(url: PARTNER_HOST) + Authorization: Bearer <credentials.partner_token>
# An outbound webhook signs the way the inbound pattern verifies: X-Signature = HMAC-SHA256(secret, raw_body);
# to let the receiver reject replays, sign "#{timestamp}.#{raw_body}" and send X-Timestamp too
```

Grep `credentials` / `ENV[` in `app/views`, `app/javascript` and serializers for the first; grep `Faraday`, `Net::HTTP`, `URI(` outside `app/clients/` for the second.

`config.force_ssl = true` in production (HTTPS redirect + HSTS + `secure` cookie flag). Disabling it for a proxy issue is solved with `config.assume_ssl`/forwarded headers, not by turning TLS enforcement off.

### Cookies and Credentials

```ruby
cookies.signed[:cart_id]                     # tamper-evident, readable
cookies.encrypted[:user_preferences]         # tamper-evident + opaque
# Flags are set on assignment - `cookies[...][key, **opts]` is a read and raises ArgumentError
cookies.permanent.encrypted[:remember_token] =
  { value: token, httponly: true, secure: true, same_site: :lax }
```

Never store access-granting tokens / IDs in unsigned `cookies[...]`; an unsigned `cookies[:user_id]` read as identity (in a controller or a cable `connect`) is `Authentication`, Critical - the client sets it. Signing/encryption is not the same as `httponly`/`secure`/`same_site` - set the flags explicitly on auth cookies.

```ruby
EDITOR=vim rails credentials:edit --environment production
Rails.application.credentials.api_key!       # raises if missing
```

A secret found hardcoded - in code or in a config file such as `storage.yml` or `database.yml` - is already leaked (git history) - moving it into credentials is half the fix; rotate it at the provider.

### Webhook Signature Verification

Verify over the **raw body** before parsing, with a constant-time compare; parse only after the signature passes.

```ruby
class WebhooksController < ActionController::API   # no session -> no CSRF token; on ActionController::Base this is the one legitimate skip_before_action :verify_authenticity_token site
  before_action :verify_signature!

  private

  def verify_signature!
    expected = OpenSSL::HMAC.hexdigest("SHA256", Rails.application.credentials.webhook_secret!, request.raw_post)
    head :unauthorized unless ActiveSupport::SecurityUtils.secure_compare(expected, request.headers["X-Signature"].to_s)
  end
end
```

Replay protection: reject when the provider's signed timestamp is older than ~5 minutes, and de-duplicate on a persisted `event_id` unique index (processing side: see `rails-http-client-patterns` Webhooks). Prefer the provider SDK's verifier (`Stripe::Webhook.construct_event`) when one exists - it does raw-body + timestamp + constant-time for you.

### Content Security Policy

```ruby
config.content_security_policy do |p|
  p.default_src :self
  p.script_src  :self          # blocks inline scripts
  p.style_src   :self, :unsafe_inline
end
config.content_security_policy_nonce_generator  = ->(req) { req.session.id.to_s }
config.content_security_policy_nonce_directives = %w[script-src]   # not style-src
```

That last line is load-bearing. Rails nonces `script-src` *and* `style-src` by default, and a browser ignores `'unsafe-inline'` in any directive that also carries a nonce - so adding the generator without narrowing the directives silently breaks every inline style the `style_src` line above was written to allow.

Existing inline scripts: migrate via nonces (`javascript_tag nonce: true`) rather than `:unsafe_inline`. Roll out with `config.content_security_policy_report_only = true` first.

## Output Format

One block per finding (reviews and audits emit several) or per pattern applied (build mode). Both modes fill every field; only two shift meaning. `Severity` in build mode rates the risk the change closes, not a current exposure. `Change` is the applied diff in build mode and the recommended remediation in review or audit mode - which is where target state lives, so no separate section is written. An audit walks a whole surface and opens with the `Posture:` line; a review opens with its first block and takes the named files, and everything in a named file is in scope, as is a parent class a named file inherits (`Api::V1::BaseController` behind a named controller). A named surface with no finding gets one line - `Clean: <surface> - <what was checked>` - and no block. One block per distinct code-level fix - findings sharing one root cause (a missing `verify_authorized`) merge into one block listing the affected actions; `IDOR` is the unscoped lookup, `Pundit` the policy or scope wiring, one block each when both are missing. An observation owned by a sibling skill (template escaping, upload validation, blob URL expiry) gets one line naming the skill and no block; a fact outside the read set gets one line, `Not in evidence: <fact> - read <file>`, and no block. Blocks run Critical first; sibling and `Not in evidence:` lines follow the blocks, then the `Clean:` lines.

```
Posture: {audit mode only, once before the blocks: the surface walked, the Critical / High count, the dominant gap - one line}

Pattern: {Strong Params | Authentication (login, token issue and storage, reset flow, unguarded mounted engine) | Pundit | CSRF | Rate Limit | Credentials (code or any config file) | SQLi | IDOR (unscoped lookup, or a raw-record render that leaks columns) | Open Redirect | Cookies | CSP | Host Auth | Transport | Webhook Signature | Channel Authorization (subscribed, actions, origins) | Secret in Client Payload | Signed ID / Holder-of-Token Link | Outbound Call Authentication | Error Response Leakage}

Severity: {Critical - exploitable now | High - exploitable with effort | Medium - hardening, including fail-closed misconfiguration (a too-narrow host regexp, a nonce directive that breaks styles) | Low - defense in depth}

Resource: {controller#actions / policy / model / channel / view / route / config file / initializer / migration - name every file a fix spans, with the actions or lines inside it}

Change: {what was applied (build) | what to apply (review, audit)}

Risk Mitigated: {mass assignment | unauthorized access | data exposure | injection | script injection (XSS via CSP gap) | cross-site request forgery | brute force | user enumeration | availability (a control that fails open or takes itself down) | secret exposure | open redirect | session hijack | header injection | MITM | unauthenticated outbound call | internal detail in error response}
```

## Avoid

- Pundit policies checking only `user.admin?` without owner access
- Login throttles keyed on IP only, or counted in `:memory_store`
- `verify_authorized` / `verify_policy_scoped` skipped per-controller without rationale
