---
name: vue-monolith-integration
description: Integrating Vue into Rails (Inertia.js, jsbundling), Django (django-vite, webpack), and Laravel (Inertia.js) monoliths - mount strategies, asset pipelines, and shared layout handling.
metadata:
  category: frontend
  tags: [vue, rails, django, laravel, inertia, monolith, integration, asset-pipeline]
user-invocable: false
---

# Vue Monolith Integration

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding Vue to an existing Rails, Django, or Laravel monolith
- Choosing between full SPA, island architecture, or widget embedding
- Configuring asset pipelines (Vite, Webpack) for monolith integration
- Setting up Inertia.js for seamless server-driven Vue pages
- Migrating from server-rendered templates to Vue incrementally

## Rules

- Detect the monolith framework first (Rails, Django, Laravel) before choosing a strategy
- Inertia.js is the primary recommendation for Rails and Laravel - it eliminates the need for a separate API layer
- Island architecture is appropriate when only parts of pages need interactivity
- Full SPA mode should only be chosen when the entire frontend will be Vue
- Shared layouts (header, nav, footer) must be handled consistently across server-rendered and Vue-rendered pages
- Asset pipeline must be configured correctly for the monolith's build system

## Patterns

### Mount Strategy Selection

| Strategy         | When to Use                                      | Backend Support              |
| ---------------- | ------------------------------------------------ | ---------------------------- |
| Inertia.js       | Replace server templates with Vue pages entirely | Rails, Laravel               |
| Islands          | Add interactivity to specific page sections      | All (Rails, Django, Laravel) |
| Widget embedding | Embed standalone Vue widgets in existing pages   | All                          |
| Full SPA         | Entire frontend is Vue, backend is API-only      | All (API mode)               |

### Inertia.js (Rails)

```ruby
# Gemfile
gem "inertia_rails"

# config/initializers/inertia_rails.rb
InertiaRails.configure do |config|
  config.version = ViteRuby.digest
end

# app/controllers/products_controller.rb
class ProductsController < ApplicationController
  def index
    products = Product.all
    render inertia: "Products/Index", props: {
      products: products.as_json(only: [:id, :name, :price])
    }
  end

  def show
    product = Product.find(params[:id])
    render inertia: "Products/Show", props: {
      product: product.as_json
    }
  end
end
```

```vue
<!-- app/frontend/pages/Products/Index.vue -->
<script setup lang="ts">
import { Head } from "@inertiajs/vue3";

defineProps<{
  products: Array<{ id: number; name: string; price: number }>;
}>();
</script>

<template>
  <Head title="Products" />
  <div>
    <h1>Products</h1>
    <div v-for="product in products" :key="product.id">
      <Link :href="`/products/${product.id}`">{{ product.name }}</Link>
    </div>
  </div>
</template>
```

### Inertia.js (Laravel)

```php
// routes/web.php
Route::get('/products', function () {
    return Inertia::render('Products/Index', [
        'products' => Product::all(),
    ]);
});

// app/Http/Controllers/ProductController.php
class ProductController extends Controller
{
    public function index()
    {
        return Inertia::render('Products/Index', [
            'products' => Product::paginate(20),
        ]);
    }
}
```

```ts
// resources/js/app.ts
import { createApp, h } from "vue";
import { createInertiaApp } from "@inertiajs/vue3";
import { resolvePageComponent } from "laravel-vite-plugin/inertia-helpers";

createInertiaApp({
  resolve: (name) =>
    resolvePageComponent(
      `./Pages/${name}.vue`,
      import.meta.glob("./Pages/**/*.vue"),
    ),
  setup({ el, App, props, plugin }) {
    createApp({ render: () => h(App, props) })
      .use(plugin)
      .mount(el);
  },
});
```

### Island Architecture (Django)

Mount Vue components on specific DOM elements within server-rendered pages:

```python
# views.py
def product_page(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    return render(request, "products/detail.html", {"product": product})
```

