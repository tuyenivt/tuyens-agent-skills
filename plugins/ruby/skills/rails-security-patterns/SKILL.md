---
name: rails-security-patterns
description: Rails security - strong params, Devise/JWT, Pundit, CSRF, SQLi, IDOR, open redirect, Rack::Attack, credentials, signed cookies, host auth.
metadata:
  category: backend
  tags: [ruby, rails, security, authentication, authorization]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

For template-layer XSS (`sanitize` allowlists, engine escape operators), see `rails-view-templates`. For upload validation / magic-byte sniffing, see `rails-active-storage-patterns`.

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

## Patterns

### Strong Parameters

```ruby
# Bad - mass assignment, claims arbitrary user_id
params.require(:order).permit(:total, :user_id)
Order.new(order_params)

# Good - ownership server-side
params.require(:order).permit(:total, tag_ids: [], items: [:product_id, :quantity])
current_user.orders.new(order_params)
```

Arrays need explicit brackets; omitting them silently drops input. When the client must reference a FK (e.g., `:product_id`), validate via `policy_scope` before save.

`params.expect` (Rails 8.0+) raises 400 on type mismatch and resists hash-confusion; prefer on new code:

```ruby
params.expect(order: [:total, :status, items: [[:product_id, :quantity]]])
```

### Authentication

`authenticate_by` (Rails 7.1+) is constant-time and defeats user-enumeration timing. `find_by(email:)&.authenticate(...)` returns fast on a missing user - that delta is observable.

```ruby
class User < ApplicationRecord
  has_secure_password
  normalizes :email, with: ->(e) { e.strip.downcase }
end

User.authenticate_by(email: params[:email], password: params[:password])
```

JWT for APIs: default to Devise + `:jwt_authenticatable` with a revocation strategy (`JwtDenylist` - a `jti` claim checked against a denylist table, rows expired past token TTL); secret from credentials; `expiration_time` <= 1 hour. Devise earns its weight whenever you need the account lifecycle (registration, password reset, lockout) - i.e. almost every email+password API, greenfield included. Hand-roll `authenticate_by` (above) + a JWT gem only for minimal token auth without that lifecycle - then you own encode/decode, `jti` revocation, and refresh yourself.

### Authorization - Pundit

```ruby
class OrderPolicy < ApplicationPolicy
  def show?    = user.admin? || record.user_id == user.id
  def fulfill? = user.admin?
  def update?  = record.user_id == user.id && record.pending?

  class Scope < Scope
    def resolve
      user.admin? ? scope.all : scope.where(user_id: user.id)
    end
  end
end

class ApplicationController < ActionController::API   # ActionController::Base for server-rendered apps
  include Pundit::Authorization
  after_action :verify_authorized,    except: :index  # index authorizes via policy_scope instead
  after_action :verify_policy_scoped, only:   :index

  rescue_from Pundit::NotAuthorizedError do
    render json: { error: "Forbidden" }, status: :forbidden
  end
end
```

Policies that only check `user.admin?` (no owner clause) silently lock owners out. Missing `rescue_from` returns a 500 instead of a 403 (and a full trace in development; production renders the generic error page). Relationship-based access (trainer->trainee, manager->team) extends the same shape: the member check tests the relationship, the Scope unions the related owner IDs (`scope.where(user_id: [user.id, *user.trainee_ids])`).

IDOR: lookups on user-supplied IDs go through `policy_scope(Model).find(params[:id])` (404 on foreign records) or `find` + `authorize` (403). Never bare `Model.find(params[:id])` followed by render. Response exposure is part of authorization: render through a serializer field allowlist, never `render json: @record` raw.

The same rule governs an ActionCable `subscribed` block, which is a lookup on a client-supplied identifier by another name - stream from an authorized object, never from a raw `params[:id]`. Channel actions (`receive`, custom methods) are unauthenticated RPC unless you check them individually; `subscribed` authorizes the subscription, not what the socket may then ask for.

