---
name: rails-view-templates
description: Rails view patterns for ERB/HAML/Slim: escaping, helper vs presenter vs ViewComponent, partials, fragment caching, Turbo/Stimulus.
metadata:
  category: backend
  tags: [ruby, rails, views, slim, haml, erb, viewcomponent, turbo, stimulus, xss, patterns]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Generating or reviewing server-rendered Rails views (`app/views/**/*.{erb,haml,slim}`)
- Choosing between helpers, presenters/decorators, and ViewComponent for view logic
- Adding or auditing fragment caching, partials, or `content_for` patterns
- Wiring Turbo Frames / Streams and Stimulus controllers into existing views
- Auditing escaping correctness when user data flows into a template (XSS surface)
- Adapting view generation when the project's template engine is Slim or HAML rather than ERB

This skill is engine-agnostic but emphasises Slim-specific traps because Slim's terse syntax hides escape-bypass operators that have no visual analogue in ERB.

## Engine Detection

Before generating or reviewing views, identify the engine:

| Signal                                       | Engine     |
| -------------------------------------------- | ---------- |
| `gem "slim-rails"` or `gem "slim"` in Gemfile | Slim       |
| `gem "haml-rails"` or `gem "haml"` in Gemfile | HAML       |
| Neither gem present                           | ERB (default) |
| Mixed: `app/views/` contains `.slim` and `.erb` | Match the surrounding directory's convention - do not introduce a new engine |

When generating new views in an existing project, **always match the existing engine**. Do not convert ERB to Slim (or vice versa) as a side effect of feature work.

## Rules

- **Default to escaped output.** Use `=` in ERB/Slim and `=` in HAML for any expression that could contain user data. Reserve unescape operators (`<%==`, `==`, `!=`) for content that has been explicitly sanitized or is hard-coded markup.
- **Never call `.html_safe` on user input.** `.html_safe` marks a string as already-escaped - applying it to user data is a direct XSS. Use `sanitize` with an explicit allowlist if HTML must be rendered.
- **Helpers for presentation only.** No DB queries inside helpers - any helper that calls `.where`, `.count`, `.sum`, `.find`, `.exists?`, or invokes a service is a hot-path query risk when called from a row partial. Move the data fetch to the controller (or a presenter that takes a pre-loaded relation) and pass the value in.
- **One concern per partial.** A partial that renders both a list item and its actions belongs in two partials.
- **Fragment cache keys must include `updated_at`.** Otherwise stale views render after writes. Use `cache item` (which keys on `cache_key_with_version`), not `cache item.id`.
- **Turbo Frame `id` must be unique per page.** Two frames with the same id collide silently and break navigation.
- **No business logic in templates.** Conditionals on user role, feature flags, or state machines belong in a presenter or policy, not in the view.

## Patterns

### Escaping: ERB / HAML / Slim Side by Side

The same escaping rule looks different in each engine. When in doubt, prefer the escaped form.

ERB:

```erb
<%# escaped (default) %>
<p><%= @order.notes %></p>

<%# UNESCAPED - dangerous if @order.notes contains user input %>
<p><%== @order.notes %></p>
<p><%= raw @order.notes %></p>
<p><%= @order.notes.html_safe %></p>
```

HAML:

```haml
-# escaped (default)
%p= @order.notes

-# UNESCAPED - dangerous
%p!= @order.notes
%p= @order.notes.html_safe
```

Slim:

```slim
/ escaped (default)
p = @order.notes

/ UNESCAPED - dangerous
p == @order.notes
p = @order.notes.html_safe
```

The Slim trap: `=` and `==` differ by a single character. In code review, grep for `^\s*[a-z]+ ==` or `\s== ` in `.slim` files and verify each instance renders trusted content (i18n strings, view helpers that return `html_safe` markup like `link_to`, `form_with`).

### Slim-Specific Traps

**`==` is unescaped output, not equality.** Ruby's `==` does not appear in Slim expressions - all `==` in a Slim file is the unescape operator. New Slim users coming from ERB often write `==` thinking it means "evaluate Ruby" and silently introduce XSS.

**Attribute values evaluate Ruby.** Slim attributes run Ruby implicitly when bare:

```slim
/ This evaluates current_user.role - a method call - and uses its return value as the class
div class=current_user.role

/ This is a literal string "current_user.role" - quoted
div class="current_user.role"
```

