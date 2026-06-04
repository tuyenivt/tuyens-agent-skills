---
name: rails-security-patterns
description: Rails security: strong params, Devise/JWT, Pundit, CSRF/XSS, SQL injection, Rack::Attack, credentials, IDOR, open redirect, file upload.
metadata:
  category: backend
  tags: [ruby, rails, security, authentication, authorization]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding auth (Devise/JWT/`authenticate_by`) or authz (Pundit)
- Reviewing strong params for mass assignment / IDOR
- Implementing rate limiting (`Rack::Attack`)
- Auditing templates / API responses for XSS / injection
- Setting up Rails credentials, signed cookies, host authorization

## Rules

- Never `params.permit!` / `params.to_unsafe_h`; never permit ownership FKs (`:user_id`, `:account_id`, `:tenant_id`)
- Every resource action calls `authorize`; every index uses `policy_scope`; enforce with `after_action :verify_authorized` / `:verify_policy_scoped`
- Parameterized queries only - never string interpolation in `where`
- Never `html_safe` / `raw` on user input - `sanitize` with an explicit tag allowlist
- Secrets via Rails credentials; never hardcoded
- Validate `redirect_to` targets against an allowlist
- Re-detect upload MIME via magic bytes; never trust client `content_type`

## Patterns

### Strong Parameters

```ruby
# Bad - mass assignment, claims arbitrary user_id
params.require(:order).permit(:total, :user_id)
order = Order.new(order_params)

# Good - ownership server-side, explicit shape
params.require(:order).permit(:total, tag_ids: [], items: [[:product_id, :quantity]])
order = current_user.orders.new(order_params)
```

Arrays need explicit brackets; omitting them silently drops input. Same FK rule for `:account_id`, `:tenant_id`. When the client must reference one (e.g., `:product_id` to buy), validate via `policy_scope` before save.

`params.expect` (Rails 7.2 backport) is stricter - raises 400 on type mismatch, resists hash-confusion. Prefer on new code:

```ruby
params.expect(order: [:total, :status, items: [[:product_id, :quantity]]])
```

### Authentication

`authenticate_by` (Rails 7.2+) is constant-time and defeats user-enumeration timing. `find_by(email:)&.authenticate(...)` returns fast when the user is missing - that delta is observable.

```ruby
class User < ApplicationRecord
  has_secure_password
  normalizes :email, with: ->(e) { e.strip.downcase }
end

user = User.authenticate_by(email: params[:email], password: params[:password])
```

Devise + JWT (API): use `:jwt_authenticatable` with a revocation strategy (`JwtDenylist`); load `jwt.secret` from credentials; keep `expiration_time` short (≤ 1 hour).

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

class ApplicationController < ActionController::Base
  include Pundit::Authorization
  after_action :verify_authorized,     except: :index
  after_action :verify_policy_scoped,  only:   :index

  rescue_from Pundit::NotAuthorizedError do
    render json: { error: "Forbidden" }, status: :forbidden
  end
end
```

Policies that only check `user.admin?` (without owner access) silently lock owners out. The `rescue_from` is mandatory - without it, denials leak stack traces.

### XSS Prevention

```erb
<%= user.bio %>                                   <%# auto-escaped %>
<%= sanitize user.bio, tags: %w[p br strong em] %> <%# allowlisted HTML %>
<%= raw user.bio %>  <%# DANGEROUS - never on user input %>
```

For markdown / rich-text, pass rendered HTML through `sanitize` even if the renderer claims safe-mode. The allowlist is the trust boundary, not the renderer config.

CSP (set `script_src :self` to block inline scripts):

```ruby
config.content_security_policy do |p|
  p.default_src :self
  p.script_src  :self
  p.style_src   :self, :unsafe_inline
end
```

### SQL Injection

```ruby
# Bad
User.where("email = '#{params[:email]}'")

# Good
User.where(email: params[:email])
User.where("name LIKE ?", "%#{User.sanitize_sql_like(params[:q])}%")
```

### CSRF

Session controllers: `protect_from_forgery with: :exception` (default). API-only (`ActionController::API`) skips CSRF - use token/JWT auth instead. Never globally `skip_before_action :verify_authenticity_token` on a session controller.

### Rate Limiting - Rack::Attack

```ruby
Rack::Attack.throttle("api/ip", limit: 300, period: 5.minutes) { |req| req.ip if req.path.start_with?("/api/") }

Rack::Attack.throttle("logins/ip", limit: 5, period: 20.seconds) do |req|
  req.ip if req.path == "/api/v1/login" && req.post?
end
```

Login throttles must key on IP **and** submitted email/username - IP-only is bypassed by credential-stuffing rotating proxies.

### Open Redirect

Rails 7+ rejects cross-host `redirect_to` by default (`UnsafeRedirectError`), but same-origin open redirects still leak through. Use a path allowlist for user-supplied destinations:

```ruby
ALLOWED = %w[/dashboard /orders /profile].freeze
def safe_return_to
  ALLOWED.include?(params[:return_to]) ? params[:return_to] : "/"
end
```

### File Upload

```ruby
class User < ApplicationRecord
  has_one_attached :avatar
  validate :acceptable_avatar

  private

  def acceptable_avatar
    return unless avatar.attached?
    errors.add(:avatar, "must be under 5MB") if avatar.blob.byte_size > 5.megabytes
    errors.add(:avatar, "must be image") unless %w[image/jpeg image/png image/webp].include?(avatar.blob.content_type)
  end
end
```

`Marcel::MimeType.for(io)` re-detects content type from magic bytes - use it for executable formats. Serve user content from a separate domain or with `Content-Disposition: attachment`.

### Host Authorization

```ruby
config.hosts << "app.example.com"
config.hosts << /.*\.example\.com/
```

Blocks Host header injection; mismatched requests get 403.

### Cookies and Credentials

```ruby
cookies.signed[:cart_id]                     # tamper-evident, readable
cookies.encrypted[:user_preferences]         # tamper-evident + opaque
cookies.permanent.encrypted[:remember_token]
```

Never store tokens / IDs that grant access in unsigned `cookies[...]`.

```ruby
EDITOR=vim rails credentials:edit --environment production
Rails.application.credentials.api_key!       # raises if missing
```

## Output Format

```
Pattern: {Strong Params | Pundit | CSRF | Rate Limit | Credentials | XSS | SQLi | IDOR | Open Redirect | Upload | Cookies}
Resource: {controller / model}
Change: {what was applied}
Risk Mitigated: {mass assignment | unauthorized access | injection | brute force | secret exposure | open redirect}
```

## Avoid

- Pundit policies that only check `user.admin?` without owner access
- Login throttles keyed on IP only (bypassed by credential stuffing)
- Same-origin open redirects not covered by `UnsafeRedirectError`
- Markdown / rich-text rendered with `raw` because the renderer "is safe"
- `verify_authorized` / `verify_policy_scoped` skipped per-controller without rationale
