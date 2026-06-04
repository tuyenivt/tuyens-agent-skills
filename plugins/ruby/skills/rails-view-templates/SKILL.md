---
name: rails-view-templates
description: Rails views for ERB/HAML/Slim - escape operators, helpers/presenters/ViewComponent, partials, fragment cache, Turbo/Stimulus, Slim traps.
metadata:
  category: backend
  tags: [ruby, rails, views, slim, haml, erb, viewcomponent, turbo, stimulus, xss]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Generating or reviewing server-rendered views (`app/views/**/*.{erb,haml,slim}`)
- Choosing helpers vs presenters vs ViewComponent
- Adding fragment caching, partials, Turbo/Stimulus wiring
- Auditing escaping when user data reaches a template

## Rules

- Always match the existing template engine; detect via `gem "slim"` / `gem "haml"`, else ERB
- Default to escaped output (`=` in all three engines); `==` (Slim), `!=` (HAML), `<%==`/`raw`/`html_safe` (ERB) only on server-trusted strings
- User-supplied HTML passes through `sanitize` with an explicit tag/attribute allowlist - never `raw` / `html_safe`
- Helpers are presentation-only: no DB queries, no service calls, no business logic
- Partials take explicit locals; one concern per partial
- Fragment cache keys take the record (`cache item`), not `item.id`
- Turbo Frame ids via `dom_id(record)`; never hand-rolled
- No inline `<script>` tags - wire JS via Stimulus

## Patterns

### Escape Operators per Engine

| Engine | Escaped | Unescaped (audit every hit) |
| ------ | ------- | --------------------------- |
| ERB    | `<%= %>` | `<%== %>`, `raw`, `html_safe` |
| HAML   | `= expr` | `!= expr` |
| Slim   | `= expr` | `== expr` |

Slim review grep: `\s== ` and `^\s*[a-z]+ ==`. Every match must come from a trusted source (i18n, `link_to`, `form_with`) - flag any user-data path.

### Slim Traps

`==` is the unescape operator, not Ruby equality. Devs coming from ERB write `==` thinking "compare" and introduce XSS silently.

Bare attribute values evaluate Ruby; quote literals:

```slim
div class=current_user.role     / evaluates Ruby
div class="user-role"           / literal string
```

Indentation defines scope - a misaligned line silently changes branch:

```slim
- if order.shipped?
  p = "Shipped on #{order.shipped_at}"
 p = "Tracking: #{order.tracking}"   / BUG - outside the if (1 space vs 2)
```

Enforce with `slim-lint` and a fixed 2-space indent.

### Helper vs Presenter vs ViewComponent

| Logic                                       | Place              |
| ------------------------------------------- | ------------------ |
| Date / currency / number formatting         | Built-in helper (`number_to_currency`, `time_ago_in_words`) |
| Stateless single-value transform            | Application helper |
| Multi-attribute formatting on one model     | Presenter / POJO   |
| Reusable UI with template + tests           | ViewComponent      |
| One-off conditional used in one template    | Inline `if`        |
| Business logic / DB query / external call   | Service object     |

Helpers form a flat namespace - no encapsulation, easy collisions. ViewComponent renders via `render OrderCardComponent.new(order: @order)` with `render_inline` tests that skip controller boot.

### Partials

```erb
<%# Bad - implicit local, contract invisible %>
<%= render 'order' %>

<%# Good - explicit locals %>
<%= render 'orders/order', order: @order, show_actions: true %>
```

`render @orders` is fine when each item maps to its class-named partial - but it is where N+1 surfaces. The fix lives upstream (controller `includes`, `counter_cache`, presenter accepting pre-loaded data); see `rails-activerecord-patterns`.

`content_for :sidebar do ... end` in the view; `yield :sidebar` in the layout.

### Fragment Caching

```slim
/ Wrong - key never changes
- cache order.id do
  = render order

/ Right - cache_key_with_version embeds updated_at
- cache order do
  = render order
```

Russian-doll: `touch: true` on child associations bubbles writes so the parent cache key invalidates:

```ruby
belongs_to :order, touch: true
```

Hot-key stampede protection:

```ruby
Rails.cache.fetch(key, expires_in: 5.minutes, race_condition_ttl: 30.seconds) { expensive_render }
```

### Turbo Frames and Streams

```slim
- @orders.each do |order|
  = turbo_frame_tag dom_id(order), src: order_path(order), loading: :lazy
    p Loading...
```

Reuse the same partial for initial render and stream update so markup stays consistent:

```ruby
render turbo_stream: turbo_stream.append("orders", partial: "orders/order", locals: { order: @order })
```

For subscription scope and channel authorization see `rails-actioncable-patterns`.

### Stimulus

```slim
div data-controller="dropdown"
  button data-action="click->dropdown#toggle" Toggle
  ul data-dropdown-target="menu" hidden=true
```

`data-action` syntax is `event->controller#method`, parsed by Stimulus - no Ruby expressions in `data-action` values.

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

### Intentional HTML Rendering

```slim
.comment-body
  = sanitize comment.body, tags: %w[p br strong em a ul ol li blockquote code], attributes: %w[href]
```

Markdown / rich-text passes through `sanitize` even if the renderer (Commonmarker, Redcarpet, Kramdown) claims safe-mode - one `raw_html: true` flag re-opens XSS. The allowlist is the trust boundary.

## Output Format

Generating:

```
Engine: {ERB | HAML | Slim}
Files Generated:
  app/views/{resource}/{action}.html.{ext}
  app/views/{resource}/_{partial}.html.{ext}
ViewComponents: {app/components/{name}_component.rb + .html.{ext} | None}
Layout Slots: {content_for / yield keys | None}
Turbo: {Frames | Streams | None}
Stimulus Controllers: {list | None}
Fragment Caching: {Russian-doll on X | Low-level | None}
```

Reviewing:

```
Severity: {Critical (XSS) | High (broken cache, frame collision) | Medium (helper/presenter misplacement) | Low (style)}
Engine: {ERB | HAML | Slim}
Location: file:line
Issue: {one line, engine-specific idiom}
```

## Avoid

- `<%==`, Slim `==`, HAML `!=` on any user-reachable expression
- Mixing template engines without a migration plan
- Inline `<script>` tags
- Slim/HAML without a linter - indentation bugs go unnoticed
- `default_scope` reaching cached fragments - stale data leaks
- Caching on `record.id` instead of the record
