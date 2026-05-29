---
name: rails-view-templates
description: Rails views for ERB/HAML/Slim: escaping, helper vs presenter vs ViewComponent, partials, fragment caching, Turbo/Stimulus, Slim traps.
metadata:
  category: backend
  tags: [ruby, rails, views, slim, haml, erb, viewcomponent, turbo, stimulus, xss]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Generating or reviewing server-rendered views (`app/views/**/*.{erb,haml,slim}`)
- Choosing between helpers, presenters/decorators, ViewComponent
- Adding / auditing fragment caching, partials, `content_for`
- Wiring Turbo Frames / Streams and Stimulus controllers
- Auditing escaping when user data flows into a template

## Engine Detection

| Signal                                | Engine |
| ------------------------------------- | ------ |
| `gem "slim-rails"` / `gem "slim"`     | Slim   |
| `gem "haml-rails"` / `gem "haml"`     | HAML   |
| Neither                               | ERB    |
| Mixed `.slim` and `.erb`              | Match the surrounding directory |

Always match the existing engine. Never convert as a side effect of an unrelated change.

## Rules

- Default to escaped output - `=` in ERB/Slim/HAML
- `sanitize` with an explicit tag/attribute allowlist for any HTML-bearing user input; never `html_safe` / `raw` / Slim `==` / HAML `!=` on it
- Helpers are presentation-only: no DB queries, no service calls
- One concern per partial; pass explicit locals
- Fragment cache keys use the record (`cache item`), not `item.id`
- Turbo Frame ids via `dom_id(record)` - never hand-rolled
- No business logic in templates - use presenters, policies, or services

## Patterns

### Escaping by Engine

```erb
<%# ERB %>
<%= @order.notes %>             <%# escaped %>
<%== @order.notes %>            <%# UNESCAPED %>
<%= raw @order.notes %>         <%# UNESCAPED %>
<%= @order.notes.html_safe %>   <%# UNESCAPED %>
```

```haml
%p= @order.notes      -# escaped
%p!= @order.notes     -# UNESCAPED
```

```slim
p = @order.notes      / escaped
p == @order.notes     / UNESCAPED
```

Review grep for Slim: `\s== ` and `^\s*[a-z]+ ==`. Each hit must render content from a trusted source (i18n, `link_to`, `form_with`) - flag any user-data path.

### Slim-Specific Traps

`==` is the unescape operator, not Ruby equality. New Slim users coming from ERB write `==` thinking "evaluate Ruby" and introduce XSS silently.

Attribute values evaluate Ruby when bare; quote them when literal:

```slim
div class=current_user.role     / evaluates the method call
div class="current_user.role"   / literal string
```

Implicit closing by indentation - a misaligned line silently changes scope:

```slim
/ Bug - second p is OUTSIDE the if branch (1 space vs 2)
- if order.shipped?
  p = "Shipped on #{order.shipped_at}"
 p = "Tracking: #{order.tracking}"
```

Enforce via `slim-lint` and a consistent 2-space indent.

`-` runs Ruby for side effects, no output. `=` outputs escaped. `==` outputs unescaped. Mixing them up is the most common review finding.

### Helper vs Presenter vs ViewComponent

| Logic                                       | Place              | Why                                                |
| ------------------------------------------- | ------------------ | -------------------------------------------------- |
| Date / currency / number formatting         | Built-in helper    | `number_to_currency`, `time_ago_in_words`          |
| Stateless single-value transform            | Application helper | Cheap, testable                                    |
| Multi-attribute formatting on one model     | Presenter / POJO   | View stays dumb, model stays unpolluted            |
| Reusable UI with template + tests           | ViewComponent      | Encapsulated; tests skip the view-layer boot       |
| One-off conditional in one template         | Inline `if`        | Don't extract until used twice                     |
| Business logic / DB query / external call   | Service object     | Never in a helper or template                      |

Helpers form a flat namespace - collisions and no encapsulation. ViewComponent gives `render OrderCardComponent.new(order: @order)` with a regular Ruby class.

### Partials

```erb
<%# Bad - implicit local, contract is invisible %>
<%= render 'order' %>

<%# Good - explicit locals %>
<%= render 'orders/order', order: @order, show_actions: true %>
```

