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
- Adding/auditing fragment caching, partials, `content_for`
- Wiring Turbo Frames / Streams and Stimulus controllers
- Auditing escaping when user data flows into a template (XSS surface)

Engine-agnostic but emphasises Slim because its terse syntax hides escape-bypass operators ERB lacks.

## Engine Detection

| Signal                                           | Engine |
| ------------------------------------------------ | ------ |
| `gem "slim-rails"` / `gem "slim"`                | Slim   |
| `gem "haml-rails"` / `gem "haml"`                | HAML   |
| Neither gem present                              | ERB    |
| Mixed `.slim` and `.erb`                         | Match the surrounding directory's convention |

When generating new views, **always match the existing engine**. Never convert as a side effect.

## Rules

- Default to escaped output: `=` (ERB/Slim/HAML)
- Never `.html_safe` on user input - use `sanitize` with an explicit tag/attribute allowlist
- Helpers for presentation only - no DB queries, no service calls
- One concern per partial
- Fragment cache keys must include `updated_at` (`cache item`, not `cache item.id`)
- Turbo Frame `id` unique per page - use `dom_id(record)`
- No business logic in templates - use presenters or policies

## Patterns

### Escaping: ERB / HAML / Slim

```erb
<%# ERB %>
<%= @order.notes %>             <%# escaped (default) %>
<%== @order.notes %>            <%# UNESCAPED - dangerous %>
<%= raw @order.notes %>         <%# UNESCAPED %>
<%= @order.notes.html_safe %>   <%# UNESCAPED %>
```

```haml
-# HAML
%p= @order.notes      -# escaped
%p!= @order.notes     -# UNESCAPED
```

```slim
/ Slim
p = @order.notes      / escaped
p == @order.notes     / UNESCAPED
```

The Slim trap: `=` and `==` differ by one character. Review grep: `^\s*[a-z]+ ==` or `\s== ` in `.slim`; verify each renders trusted content (i18n, `link_to`, `form_with`).

### Slim-Specific Traps

**`==` is unescaped output, not equality.** All `==` in Slim is the unescape operator - Ruby equality doesn't appear. New Slim users coming from ERB write `==` thinking "evaluate Ruby" and silently introduce XSS.

**Attribute values evaluate Ruby when bare:**

```slim
div class=current_user.role         / evaluates the method call
div class="current_user.role"       / literal string
```

Quote attributes that should be literal.

**Implicit closing by indentation.** A misaligned line silently changes scope:

```slim
/ Bug - second p is OUTSIDE the if branch (1 space vs 2)
- if order.shipped?
  p = "Shipped on #{order.shipped_at}"
 p = "Tracking: #{order.tracking}"
```

Use `slim-lint` and consistent 2-space indent.

**`-` vs `=`.** `-` runs Ruby for side effects, no output. `=` outputs escaped. `==` outputs unescaped. The most common Slim review finding is mixing them up.

### Helper vs Presenter vs ViewComponent

| Logic                                           | Place                  | Why                                                    |
| ----------------------------------------------- | ---------------------- | ------------------------------------------------------ |
| Format date / currency / number                 | Built-in helper        | `number_to_currency`, `time_ago_in_words` are idiomatic|
| Stateless single-value transform                | Application helper     | Cheap, testable                                        |
| Multi-attribute formatting on one model         | Presenter (Draper/POJO)| Keeps view dumb, model unpolluted                      |
| Reusable UI with template + tests              | ViewComponent          | Encapsulated, fast tests, no view-layer boot           |
| One-off conditional in one template             | Inline `if`            | Don't extract until used twice                         |
| Business logic / DB query / external call       | Service object         | Never in a helper or template                          |

Helpers are loaded into every view as a flat namespace - collisions, no encapsulation, hard to test. ViewComponent gives `render OrderCardComponent.new(order: @order)` with a regular Ruby class unit-testable without booting the view layer.

### Partials

```erb
<%# Bad - implicit local %>
<%= render 'order' %>

<%# Good - explicit locals; contract is visible %>
<%= render 'orders/order', order: @order, show_actions: true %>
```

