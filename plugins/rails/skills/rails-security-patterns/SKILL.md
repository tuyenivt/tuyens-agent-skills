---
name: rails-security-patterns
description: "Rails security: strong parameters, Devise (with JWT for APIs), Pundit authorization, CSRF, XSS prevention, SQL injection, Rack::Attack rate limiting, Rails credentials."
user-invocable: false
---

## 1. Strong Parameters

```ruby
class OrdersController < ApplicationController
  private

  def order_params
    params.require(:order).permit(:total, :status, :customer_id, metadata: {})
  end
end

# ❌ NEVER: params.permit! or params.to_unsafe_h
# ❌ NEVER: permit(:id) — attackers can change record IDs
```

## 2. Authentication — Devise + JWT

```ruby
# Gemfile
gem "devise"
gem "devise-jwt"

# Standard Devise setup for session-based auth
# For API-only:
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

## 3. Authorization — Pundit

```ruby
# app/policies/order_policy.rb
class OrderPolicy < ApplicationPolicy
  def show?
    record.customer_id == user.id || user.admin?
  end

  def update?
    record.customer_id == user.id && record.pending?
  end

  class Scope < Scope
    def resolve
      if user.admin?
        scope.all
      else
        scope.where(customer_id: user.id)
      end
    end
  end
end

# Controller
class OrdersController < ApplicationController
  def show
    @order = Order.find(params[:id])
    authorize @order
  end

  def index
    @orders = policy_scope(Order)
  end
end

# Ensure authorization in every action
class ApplicationController < ActionController::Base
  include Pundit::Authorization
  after_action :verify_authorized, except: :index
  after_action :verify_policy_scoped, only: :index
end
```

## 4. CSRF Protection

```ruby
# Default: enabled for all non-GET requests
class ApplicationController < ActionController::Base
  protect_from_forgery with: :exception
end

# API-only: skip CSRF (use token auth instead)
class Api::BaseController < ActionController::API
  # No CSRF needed — stateless token auth
end

# ❌ NEVER: skip_before_action :verify_authenticity_token globally
```

## 5. XSS Prevention

```ruby
# Rails auto-escapes output in ERB by default
<%= user.name %> # ✅ Safe — auto-escaped

# ❌ Dangerous — only use for trusted content
<%= raw user.bio %>
<%= user.bio.html_safe %>

# ✅ Sanitize user HTML
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

## 6. SQL Injection

```ruby
# ✅ Parameterized queries
User.where("email = ?", params[:email])
User.where(email: params[:email])

# ✅ Sanitize for LIKE
User.where("name LIKE ?", "%#{User.sanitize_sql_like(params[:q])}%")

# ❌ NEVER: string interpolation in queries
User.where("email = '#{params[:email]}'") # SQL INJECTION!
```

## 7. Rate Limiting — Rack::Attack

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

# Block bad actors
Rack::Attack.blocklist("block bad IPs") do |req|
  Rack::Attack::Fail2Ban.filter("bad-#{req.ip}", maxretry: 3, findtime: 10.minutes, bantime: 1.hour) do
    req.path == "/api/v1/login" && req.post? && req.env["rack.attack.match_data"]
  end
end
```

## 8. Rails Credentials

```ruby
# Edit credentials
EDITOR=vim rails credentials:edit

# Access in code
Rails.application.credentials.api_key!     # raises if missing
Rails.application.credentials.dig(:aws, :secret_key)

# Per-environment credentials
EDITOR=vim rails credentials:edit --environment production

# ❌ NEVER: hardcode secrets in code or config files
# ❌ NEVER: commit .env files with real secrets
```

## Anti-Patterns

- ❌ `skip_before_action :verify_authenticity_token` globally
- ❌ String interpolation in `where` clauses
- ❌ `params.permit!` — allows mass assignment of any attribute
- ❌ Hardcoded secrets in source code
- ❌ Missing authorization checks (`authorize` / `policy_scope`)
- ❌ `html_safe` on user-provided content
