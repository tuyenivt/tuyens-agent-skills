---
name: codemap-layer-patterns
description: Directory-to-layer mapping for codemap (entry/api/service/domain/data/infra) across 11 stacks - Spring, Rails, Django, FastAPI, Go, Rust, .NET, Laravel, React, Vue, Angular.
metadata:
  category: core
  tags: [codemap, layers, architecture, mapping]
user-invocable: false
---

# Codemap Layer Patterns

> Load `Use skill: stack-detect` first to determine the project stack.
> Load `Use skill: codemap-schema` for the canonical 6-layer enum.

Heuristic mapping from directory naming to the 6 codemap layers (`entry`, `api`, `service`, `domain`, `data`, `infra`). Consumed by `task-codemap` during layer assignment.

## When to Use

- During the layer-assignment phase of `codemap-build-pipeline`.

## Rules

**Precedence** (apply in order; first that resolves wins):

1. **Most specific match wins.** Collect every matching mapping - stack-specific exceptions (exact filenames like `routes.rb`, `*Application.java`, or path prefixes like `app/api/`) and cross-stack directory segments alike. The match anchored deepest in the path governs: `app/api/` beats the `app/` exception; `components/` under Next `app/` beats the `app/` exception. On equal depth, the stack-specific exception wins.
2. **Content axis** for ambiguous model dirs only - the rich-vs-anemic rule below.

For stacks not among the 11 listed, apply the cross-stack map alone - it stays authoritative without a stack block.

Then:

3. **Patterns are hints.** Defer to explicit project convention when it contradicts the table.
4. **No match -> omit `layer`.** Better undefined than guessed. Test files omit `layer` by design (tests are not a runtime layer) - exclude them from the unassigned-percentage denominator.
5. **Files inherit to their members.** Functions and classes get the same layer as their file.
6. **Frontend trees collapse.** SPAs rarely use all 6 layers - expect `data` empty unless the app has a server runtime.

## Patterns

### Cross-stack directory map (primary)

| Directory segment | Layer |
| --- | --- |
| `cmd/`, `main/`, `bin/`, `entrypoint/`, `bootstrap/` | `entry` |
| `controllers/`, `handlers/`, `routes/`, `routers/`, `api/`, `resolvers/`, `endpoints/`, `actions/` | `api` |
| `services/`, `usecases/`, `use_cases/`, `interactors/`, `application/`, `commands/`, `queries/`, `workflows/` | `service` |
| `domain/`, `models/`, `entities/`, `aggregates/`, `value_objects/`, `policies/` | `domain` |
| `repositories/`, `repos/`, `dao/`, `persistence/`, `db/`, `database/`, `migrations/`, `mappers/`, `orm/` | `data` |
| `infrastructure/`, `infra/`, `adapters/`, `gateways/`, `clients/`, `integrations/`, `messaging/`, `queues/`, `pubsub/`, `observability/`, `logging/`, `metrics/`, `tracing/`, `config/` | `infra` |

Singular and plural forms are equivalent (`controller/` = `controllers/`). Stems count too (`migrate/` = `migrations/`). A filename matching a segment stem counts as that segment (`models.py` = `models/`, `tasks.py` = `tasks/`) - single-file modules are the default layout in Django/Flask apps.

**Presentational UI** (`components/`, `views/`, `widgets/`, `ui/`) maps to `api` - it is the frontend's presentation surface. Route-level pages/components already map to `entry`/`api` per the stack blocks; leaf components join them at `api` rather than falling to `unassigned`.

### Rich-vs-anemic model rule (shared)

ORM-style model files (`models/`, `app/Models/`, `entity/`) are ambiguous - they may hold business logic or be pure persistence shells. Apply across Rails, Django, Laravel, and Spring/JPA: file with non-trivial logic -> `domain`; anemic data class -> `data`. Judge from the graph first - member `complexity` and `summary` fields (mostly `simple` field-holders -> anemic); read the source file only when the graph leaves it ambiguous.

### Stack-specific exceptions

When the cross-stack map gives the wrong answer, apply these.

