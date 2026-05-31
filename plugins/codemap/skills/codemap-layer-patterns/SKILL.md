---
name: codemap-layer-patterns
description: Directory-name to architectural layer mapping table across Rails, Django, Spring, .NET, Go, Rust, React, Vue, Angular. Used during layer assignment.
metadata:
  category: core
  tags: [codemap, layers, architecture, mapping]
user-invocable: false
---

# Codemap Layer Patterns

> Load `Use skill: stack-detect` first to determine the project stack.
> Load `Use skill: codemap-schema` for the canonical 6-layer enum.

Heuristic mapping from directory naming conventions to the 6 codemap layers (`entry`, `api`, `service`, `domain`, `data`, `infra`). Consumed by `task-codemap` during the layer-assignment phase.

## When to Use

- During step 6 of `codemap-build-pipeline` to assign `node.layer` to each node.
- Map by **deepest matching directory segment in the file path**, not by file name.
- A node may match multiple patterns; pick the most specific.

## Rules

1. **Patterns are hints, not rules.** Override when the project's own convention contradicts the table.
2. **Match deepest segment first.** `src/infrastructure/persistence/user_repo.rb` -> `data` (from `persistence`), not `infra` (from `infrastructure`).
3. **No match -> omit layer.** Better to leave `layer` undefined than to guess.
4. **Frontend trees collapse.** SPAs and SSR apps rarely have all 6 layers; map their nodes to `entry` (routes, pages), `api` (data-fetching clients), `service` (stores, composables, hooks with logic), `domain` (typed models, validators), `data` (none unless server-side), `infra` (build config, observability wrappers).

## Patterns

### Cross-stack directory map

| Directory segment | Layer |
| --- | --- |
| `cmd/`, `main/`, `bin/`, `entrypoint/`, `bootstrap/` | `entry` |
| `controllers/`, `controller/`, `handlers/`, `handler/`, `routes/`, `routers/`, `api/`, `resolvers/`, `endpoints/`, `actions/` | `api` |
| `services/`, `service/`, `usecases/`, `use_cases/`, `interactors/`, `application/`, `commands/`, `queries/`, `workflows/` | `service` |
| `domain/`, `domains/`, `models/`, `entities/`, `aggregates/`, `value_objects/`, `policies/`, `invariants/` | `domain` |
| `repositories/`, `repository/`, `repos/`, `dao/`, `daos/`, `persistence/`, `db/`, `database/`, `migrations/`, `mappers/`, `orm/` | `data` |
| `infrastructure/`, `infra/`, `adapters/`, `gateways/`, `clients/`, `integrations/`, `external/`, `messaging/`, `queues/`, `pubsub/`, `observability/`, `logging/`, `metrics/`, `tracing/`, `config/`, `configs/`, `bootstrap/` (when alongside infrastructure) | `infra` |

### Spring Boot (Java / Kotlin)

| Segment | Layer |
| --- | --- |
| `*Application.java/.kt`, `config/`, `Application.kt` | `entry` |
| `controller/`, `web/`, `rest/`, `api/` | `api` |
| `service/`, `application/`, `usecase/` | `service` |
| `domain/`, `model/` (in DDD layout) | `domain` |
| `repository/`, `dao/`, `persistence/`, `entity/` (JPA entities are data) | `data` |
| `infrastructure/`, `client/`, `messaging/`, `kafka/`, `rabbit/`, `config/` (when only beans), `actuator/` | `infra` |

### Rails

| Segment | Layer |
| --- | --- |
| `config/routes.rb`, `config/application.rb` | `entry` |
| `app/controllers/` | `api` |
| `app/services/`, `app/operations/`, `app/interactors/` | `service` |
| `app/models/` (the model layer combines domain + data in Rails - map to `domain` unless the file is a pure ActiveRecord model with no logic, then `data`) | `domain` or `data` |
| `db/migrate/`, `app/repositories/`, `app/queries/` | `data` |
| `config/initializers/`, `lib/`, `app/jobs/` (Sidekiq), `app/mailers/` | `infra` |

### Django

| Segment | Layer |
| --- | --- |
| `wsgi.py`, `asgi.py`, `urls.py` (root) | `entry` |
| `views/`, `viewsets/`, `serializers/`, `urls.py` (per app) | `api` |
| `services/`, `selectors/` (services layer convention) | `service` |
| `models/` (Django models) - map to `domain` if rich, `data` if anemic | `domain` or `data` |
| `migrations/`, `managers/`, `querysets/` | `data` |
| `settings/`, `middleware/`, `tasks/` (Celery), `signals/` | `infra` |

### FastAPI / Flask

| Segment | Layer |
| --- | --- |
| `main.py`, `app.py`, `__main__.py` | `entry` |
| `routers/`, `api/`, `endpoints/`, `views/` | `api` |
| `services/`, `crud/` (when wrapping repository calls), `usecases/` | `service` |
| `models/`, `schemas/` (Pydantic models split: business -> `domain`, DTOs -> `schema` node type, not layered) | `domain` |
| `db/`, `repositories/`, `alembic/`, `migrations/` | `data` |
| `core/`, `config/`, `dependencies/`, `middleware/` | `infra` |

