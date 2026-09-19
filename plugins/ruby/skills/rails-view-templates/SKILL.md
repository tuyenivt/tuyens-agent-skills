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
- Default to escaped output (`=` in all three engines); `==` (Slim), `!=` (HAML), `<%==` (ERB), and `raw` / `html_safe` in any engine, only on server-trusted strings
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
| ERB    | `<%= %>` | `<%== %>` |
| HAML   | `= expr` | `!= expr` |
| Slim   | `= expr` | `== expr`, and `attr==value` in an attribute |

Neither `raw` nor `html_safe` is ERB syntax - `raw` is an ActionView helper and `html_safe` an ActiveSupport `String` method - so both unescape in HAML and Slim exactly as in ERB (`= raw user.bio`). Only the operator column is engine-specific; grep for `raw\b` and `html_safe` in every engine.

Slim review grep: `==` unanchored. `\s== ` misses the attribute form `a href==user.url` (no space on either side) and a column-0 `== x`; `^\s*[a-z]+ ==` additionally misses shortcut tags (`.row == x`, `#main == x`), whose leading `.`/`#` is not `[a-z]`. Every match must come from a trusted source (i18n, `link_to`, `form_with`) - flag any user-data path. Two adjacent escapes: user data interpolated into a `script` block is Critical regardless of operator - HTML-escaping doesn't cover the JS string context; move it to an escaped `data-*` value (see Stimulus), which the browser entity-decodes as attribute text - safe under `=`, still Critical under an unescape operator. And user data in *attribute values* (`div class=user.theme`) is attribute-escaped but still allows class/attribute injection - allowlist the permitted values.

User-visible strings go through `t()`, and i18n is a third unescape surface - a narrower one than it looks. For a key ending in `_html` (or named `html`) Rails marks the *translation* html_safe but still HTML-escapes every interpolated value first (`html_escape_translation_options`), so `t(".greeting_html", name: user.name)` with a plain String is safe. Two things do get through: a value that is *already* `html_safe` (a `raw(...)` result, a SafeBuffer, another `_html` translation) passes untouched, and markup in the locale entry itself is rendered as-is. So the rule is about what you hand it - never interpolate a SafeBuffer built from user data - and about who may edit the locale file, which for user-editable translations is the whole attack.

### Slim Traps

`==` is the unescape operator, not Ruby equality. Devs coming from ERB write `==` thinking "compare" and introduce XSS silently.

Bare attribute values evaluate Ruby; quote literals:

```slim
/ bare value evaluates Ruby:
div class=current_user.role
/ quoted value is a literal string:
div class="user-role"
```

(Slim `/` comments are line-level only - a trailing `/ ...` on a tag line renders as content.)

Indentation defines scope - a misaligned line silently changes branch:

```slim
- if order.shipped?
  p = "Shipped on #{order.shipped_at}"
p = "Tracking: #{order.tracking}"
/ BUG: dedented to column 0, so it renders for every order, shipped or not
```

That is the dangerous shape, because it compiles. A dedent to a level that matches no enclosing block (1 space here) is *not* silent - Slim raises `Slim::Parser::SyntaxError: Malformed indentation` and HAML raises `Inconsistent indentation`, so the template never renders at all.

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

Presenter vs component when both fit: formatting that belongs to one reusable piece of UI lives in that component's class (`status_badge_class` in the row component); a presenter is for model-wide formatting consumed by *several* views/components. Conversion helpers (markdown-to-HTML) stay stateless application helpers feeding `sanitize` in the template.

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

/ Right - the record supplies cache_key + cache_version (updated_at), so an update invalidates
- cache order do
  = render order
```

Uniform lists use collection caching - one `read_multi` instead of a cache read per row:

```slim
= render partial: "orders/order", collection: @orders, cached: true
```

`cached: true` keys on the record alone, so one partial reused with different `locals:` - a public variant and an operator variant with extra columns - collides, and whichever renders first is served to both. Put the distinguishing local in the key: `cached: ->(order) { [order, show_operator_columns] }`.

`cached: true` is partial-only. ViewComponent rows render via `OrderCardComponent.with_collection(@orders)`, which passes the collection member as `order_card:` (derived from the class name) - so the component needs `with_collection_parameter :order` for an `order:` initializer, or it raises `ViewComponent::MissingCollectionArgumentError`. Don't wrap component renders in `cache` blocks - template digests don't track component files, so component edits never bust the fragment.

Russian-doll: `touch: true` on child associations bubbles writes so the parent cache key invalidates:

```ruby
belongs_to :order, touch: true
```

Hot-key stampede protection (controller-computed aggregates cache here too, not in the view):

```ruby
Rails.cache.fetch(key, expires_in: 5.minutes, race_condition_ttl: 30.seconds) { expensive_render }
```

Caching and streams compose, but not because broadcasts skip the cache - they render through `ApplicationController.render`, which honours `perform_caching`, so `cache` blocks inside a broadcast partial read and write the store exactly as in a request render. What makes it safe is the key: the `after_*_commit` that triggers the broadcast has already bumped the record's `updated_at`, so a `cache record` key is new by the time the broadcast renders. A fragment whose key omits the record that was touched will happily broadcast stale HTML - that is the case to check.

### Turbo Frames and Streams

```slim
- @orders.each do |order|
  = turbo_frame_tag dom_id(order), src: order_path(order), loading: :lazy do
    p Loading...
