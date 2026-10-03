---
name: domain-surface-discovery
description: "Inventory a service repo's entry points: screens, routes, jobs, listeners, webhooks, events out, outbound clients, tables; propose capabilities."
metadata:
  category: domain
  tags: [domain, surfaces, discovery, routes, jobs, listeners, webhooks, inventory]
user-invocable: false
---

# Domain Surface Discovery

> Load `Use skill: domain-kb-layout` first and read at least its Rules and these Patterns sections: Generated-file frontmatter, CLAUDE.md (the `## Capabilities` table), ATLAS.md (`## Unmapped changes`), Flow card (the Trigger block), and the Ledger, playbook, contracts, debt, surfaces entry for `surfaces/<repo>.md`. It owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Finds every place a business flow can start, leave, or land in one service repository, emits it as the repo's `surfaces/<repo>.md`, and proposes which business capability each trigger belongs to. Stack-agnostic: it recognises surfaces by what the code does and uses framework knowledge only to know where to look first.

## When to Use

- `task-domain-sync` Discover pass (`init`, `update`), over every repo; inventories are rewritten for repos whose files changed or whose rows changed
- Standalone: one repo directory named by the user

## Inputs

| Input                 | Required | Notes                                                                                                                              |
| --------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Repo                  | yes      | `repos/<repo>/` and its stack note from `_index/sync-state.json` (`unknown stack` is accepted)                                      |
| Scope                 | no       | The repo's `Scope` cell from `CLAUDE.md` `## Repos` with table escapes removed (`\|` read as a pipe): `all` (default), or `include=<regex>` on repo-relative paths, optionally `; tables=<regex>` on table names |
| Other repos           | no       | The other `repos/<repo>/` directories in scope, with their inventories when already discovered this run; needed to tell `internal api` from `public api` and to give a screen its backend's capability |
| Existing inventory    | no       | `surfaces/<repo>.md` from the last sync; `Used by flows` is carried for rows whose surface persists, and the file's `## Notes` whole                 |
| Capability table      | no       | `CLAUDE.md` `## Capabilities` rows, the existing `capabilities/` ids with each `capability.md` `aliases`, and each card's Trigger `Surface` and `capability` |
| Unmapped changes      | no       | Rows of ATLAS `## Unmapped changes` whose file sits under this repo; rows for other repos are left to their own pass                |

## Rules

- **Scope is applied before any row is written.** A surface whose registration file does not match `include` is not a row and is counted under `skipped by scope`; a table is in scope when its name matches `tables`, whatever file declares it, or, with no `tables`, when a file matching `include` reads or writes it (its row still cites the declaring file); one out of scope is counted there too. `{n} files in` counts the tracked files `include` matches, every tracked file for `all`. A file outside the pattern that belongs to the same business area (a handler the in-scope router mounts, the schedule table or routes file that binds an in-scope handler, a migration for an in-scope table) is included without counting toward `{n} files in`, and the summary names each under `Scope judgement`. `all` skips nothing.
- **A surface is evidence in code, cited `file:line`**, and one row per distinct kind and surface string. Kinds and their evidence:

| Kind             | Evidence                                                                                                                         | Surface string                                                     |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| ui screen        | A page a frontend router serves, or a server route that renders HTML for a browser                                                | The full path as routed (`/orders/[id]/refund`)                    |
| webhook in       | A route an external system calls back: its handler verifies a signature over the request body or a per-sender shared secret, or its path names `webhook`; a bearer or session check alone is auth, not a webhook, and an OAuth or OIDC `/callback` redirect is authentication | `METHOD /full/path`                              |
| internal api     | Any other route whose path or client name another repo in scope calls                                                             | `METHOD /full/path`                                                |
| public api       | Any other route                                                                                                                   | `METHOD /full/path`                                                |
| schedule         | A statement binding a time (cron, interval) to a callable; a Vercel cron's target route is this row only, not also a route | The job or function name (`Class.method` for a Spring `@Scheduled` method, the beat entry key for Celery); the schedule key for an entry with no class (`command:`), the path for a Vercel cron |
| message          | A statement binding a topic, queue, or event type to a handler, cited where the name is bound (a dispatch `case` when nothing else names it); a queue or job class only this repo's own code enqueues is a hop inside a flow, not a row | `event_type=<x>`, `<topic>`, or `<queue>` as bound      |
| webhook out      | An outbound request to a URL the code reads per customer, partner, or tenant from data or config                                  | `METHOD <url template>`                                            |
| event out        | A publish to a topic, queue, or bus                                                                                                | `event_type=<x>` or `<topic>` as published                         |
| outbound client  | Any other outbound request: a base URL from config, a hardcoded URL, or a vendor SDK operation                                     | `METHOD <path> (<base config key>)`, `METHOD (<config key>)` when the whole URL is one config value, `METHOD <host><path>` for a hardcoded URL, or `<sdk>.<operation>` |
| table            | The schema file (`schema.rb` and `*_schema.rb`, `structure.sql`, `schema.prisma` or `prisma/schema/*.prisma`, DDL), else the migrations net of later drops, else an ORM model declaration | The table name as the database holds it (`@@map`, `db_table`, Django's `<app_label>_<modelclass>` default with the class name lowercased and unbroken, JPA `@Table(name=)` else the configured naming strategy's rendering of the entity name, snake_case under Spring Boot), after any rename |