When the credential *is* the link - an emailed tracking URL, a document download, any anonymous holder-of-token access - use Rails' own signed ids rather than inventing a scheme: `record.signed_id(expires_in: 7.days, purpose: :tracking)` and `Model.find_signed!(token, purpose: :tracking)`. The purpose scopes the token to one use case (a `:tracking` token is refused by `find_signed!` for any other purpose), the expiry bounds forwarding, and the signature makes ids unguessable without a lookup table; the token stays replayable until it expires - single use needs your own nonce table. Authorization for such a request is the token verification itself - there is no `current_user` to `authorize` against, and that is the one legitimate exception to the rule above.

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

### Rate Limiting - Rack::Attack

```ruby
Rack::Attack.throttle("api/ip", limit: 300, period: 5.minutes) { |req| req.ip if req.path.start_with?("/api/") }

Rack::Attack.throttle("logins/email_ip", limit: 5, period: 20.seconds) do |req|
  next unless req.path == "/api/v1/login" && req.post?
  parsed = (JSON.parse(req.body.read) rescue nil)   # req.params is blind to a JSON body
  req.body.rewind
  email = parsed.is_a?(Hash) ? parsed["email"].to_s.downcase : ""
  "#{req.ip}:#{email}"
end
```

Login throttles must key on IP **and** submitted email - IP-only is bypassed by credential stuffing via rotating proxies. The body parse above is not optional on a JSON endpoint: `Rack::Request#params` merges query string and form-encoded body only, so with `req.params['email']` the discriminator silently collapses to `"#{ip}:"` and you are back to the IP-only throttle this rule exists to prevent.

Counters are only as shared as the cache behind them. Inside Rails, Rack::Attack defaults its store to `Rails.cache`, so the failure is subtler than "per-process": a file store does not span hosts and `:memory_store` does not span processes. Point it somewhere genuinely shared, and pass an *instance* - `Rack::Attack.cache.store = Redis` assigns the class, which `StoreProxy` does not recognise, and the first request raises `NoMethodError` and takes throttling down with it:

```ruby
Rack::Attack.cache.store = ActiveSupport::Cache::RedisCacheStore.new(url: ENV["REDIS_URL"])
```

For a token-only endpoint with no email field, key on IP plus the token's *subject* once verified, and add a `Fail2Ban`-style blocklist on repeated signature failures so enumeration costs the attacker an IP ban rather than just a 429.

### Open Redirect

Rails rejects cross-host `redirect_to` with `UnsafeRedirectError` only when `config.action_controller.raise_on_open_redirects` is true - it defaults to false and is switched on by `load_defaults 7.0`+, so a 7.2 or 8.0 app upgraded on older defaults has no protection at all. `redirect_to url, allow_other_host: true` opts back out per call site. Same-origin open redirects pass either way. Use a path allowlist; exact-match comparison also kills protocol-relative bypasses (`//evil.com`) that naive prefix checks miss:

```ruby
ALLOWED = %w[/dashboard /orders /profile].freeze
def safe_return_to
  ALLOWED.include?(params[:return_to]) ? params[:return_to] : "/"
end
```