`render @orders` is fine when each item renders its class-named partial. It's where N+1 hides - see below.

`content_for :sidebar do ... end` in the view; `yield :sidebar` in the layout. Never inline `<script>` tags - wire JS via Stimulus.

### View-Side Query Smells

The view is where N+1 surfaces; the fix lives upstream (controller `includes`, `counter_cache`, presenter accepting pre-loaded data):

```slim
- @orders.each do |order|
  span = order.customer.name        / N queries without includes(:customer)
  span = order.line_items.count     / N COUNT queries; use counter_cache
  span = format_money(order)        / N queries if format_money hits DB
```

Flag in review even when the view "looks fine" - the cost is invisible until rendered in a collection.

### Fragment Caching

Russian-doll caching keys on `cache_key_with_version` (includes `updated_at`). `touch: true` on child associations bubbles writes so the parent cache invalidates:

```slim
/ Wrong - key never changes
- cache order.id do
  = render order

/ Right - cache_key_with_version embeds updated_at
- cache order do
  = render order
```

```ruby
belongs_to :order, touch: true  # writing a line_item bumps order.updated_at
```

Hot-key stampede protection:

```ruby
Rails.cache.fetch(key, expires_in: 5.minutes, race_condition_ttl: 30.seconds) { expensive_render }
```

### Turbo Frames and Streams

```slim
- @orders.each do |order|
  = turbo_frame_tag dom_id(order), src: order_path(order), loading: :lazy
    p Loading order ##{order.number}...
```

`dom_id(order)` -> stable ids like `order_42`. Hand-rolled ids that could collide break navigation silently.

Streams broadcast partial updates; reuse the same partial across initial render and stream update for consistent markup:

```ruby
render turbo_stream: turbo_stream.append("orders", partial: "orders/order", locals: { order: @order })
```

### Stimulus

```slim
div data-controller="dropdown" data-dropdown-open-value=false
  button data-action="click->dropdown#toggle" Toggle
  ul data-dropdown-target="menu" hidden=true
```

`data-action` syntax is `event->controller#method` - parsed by Stimulus, not Ruby. Don't put Ruby expressions in `data-action` values.

### ViewComponent

```ruby
class OrderCardComponent < ViewComponent::Base
  def initialize(order:, show_actions: false)
    @order, @show_actions = order, show_actions
  end

  def status_badge_class
    { "pending" => "badge-yellow", "shipped" => "badge-green", "cancelled" => "badge-red" }[@order.status]
  end
end
```

```slim
.order-card
  h3 = @order.number
  span class=status_badge_class = @order.status.humanize
  - if @show_actions
    = render 'orders/actions', order: @order
```

Tests use `render_inline` - no controller, no full request.

### Intentional HTML Rendering

```slim
.comment-body
  = sanitize comment.body, tags: %w[p br strong em a ul ol li blockquote code], attributes: %w[href]
```

Pass markdown / rich-text through `sanitize` even if the renderer (Commonmarker, Redcarpet, Kramdown) claims safe-mode - one `raw_html: true` option re-opens XSS. The allowlist is the trust boundary.

## Output Format

Generating:

```
Engine: {ERB | HAML | Slim}
Files Generated:
  app/views/{resource}/index.html.{ext}
  app/views/{resource}/show.html.{ext}
  app/views/{resource}/_form.html.{ext}
  app/views/{resource}/_{resource}.html.{ext}
ViewComponents (if any):
  app/components/{name}_component.rb + .html.{ext}
Layout Slots: {content_for / yield keys}
Turbo: {Frames | Streams | None}
Stimulus Controllers: {list | None}
Fragment Caching: {Russian-doll on X | None | Low-level only}
```

Reviewing:

```
Severity: {Critical (XSS) | High (broken cache, frame collision) | Medium (helper/presenter misplacement) | Low (style)}
Engine: {ERB | HAML | Slim}
Location: file:line
Issue: {one line, engine-specific idiom}
```

## Avoid

- `default_scope` reaching the view via cached partial keys - stale data leaks
- Mixing template engines without a migration plan
- `<%==`, Slim `==`, HAML `!=` on anything reachable from user input
- Inline `<script>` tags - use Stimulus + importmap/jsbundling
- Slim/HAML without a linter - indentation bugs go unnoticed