```

The trailing `do` is required. Slim compiles a nested block under a bare `=` as its own block and still emits the closing `end`, so the placeholder never reaches the helper and the generated Ruby has an unbalanced `end` - a compile error inside the enclosing `each`.

Frame vs stream: a frame with `src:` *pulls* on navigation/lazy-load; live in-place updates *push* via `turbo_stream_from` + a broadcast targeting `dom_id(record)`. Reuse the same partial for initial render and stream update so markup stays consistent (rows built as ViewComponents: have the broadcast render the component, or keep the row a partial both paths share); a local the broadcast cannot pass defaults via `local_assigns.fetch(:operator, false)`:

```ruby
# push path (model callback or job) - the partial receives the record only
order.broadcast_replace_later_to [order.user, :orders], partial: "orders/order", locals: { order: order }
# request path
render turbo_stream: turbo_stream.append("orders", partial: "orders/order", locals: { order: @order })
# in the shared partial
- operator = local_assigns.fetch(:operator, false)
```

For subscription scope and channel authorization see `rails-actioncable-patterns`.

### Stimulus

```slim
div data-controller="dropdown"
  button data-action="click->dropdown#toggle" Toggle
  ul data-dropdown-target="menu" hidden=true
```

`data-action` syntax is `event->controller#method`, parsed by Stimulus - no Ruby expressions in `data-action` values. A new controller under `app/javascript/controllers/` is registered by `controllers/index.js` (`stimulus-rails` pins the directory); nothing else to wire.

Server data reaches controllers through the values API with the escaped operator - `div data-controller="chart" data-chart-points-value=@points.to_json` - never an inline `script`.

### ViewComponent

```ruby
class OrderCardComponent < ViewComponent::Base
  with_collection_parameter :order   # with_collection passes `order_card:` otherwise

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

Markdown / rich-text passes through `sanitize` even if the renderer claims safe-mode - one flag re-opens XSS, and each renderer spells it differently: Commonmarker `unsafe: true`, Redcarpet the *absence* of `escape_html:`/`filter_html:`, Kramdown passes raw HTML through by default. The allowlist is the trust boundary. Allowlisting `href` keeps user links live - also force `rel="nofollow noopener"` so user content can't vouch for or script-reach its targets: either a post-process on the sanitized fragment, or a `Rails::HTML::PermitScrubber` subclass that carries the allowlist and adds `rel` - passing `scrubber:` replaces `tags:`/`attributes:`, so a rel-only scrubber would drop the allowlist. `sanitize` itself won't add attributes.

## Output Format

Generating - emit the block, then the template code for every file it lists. Multi-valued slots (`Turbo:`, `Fragment Caching:`) list every applying value, `+`-joined. A pre-existing bug the page inherits (a global broadcast scope, a helper that queries) gets one numbered finding above the block, naming the owning skill when it is a sibling's:

```
Engine: {ERB | HAML | Slim}

Files Generated:
  app/views/{resource}/{action}.html.{ext}
  app/views/{resource}/_{partial}.html.{ext}
  app/javascript/controllers/{name}_controller.js      # Stimulus, when one is added
  app/helpers/{name}_helper.rb                          # when a stateless transform is added
  config/locales/{locale}.yml                          # keys added, when strings are user-visible

ViewComponents: {app/components/{name}_component.rb + .html.{ext} | None}

Layout Slots: {content_for / yield keys | None}

Turbo: {Frames | Streams | None}

Stimulus Controllers: {list | None}

Fragment Caching: {Record (cache record) on X | Russian-doll on X | Collection (cached: true, or a lambda key when locals vary) on X | Low-level | None}

Logic Moves: {helper -> presenter/component verdicts | None}
```

Reviewing - one block per finding in the format below, Critical first; after all blocks, emit the corrected template code for each affected file. A project-wide finding (no linter) takes `Location: Gemfile`; a cross-file finding cites the file where the fix lands; a finding on a non-template file takes `Engine: n/a`:

```
Severity: {Critical (XSS, JS-context injection, a cache or stream that leaks across users, roles or tenants, a credential or token rendered into the markup - a key designed as publishable is not one) | High (stale/never-invalidating cache, logic/indentation bug, frame collision, per-row rendering or N+1 that degrades the page, a user-supplied href with an unrestricted scheme) | Medium (attribute injection, helper/presenter misplacement) | Low (style, partial contract)}

Engine: {ERB | HAML | Slim | n/a (non-template file)}

Location: file:line

Issue: {one line, engine-specific idiom}

Fix: {one-line remediation | handoff: <skill> - one line when the mechanism lives outside app/views}
```

An N+1 or a missing preload seen from the template gets a block here with the query fix named, and a pointer to `rails-activerecord-patterns` for the model-side change - the reader is looking at the view, so dropping the finding entirely is worse than a one-line handoff. Findings whose mechanism lives outside `app/views/**` (channel authorization, `current_account` resolution, broadcast scoping) get a block with `Location:` naming that file and one line saying the fix belongs to that skill.

## Avoid

- `<%==`, Slim `==`, HAML `!=` on any user-reachable expression
- Mixing template engines without a migration plan
- Inline `<script>` tags
- Slim/HAML without a linter - indentation bugs go unnoticed
- Fragment keys omitting implicit scope context - data cached under a `default_scope` (tenant scoping is the dangerous case) serves other scopes; include the scoping value in the key (`cache [Current.tenant, :stats]`)
- Caching on `record.id` instead of the record