Dynamic in-app targets (`/orders/42`) that no enumerable list can express: require an app-relative path - `to.match?(%r{\A/[^/\\]})` (single leading `/`; rejecting a second `/` or `\` kills the protocol-relative `//evil.com` and browser-normalized `/\evil.com` bypasses).

### Host Authorization and Transport

```ruby
config.hosts << "app.example.com"
config.hosts << ".example.com"        # leading dot = this host and its subdomains
```

Rails anchors both forms and tolerates a port on both: `".example.com"` becomes `/\A(.+\.)?example\.com(?::\d+)?\z/i` (a bare `"app.example.com"` matches that host only), and a Regexp is wrapped by `sanitize_regexp` into `/\A...(?::\d+)?\z/` - case-sensitive unless you add `/i` yourself. So a trailing-garbage `Host: www.example.com.evil.com` is rejected either way. The trap runs the other direction - because the anchoring is automatic, a Regexp must match the *whole* hostname (`/example\.com/` will not match `www.example.com`; write `/.*\.example\.com/`), and one left open in the middle still matches too much: `/.*example\.com/` accepts `evilexample.com`. Prefer the String form for that reason, not for anchoring.

Blocks Host header injection; mismatched requests get 403. `config.hosts.clear` disables the protection entirely - it is never the fix for a host mismatch.

`config.force_ssl = true` in production (HTTPS redirect + HSTS + `secure` cookie flag). Disabling it for a proxy issue is solved with `config.assume_ssl`/forwarded headers, not by turning TLS enforcement off.

### Cookies and Credentials

```ruby
cookies.signed[:cart_id]                     # tamper-evident, readable
cookies.encrypted[:user_preferences]         # tamper-evident + opaque
# Flags are set on assignment - `cookies[...][key, **opts]` is a read and raises ArgumentError
cookies.permanent.encrypted[:remember_token] =
  { value: token, httponly: true, secure: true, same_site: :lax }
```

Never store access-granting tokens / IDs in unsigned `cookies[...]`. Signing/encryption is not the same as `httponly`/`secure`/`same_site` - set the flags explicitly on auth cookies.

```ruby
EDITOR=vim rails credentials:edit --environment production
Rails.application.credentials.api_key!       # raises if missing
```

A secret found hardcoded is already leaked (git history) - moving it into credentials is half the fix; rotate it at the provider.

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

One block per finding (reviews and audits emit several) or per pattern applied (build mode). Both modes fill every field; only two shift meaning. `Severity` in build mode rates the risk the change closes, not a current exposure. `Change` is the applied diff in build mode and the recommended remediation in review or audit mode - which is where target state lives, so no separate section is written. An audit walks a whole surface and opens with the `Posture:` line; a review takes the named files, and everything in a named file is in scope. A named surface with no finding gets one line - `Clean: <surface> - <what was checked>` - and no block. One block per distinct code-level fix - findings sharing one root cause (a missing `verify_authorized`) merge into one block listing the affected actions; `IDOR` is the unscoped lookup, `Pundit` the policy or scope wiring, one block each when both are missing. An observation owned by a sibling skill (template escaping, upload validation) gets one line naming the skill and no block; a fact outside the read set is `not in evidence` plus the file.

```
Posture: {one line, audit mode only, once before the blocks}

Pattern: {Strong Params | Authentication | Pundit | CSRF | Rate Limit | Credentials | SQLi | IDOR | Open Redirect | Cookies | CSP | Host Auth | Transport | Webhook Signature | Channel Authorization | Secret in Client Payload | Signed URL / Object Storage | Outbound Call Authentication | Error Response Leakage}

Severity: {Critical - exploitable now | High - exploitable with effort | Medium - hardening, including fail-closed misconfiguration (a too-narrow host regexp, a nonce directive that breaks styles) | Low - defense in depth}

Resource: {controller#actions / policy / model / channel / view / route / config file / initializer / migration - name every file a fix spans, with the actions or lines inside it}

Change: {what was applied (build) | what to apply (review, audit)}

Risk Mitigated: {mass assignment | unauthorized access | data exposure | injection | script injection (XSS via CSP gap) | cross-site request forgery | brute force | user enumeration | availability (a control that fails open or takes itself down) | secret exposure | open redirect | session hijack | header injection | MITM | unauthenticated outbound call | internal detail in error response}
```

## Avoid

- Pundit policies checking only `user.admin?` without owner access
- Login throttles keyed on IP only
- Same-origin open redirects not covered by `UnsafeRedirectError`
- `verify_authorized` / `verify_policy_scoped` skipped per-controller without rationale
- Storing access tokens in unsigned cookies
- Blanket `skip_before_action :verify_authenticity_token` on session controllers
