---
name: task-domain-devenv
description: "Build a domain's local multi-service dev environment: discover repos, devenv.yaml manifest, Compose render, live and solo modes, verify."
metadata:
  category: domain
  tags: [domain, devenv, docker-compose, local-development, multi-service, e2e, worktree]
  type: workflow
user-invocable: true
---

# Domain Dev Environment

Builds `devenv/` in the knowledge-base root: one Docker Compose environment that runs the domain's services together on shared infrastructure, any of them from a developer's own branch or worktree with live reload and a debugger, or one of them alone with its peers mocked. It reads the repos, proposes a manifest a person reviews, renders the environment from it, and proves it starts. It never changes a service repository.

## When to Use

- A cross-service flow must be verified locally, by hand or with Playwright, with some services running a developer's unmerged work
- A new domain needs its environment (`init`, then `render`), or the repos changed what they need (`update`, `update --check`)

**Not for:** performance or load testing (one shared instance per engine, development settings); production parity of instance settings; repos outside `repos/`, which a person adds there first.

## Inputs

| Input       | Required | Notes                                                                                                               |
| ----------- | -------- | ------------------------------------------------------------------------------------------------------------------- |
| Mode        | yes      | `init` (discover, write the manifest, stop for review), `render` (manifest to files, verify), `update` (rediscover, propose manifest changes, render) |
| `--check`   | no       | With `update`: report the proposed changes and write nothing                                                         |
| `--flow <name>` | no   | The manifest flow verification starts; default the flow with the fewest services other than `all`, else `all`         |
| `--no-up`   | no       | Verify the configuration only; start nothing                                                                         |
| `--keep`    | no       | Leave the verified stack running                                                                                     |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate the root and check the mode

Use skill: `domain-devenv-layout` for every path, field, template, and host rule named below, and Use skill: `domain-kb-layout` for its Rules and the `_index/sync-state.json`, `_index/priority.json`, and flow card entries. The root is the working directory. No `repos/` directory, or one with no subdirectory, stops with `no repos - add the service repos under repos/ first`. `init` with `devenv/devenv.yaml` present stops with `devenv exists - run task-domain-devenv update`; `render` or `update` without it stops with `no manifest - run task-domain-devenv init`. The knowledge base counts as synced when `sync-state.json` records a `sha` for any repo; only then are `surfaces/<repo>.md`, flow cards, and `priority.json` read (a listed file that is absent is read as absent), and a non-null `in_progress` there puts the Sync line on the console; unsynced, no Sync line, whatever `in_progress` holds. `render` and `update` without `--check` or `--no-up` check `docker info` once; unreachable, verification runs config-only and the Verify line says why. A typed `--flow` that the manifest's `flows` lacks stops with `unknown flow <name> - flows: <keys>`. A stop emits its message alone, no console block. Every repo is read at its checkout `HEAD`, whatever `sync-state.json` records.

### Step 3 - Detect each repo's stack (`init`, `update`)