If `current_user.role` returns user-controlled content (it shouldn't, but legacy schemas exist), the attribute injection surface is the same as `<%= %>` in ERB. Quote attributes that should be literal.

**Implicit closing.** Slim closes blocks by indentation, not by `<% end %>`. A misaligned line silently changes scope:

```slim
/ Bug: the second p is OUTSIDE the if branch
- if order.shipped?
  p = "Shipped on #{order.shipped_at}"
 p = "Tracking: #{order.tracking}"
```

The second `p` is at 1 space indent, not 2 - so it renders unconditionally. Slim won't error; it will render with `tracking` of an unshipped order. Use a linter (`slim-lint`) and consistent 2-space indent.

**`-` vs `=`.** Bare `-` runs Ruby for side effects only and produces no output. Bare `=` outputs the result. `==` outputs unescaped. Mixing them up is the most common Slim review finding.

### Helper vs Presenter vs ViewComponent

A decision matrix for where view logic belongs:

| Logic Type                                             | Place It In                  | Reason                                                                |
| ------------------------------------------------------ | ---------------------------- | --------------------------------------------------------------------- |
| Format a date, currency, or number                     | Rails built-in helper        | `number_to_currency`, `time_ago_in_words` - already idiomatic         |
| Stateless transformation of a single value             | Application helper module    | `app/helpers/orders_helper.rb` - cheap, testable                      |
| Multi-attribute formatting tied to one model           | Presenter (Draper or POJO)   | `OrderPresenter#display_status` - keeps view dumb, model unpolluted   |
| Reusable UI element with its own template + tests     | ViewComponent                | `app/components/order_card_component.rb` - encapsulated, fast tests   |
| One-off conditional in one template                    | Inline `if`                  | Don't extract until used twice                                        |
| Business logic, DB query, or external call             | Service object               | Never in a helper or template                                         |

**Why presenters/ViewComponents over helpers for non-trivial logic:** helpers are loaded into every view as a flat namespace - method collisions, no encapsulation, hard to test in isolation. ViewComponent gives you `render OrderCardComponent.new(order: @order)` with a separate template file and a regular Ruby class you can unit-test without booting the view layer.

### Partials and Layouts

Bad - implicit local variable, hard to grep:

```erb
<%= render 'order' %>  <%# What does this partial expect? Read the file to find out. %>
```

Good - explicit locals make the contract visible:

```erb
<%= render 'orders/order', order: @order, show_actions: true %>
```

In Slim, the same explicit form:

```slim
= render 'orders/order', order: @order, show_actions: true
```

**Collection rendering.** `render @orders` is fine when each item renders the partial named after its class (`_order.html.slim`). It's also where N+1 hides - see the perf section below.

**`content_for` for layout slots.** When a page needs to inject into the layout (sidebar, page-specific JS), use `content_for :sidebar do ... end` in the view and `<%= yield :sidebar %>` (or `= yield :sidebar` in Slim) in the layout. Don't ad-hoc `<script>` tags in the body.

### View-Side Query Smells

The view layer is where ActiveRecord N+1s usually surface. Three patterns to recognise on sight, all of which fan out one query per rendered row:

```slim
/ 1. Association access without controller-side preload
- @orders.each do |order|
  span = order.customer.name        / N queries unless includes(:customer) upstream

/ 2. Aggregation method that issues SQL
- @orders.each do |order|
  span = order.line_items.count     / N COUNT queries; use counter_cache or pre-aggregate

/ 3. Helper invoked per row that hits the DB
- @orders.each do |order|
  span = format_money(order)        / N queries if format_money calls .sum / .where
```

The view file itself rarely needs editing - the fix lives upstream: `includes(...)` in the controller, `counter_cache` on the association, or moving the query to a presenter that accepts pre-loaded data. Flag these in review even when the view "looks fine"; the cost is invisible until the partial is rendered in a collection.

### Fragment Caching

Russian-doll caching keys on the model's `cache_key_with_version` (which includes `updated_at`). Touch parents on child writes so the parent cache invalidates when a child changes:

```slim
/ Wrong: keys on the id alone - the cache never invalidates because the id never changes
- cache order.id do
  = render order

/ Right: keys on cache_key_with_version - includes updated_at so writes bust the cache
- cache order do
  = render order
```

```ruby
# app/models/line_item.rb
belongs_to :order, touch: true   # writing a line_item bumps order.updated_at
```

```slim
/ app/views/orders/_order.html.slim
- cache order do
  .order
    h2 = order.number
    - cache order.line_items do
      ul
        - order.line_items.each do |item|
          - cache item do
            li = render 'line_items/line_item', item: item
```

Each `cache` block keys on the object's `cache_key_with_version`. Without `touch: true`, a `LineItem` write would bump only the line_item key - the order block's cache would stay stale.

**Cache stampede protection.** Hot keys with expensive regeneration use `race_condition_ttl` so concurrent expiries do not pile up:

```ruby
Rails.cache.fetch(key, expires_in: 5.minutes, race_condition_ttl: 30.seconds) do
  expensive_render
end
```

### Turbo Frames and Streams

Turbo Frames let you replace a region of the page without a full reload:

```slim
/ Index page lists frames; each frame fetches its content lazily
- @orders.each do |order|
  = turbo_frame_tag dom_id(order), src: order_path(order), loading: :lazy
    p Loading order ##{order.number}...
```

The `dom_id(order)` helper produces stable ids like `order_42`. **Do not hand-roll frame ids that could collide** - two frames with the same id break navigation silently (the second one's content replaces the first on any update).

Turbo Streams broadcast partial updates over WebSocket or as form responses:

```ruby
# in a controller action
respond_to do |format|
  format.turbo_stream do
    render turbo_stream: turbo_stream.append("orders", partial: "orders/order", locals: { order: @order })
  end
end
```

The `_order.html.slim` partial must be the same one used elsewhere - reuse keeps markup consistent across initial render and stream update.

### Stimulus Controller Wiring

Stimulus connects DOM to JS via data attributes. Keep wiring declarative in the template:

```slim
div data-controller="dropdown" data-dropdown-open-value=false
  button data-action="click->dropdown#toggle" Toggle
  ul data-dropdown-target="menu" hidden=true
    li Item
```

In Slim, attribute names with hyphens require quoting on the value side (`data-controller="dropdown"`). The `data-action` syntax is `event->controller#method`. **Do not put Ruby logic inside data-action values** - those are JS event names, not Ruby expressions.

### ViewComponent Pattern

When a piece of UI is reused across views or has non-trivial logic, extract it:

```ruby
# app/components/order_card_component.rb
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
/ app/components/order_card_component.html.slim
.order-card
  h3 = @order.number
  span class=status_badge_class = @order.status.humanize
  - if @show_actions
    = render 'orders/actions', order: @order
```

```slim
/ usage in a view
= render OrderCardComponent.new(order: @order, show_actions: true)
```

Tests live in `spec/components/order_card_component_spec.rb` and use `render_inline` - no controller, no full request.

## Output Format

When generating views, document:

```
Engine: {ERB | HAML | Slim}
Files Generated:
  app/views/{resource}/index.html.{ext}      # collection page
  app/views/{resource}/show.html.{ext}       # detail page
  app/views/{resource}/_form.html.{ext}      # shared form partial
  app/views/{resource}/_{resource}.html.{ext} # collection item partial
ViewComponents (if any):
  app/components/{name}_component.rb + .html.{ext}
Layout Slots Used: {list of content_for / yield keys}
Turbo: {Frames used | Streams used | None}
Stimulus Controllers Referenced: {list, or "None"}
Fragment Caching: {Russian-doll on X | None | Low-level only}
```

When reviewing views, classify findings as:

```
Severity: {Critical (XSS) | High (broken cache invalidation, frame-id collision) | Medium (helper/presenter misplacement) | Low (style)}
Engine: {ERB | HAML | Slim}
Location: file:line
Issue: {one-line description naming the engine-specific idiom}
```

## Avoid

- `.html_safe` on user input - use `sanitize` with an explicit tag/attribute allowlist if HTML must render
- `<%==`, `==`, `!=` (HAML/Slim unescape) on any expression that could contain user data
- Helpers that issue DB queries or call services - move to presenter or controller
- `default_scope` showing up in the view layer via cached partial keys - the cache_key won't reflect the scope and stale data leaks
- Hand-rolled Turbo Frame ids - always use `dom_id(record)` so they're collision-free
- Putting Ruby expressions in `data-action` values - those are JS event names parsed by Stimulus, not Ruby
- Mixing template engines in one project without an explicit migration plan - choose one and stick to it
- Inline `<script>` tags in views - use Stimulus controllers and importmap/jsbundling instead
- `render 'partial'` without explicit locals - implicit locals are unreviewable
- Caching a partial without including `updated_at` in the key (`cache item.id` instead of `cache item`)
- Relying on Slim/HAML indentation without a linter - misaligned blocks change semantics silently
