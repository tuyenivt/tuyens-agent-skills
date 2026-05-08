---
name: rails-security-patterns
description: Rails security hardening patterns covering strong parameters, Devise/JWT authentication, Pundit authorization, CSRF/XSS prevention, SQL injection guards, Rack::Attack rate limiting, and credentials management.
metadata:
  category: backend
  tags: [ruby, rails, security, authentication, authorization]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding authentication (Devise/JWT) or authorization (Pundit) to endpoints
- Reviewing controller params for mass assignment safety
- Implementing rate limiting for public or login endpoints
- Auditing templates or API responses for XSS/injection risks
- Setting up Rails credentials for secrets management
- Designing role-based access policies (admin, owner, public)

## Rules

- Never use `params.permit!` or `params.to_unsafe_h` - always whitelist attributes explicitly
- Never permit `:id` in strong params - attackers can change record ownership
- Every controller action that reads or mutates a resource must call `authorize`
- Every index/list action must use `policy_scope` to filter records by user permissions
- Use `after_action :verify_authorized` and `after_action :verify_policy_scoped` in ApplicationController
- Use parameterized queries for all user input - never string interpolation in `where`
- Store all secrets in Rails credentials - never hardcode in source or config files
- Never use `html_safe` or `raw` on user-provided content

## Patterns

### Strong Parameters

Bad - permits everything (mass assignment vulnerability):

```ruby
def order_params
  params.permit!
end
```

Good - explicit whitelist:

```ruby
class OrdersController < ApplicationController
  private

  def order_params
    params.require(:order).permit(:total, :status, :customer_id, metadata: {})
  end
end
```

For arrays of scalars and arrays of nested attributes, use the explicit array syntax - omitting the brackets silently drops the input:

```ruby
# Array of scalars: tag_ids: []
# Array of nested params: items: [[:product_id, :quantity]]
params.require(:order).permit(:total, tag_ids: [], items: [[:product_id, :quantity]])
```

### `params.expect` (Rails 8 / 7.2 backport)

Rails 8 introduces `params.expect` as a stricter replacement for `params.require(...).permit(...)`. It raises `ActionController::ParameterMissing` on type mismatches (e.g., the client sends `order=foo` instead of `order={...}`) and resists hash-confusion attacks where a string is sent where an object is expected:

```ruby
# Before
params.require(:order).permit(:total, :status, items: [[:product_id, :quantity]])

# After (Rails 8+, available via gem on 7.2)
params.expect(order: [:total, :status, items: [[:product_id, :quantity]]])
```

Prefer `expect` on new code; it returns 400 instead of letting a malformed nested array sneak through as `nil`.

### IDOR via Nested Params

Bad - permitting an FK that the user can spoof:

```ruby
def order_params
  params.require(:order).permit(:total, :status, :user_id) # user can claim any user_id
end

def create
  order = Order.new(order_params)
  order.save!
end
```

Good - never trust client-supplied ownership FKs; assign from session:

```ruby
def order_params
  params.require(:order).permit(:total, :status) # no :user_id
end

def create
  order = current_user.orders.new(order_params) # ownership enforced server-side
  order.save!
end
```

