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
- Secrets via Rails credentials; never hardcoded
- Validate `redirect_to` targets against an allowlist
- API-only controllers carry token/JWT auth; do not blanket `skip_before_action :verify_authenticity_token` on session controllers

## Patterns

### Strong Parameters

```ruby
# Bad - mass assignment, claims arbitrary user_id
params.require(:order).permit(:total, :user_id)
Order.new(order_params)

# Good - ownership server-side
params.require(:order).permit(:total, tag_ids: [], items: [[:product_id, :quantity]])
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

Policies that only check `user.admin?` (no owner clause) silently lock owners out. Missing `rescue_from` leaks stack traces on denial. Relationship-based access (trainer->trainee, manager->team) extends the same shape: the member check tests the relationship, the Scope unions the related owner IDs (`scope.where(user_id: [user.id, *user.trainee_ids])`).

IDOR: lookups on user-supplied IDs go through `policy_scope(Model).find(params[:id])` (404 on foreign records) or `find` + `authorize` (403). Never bare `Model.find(params[:id])` followed by render. Response exposure is part of authorization: render through a serializer field allowlist, never `render json: @record` raw.

### SQL Injection

```ruby
# Bad
User.where("email = '#{params[:email]}'")

# Good
User.where(email: params[:email])
User.where("name LIKE ?", "%#{User.sanitize_sql_like(params[:q])}%")
```

### CSRF

Session controllers: `protect_from_forgery with: :exception` (default). API-only (`ActionController::API`) has no CSRF middleware - use token/JWT auth. Never globally skip the token check on session controllers.

### Rate Limiting - Rack::Attack

```ruby
Rack::Attack.throttle("api/ip", limit: 300, period: 5.minutes) { |req| req.ip if req.path.start_with?("/api/") }

Rack::Attack.throttle("logins/email_ip", limit: 5, period: 20.seconds) do |req|
  next unless req.path == "/api/v1/login" && req.post?
  "#{req.ip}:#{req.params['email'].to_s.downcase}"
end
```

Login throttles must key on IP **and** submitted email - IP-only is bypassed by credential stuffing via rotating proxies. Back the counters with a shared store (`Rack::Attack.cache.store = Redis`) - the in-memory default resets per process and undercounts under multi-process Puma.

### Open Redirect

Rails 7+ rejects cross-host `redirect_to` (`UnsafeRedirectError`), but same-origin open redirects still pass. Use a path allowlist; exact-match comparison also kills protocol-relative bypasses (`//evil.com`) that naive prefix checks miss:

```ruby
ALLOWED = %w[/dashboard /orders /profile].freeze
def safe_return_to
  ALLOWED.include?(params[:return_to]) ? params[:return_to] : "/"
end
```

### Host Authorization and Transport

```ruby
config.hosts << "app.example.com"
config.hosts << /.*\.example\.com/
```

Blocks Host header injection; mismatched requests get 403. `config.hosts.clear` disables the protection entirely - it is never the fix for a host mismatch.

`config.force_ssl = true` in production (HTTPS redirect + HSTS + `secure` cookie flag). Disabling it for a proxy issue is solved with `config.assume_ssl`/forwarded headers, not by turning TLS enforcement off.

### Cookies and Credentials

```ruby
cookies.signed[:cart_id]                     # tamper-evident, readable
cookies.encrypted[:user_preferences]         # tamper-evident + opaque
cookies.permanent.encrypted[:remember_token, httponly: true, secure: true, same_site: :lax]
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
config.content_security_policy_nonce_generator = ->(req) { req.session.id.to_s }
```

Existing inline scripts: migrate via nonces (`javascript_tag nonce: true`) rather than `:unsafe_inline`. Roll out with `config.content_security_policy_report_only = true` first.

## Output Format

One block per finding (reviews and audits emit several):

```
Pattern: {Strong Params | Authentication | Pundit | CSRF | Rate Limit | Credentials | SQLi | IDOR | Open Redirect | Cookies | CSP | Host Auth | Transport | Webhook Signature}
Severity: {Critical - exploitable now | High - exploitable with effort | Medium - hardening | Low - defense in depth}
Resource: {controller / model / config file}
Change: {what was applied}
Risk Mitigated: {mass assignment | unauthorized access | data exposure | injection | brute force | secret exposure | open redirect | session hijack | header injection | MITM}
```

## Avoid

- Pundit policies checking only `user.admin?` without owner access
- Login throttles keyed on IP only
- Same-origin open redirects not covered by `UnsafeRedirectError`
- `verify_authorized` / `verify_policy_scoped` skipped per-controller without rationale
- Storing access tokens in unsigned cookies
- Blanket `skip_before_action :verify_authenticity_token` on session controllers