### Go / Gin / Echo / Fiber

| Segment | Layer |
| --- | --- |
| `cmd/`, `main.go` | `entry` |
| `handler/`, `handlers/`, `controller/`, `api/`, `routes/` | `api` |
| `service/`, `usecase/`, `app/` | `service` |
| `domain/`, `model/`, `entity/` | `domain` |
| `repository/`, `repo/`, `store/`, `db/`, `migrations/`, `dao/` | `data` |
| `pkg/`, `internal/infrastructure/`, `client/`, `adapter/`, `config/` | `infra` |

### Rust / Axum / Actix

| Segment | Layer |
| --- | --- |
| `main.rs`, `bin/` | `entry` |
| `routes/`, `handlers/`, `api/`, `controller/` | `api` |
| `services/`, `usecase/`, `application/` | `service` |
| `domain/`, `model/`, `entities/` | `domain` |
| `repositories/`, `db/`, `persistence/`, `migrations/`, `sqlx/`, `diesel/` | `data` |
| `infra/`, `client/`, `config/`, `telemetry/` | `infra` |

### .NET / ASP.NET Core

| Segment | Layer |
| --- | --- |
| `Program.cs`, `Startup.cs` | `entry` |
| `Controllers/`, `Endpoints/`, `Minimal*.cs` | `api` |
| `Application/`, `Services/`, `UseCases/`, `Features/` (CQRS commands/queries) | `service` |
| `Domain/`, `Core/Domain/`, `Entities/` | `domain` |
| `Infrastructure/Persistence/`, `Repositories/`, `Migrations/`, `EF/`, `DbContext.cs` | `data` |
| `Infrastructure/`, `Adapters/`, `Configuration/`, `Logging/` | `infra` |

### Laravel (PHP)

| Segment | Layer |
| --- | --- |
| `public/index.php`, `bootstrap/app.php`, `routes/` | `entry` |
| `app/Http/Controllers/`, `app/Http/Requests/`, `app/Http/Resources/` | `api` |
| `app/Services/`, `app/Actions/`, `app/Jobs/` (logic side) | `service` |
| `app/Models/` - same dual rule as Rails | `domain` or `data` |
| `database/migrations/`, `app/Repositories/` | `data` |
| `config/`, `app/Providers/`, `app/Http/Middleware/`, `app/Console/Commands/` | `infra` |

### React (Next.js, Vite, Remix)

| Segment | Layer |
| --- | --- |
| `app/` (Next App Router root), `pages/` (Next Pages Router), `routes/` (Remix), `src/main.tsx` (Vite) | `entry` |
| `app/api/`, `pages/api/`, `app/(routes)/route.ts`, `loaders/`, `actions/` (server actions/loaders) | `api` |
| `hooks/`, `stores/`, `context/`, `providers/`, `services/` | `service` |
| `types/`, `models/`, `schemas/`, `validators/` | `domain` |
| `db/`, `prisma/`, `drizzle/`, `lib/db/` | `data` |
| `lib/`, `utils/`, `config/`, `instrumentation.ts`, `middleware.ts` | `infra` |

### Vue (Nuxt, Vite)

| Segment | Layer |
| --- | --- |
| `pages/`, `app.vue`, `nuxt.config.ts`, `src/main.ts` | `entry` |
| `server/api/`, `server/routes/` (Nuxt), `composables/use*Api.ts` | `api` |
| `composables/`, `stores/` (Pinia), `services/` | `service` |
| `types/`, `models/`, `schemas/` | `domain` |
| `server/db/`, `server/repositories/` | `data` |
| `plugins/`, `middleware/`, `utils/`, `config/` | `infra` |

### Angular

| Segment | Layer |
| --- | --- |
| `main.ts`, `app/app.config.ts`, `app/app.routes.ts` | `entry` |
| `*.component.ts` files at route level, `resolvers/`, `guards/` | `api` |
| `services/`, `*.service.ts`, `facades/`, `state/`, `+state/` (NgRx) | `service` |
| `models/`, `interfaces/`, `types/`, `domain/` | `domain` |
| `repositories/`, `db/`, `data-access/` | `data` |
| `interceptors/`, `config/`, `core/`, `shared/utils/` | `infra` |

## Output Format

This skill produces no artifact. Consuming workflows apply the table inline during layer assignment and emit `layer` fields on graph nodes per the `codemap-schema` contract.

Report layer-assignment summary in the build log as:

```
Layer assignment:
  entry: <count>
  api: <count>
  service: <count>
  domain: <count>
  data: <count>
  infra: <count>
  unassigned: <count>
```

If `unassigned` exceeds 25% of nodes, the build pipeline must surface this as a warning - the project layout does not match standard conventions and the user may want to inspect the unassigned nodes.

## Avoid

- Treating the table as exhaustive. Projects invent their own folder names; defer to project convention when it conflicts.
- Assigning layers based on file extension instead of directory.
- Forcing every node into a layer. Documentation, generated code, and tests legitimately have no layer.
- Mixing layer with node type. `endpoint` is a type; `api` is a layer. A controller file is `type: file` `layer: api`; its handler methods are `type: function` `layer: api`.