```html
<!-- templates/products/detail.html -->
{% load django_vite %} {% vite_hmr_client %}

<h1>{{ product.name }}</h1>
<p>{{ product.description }}</p>

<!-- Vue island: interactive review section -->
<div id="reviews-app" data-product-id="{{ product.id }}"></div>

{% vite_asset 'src/islands/reviews.ts' %}
```

```ts
// src/islands/reviews.ts
import { createApp } from "vue";
import ReviewSection from "./ReviewSection.vue";

const el = document.getElementById("reviews-app");
if (el) {
  const app = createApp(ReviewSection, {
    productId: el.dataset.productId,
  });
  app.mount(el);
}
```

### Widget Embedding (Any Backend)

```ts
// src/widgets/product-configurator.ts
import { createApp } from "vue";
import ProductConfigurator from "./ProductConfigurator.vue";

// Self-mounting widget - finds all matching elements
document.querySelectorAll("[data-vue-configurator]").forEach((el) => {
  const htmlEl = el as HTMLElement;
  const app = createApp(ProductConfigurator, {
    productId: htmlEl.dataset.productId,
    options: JSON.parse(htmlEl.dataset.options || "{}"),
  });
  app.mount(el);
});
```

```html
<!-- Any server template -->
<div
  data-vue-configurator
  data-product-id="123"
  data-options='{"colors":["red","blue"]}'
></div>
```

### Asset Pipeline Configuration

**Rails with Vite (jsbundling-rails + vite_rails):**

```ruby
# Gemfile
gem "vite_rails"
```

```ts
// vite.config.ts
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import RubyPlugin from "vite-plugin-ruby";

export default defineConfig({
  plugins: [vue(), RubyPlugin()],
});
```

**Django with django-vite:**

```python
# settings.py
DJANGO_VITE = {
    "default": {
        "dev_mode": DEBUG,
        "dev_server_host": "localhost",
        "dev_server_port": 5173,
    },
}
```

**Laravel with Vite (built-in):**

```ts
// vite.config.ts
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import laravel from "laravel-vite-plugin";

export default defineConfig({
  plugins: [laravel({ input: ["resources/js/app.ts"] }), vue()],
});
```

### Shared Layouts

**Inertia.js persistent layouts:**

```vue
<!-- layouts/AppLayout.vue -->
<template>
  <div>
    <nav><!-- shared navigation --></nav>
    <main>
      <slot />
    </main>
    <footer><!-- shared footer --></footer>
  </div>
</template>
```

```vue
<!-- pages/Products/Index.vue -->
<script setup lang="ts">
import AppLayout from "~/layouts/AppLayout.vue";

defineOptions({ layout: AppLayout });
</script>
```

**Island architecture shared layout**: The server template handles the shared layout (header, footer, nav). Vue islands only control interactive sections within the server-rendered page.

## Output Format

Consuming workflow skills depend on this structure.

```
## Monolith Integration Design

**Backend:** {Rails | Django | Laravel}
**Mount strategy:** {Inertia.js | Islands | Widget | Full SPA}
**Asset pipeline:** {Vite | Webpack}

### Integration Points

| Page/Section       | Strategy   | Vue Component         | Data Source            |
| ------------------ | ---------- | --------------------- | ---------------------- |
| /products          | Inertia    | Products/Index.vue    | Controller props       |
| /products/:id      | Islands    | ReviewSection.vue     | API fetch              |
| /checkout (widget) | Widget     | CartWidget.vue        | data-* attributes      |

### Shared Layout

| Element    | Handled By        | Notes                           |
| ---------- | ----------------- | ------------------------------- |
| Navigation | {Server | Vue}    | {persistent layout | template}  |
| Footer     | {Server | Vue}    | {persistent layout | template}  |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Full SPA mode when only parts of pages need interactivity (over-engineering)
- Inertia.js with Django (limited community support - use islands instead)
- Duplicating layouts in both server templates and Vue (single source of truth)
- Manual CSRF token handling when Inertia.js handles it automatically
- Loading the entire Vue bundle on pages with no Vue components
- Mixing jQuery and Vue on the same DOM elements (unpredictable behavior)
- Serving Vue assets without proper cache headers (stale bundles after deploy)
- Widget embedding with heavy state management (use Inertia or full SPA instead)