- **Precedence for a route:** `ui screen`, then `webhook in`, then `internal api`, then `public api`. With no other repos supplied, every route that is neither `ui screen` nor `webhook in` is `public api` and the block says so. A registration bound to no method (`app.all`, `match via: :all`, a Go pattern with no method, a default-export API file) is one row as `ANY /full/path`; a Go 1.22+ pattern (`"POST /orders/{id}"`) carries its method; a Django class-based view gives one row per business method it or its mixins implement (`get`, `post`, `put`, `patch`, `delete`; never `head`, `options`, `trace`), a view rendering HTML being one `ui screen` row instead; a DRF viewset one row per route its router builds (list and create on the collection path, retrieve, update, partial_update, and destroy on the detail path, each `@action`); a Next.js `route.*` file one row per exported method function; and a React Router resource route `GET` for its `loader` and `POST` for its `action`.
- **The full path is composed** from every statement or config key that contributes to it (for example namespace, controller prefix, router mount, class-level mapping, `server.servlet.context-path`, `spring.mvc.servlet.path`, `setGlobalPrefix` and URI versioning, Next.js `basePath`, React Router `basename`), written with the framework's own parameter syntax (`:id`, `{id}`, `[id]`). In the Next.js App Router, route groups `(x)` and parallel-route slots `@x` are not path segments, and `_private` folders and intercepting `(.)x`, `(..)x`, `(..)(..)x`, and `(...)x` folders are not routes at all; a server action is not a surface. In React Router `flatRoutes()`, `($x)` is an optional segment, a leading `_` a pathless layout (`_index` an index route), and a trailing `_` escapes nesting. A file-based router's file is its registration and is cited at line 1; a route only a convention would add, with no file or statement expressing it, is not a row. A DSL statement that binds several actions cites the same line for each surface, one row per method it binds (`PATCH` and `PUT` two rows), and an action with no handler method is not a row.
- **Not surfaces:** helpers, wrappers, tests, models that do not create tables, a job class only app code enqueues (it is a hop inside a flow), operational routes (`/healthz`, `/health`, `/ready`, `/readyz`, `/live`, `/livez`, `/up`, `/metrics`, `/ping`, `/actuator/**`), framework housekeeping schedules (Solid Queue's `clear_solid_queue_finished_jobs`), and framework bookkeeping tables (`schema_migrations`, `ar_internal_metadata`, `solid_queue_*`, `solid_cache_entries`, `solid_cable_messages`, `django_*` and, with a Django manifest, `auth_*`, `flyway_schema_history`, `alembic_version`, `_prisma_migrations`); the operational routes and housekeeping schedules are named in the block under `Operational routes and housekeeping schedules skipped`, none is rowed.
- **Capabilities.** Each trigger (ui screen, webhook in, internal api, public api, schedule, message) is assigned to exactly one capability, by the first of these that answers, the tag in parentheses naming it in the summary: `infrastructure` when the trigger is authentication or token issuance (`/oauth/*`, login, session, OAuth callbacks, API-key management), API documentation or schema pages, an admin or background-job console, staff or role management, or maintenance status (`infrastructure`); the first `## Capabilities` row whose pattern matches its surface (`table row`); the capability of the card whose Trigger Surface it already is, or that the layout's Ids rule matches to it by reverse-index majority when the surface string changed (`card`); the capability the existing inventory row for this surface carries (`inventory`); for a ui screen, the capability of the first backend surface its data calls hit, found in the other repos directly when their inventory is not written yet (`screen`); an existing capability id or alias equal to the trigger's business noun (`existing`); the capability of other triggers in this repo whose handlers write, or only read, the same entity (`entity`); otherwise a proposed capability named by that noun, kebab-case and singular (`proposed`). A pattern is a literal surface, or a prefix ending in `*` that matches any remainder, `/` included (`POST /api/orders*` matches `POST /api/orders`, every path below it, and `POST /api/orders-export`). `infrastructure` is never proposed as a capability and gets no `capability.md`; its rows stay in the inventory and serve as hops. The business noun is, in order, the handler module's name without a `Job`, `Worker`, `Controller`, `Consumer`, `Listener`, `Handler`, `Processor`, `Task`, `Subscriber`, `Mailer`, `Resolver`, `Service`, or `View` suffix; for a bare function the directory it lives in; and when that name is technical (`api`, `app`, `src`, `internal`, `http`, `server`, `handler`, `handlers`, `controllers`, `views`, `pages`, `page`, `route`, `routes`, `webhooks`, `consumer`, `consumers`, `jobs`, `workers`, `tasks`, `cron`, or a dynamic or group folder such as `[id]` or `(shop)`) the entity the handler writes, or reads when it writes nothing; nouns compare in the singular (`orders` equals `order`). Outbound kinds and tables carry no capability. Every capability line in the summary carries one literal pattern per trigger, its surface as written (`POST /api/orders/:id/refund`, `/orders/[id]/refund`, `ReconcileRefundsJob`, `event_type=order.refunded`; a person widens them to prefixes); the consuming workflow writes them to `## Capabilities` when that table has no rows at the start of the run, every repo's lines in repo order and the `infrastructure` line left out, and standalone they are only reported. A trigger the table assigns to a capability other than its card's `capability:` takes the table's, and its capability line adds `moves card: <capability>/<flow>` for the consuming workflow to move the card there.
- **External callers are named, not rowed.** A client base URL that points outside the repos, a webhook sender the handler verifies, or a caller name in an auth allow-list is collected as an external caller name for the summary, so the Link pass can match `consumers/`; it is a row only when it is also an outbound surface of this repo. A scheduler platform (Vercel cron) or the framework itself is not an external caller.
- **Rows persist by surface string.** A row matching one in the existing inventory keeps its `Used by flows`, even when its kind changed; any other row's cell reads `none - not yet traced` until the Analyse pass fills it, and a row no flow cites after Analyse reads `none - no flow cites it`. `## Notes` is carried; frontmatter `generated: domain-sync`, `id` is `surface-<repo>`, `sources` is `<repo>@` plus the first 7 characters of `git -C repos/<repo> rev-parse HEAD`, `synced` today, `freshness: current`, `aliases` carried.
- **Nothing invented.** A surface the stack note suggests but the search does not find is not a row; a table named only in a comment or in application SQL (no schema file, migration, or model declares it) is not a row.

## Patterns

### Where to look first, by stack note

| Stack note says       | Routes and screens                                                        | Schedules and listeners                                        | Tables                             |
| --------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------- |
| Rails                 | `config/routes.rb`, controllers, `app/views` for HTML routes              | `config/recurring.yml`, `config/schedule.rb`, `config/schedule*.yml`, `config/sidekiq.yml` `:scheduler:`, `app/jobs`, `app/consumers`, `app/workers` | `db/schema.rb` or `db/structure.sql`, `db/migrate` |
| Express, NestJS       | router registrations, `@Controller` plus method decorators                | scheduler registrations, queue processors, consumer classes     | migrations, schema files, ORM entities |
| Spring                | `@RequestMapping` family, class-level mappings                            | `@Scheduled`, `@KafkaListener`, `@SqsListener`, `@RabbitListener` | Flyway or Liquibase, JPA entities |
| Gin, net/http         | `r.GET`, `r.POST`, groups, `http.HandleFunc` and `mux.Handle` patterns    | cron libraries, queue receive loops with a `switch` on type     | migration files, SQL DDL          |
| FastAPI, Django       | `@app.get` and `@router.get` families, `APIRouter(prefix=)`, `include_router(prefix=)`, `app.mount`, `urls.py` | Celery `@shared_task`, `@app.task`, `beat_schedule` and `CELERY_BEAT_SCHEDULE`, consumer modules | Alembic, Django migrations   |
| Next.js               | `app/**/page.*` and `pages/**` except `pages/api/**`, `_app`, `_document`, `_error`, `404`, `500` (screens); `app/**/route.*`, `pages/api/**` (routes); `src/app/` and `src/pages/` alike | `vercel.json` `crons`                             | `prisma/schema.prisma`, `prisma/migrations`, Drizzle schema |
| React Router, Vite    | `createBrowserRouter`, `<Route path>`, `app/routes.ts` or `flatRoutes()` files (screens); a route module exporting `action` or `loader` with no default export is a route | none                    | migrations, ORM schema when present |
| unknown stack         | grep for HTTP verbs with path strings, cron expressions, topic or queue strings, `CREATE TABLE` | same                                    | same                               |

The table says where to start, not where to stop: every kind is searched across the whole repo before it is reported absent.

Bad - a helper reported as a route, a publish reported as a client:

```
| public api | createRefund | repos/payments/src/services/refund.service.ts:12 | payments | |
| outbound client | SNS publish | repos/payments/src/events/publisher.ts:8 | - | |
```

Good - the registration reported, the event named (a `## Capabilities` row `payments | POST /payments/refunds*` gives the capability):

```
| internal api | POST /payments/refunds | repos/payments/src/routes/refunds.ts:9 | payments | none - not yet traced |
| event out | event_type=payment.refund.completed | repos/payments/src/services/refund.service.ts:41 | - | none - not yet traced |
```

### Unmapped changes

For each supplied row under this repo, check whether the file now hosts a surface or holds the callable a surface binds (a job class a schedule names). A file that does is reported under `Placed`; one that does not is not reported.

## Output Format

`surfaces/<repo>.md` exactly as `domain-kb-layout` defines it (frontmatter with `id: surface-<repo>`, `# {repo} surfaces`, `## Surfaces` with `| Kind | Surface | Enforced at | Capability | Used by flows |`, `Capability` filled for trigger rows, `infrastructure` included, and `-` otherwise, `## Notes`), then this summary block:

```
- **Repo:** {repo} ({stack note})
- **Scope:** {all | include=<regex>{; tables=<regex>}} - {n} files in, {n} surfaces skipped by scope
- **Scope judgement:** {file - why it belongs; file - why it belongs | none}
- **Surfaces:** {n} ({n} ui screen, {n} webhook in, {n} internal api, {n} public api, {n} schedule, {n} message, {n} webhook out, {n} event out, {n} outbound client, {n} table)
- **Routes classified:** {with other repos | no other repos supplied - non-screen, non-webhook routes are public api}
- **Operational routes and housekeeping schedules skipped:** {paths and names | none}
- **Capabilities:**
  - {capability}: {trigger ({table row | card | inventory | screen | existing | entity | proposed | infrastructure}), ...}; patterns: {pattern, pattern | none}{; moves card: <capability>/<flow>}
- **External callers named:** {names | none}
- **Placed:**
  - {file} -> {kind}: {surface}{ (capability)}
```

`Placed` reads `- none - no unmapped changes supplied` or `- none - no supplied file hosts a surface` when empty; the capability suffix appears only for trigger kinds. Row order inside `## Surfaces` is by kind in the Kinds table order, then by surface string. `infrastructure` lines read `patterns: none`. The consuming workflow writes the inventory; standalone, both blocks are emitted inline.

## Avoid

- Reporting a wrapper, helper, or test double as a surface
- Adding a route only a framework convention would create, with no file or statement expressing it
- Classifying a route `internal api` on the strength of its name rather than a caller found in another repo
- Naming a capability after a technical folder when its handlers write a business entity
- Proposing a capability for auth, documentation, admin, staff, or maintenance plumbing
- Rowing a surface whose registration file the scope excludes without naming it under Scope judgement