**Spring (Java/Kotlin):** `*Application.{java,kt}` -> `entry`. `entity/` (JPA) -> `data`, not `domain`. `actuator/` -> `infra`.

**Rails:** `config/routes.rb`, `config/application.rb` -> `entry`. `app/models/` follows the rich-vs-anemic rule. `app/jobs/` (Sidekiq), `app/mailers/`, `config/initializers/` -> `infra`.

**Django:** `wsgi.py`, `asgi.py`, root `urls.py` -> `entry`. App-level `urls.py`, `views/`, `viewsets/`, `serializers/` -> `api`. `models/` follows the rich-vs-anemic rule. `migrations/`, `managers/`, `querysets/` -> `data`. `settings/`, `middleware/`, `signals/`, Celery `tasks/` -> `infra`.

**FastAPI/Flask:** `main.py`, `app.py`, `__main__.py` -> `entry`. `routers/` -> `api`. Pydantic split: business models -> `domain`; DTOs -> emit as `schema` node type (not layered). `alembic/` -> `data`. `core/`, `dependencies/` -> `infra`.

**Go (Gin/Echo/Fiber):** `cmd/`, `main.go` -> `entry`. `store/` -> `data`. `pkg/`, `internal/infrastructure/` -> `infra`.

**Rust (Axum/Actix):** `main.rs`, `bin/` -> `entry`. `sqlx/`, `diesel/` -> `data`. `telemetry/` -> `infra`.

**.NET (ASP.NET Core):** `Program.cs`, `Startup.cs` -> `entry`. `Minimal*.cs` -> `api`. `Features/` (CQRS) -> `service`. `DbContext.cs`, `EF/` -> `data`.

**Laravel:** `public/index.php`, `bootstrap/app.php`, `routes/` -> `entry`. `app/Http/Requests/`, `app/Http/Resources/` -> `api`. `app/Models/` follows the rich-vs-anemic rule. `app/Actions/`, `app/Jobs/` (with logic) -> `service`. `app/Providers/`, `app/Console/Commands/`, `app/Http/Middleware/` -> `infra`.

**React (Next/Vite/Remix):** Next `app/`, `pages/`, Remix `routes/`, Vite `src/main.tsx` -> `entry`. `app/api/`, `pages/api/`, route handlers, `loaders/`, server `actions/` -> `api`. `hooks/`, `stores/`, `context/`, `providers/` -> `service`. `prisma/`, `drizzle/`, `lib/db/` -> `data`. `instrumentation.ts`, `middleware.ts`, `lib/`, `utils/` -> `infra`.

**Vue (Nuxt/Vite):** `pages/`, `app.vue`, `nuxt.config.ts`, `src/main.ts` -> `entry`. `server/api/`, `server/routes/`, `composables/use*Api.ts` -> `api`. `composables/`, `stores/` (Pinia) -> `service`. `server/db/`, `server/repositories/` -> `data`. `plugins/`, `middleware/` -> `infra`.

**Angular:** `main.ts`, `app/app.config.ts`, `app/app.routes.ts` -> `entry`. Route-level `*.component.ts`, `resolvers/`, `guards/` -> `api`. `*.service.ts`, `facades/`, `state/`, `+state/` (NgRx) -> `service`. `interceptors/`, `core/` -> `infra`.

## Output Format

No artifact. Consumers apply the table inline and emit `layer` on nodes per `codemap-schema`.

Report assignment summary in the build log:

```
Layer assignment:
  entry: <count>    domain: <count>
  api: <count>      data: <count>
  service: <count>  infra: <count>
  unassigned: <count>
```

If `unassigned` exceeds 25% of nodes (test files excluded from the denominator per Rule 4), surface as a warning - the project layout does not match standard conventions.

## Avoid

- Treating the table as exhaustive. Defer to project convention on conflicts.
- Assigning layer by file extension.
- Confusing layer with node type. `endpoint` is a type; `api` is a layer. A controller file is `type: file, layer: api`; its methods are `type: function, layer: api`.
