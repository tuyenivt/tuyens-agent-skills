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
- Setting up Rails credentials
- Designing role-based access policies

## Rules

- Never `params.permit!` or `params.to_unsafe_h`
- Never permit ownership FKs (`:user_id`, `:account_id`, `:tenant_id`) - assign server-side
- Every action reading/mutating a resource calls `authorize`; every index uses `policy_scope`
- `after_action :verify_authorized` / `:verify_policy_scoped` in `ApplicationController`
- Parameterized queries only - never string interpolation in `where`
- Secrets in Rails credentials; never hardcoded
- Never `html_safe` / `raw` on user input

## Patterns

### Strong Parameters

```ruby
# Bad - mass assignment
params.permit!

# Good
params.require(:order).permit(:total, :status, metadata: {})
```

Arrays need explicit shape - omitting brackets silently drops input:

```ruby
# Array of scalars: tag_ids: []
# Array of nested params: items: [[:product_id, :quantity]]
params.require(:order).permit(:total, tag_ids: [], items: [[:product_id, :quantity]])
```

### `params.expect` (Rails 8 / 7.2 backport)

Stricter than `require.permit` - raises 400 on type mismatch, resists hash-confusion:

```ruby
params.expect(order: [:total, :status, items: [[:product_id, :quantity]]])
```

Prefer on new code.

### IDOR via Nested Params

```ruby
# Bad - user can claim any user_id
params.require(:order).permit(:total, :user_id)
order = Order.new(order_params)

# Good - ownership server-side
params.require(:order).permit(:total)
order = current_user.orders.new(order_params)
```

Same for `:account_id`, `:tenant_id`, `:organization_id`. If the client must reference one (e.g., `:product_id` they're buying), validate via `policy_scope` before save.

### Authentication

**Rails 7.2+ `authenticate_by`** - constant-time, defeats user-enumeration timing:

```ruby
class User < ApplicationRecord
  has_secure_password
  normalizes :email, with: ->(e) { e.strip.downcase }
end

user = User.authenticate_by(email: params[:email], password: params[:password])
```

`User.find_by(email: ...)&.authenticate(...)` leaks existence via timing (fast when user missing).

**Devise + JWT** (API):

```ruby
class User < ApplicationRecord
  devise :database_authenticatable, :registerable,
         :jwt_authenticatable, jwt_revocation_strategy: JwtDenylist
end

# config/initializers/devise.rb
Devise.setup do |config|
  config.jwt do |jwt|
    jwt.secret = Rails.application.credentials.devise_jwt_secret_key!
    jwt.expiration_time = 1.hour.to_i
  end
end
```

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

class OrdersController < ApplicationController
  def show
    @order = Order.find(params[:id])
    authorize @order
    render json: OrderSerializer.new(@order)
  end

  def index
    @orders = policy_scope(Order).page(params[:page])
    render json: OrderSerializer.new(@orders)
  end
end
```

### XSS Prevention

```ruby
<%= user.name %>                                  # auto-escaped
<%= sanitize user.bio, tags: %w[p br strong em] %> # allow specific tags

# Bad: <%= raw user.bio %> or <%= user.bio.html_safe %>
```

For intentional HTML (markdown, rich-text), use `sanitize` with an explicit allowlist - never `raw` / `html_safe` / Slim `==` / HAML `!=`. The allowlist is the trust boundary, not the renderer config.

CSP:

```ruby
config.content_security_policy do |p|
  p.default_src :self
  p.script_src  :self
  p.style_src   :self, :unsafe_inline
end
```

### SQL Injection

```ruby
# Bad - SQL injection
User.where("email = '#{params[:email]}'")

# Good
User.where(email: params[:email])
User.where("email = ?", params[:email])
User.where("name LIKE ?", "%#{User.sanitize_sql_like(params[:q])}%")
```

### CSRF

```ruby
# Default for session-based controllers
protect_from_forgery with: :exception

# API-only: skip - use token auth instead
class Api::BaseController < ActionController::API
end
```

### Rate Limiting - Rack::Attack

```ruby
Rack::Attack.throttle("api/ip", limit: 300, period: 5.minutes) { |req| req.ip if req.path.start_with?("/api/") }

Rack::Attack.throttle("logins/ip", limit: 5, period: 20.seconds) do |req|
  req.ip if req.path == "/api/v1/login" && req.post?
end

Rack::Attack.blocklist("block bad IPs") do |req|
  Rack::Attack::Fail2Ban.filter("bad-#{req.ip}", maxretry: 3, findtime: 10.minutes, bantime: 1.hour) do
    req.path == "/api/v1/login" && req.post? && req.env["rack.attack.match_data"]
  end
end
```

### Open Redirect

```ruby
# Rails 7+ default rejects cross-host (raises UnsafeRedirectError)
redirect_to params[:return_to]

# Explicit allowlist
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

Never trust client-reported `content_type` for security decisions on executable formats - `Marcel::MimeType.for(io)` re-detects from magic bytes. Serve user content from a separate domain or with `Content-Disposition: attachment`.

### Host Authorization

```ruby
config.hosts << "app.example.com"
config.hosts << /.*\.example\.com/
```

Blocks Host header injection - requests with mismatched Host get 403.

### Signed / Encrypted Cookies

```ruby
cookies.signed[:cart_id]                       # tamper-evident, readable - non-sensitive IDs
cookies.encrypted[:user_preferences]           # tamper-evident + opaque - anything sensitive
cookies.permanent.encrypted[:remember_token]   # long-lived
```

Never use `cookies[:foo]=` for security-sensitive values.

### Rails Credentials

```ruby
EDITOR=vim rails credentials:edit
EDITOR=vim rails credentials:edit --environment production

Rails.application.credentials.api_key!         # raises if missing
Rails.application.credentials.dig(:aws, :secret_key)
```

## Output Format

```
Pattern: {Strong Params | Pundit | CSRF | Rate Limit | Credentials | XSS | SQLi | IDOR | Open Redirect | Upload | Cookies}
Resource: {controller / model}
Change: {what was applied}
Risk Mitigated: {mass assignment | unauthorized access | injection | brute force | secret exposure | open redirect}
```

## Avoid

- Global `skip_before_action :verify_authenticity_token`
- String interpolation in `where`
- `params.permit!` / `to_unsafe_h`
- Hardcoded secrets - use credentials
- Missing `authorize` / `policy_scope` calls
- `html_safe` / `raw` on user input
- Pundit policies only checking `user.admin?` without owner access
- Missing `rescue_from Pundit::NotAuthorizedError` (stack trace leaks)
- Permitting ownership FKs in strong params
- Unvalidated `redirect_to params[...]`
- Trusting client-reported `content_type` on uploads
- Tokens in unsigned `cookies[...]`
