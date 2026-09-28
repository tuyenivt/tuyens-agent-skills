---
name: domain-surface-discovery
description: Inventory a service repo's entry points: screens, routes, jobs, listeners, webhooks, events out, outbound clients, tables; propose capabilities.
metadata:
  category: domain
  tags: [domain, surfaces, discovery, routes, jobs, listeners, webhooks, inventory]
user-invocable: false
---

# Domain Surface Discovery

Finds every place a business flow can start, leave, or land in one service repository, writes it as the repo's `surfaces/<repo>.md` per `domain-kb-layout`, and proposes which business capability each trigger belongs to. Stack-agnostic: it recognises surfaces by what the code does and uses framework knowledge only to know where to look first.

## When to Use

- `task-domain-sync` Discover pass, over every repo on every run; inventories are rewritten for repos whose files changed or whose rows changed
- Standalone: one repo directory named by the user

## Inputs

| Input                 | Required | Notes                                                                                                                              |
| --------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Repo                  | yes      | `repos/<repo>/` and its stack note from `_index/sync-state.json` (`unknown stack` is accepted)                                      |
| Scope                 | no       | The repo's `Scope` cell from `CLAUDE.md` `## Repos`: `all` (default), or `include=<regex>` on repo-relative paths, optionally `; tables=<regex>` on table names |
| Other repos           | no       | The other `repos/<repo>/` directories in scope, with their inventories when already discovered this run; needed to tell `internal api` from `public api` and to give a screen its backend's capability |
| Existing inventory    | no       | `surfaces/<repo>.md` from the last sync; `Used by flows` and `## Notes` are carried for rows whose surface persists                 |
| Capability table      | no       | `CLAUDE.md` `## Capabilities` rows and the existing `capabilities/` ids with each `capability.md` `aliases`                          |
| Unmapped changes      | no       | Rows of ATLAS `## Unmapped changes` whose file sits under this repo; rows for other repos are left to their own pass                |

## Rules

- **Scope is applied before any row is written.** A surface whose registration file does not match `include` is not a row and is counted under `skipped by scope`; a table whose name does not match `tables` is not a row. A file outside the pattern whose content clearly belongs to the same business area (a handler the in-scope router mounts, a migration for an in-scope table) is included, and the summary names it under `Scope judgement`. `all` skips nothing.
- **A surface is evidence in code, cited `file:line`**, and one row per distinct kind and surface string. Kinds and their evidence:

| Kind             | Evidence                                                                                                                         | Surface string                                                     |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| ui screen        | A page a frontend router serves, or a server route that renders HTML for a browser                                                | The full path as routed (`/orders/[id]/refund`)                    |
| webhook in       | A route an external system calls back: its handler verifies a signature over the request body or a per-sender shared secret, or its path names `webhook` or `callback`; a bearer or session check alone is auth, not a webhook | `METHOD /full/path`                              |
| internal api     | Any other route whose path or client name another repo in scope calls                                                             | `METHOD /full/path`                                                |
| public api       | Any other route                                                                                                                   | `METHOD /full/path`                                                |
| schedule         | A statement binding a time (cron, interval) to a callable                                                                          | The job or function name                                           |
| message          | A statement binding a topic, queue, or event type to a handler                                                                     | `event_type=<x>`, `<topic>`, or `<queue>` as bound                 |
| webhook out      | An outbound request to a URL the code reads per customer, partner, or tenant from data or config                                  | `METHOD <url template>`                                            |
| event out        | A publish to a topic, queue, or bus                                                                                                | `event_type=<x>` or `<topic>` as published                         |
| outbound client  | Any other outbound request: a base URL from config, a hardcoded URL, or a vendor SDK operation                                     | `METHOD <path> (<base config key>)`, `METHOD <host><path>` for a hardcoded URL, or `<sdk>.<operation>` |
| table            | The schema file (`schema.rb`, `structure.sql`, `schema.prisma`, DDL), else the migrations net of later drops, else an ORM model declaration | The table name                                          |

- **Precedence for a route:** `ui screen`, then `webhook in`, then `internal api`, then `public api`. With no other repos supplied, every route that is neither `ui screen` nor `webhook in` is `public api` and the block says so. A registration bound to no method (`HandleFunc`, `app.all`, `match via: :all`, a default-export API file) is one row as `ANY /full/path`.
- **The full path is composed** from every statement that contributes to it (namespace, controller prefix, router mount, class-level mapping), written with the framework's own parameter syntax (`:id`, `{id}`, `[id]`). A file-based router's file is its registration and is cited at line 1; a route only a convention would add, with no file or statement expressing it, is not a row. A DSL statement that binds several actions cites the same line for each surface.
- **Not surfaces:** helpers, wrappers, tests, models that do not create tables, a job class only app code enqueues (it is a hop inside a flow), and operational routes (`/healthz`, `/health`, `/ready`, `/live`, `/metrics`, `/ping`), which are named in the block and never rowed.
- **Capabilities.** Each trigger (ui screen, webhook in, internal api, public api, schedule, message) is assigned to exactly one capability, in this order: `infrastructure` when the trigger is authentication or token issuance (`/oauth/*`, login, session, API-key management), API documentation or schema pages, an admin or background-job console, staff or role management, or maintenance status; the capability of the card whose Trigger Surface it already is; the first `## Capabilities` row whose pattern matches its surface (a pattern is a literal surface, or a prefix ending in `*` that matches any remainder, `/` included); an existing capability id or alias equal to the trigger's business noun; otherwise a proposed capability named by that noun (kebab-case). `infrastructure` is never proposed as a capability and gets no `capability.md`; its rows stay in the inventory and serve as hops. The business noun is, in order, the handler module's name; for a ui screen the capability of the first backend surface its data calls hit, so screens never form a capability of their own; for a bare function the directory it lives in; and when that name is technical (`api`, `handlers`, `controllers`, `pages`) the entity the handler writes, or reads when it writes nothing. Outbound kinds and tables carry no capability. The first Discover pass writes one `## Capabilities` row per proposed capability with the patterns it derived: a prefix wildcard for route paths (`POST /api/orders/*`), literal strings for schedules and event types (`ReconcileRefundsJob`, `event_type=order.refunded`).
- **External callers are named, not rowed.** A client base URL that points outside the repos, a webhook sender the handler verifies, or a caller name in an auth allow-list is collected as an external caller name for the summary, so the Link pass can match `consumers/`; it is a row only when it is also an outbound surface of this repo.
- **Rows persist by kind and surface string.** A row matching one in the existing inventory keeps its `Used by flows`; any other row's cell reads `none - not yet traced` until the Analyse pass fills it, and a row no flow cites after Analyse reads `none - no flow cites it`. `## Notes` is carried; frontmatter `id` is `surface-<repo>`, `sources` is `<repo>@` plus the first 7 characters of `git rev-parse HEAD`, `synced` today, `freshness: current`, `aliases` carried.
- **Nothing invented.** A surface the stack note suggests but the search does not find is not a row; a table named only in a comment is not a row.