The same applies to `:account_id`, `:tenant_id`, `:organization_id` - any column that decides who owns the record. If the client must reference one (e.g., a `:product_id` they're buying), validate it against `policy_scope` before saving.

### Authentication - Built-in `authenticate_by`

For projects that don't need Devise's full feature set, Rails 7.2+ ships timing-safe authentication via `authenticate_by`. It compares the password digest in constant time, defeating user-enumeration timing attacks that naive `find_by(email: ...)` then `authenticate(password)` exposes:

```ruby
class User < ApplicationRecord
  has_secure_password
  normalizes :email, with: ->(e) { e.strip.downcase }
end

# Constant-time auth - same duration whether email exists or not
user = User.authenticate_by(email: params[:email], password: params[:password])
```

Bad - leaks user existence via timing:

```ruby
user = User.find_by(email: params[:email]) # fast when user missing
user&.authenticate(params[:password])       # slow only when user found
```

### Authentication - Devise + JWT

```ruby
# Gemfile
gem "devise"
gem "devise-jwt"

# API-only JWT setup
class User < ApplicationRecord
  devise :database_authenticatable, :registerable,
         :jwt_authenticatable, jwt_revocation_strategy: JwtDenylist
end

# config/initializers/devise.rb
config.jwt do |jwt|
  jwt.secret = Rails.application.credentials.devise_jwt_secret_key!
  jwt.dispatch_requests = [["POST", %r{^/api/v1/login$}]]
  jwt.revocation_requests = [["DELETE", %r{^/api/v1/logout$}]]
  jwt.expiration_time = 1.hour.to_i
end
```

### Authorization - Pundit

Bad - no authorization check:

```ruby
class OrdersController < ApplicationController
  def show
    @order = Order.find(params[:id])
    render json: @order # anyone can view any order
  end
end
```

Good - Pundit policy with role-based access:

```ruby
# app/policies/order_policy.rb
class OrderPolicy < ApplicationPolicy
  def show?
    user.admin? || record.user_id == user.id
  end

  def fulfill?
    user.admin?
  end

  def update?
    record.user_id == user.id && record.pending?
  end

  class Scope < Scope
    def resolve
      if user.admin?
        scope.all
      else
        scope.where(user_id: user.id)
      end
    end
  end
end

# Controller with authorization
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

  def fulfill
    @order = Order.find(params[:id])
    authorize @order
    result = FulfillOrder.new(order: @order).call
    if result.success?
      render json: OrderSerializer.new(result.value)
    else
      render json: { errors: result.errors }, status: :unprocessable_entity
    end
  end
end

# ApplicationController enforcement
class ApplicationController < ActionController::Base
  include Pundit::Authorization
  after_action :verify_authorized, except: :index
  after_action :verify_policy_scoped, only: :index

  rescue_from Pundit::NotAuthorizedError do |_exception|
    render json: { error: "Forbidden" }, status: :forbidden
  end
end
```

### CSRF Protection

```ruby
# Default: enabled for all non-GET requests
class ApplicationController < ActionController::Base
  protect_from_forgery with: :exception
end

# API-only: skip CSRF (use token auth instead)
class Api::BaseController < ActionController::API
  # No CSRF needed - stateless token auth
end
```

### XSS Prevention

Bad - rendering user content without escaping:

```ruby
<%= raw user.bio %>
<%= user.bio.html_safe %>
```

Good - auto-escaping (default) and sanitize for allowed HTML:

```ruby
<%= user.name %>  # auto-escaped by Rails
<%= sanitize user.bio, tags: %w[p br strong em] %>

# Content Security Policy
# config/initializers/content_security_policy.rb
Rails.application.configure do
  config.content_security_policy do |policy|
    policy.default_src :self
    policy.script_src  :self
    policy.style_src   :self, :unsafe_inline
  end
end
```

### SQL Injection Prevention

Bad - string interpolation in queries:

```ruby
User.where("email = '#{params[:email]}'") # SQL INJECTION
```

Good - parameterized queries:

```ruby
User.where("email = ?", params[:email])
User.where(email: params[:email])

# Sanitize for LIKE patterns
User.where("name LIKE ?", "%#{User.sanitize_sql_like(params[:q])}%")
```

### Rate Limiting - Rack::Attack

```ruby
# Gemfile
gem "rack-attack"

# config/initializers/rack_attack.rb
Rack::Attack.throttle("api/ip", limit: 300, period: 5.minutes) do |req|
  req.ip if req.path.start_with?("/api/")
end

Rack::Attack.throttle("logins/ip", limit: 5, period: 20.seconds) do |req|
  req.ip if req.path == "/api/v1/login" && req.post?
end

# Block repeated auth failures
Rack::Attack.blocklist("block bad IPs") do |req|
  Rack::Attack::Fail2Ban.filter("bad-#{req.ip}", maxretry: 3, findtime: 10.minutes, bantime: 1.hour) do
    req.path == "/api/v1/login" && req.post? && req.env["rack.attack.match_data"]
  end
end
```

### Open Redirect Prevention

Bad - user-supplied redirect target (phishing vector):

```ruby
redirect_to params[:return_to] # attacker sends ?return_to=https://evil.com
```

Good - validate against an allowlist or use `redirect_to ... allow_other_host: false` (default since Rails 7):

```ruby
# Rails 7+ default rejects cross-host redirects
redirect_to params[:return_to] # raises ActionController::Redirecting::UnsafeRedirectError on external host

# Explicit allowlist
ALLOWED_RETURN_PATHS = %w[/dashboard /orders /profile].freeze

def safe_return_to
  ALLOWED_RETURN_PATHS.include?(params[:return_to]) ? params[:return_to] : "/"
end
```

### File Upload Validation

Bad - accept any uploaded file as-is:

```ruby
@user.avatar.attach(params[:avatar])
```

Good - validate content type, size, and (where relevant) reprocess to strip metadata:

```ruby
class User < ApplicationRecord
  has_one_attached :avatar do |attachable|
    attachable.variant :thumb, resize_to_limit: [200, 200]
  end

  validate :acceptable_avatar

  private

  def acceptable_avatar
    return unless avatar.attached?
    errors.add(:avatar, "must be under 5MB") if avatar.blob.byte_size > 5.megabytes
    acceptable = %w[image/jpeg image/png image/webp]
    errors.add(:avatar, "must be JPEG, PNG, or WebP") unless acceptable.include?(avatar.blob.content_type)
  end
end
```

Never trust the client-reported `content_type` for security decisions on executable formats - `Marcel::MimeType.for(io)` re-detects from magic bytes. Keep uploaded user content on a separate domain or path served with `Content-Disposition: attachment` to defeat reflected-file-download attacks.

### Host Authorization

```ruby
# config/environments/production.rb
config.hosts << "app.example.com"
config.hosts << /.*\.example\.com/

# Blocks Host header injection attacks - requests with mismatched Host get 403
```

### Cookies - Signed and Encrypted

```ruby
# Signed: tamper-evident but readable - use for non-sensitive identifiers
cookies.signed[:cart_id] = cart.id

# Encrypted: tamper-evident AND opaque - use for any sensitive data
cookies.encrypted[:user_preferences] = { theme: "dark" }

# Permanent variants for long-lived cookies
cookies.permanent.encrypted[:remember_token] = token
```

Never use `cookies[:foo]=` for security-sensitive values - clients can read and modify them freely.

### Rails Credentials

```ruby
# Edit credentials
EDITOR=vim rails credentials:edit

# Access in code
Rails.application.credentials.api_key!     # raises if missing
Rails.application.credentials.dig(:aws, :secret_key)

# Per-environment credentials
EDITOR=vim rails credentials:edit --environment production
```

## Output Format

When applying security patterns, document each measure:

```
Pattern: {Strong Params | Pundit Policy | CSRF | Rate Limiting | Credentials | XSS Prevention | SQL Injection Guard}
Resource: {controller or model name}
Change: {description of what was applied}
Risk Mitigated: {mass assignment | unauthorized access | injection | brute force | secret exposure}
```

## Avoid

- `skip_before_action :verify_authenticity_token` globally - disables CSRF for all actions
- String interpolation in `where` clauses - SQL injection vector
- `params.permit!` or `to_unsafe_h` - allows mass assignment of any attribute
- Hardcoded secrets in source code or config files - use Rails credentials
- Missing `authorize` / `policy_scope` calls - any user can access any resource
- `html_safe` or `raw` on user-provided content - XSS vulnerability
- Pundit policies that only check `user.admin?` without owner access - overly restrictive for resource owners
- Missing `rescue_from Pundit::NotAuthorizedError` - leaks stack traces to clients
- Permitting ownership FKs (`:user_id`, `:account_id`) in strong params - lets clients reassign records
- Unvalidated `redirect_to params[...]` - open redirect / phishing vector
- Trusting client-reported `content_type` on uploads - re-detect from magic bytes for executable formats
- Storing tokens/secrets in unsigned `cookies[...]` - use `cookies.encrypted` or `cookies.signed`