`render @orders` is fine when each item renders the partial named after its class. It's where N+1 hides - see below.

`content_for :sidebar do ... end` in the view; `yield :sidebar` in the layout. Don't add inline `<script>` tags.

### View-Side Query Smells

The view layer is where N+1 usually surfaces. Three patterns to recognise on sight - the fix lives upstream (controller `includes`, `counter_cache`, presenter accepting pre-loaded data):

```slim
- @orders.each do |order|
  span = order.customer.name        / N queries without includes(:customer)
  span = order.line_items.count     / N COUNT queries; use counter_cache
  span = format_money(order)        / N queries if format_money hits DB
```

Flag in review even when the view "looks fine" - the cost is invisible until rendered in a collection.

### Fragment Caching

Russian-doll caching keys on `cache_key_with_version` (includes `updated_at`). `touch: true` on child associations bubbles writes to parent so the parent cache invalidates:

```slim
/ Wrong - key never changes
- cache order.id do
  = render order

/ Right
- cache order do
  = render order
```

```ruby
belongs_to :order, touch: true  # writing a line_item bumps order.updated_at
```

```slim
- cache order do
  .order
    h2 = order.number
    - cache order.line_items do
      ul
        - order.line_items.each do |item|
          - cache item do
            li = render 'line_items/line_item', item: item
```

Cache stampede protection for hot keys:

```ruby
Rails.cache.fetch(key, expires_in: 5.minutes, race_condition_ttl: 30.seconds) do
  expensive_render
end
```

### Turbo Frames and Streams

```slim
- @orders.each do |order|
  = turbo_frame_tag dom_id(order), src: order_path(order), loading: :lazy
    p Loading order ##{order.number}...
```

`dom_id(order)` -> stable ids like `order_42`. Hand-rolling frame ids that could collide breaks navigation silently.

Streams broadcast partial updates over WebSocket or as form responses:

```ruby
respond_to do |format|
  format.turbo_stream do
    render turbo_stream: turbo_stream.append("orders", partial: "orders/order", locals: { order: @order })
  end
end
```

Reuse the same partial across initial render and stream update for consistent markup.

### Stimulus

```slim
div data-controller="dropdown" data-dropdown-open-value=false
  button data-action="click->dropdown#toggle" Toggle
  ul data-dropdown-target="menu" hidden=true
    li Item
```

`data-action` syntax: `event->controller#method`. Do not put Ruby expressions in `data-action` values - they're JS event names parsed by Stimulus.

### ViewComponent

```ruby
class OrderCardComponent < ViewComponent::Base
  def initialize(order:, show_actions: false)
    @order = order
    @show_actions = show_actions
  end

  def status_badge_class
    case @order.status
    when "pending"   then "badge-yellow"
    when "shipped"   then "badge-green"
    when "cancelled" then "badge-red"
    end
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

### Intentional HTML rendering

For markdown / rich-text / admin-curated copy, `sanitize` with an explicit allowlist - never `raw` / `html_safe` / Slim `==` / HAML `!=`:

```slim
.comment-body
  = sanitize comment.body, tags: %w[p br strong em a ul ol li blockquote code], attributes: %w[href]
```

For markdown pipelines (`Commonmarker`, `Redcarpet`, `Kramdown`), pass rendered HTML through `sanitize` even if the renderer claims safe-mode - one `raw_html: true` option re-opens XSS. The allowlist is the trust boundary.

## Output Format

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

- `.html_safe` on user input
- `<%==`, `==`, `!=` on user data
- Helpers issuing DB queries or calling services
- `default_scope` reaching the view via cached partial keys - stale data leaks
- Hand-rolled Turbo Frame ids - use `dom_id(record)`
- Ruby expressions in `data-action` values
- Mixing template engines without a migration plan
- Inline `<script>` tags - use Stimulus + importmap/jsbundling
- `render 'partial'` without explicit locals
- `cache item.id` (key never changes) - use `cache item`
- Slim/HAML indentation without a linter