## Patterns

### Where to look first, by stack note

| Stack note says       | Routes and screens                                                        | Schedules and listeners                                        | Tables                             |
| --------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------- |
| Rails                 | `config/routes.rb`, controllers, `app/views` for HTML routes              | `config/recurring.yml`, `config/schedule.rb`, `config/schedule*.yml`, `app/jobs`, `app/consumers`, `app/workers` | `db/schema.rb` or `db/structure.sql`, `db/migrate` |
| Express, NestJS       | router registrations, `@Controller` plus method decorators                | scheduler registrations, queue processors, consumer classes     | migrations, schema files, ORM entities |
| Spring                | `@RequestMapping` family, class-level mappings                            | `@Scheduled`, `@KafkaListener`, `@SqsListener`, `@RabbitListener` | Flyway or Liquibase, JPA entities |
| Gin, net/http         | `r.GET`, `r.POST`, groups, `http.HandleFunc`                              | cron libraries, queue receive loops with a `switch` on type     | migration files, SQL DDL          |
| FastAPI, Django       | `@app.get` and `@router.get` families, `include_router(prefix=)`, `urls.py` | Celery `@shared_task`, `@app.task`, `beat_schedule`, consumer modules | Alembic, Django migrations   |
| Next.js               | `app/**/page.tsx` and `pages/**` (screens); `app/**/route.ts`, `pages/api/**` (routes) | `vercel.json` `crons`                             | `prisma/schema.prisma`, `prisma/migrations`, Drizzle schema |
| React Router, Vite    | `createBrowserRouter`, `<Route path>`, `app/routes.ts` (screens)          | none                                                           | none                               |
| unknown stack         | grep for HTTP verbs with path strings, cron expressions, topic or queue strings, `CREATE TABLE` | same                                    | same                               |

The table says where to start, not where to stop: every kind is searched across the whole repo before it is reported absent.

Bad - a helper reported as a route, a publish reported as a client:

```
| public api | createRefund | repos/payments/src/services/refund.service.ts:12 | payments | |
| outbound client | SNS publish | repos/payments/src/events/publisher.ts:8 | - | |
```

Good - the registration reported, the event named:

```
| internal api | POST /payments/refunds | repos/payments/src/routes/refunds.ts:9 | payments | none - not yet traced |
| event out | event_type=payment.refund.completed | repos/payments/src/services/refund.service.ts:41 | - | none - not yet traced |
```

### Unmapped changes

For each supplied row under this repo, check whether the file now hosts a surface. A file that does is reported under `Placed`; one that does not stays with the consumer.

## Output Format

`surfaces/<repo>.md` exactly as `domain-kb-layout` defines it (frontmatter with `id: surface-<repo>`, `# {repo} surfaces`, `## Surfaces` with `| Kind | Surface | Enforced at | Capability | Used by flows |`, `Capability` filled for trigger rows, `infrastructure` included, and `-` otherwise, `## Notes`), then this summary block:

```
- **Repo:** {repo} ({stack note})
- **Scope:** {all | include=<regex>{; tables=<regex>}} - {n} files in, {n} surfaces skipped by scope
- **Scope judgement:** {file - why it belongs | none}
- **Surfaces:** {n} ({n} ui screen, {n} webhook in, {n} internal api, {n} public api, {n} schedule, {n} message, {n} webhook out, {n} event out, {n} outbound client, {n} table)
- **Routes classified:** {with other repos | no other repos supplied - non-screen, non-webhook routes are public api}
- **Operational routes skipped:** {paths | none}
- **Capabilities:**
  - {capability} ({from table | existing | proposed | infrastructure}): {trigger, trigger}
- **External callers named:** {names | none}
- **Placed:**
  - {file} -> {kind}: {surface}{ (capability)}
```

`Placed` reads `- none - no unmapped changes supplied` or `- none - no supplied file hosts a surface` when empty; the capability suffix appears only for trigger kinds. Row order inside `## Surfaces` is by kind in the table order above, then by surface string. The inventory is written by the consuming workflow; standalone, both blocks are emitted inline.

## Avoid

- Reporting a wrapper, helper, or test double as a surface
- Adding a route only a framework convention would create, with no file or statement expressing it
- Classifying a route `internal api` on the strength of its name rather than a caller found in another repo
- Naming a capability after a technical folder when its handlers write a business entity
- Proposing a capability for auth, documentation, admin, staff, or maintenance plumbing
- Rowing a surface whose registration file the scope excludes without naming it under Scope judgement
