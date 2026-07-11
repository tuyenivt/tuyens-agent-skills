---
name: vue-monolith-integration
description: Integrate Vue into Rails/Django/Laravel monoliths via Inertia.js, islands, widgets, or full SPA with correct asset pipeline and layouts.
metadata:
  category: frontend
  tags: [vue, rails, django, laravel, inertia, monolith, integration, asset-pipeline]
user-invocable: false
---

# Vue Monolith Integration

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding Vue to an existing Rails, Django, or Laravel monolith
- Choosing between Inertia.js, islands, widgets, or full SPA
- Configuring Vite for the monolith's asset pipeline
- Migrating server-rendered templates to Vue incrementally

## Rules

- Detect backend framework before choosing a strategy
- One mount strategy per page; mixing Inertia and islands on the same route is undefined
- Layout owner is single-source: either the server template or a Vue persistent layout, never both
- Inertia.js handles CSRF, history, and partial reloads - do not reimplement
- Islands/widgets that call backend endpoints must send the monolith's CSRF token (Rails: `csrf-token` meta tag; Django: `csrftoken` cookie -> `X-CSRFToken` header; Laravel: `XSRF-TOKEN` cookie)

## Patterns

### Strategy Selection

| Strategy   | Use When                                                            | Backend Fit         |
| ---------- | ------------------------------------------------------------------- | ------------------- |
| Inertia.js | Replacing server views with Vue pages                               | Rails, Laravel      |
| Islands    | Page-specific interactive section; one entry, one mount per page    | Django, Rails, Laravel |
| Widget     | Reusable component mounted on many pages via data attributes        | Any                 |
| Full SPA   | Entire frontend is Vue, backend is API                              | Any (API mode)      |

Inertia.js has no first-party Django adapter; prefer islands there. Unknown or other backend (e.g. Spring, .NET MVC): use Widget or Full SPA; Inertia only if a maintained community adapter exists.

### Inertia.js (Rails)

```ruby
# Gemfile
gem "inertia_rails"

# config/initializers/inertia_rails.rb
InertiaRails.configure { |c| c.version = ViteRuby.digest }

# app/controllers/products_controller.rb
class ProductsController < ApplicationController
  def index
    render inertia: "Products/Index", props: {
      products: Product.all.as_json(only: [:id, :name, :price])
    }
  end
end
```

```vue
<!-- app/frontend/pages/Products/Index.vue -->
<script setup lang="ts">
import { Head, Link } from "@inertiajs/vue3";
defineProps<{ products: Array<{ id: number; name: string; price: number }> }>();
</script>

<template>
  <Head title="Products" />
  <Link v-for="p in products" :key="p.id" :href="`/products/${p.id}`">
    {{ p.name }}
  </Link>
</template>
```

### Inertia.js (Laravel)

```php
// app/Http/Controllers/ProductController.php
public function index()
{
    return Inertia::render('Products/Index', [
        'products' => Product::paginate(20),
    ]);
}
```

```ts
// resources/js/app.ts
import { createApp, h } from "vue";
import { createInertiaApp } from "@inertiajs/vue3";
import { resolvePageComponent } from "laravel-vite-plugin/inertia-helpers";

createInertiaApp({
  resolve: (name) =>
    resolvePageComponent(`./Pages/${name}.vue`, import.meta.glob("./Pages/**/*.vue")),
  setup: ({ el, App, props, plugin }) =>
    createApp({ render: () => h(App, props) }).use(plugin).mount(el),
});
```

### Islands (Django)

```django
{% load django_vite %}
{% vite_hmr_client %}
<h1>{{ product.name }}</h1>
<div id="reviews-app" data-product-id="{{ product.id }}"></div>
{% vite_asset 'src/islands/reviews.ts' %}
```

```ts
// src/islands/reviews.ts
import { createApp } from "vue";
import ReviewSection from "./ReviewSection.vue";

const el = document.getElementById("reviews-app");
if (el) createApp(ReviewSection, { productId: el.dataset.productId }).mount(el);
```

### Widget (Any Backend)

```ts
// src/widgets/configurator.ts
import { createApp } from "vue";
import ProductConfigurator from "./ProductConfigurator.vue";

document.querySelectorAll<HTMLElement>("[data-vue-configurator]").forEach((el) => {
  createApp(ProductConfigurator, {
    productId: el.dataset.productId,
    options: JSON.parse(el.dataset.options || "{}"),
  }).mount(el);
});
```

```html
<div data-vue-configurator data-product-id="123" data-options='{"colors":["red","blue"]}'></div>
```

### Asset Pipeline

```ts
// vite.config.ts - Rails (vite_rails)
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import RubyPlugin from "vite-plugin-ruby";
export default defineConfig({ plugins: [vue(), RubyPlugin()] });
```

```ts
// vite.config.ts - Laravel
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import laravel from "laravel-vite-plugin";
export default defineConfig({
  plugins: [laravel({ input: ["resources/js/app.ts"] }), vue()],
});
```

```python
# settings.py - Django (django-vite)
DJANGO_VITE = {"default": {"dev_mode": DEBUG, "dev_server_port": 5173}}
```

### Shared Layout (Inertia persistent)

```vue
<!-- pages/Products/Index.vue -->
<script setup lang="ts">
import AppLayout from "~/layouts/AppLayout.vue";
defineOptions({ layout: AppLayout });
</script>
```

For islands and widgets the server template owns the layout; Vue controls only mounted regions.

## Output Format

```
## Monolith Integration Design

**Backend:** {Rails | Django | Laravel | other (name it)}
**Mount strategy:** {Inertia.js | Islands | Widget | Full SPA}
**Asset pipeline:** Vite ({vite-plugin-ruby | laravel-vite-plugin | django-vite})

### Integration Points

| Page/Section  | Strategy | Vue Component      | Data Source      |
| ------------- | -------- | ------------------ | ---------------- |
| /products     | Inertia  | Products/Index.vue | Controller props |
| /products/:id | Islands  | ReviewSection.vue  | API fetch        |

### Layout Ownership

- Navigation: {Server template / Vue persistent layout}
- Footer: {Server template / Vue persistent layout}

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Inertia.js on Django (no first-party adapter).
- Loading the Vue bundle on pages with no mount points.
- Mixing jQuery and Vue on the same DOM nodes.
- Heavy state management inside widgets - escalate to Inertia or SPA.