Use skill: `stack-detect` once per `repos/<repo>/` (its marker files and instruction files there, not the root's; each repo is its own project, so the cache rule holds per repo). The block is surfaced only through the inventory's `Stack` line, the manifest's `profile`, and the console table's `Stack` column, which reads `<Language> / <Framework>` from it; on `render` the column reads the `stack` recorded in `sync-state.json` when synced, else `-`.

### Step 4 - Discover each repo (`init`, `update`)

Use skill: `domain-devenv-discovery` per repo, with its stack block, the other repo names, and, when synced, every `surfaces/*.md` (its own first; the others' `internal api` rows tell a peer and seed its stubs). Use skill: `domain-devenv-stack-profiles` for the profile each inventory names. A repo whose inventory reads `not a service` goes into the Services line's `excluded` list and appears nowhere else. Then re-file: an `External` row whose `Unknowns` line names candidate repos becomes a `Peer` row of the repo whose `Dev hosts` line serves that host (its calls kept), and the unknown is dropped; no match, it stays external.

### Step 5 - Assemble the manifest (`init`, `update`)

Build the manifest from the inventories, every field the layout's Manifest section defines, in its order:

- **Root:** `domain` is the root directory name, kebab-cased, a trailing `-kb` dropped (`update` keeps the manifest's); `proxy_port` 8000; `tls` at `init` is `issuer: mkcert`, `port: 443` whatever the repos say, and `update` keeps the manifest's `tls` (a person's `issuer: none` or other port stands) - every host and origin below is computed from the `tls` in force.
- **Infra:** one entry per engine some `Uses` row names, `sqlite` excepted (it needs none). An engine's `image` is its repository (`mysql`, `postgres`, `redis`, `rabbitmq` with a `-management` tag, `apache/kafka`, `quay.io/keycloak/keycloak`) at the one exact version the inventories' `Engine` rows name, decided in this order: any row reading `unknown - Keycloak below 26` or `unknown - kafka image <image>` makes the entry that value; else several exact versions `unknown - versions differ: <version> (<repo>), ...`; else the one exact version, other `unknown` rows ignored; else `unknown - no production version in the repos`; `evidence` is the row cited. `host_port` is the engine's own port for `mysql`, `postgres`, `redis`, and `rabbitmq`; `keycloak`, `kafka`, and `mailpit` take none. `rabbitmq.vhost` is `domain`; `topology` is `provisioned` when any inventory's Topology line says so, with the union of their declarations as `declarations`, else `apps`. `keycloak.realm` is `domain`, `host` by the layout's host rule from the `Dev hosts` `keycloak` lines, `users` one per distinct role in the union of every `uses.keycloak.roles`, username and role the same, else one `dev` user with no roles. Tool images - `mailpit` (`axllent/mailpit`, when any inventory uses it; it has no `Engine` row), `wiremock` (`wiremock/wiremock`), `proxy` (`caddy`, on Docker Hub `library/caddy`), `playwright` (`mcr.microsoft.com/playwright`, when a frontend exists), `curl` (`curlimages/curl`, with `topology: provisioned`) - are the newest tag of the accepted shape the registry's tag list returns (`https://hub.docker.com/v2/repositories/<repo>/tags?page_size=100`, `https://mcr.microsoft.com/v2/playwright/tags/list`; shapes: `X.Y.Z` for wiremock, caddy, and curl, `vX.Y.Z` for mailpit, `vX.Y.Z-noble` for playwright, newest by numeric X, Y, Z, every other tag skipped), else `unknown - pin a tag`; `update` keeps a pinned one.
- **External:** `external.<name>` per distinct `External` row name, kebab-cased, with its `port` (`unknown - <why>` kept, which keeps every service using it out of the render; rows naming different ports `unknown - ports differ: <port> (<repo>), ...`) and the union of its `calls`, a `none - ...` cell contributing nothing (an empty list seeds no stub).
- **Services:** one entry per inventory, keyed by the repo directory name, in `repos/` order; every inventory value is taken without its ` - file:line` citation, which goes to `evidence`. `profile` and `kind` from their lines; `runtime` from the Stack line's version; `port` the inventory's (a `profile default` is written as the number); `host_port` from 3001 in manifest order; `debug_port` from 12341 in manifest order among the services whose profile has a debug port, `none` for the others; a `worker` omits `port`, `host_port`, `health`, and `routes`. `packages` is the inventory's `Packages` list; `processes` the Process table (`default` kept, `{run, live}` and `{live}` forms kept); `migrate`, `health`, `build`, and the profile fields (`module`, `main`, `tools`) from their lines, `unknown` values kept. `env` is the Env table plus a `sqlite` row's key and Dev value (never under `uses`), `secrets` the Secret table. `uses.<engine>` carries `database` (the `database` role's Dev value, or the one inside a `url` role's value, else `<user>_development`), `db` for redis (from 0, in manifest order; a seventeenth is an unknown on that service), `client` (the `client id` Dev value, else the service key) and `roles` (the inventory's `Roles` line; a `Roles` line on a service with no keycloak row is an unknown, `roles: <roles> checked but no OIDC key - set uses.keycloak`) for keycloak, and under `env` every config key of the engine with the naming contract's value for its `Role` (a `url` keeps its Dev value's scheme and driver prefix; `issuer` is `<keycloak origin>/realms/<realm>`; a keycloak `url` is the Keycloak origin plus the Dev value's path; `other` keeps the Dev value). `peers.<peer>` carries `calls` and, under `env`, each key, the ` (browser)` marker stripped from the name: a server-side key `http://<peer>:<peer port>` plus the path of its Dev value (none when the Dev value is `-`); a ` (browser)` key the origin of the peer's route host plus the route path; a key whose Dev value is an `https://` URL the peer's origin, and the peer then gets a route `/` on its host. `external.<name>.env` keys are `http://<name>.mock:<port>`; a key whose Dev value is not a URL (an ARN, a queue or bucket name) keeps that value and adds the unknown `<KEY>: not a URL - set external.<name> and the key by hand`. `evidence` maps every cited slot (`runtime`, `port`, `health`, `migrate`, each `packages`, `build`, process, config key, peer, and external entry) to its `file:line`; `unknowns` is the inventory's `Unknowns` lines, verbatim.
- **Routes:** a service with a `Dev hosts` `route` line gets `host` that name, `path` `/`; a backend some frontend calls through a ` (browser)` key gets a route on that frontend's host at the path of the key's Dev value (`/` when it has none) when the value's host is the frontend's host or `localhost`, else on the value's host at that path; a frontend with no dev host is routed `/` at `<svc>.localhost`. One `/` route per host: two services claiming `/` on one host is an unknown on both (`route: host <h> also claimed by <svc> - set routes`), a backend's path route under a frontend's host is not.
- **Flows:** `all` with every service, in manifest order; when synced, each `priority.json` entry in its order, then each card it does not list in path order, whose card is not `freshness: orphaned` and whose `files` list names two or more manifest services (the segment after `repos/`, segments that are not a service key dropped), as `<capability>/<flow>: [those services, in manifest order]`, at most eight besides `all`; unsynced, `all` only and a console Unknowns line (the manifest has no slot for it) `flows: all only - the knowledge base is not synced - name the flows in devenv.yaml, or run task-domain-sync init (task-domain-sync --resume when sync-state.json records an in_progress value)`.

`init` writes `devenv/devenv.yaml` and goes to Step 8. `update` compares the assembled manifest with the existing one and lists each difference as a proposal, of these kinds only: a service added (a directory under `repos/` the manifest lacks whose inventory is a service) or removed (a manifest service whose directory is gone, whatever the knowledge base lists; flows drop it); an infra entry, external, config key, process, peer, route, secret, role, package, or build key added or gone; a value whose evidence changed (the manifest's `evidence` entry names another file, or its `file:line` now states another value - a line that moved with the same value is not a change, and `update` refreshes the line number silently); a flow whose card-derived member list changed (`all` follows the services); a route host or env value carrying a proxied origin that the `tls` in force and the host rule no longer yield. Any other difference is a person's edit, kept and never proposed; a field with no `evidence` entry (`domain`, `proxy_port`, `tls`, a tool image, a `host_port`, a `debug_port`, a hand-written unknown) keeps the manifest's value and is proposed only when its whole entry is added or removed (a whole entry reads `none -> <entry>` or `<entry> -> none`). A manifest whose `evidence` maps are empty (hand-written, or from an earlier version) has nothing to compare evidence against: every value difference is then a proposal. The console then describes the manifest as it stands (its services, flows, and the table; a removed service's `Stack` reads `-`) and the proposals describe the change; a violation Step 6 would report in the existing manifest is an Unknowns line `manifest: <field> - <violation> - fix devenv.yaml` and never stops `update`. With `--check` the workflow goes to Step 8 with the list. Otherwise, with no proposals it reports `unchanged` and continues; with some it asks once with the full list, applies the accepted proposals, writes the manifest, and continues only once answered.

### Step 6 - Render (`render`, `update`)

Validate the manifest's structure: unique `host_port`, debug, `proxy_port`, and `tls.port` values, every flow member a service key, no `latest` or tag-less image, every value inside its enum, and the layout's TLS-off host rule. Invalid, the workflow writes nothing and goes to Step 8 with `Verify: config invalid - <first violation>`. An `unknown` value is never a violation: a service with one at any depth under a field its profile reads, lacking a field its profile needs, using an infra entry or external with one, or depending on an unpinned tool image (`proxy`: every service; `wiremock`: every service with peers or externals; `curl`: every service using rabbitmq with `topology: provisioned`; `playwright`: `e2e`, listed under `Not rendered` by that name) is left out of every rendered file and listed under `Not rendered`; flows drop it. Write every `regenerate` file from the templates with each profile slot from `domain-devenv-stack-profiles`, `chmod +x devenv/bin/dev` after writing it (Git on Windows records no mode bit; a person committing from there runs `git update-index --chmod=+x devenv/bin/dev`); delete the `regenerate` files of a service that is no longer in the manifest or is not rendered (its overlays, `services/<svc>/`, `.devcontainer/<svc>/`), counted as removed; a file or folder the layout's folder table does not list (a person's `NOTES.md`) is left alone. Write every `seed` file only when absent: a peer stub is `stubs/peers/<peer>/<method>-<path>.json` and an external stub `stubs/external/<name>/<method>-<path>.json`, method lower-cased, the leading `/` dropped, each other `/` written `-`, `{param}` written `param` (`POST /payments/refunds` is `post-payments-refunds.json`, `GET /payments/refunds/{id}` is `get-payments-refunds-id.json`), its `metadata.evidence` the manifest's `evidence` entry for that peer or external, the key dropped when there is none; `seed files kept` counts the seed files the manifest implies that already existed. `sources.env` and anything under `.cache/`, `wt/`, or `infra/tls/` are never written by the workflow (`bin/dev` owns them), nor anything outside `devenv/`; `devenv.yaml` is written only in Step 5 and by Step 7's unknowns.

### Step 7 - Verify (`render`, `update`)

Run `bash -n devenv/bin/dev`, then, in `devenv/`, `docker compose -f compose.yaml -f compose.local.yaml --profile '*' config -q` and the same with `-f overlays/<svc>.live.yaml` inserted before `compose.local.yaml` for each rendered service and with `-f overlays/<svc>.solo.yaml` so inserted for each (explicit `-f`, so the `COMPOSE_FILE` a previous `bin/dev up` left in `.env` is not read). A failure is a rendering defect: it ends the step with `config invalid - <first error>` when the fix below does not clear it. Unless `--no-up`, Docker is unreachable, nothing is rendered, or `tls.issuer` is not `none` and `infra/tls/cert.pem` is absent (the workflow never runs `bin/dev certs`, which creates a CA on the developer's machine), run `bin/dev up <flow>` with the developer's `sources.env` as it stands (`bin/dev` creates it from the example when absent, so unmapped services run pinned from `repos/`), and read each service's state from `docker compose ps -a` (a `worker` has no healthcheck: `running` is its healthy state). A failing service's last 40 log lines classify the cause: a rendering defect (a wrong command, path, package, port, or escape) is a slot filled wrongly, fixed in the render and the step repeats, at most twice; a cause in the service (a missing secret, a failed migration, a hardcoded host) is appended to the service's `unknowns` in the manifest and reported. Then `bin/dev down` unless `--keep`.

### Step 8 - Report

Emit the console block. `### Unknowns` lists every `unknown` infra and external value, every service field whose value starts `unknown` (at any depth), every service's `unknowns` line, and the flows and manifest lines of Step 5, as `- {svc or infra or external or flows or manifest}: {field} - {why} - {what to set}`: a service's line `{slot}: {why} - {what}` becomes `- {svc}: {slot} - {why} - {what}`, an `unknown - <why>` value `- {owner}: {field} - {why} - set it in devenv.yaml`. `Infra` lists the engines only; `hosts` is the layout's proxied hosts. Excluded repos appear only in the Services line.

## Output Format

```
## Domain devenv

- **Sync:** unfinished at {command}:{pass} - files read as they stand, partly written by the unfinished run; when no sync is running, run task-domain-sync --resume     {only when synced and in_progress is set}
- **Mode:** {init | render | update | update --check}
- **Root:** {absolute path}/devenv
- **Services:** {n} ({n} backend, {n} frontend, {n} worker); excluded: {repo - reason, ... | none | not checked - render}
- **Infra:** {engine image, ... | none}
- **TLS:** {off - issuer none | mkcert on port {n}}; hosts: {host, ...}
- **Flows:** {name (svc, svc), ...}
- **Manifest:** {written - review devenv.yaml, then run task-domain-devenv render | unchanged | {n} proposals, {n} applied | {n} proposals - not applied (--check)}{; {n} unknowns appended by Verify}
- **Files:** {n} regenerated, {n} seeded, {n} seed files kept, {n} removed | none - {init | --check | invalid manifest}
- **Not rendered:** {svc - field: value, ... | every service - {field: value} | none | not run - {init | --check | invalid manifest}}
- **Verify:** {config valid; {flow} up: {svc} healthy, {svc} unhealthy - {cause} | config valid; not started - {--no-up | Docker unreachable | no certificate - run bin/dev certs | nothing rendered} | config invalid - {first error} | not run - {init | --check}}
- **Next:** {review devenv.yaml, resolve its unknowns, run task-domain-devenv render | run task-domain-devenv update to apply | none - the repos match the manifest | fix devenv.yaml: {first violation}, then task-domain-devenv render | fix the render: {first error or unhealthy service}, then task-domain-devenv render | resolve the unknowns below, then task-domain-devenv render | run bin/dev certs and add the bin/dev hosts lines, then bin/dev up {flow} | map sources in devenv/sources.env, then bin/dev up {flow}}

| Service | Stack | Profile | Kind | Uses | Peers | Processes | Health |
| ------- | ----- | ------- | ---- | ---- | ----- | --------- | ------ |

### Proposals     {update only}

- {add | change | remove} {field path}: {old} -> {new} - {evidence}

### Unknowns

- {svc or infra or external or flows or manifest}: {field} - {why} - {what to set}
```

`Services` counts every manifest service, rendered or not, and the table lists exactly those; `Uses`, `Peers`, and `Processes` list keys, `none` when empty. `Health` reads `healthy` (a `worker` when running), `unhealthy - {cause}`, or `not started`. `Next` is the first value whose condition holds, in the order listed: `init`; `--check` with proposals; `--check` without; an invalid manifest; a Verify failure (`config invalid`, or a service still unhealthy after two fixes); an unknown that keeps a service out of the render or that Verify appended; TLS on with no certificate; else the stack is runnable, `{flow}` being the typed `--flow`, else its default. `Proposals` reads `- none - the repos match the manifest` when empty, `Unknowns` `- none`.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: both layouts loaded; no-repos, manifest-present, and manifest-absent stops checked; surfaces, cards, and priority read only when synced, the Sync line only then; Docker reachability checked once; repos read at `HEAD`
- [ ] Step 3: `stack-detect` run once per repo directory and surfaced only through the inventory, `profile`, and the `Stack` column
- [ ] Step 4: discovery run per repo with its stack, the other repo names, and every surfaces file when synced; `domain-devenv-stack-profiles` loaded for each profile named; non-services excluded; externals re-filed against the other repos' dev hosts
- [ ] Step 5: every Manifest field assembled as listed - `domain`, `proxy_port`, `tls` (mkcert on 443 at `init`, kept on `update`), infra images at the one agreed version or `unknown - versions differ`, vhost and realm `domain`, Keycloak users per role in use, tool images from the registry's tag list or `unknown - pin a tag`, externals with port and calls, each service's ports, build, profile fields, env, secrets, uses, peers, externals, evidence, and unknowns, routes by the host rule, flows from ranked then unranked non-orphaned cards spanning two or more services, at most eight; `init` writes and reports; `update` proposes only the listed kinds, keeps a person's edits, reports the manifest as it stands, ends on `--check`, applies only accepted proposals
- [ ] Step 6: manifest validated, an invalid one reported and nothing written; services with unknown or missing fields, unknown infra or externals, or an unpinned tool image left out and listed; regenerate files rewritten, `bin/dev` made executable, stale service files removed, unlisted files left alone, seed files only when absent, stubs named by method and path with their evidence; nothing written outside `devenv/`, never `sources.env`, `.cache/`, `wt/`, or `infra/tls/`
- [ ] Step 7: `bash -n` and `compose config` with explicit `-f` over the base, each live, and each solo overlay, `compose.local.yaml` last; stack started unless `--no-up`, no Docker, nothing rendered, or TLS on without a certificate (never running `bin/dev certs`); state read with `ps -a`, a worker healthy when running; failures classified, rendering defects fixed at most twice, service causes appended as unknowns; stack stopped unless `--keep`
- [ ] Step 8: console block emitted with every slot, the services table, and the Unknowns section built from infra, externals, service fields and lines, flows, and manifest violations

## Avoid

- Editing, committing, or adding files to a service repository, or using its existing Dockerfile or compose file as the template
- Pointing live mode or a bind mount at `repos/<svc>`
- Hand-editing a generated file to make verification pass instead of fixing the render
- Choosing between two production versions of one engine without asking
- Reusing a repository's certificate or key, or running `mkcert` on the developer's behalf
