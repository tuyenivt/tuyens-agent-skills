---
name: domain-devenv-discovery
description: "Inventory a service repo's runtime needs from code: version, port, processes, infra and config keys, peers, external deps, secrets, health."
metadata:
  category: domain
  tags: [domain, devenv, discovery, config, env-vars, dependencies, runtime]
user-invocable: false
---

# Domain Dev Environment Discovery

> Load `Use skill: stack-detect` first to determine the repo's stack, then `Use skill: domain-devenv-layout` (its Manifest section names every field an `Unknowns` line may cite, its naming contract the values) and `Use skill: domain-devenv-stack-profiles` (the per-stack evidence, defaults, and `Unknowns` entries this inventory checks).

Reads one service repository and states what it needs to run next to its peers: the runtime, the port, the processes, every piece of infrastructure it connects to and the config key it reads for it, the other repos it calls, the systems outside the domain it calls, and the values it cannot start without. Every value is cited; whatever the repo does not say stays `unknown`.

## When to Use

- `task-domain-devenv` `init` and `update`, once per repo under `repos/`
- Standalone: one repo directory named by the user; the inventory is emitted inline

## Inputs

| Input            | Required | Notes                                                                                                         |
| ---------------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| Repo             | yes      | `repos/<repo>/`, read at its checkout `HEAD`                                                                    |
| Stack            | yes      | The `stack-detect` block for the repo                                                                         |
| Other repos      | yes      | The other directory names under `repos/`, to tell a peer from an external dependency                          |
| Surfaces         | no       | `surfaces/<repo>.md` when the knowledge base records a sync; its `outbound client`, `message`, and `event out` rows are where to look first, and its peers' `internal api` rows are the calls a stub needs |

## Rules

- **Evidence or `unknown`.** Every value cites `repos/<repo>/file:line`, root-relative as the manifest and the surfaces files cite; a value the repo does not state is `unknown - <what is missing>` and also an `Unknowns` line. An `Unknowns` line names the manifest field a person sets, the repo change the environment cannot make, or the decision a person makes. A framework default counts only as the profile's `default`, never as evidence. Only what the development environment reads counts: a key, host, or setting read solely under a `production:` entry, a production profile, or a production config file is not a row.
- **Existing container files are evidence, never templates.** A `Dockerfile`, compose file, `.devcontainer/`, `.env.example` or `.env.sample`, `Procfile`, CI service containers (`services:` in a GitHub Actions or GitLab job), and deploy configuration (ECS task definitions, Terraform, Helm values) are read for engine versions, packages, ports, processes, and env keys; their structure is not copied, and a Dockerfile's base tag is not a runtime source (the profile's files are).
- **A config key is the name the running service reads.** It is the env name the code or config file reads (`ENV.fetch("X")`, `ENV["X"]`, `<%= ENV[...] %>` and `${X}` in YAML, `process.env.X`, NestJS `ConfigService.get('X')`, `os.environ`, `os.getenv`, `os.Getenv`, viper `AutomaticEnv` with its `SetEnvPrefix`); a Spring property is its relaxed-binding env name (`spring.datasource.url` is `SPRING_DATASOURCE_URL`) unless its value, or a `@Value("${X}")`, is a `${X}` placeholder, which makes `X` the key. A key a library reads by convention with no code site (Rails `DATABASE_URL`, which merges over `config/database.yml` unless the environment's entry sets `url:`; `<NAME>_DATABASE_URL` per extra database; Sidekiq's `REDIS_URL`; django-environ's `env.db()` reading `DATABASE_URL`; a pydantic-settings field with its `env_prefix` or `validation_alias` applied) is cited at the file that activates the convention (`config/database.yml`, the initializer, the settings class). A setting the code fixes with no env path is not a key: it is `hardcoded at file:line` under `Unknowns`, a repo change the environment cannot make.
- **Infra is what the code connects to.** A driver or client in the package manifest is a candidate; the config key that feeds it, cited where it is read, makes it a row. Engines: `mysql`, `postgres`, `redis`, `rabbitmq`, `kafka`, `keycloak` (any OIDC issuer, JWKS, or Keycloak admin URL), `mailpit` (SMTP settings), `sqlite` (embedded; a `Uses` row that needs no infra entry). Object storage, a cloud queue, or a search engine is an `External` row (`<what>`) with a stub port, which a person supplies. When one engine is configured through several keys, each key is a row with its `Role`; the `Dev value` cell carries the value the repo's development config or example file gives the key, whole (a `url` with its scheme and driver prefix; a `database`, `db`, `client id`, or `vhost` as named), else `-`. A credential the naming contract fixes (a database password, a Keycloak client secret) is a `Uses` row by its `Role`, never a `Secret`; `Secrets` are credentials for systems the environment does not provide.
- **A peer is another repo in this domain.** An outbound base URL key is a peer when its development or test default names another repo's host or service, its key or client name starts with another repo's name, or a surfaces row of that repo serves the paths it calls; a browser-side key (`NEXT_PUBLIC_*`, `VITE_*`) is a row like a server-side one with ` (browser)` after its key, so the workflow gives it the peer's origin. Otherwise it is external, and when its host is a dev host no repo evidence resolves, an `Unknowns` line names the candidate repos for the consuming workflow to re-file against their `Dev hosts`. A peer row lists the calls found (`METHOD /path`, a path parameter written `{id}`), which seed its stubs; a configured key with no call site is a row with `Calls` `none - no call site`. An external row lists its calls too (`none - not HTTP` for a queue or storage API), and its `Port` is the port of the URL the code's default or production config names (`443` for a bare `https://`, an SDK-addressed service or an ARN included), else `unknown`.
- **Versions.** The runtime from the files the profile names. An engine's version from deploy configuration (the production source), then CI service containers, then an existing compose file, cited; a floating tag (`mysql:8.0`, `redis:7`) or a managed-service `engine_version` (`8.0.mysql_aurora.3.x`) is not a version and the search moves to the next source, `unknown - floating tag <tag>` when nothing exact follows; one found nowhere `unknown - no production version in the repo`; a Keycloak tag below 26 `unknown - Keycloak below 26`; a kafka image other than `apache/kafka` `unknown - kafka image <image>` (a Confluent tag is not a Kafka version); tool images (`mailpit`, `wiremock`, `proxy`, `playwright`, `curl`) get no `Engine` row, the consuming workflow pins them; the `Version` cell is the bare version, a tag's `-management` or `-alpine` suffix dropped. Two repos naming different versions of one engine is the consuming workflow's decision, not this repo's.
- **Dev hosts and HTTPS are read from the repo, certificates are not.** A dev host is a name the repo's own development setup serves or expects (a `.devcontainer` or compose hostname, a documented hosts-file entry, `config.hosts`, an app URL or OIDC redirect URI in development config, a cookie domain), marked `route` or `keycloak` by what it serves; `localhost` is never one. HTTPS is required when development code demands it (`force_ssl`, `Secure` or `SameSite=None` cookies, `https://` redirect URIs, HSTS, a peer called by an `https://` URL). A certificate or key file in the repo is read only for the host names it covers, which are dev-host evidence; its key material is never used. TLS is on in every environment by default, so the HTTPS line decides nothing by itself: it explains the hosts and feeds the scheme check. Where the profile's `Scheme` slot says `set in code`, that setting is looked for; absent while the code builds absolute URLs (redirects, OAuth callbacks, mail links), it is an unknown. A service that terminates TLS itself in development (`server.ssl.*`, puma `ssl_bind`, uvicorn `--ssl-*`), or that forces HTTPS in development (`force_ssl`, `requiresSecure`, `redirectToHttps`), is an unknown: the proxy terminates TLS, and the health probe and peer calls arrive over plain HTTP with no forwarded header. A `config.hosts =` assignment in `development.rb` replaces Rails' host list and is an unknown, as is each `Unknowns` entry the service's profile names, by the profile's own predicate (Django `ALLOWED_HOSTS` not read from env, a Flask or FastAPI trusted-host setting, Next.js `allowedDevOrigins` or Vite `server.allowedHosts` absent, Yarn Plug'n'Play, a Prisma `output` inside the source tree, an uncommented Rails `config.file_watcher`).
- **Kind.** `backend` serves HTTP; `frontend` is a browser app; `worker` has no listener (a consumer or scheduler only). A library, a schema or contract package, an infrastructure-as-code repo, or a repo with no server, worker, or frontend entry point is `Kind: not a service` with the evidence, and the block ends there.

## Patterns

### Where to look first

| Slot          | Look in, in order                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Processes     | `Procfile`, `Procfile.dev`, `package.json` scripts, `Makefile` run targets, the profile's worker gems or libraries, an existing compose file's services |
| Port          | the server config (`config/puma.rb`, `server.port`, the `listen` call, `uvicorn` arguments), `PORT` default, then the profile default |
| Infra keys    | `config/database.yml`, `config/*.yml`, `config/initializers/`, `application*.yml` and `.properties`, `settings.py`, a config module, `.env.example` |
| Peers, external | client classes and their base-URL config, `surfaces/<repo>.md` outbound client rows, HTTP client construction sites          |
| Secrets       | keys read with no default whose name or use is a credential (`*_KEY`, `*_SECRET`, `*_TOKEN`, `*_PASSWORD`, Rails credentials), `.env.example` entries left blank, minus the `Uses` credentials |
| Roles         | authorization checks on a token role (`@PreAuthorize("hasRole(...)")`, `@Roles`, a claims lookup); a scope check (`hasAuthority('SCOPE_x')`) is an `Unknowns` line (`client scope x - add it to the realm by hand`); a database-backed role check (`rolify` `has_role?`, the app's own roles table) is an `Unknowns` line (`roles live in the database - seed them`) |
| Topology      | rabbitmq only: exchange, queue, and binding declarations in code (`apps`); none in code and present in deploy configuration (`provisioned`, each declaration listed) |
| Browser       | for a frontend: the API base URL key and every outbound call's host; for a backend: `from the frontends' inventories` (the consuming workflow fills it) |
| Dev hosts, HTTPS | `.devcontainer/`, compose files, README setup steps, `config/environments/development.rb`, session and cookie config, OIDC client config, `server.ssl.*`, certificate files' subject names |
| Build         | the facts the profile's Dockerfile and commands need, for the manifest `build` map: `tool` (bundler, gradle or maven, npm or pnpm or yarn by lockfile - `yarn1` when `yarn.lock` opens with `# yarn lockfile v1` - uv or poetry or pip by lockfile, go; a lockfile no profile tool owns, `bun.lock`, `pdm.lock`, is `unknown - no profile tool`), `framework` (node: nest, tsx, node by the dev script; python: fastapi, django, flask; web: next or vite by that dependency, else unknown), `entry` (node: the dev script's entry file; python: `<module>:<app>` from the uvicorn or gunicorn `UvicornWorker` call, the file a `fastapi run` names, or `<module>` from the Flask app), `debugger` (rails: `rdbg` when `debug` is in `Gemfile.lock`, else none), `generate` (node: `prisma` when a schema exists, else none), `native` (node: a dependency with `binding.gyp` or a `gypfile` lockfile entry), `manifests` (the optional files the profile names that exist: `.npmrc`, `pnpm-workspace.yaml`, `.yarnrc.yml`, `.yarn/`, `prisma/`, `prisma.config.ts`, a dev requirements file, Rails `package.json` and lockfile; `.` for a workspace monorepo or a `gemspec`/`path:` Gemfile), `steps` (the builds the profile names that the repo has a script for: node `npm run build`, rails `npm ci && npm run build`, `npm ci && npm run build:css`, `bin/rails tailwindcss:build`); node writes `processes.web: exec npm run start:prod` when that script exists; a process whose live command differs is written `{run: <cmd>, live: <cmd>}`, a live-only one `{live: <cmd>}` |
| Profile fields, Health | spring: the boot module from `settings.gradle*` or the parent `pom.xml` and the `bootJar` or `spring-boot-maven-plugin` module (`module`), and `management.server.port`, which turns `Health` into `tcp`; go: `main` always (`./cmd/<svc>`, else the only `./cmd/*`, else `.` for a root `main.go`; several and none is `<svc>` is `unknown - several main packages`), and the CLIs the profile installs (`tools`, versions a person pins); unknown profile: `base`, `build.install`, `web` |

Bad - a guess presented as a fact, and a peer mistaken for an external system:

```
| mysql | DB_HOST | host | - | (Rails default) |
| payments | PAYMENTS_URL | - | 443 | POST /payments/refunds | repos/orders/app/clients/payments_client.rb:8 |
```

Good - the key the code reads, and the peer recognised by its default host:

```
| mysql | DATABASE_URL | url | mysql2://root@127.0.0.1:3306/orders_development | repos/orders/config/database.yml:14 |
| payments | PAYMENTS_URL | http://payments:3000 | POST /payments/refunds, GET /payments/refunds/{id} | repos/orders/app/clients/payments_client.rb:8, repos/orders/config/settings.yml:22 |
```

## Output Format

One block per repo, every table kept with its header and one `none - <evidence>` row when empty (a `not a service` block ends after its `Kind` line):

```markdown
### {repo}

- **Stack:** {Language} / {Framework} ({{language runtime version} - {file:line} | unknown - <what is missing>})
- **Profile:** {rails | spring | node | python | go | web | none - not a service | unknown - no profile for <Framework>}
- **Kind:** {backend | frontend | worker | not a service - <evidence>}
- **Port:** {n - file:line | n - profile default | none - worker | unknown - <what is missing>}
- **Health:** {path - file:line | tcp | none - worker | unknown - <what is missing>}
- **Migrate:** {command - file:line | default | none - <evidence> | unknown - <what is missing>}
- **Packages:** {package (because <dependency> - file:line), ... | none}
- **Build:** {tool: <x> - file:line; framework: <x> - file:line; entry: <x> - file:line; debugger: <x> - file:line; generate: <x> - file:line; native: <bool> - file:line; manifests: <paths> | none; steps: <commands> - file:line | none} {only the keys the profile reads}
- **Profile fields:** {module: <module> - file:line; main: <package> - file:line; tools: {<cli>: <version to pin>, ...}; base, build.install, web - set by hand (profile custom) | none}

| Process | Command | Evidence |
| ------- | ------- | -------- |

| Uses | Config key | Role | Dev value | Evidence |
| ---- | ---------- | ---- | --------- | -------- |

| Peer | Config key | Dev value | Calls | Evidence |
| ---- | ---------- | --------- | ----- | -------- |

| External | Config key | Dev value | Port | Calls | Evidence |
| -------- | ---------- | --------- | ---- | ----- | -------- |

| Env | Development value | Evidence |
| --- | ----------------- | -------- |

| Secret | Evidence |
| ------ | -------- |

| Engine | Version | Evidence |
| ------ | ------- | -------- |

- **Roles:** {role, ... - file:line | none}
- **Topology:** {apps - file:line | provisioned - exchange <name> <type>; queue <name>; binding <exchange> -> <queue> <routing key> - file:line | none in this repo - <where looked> | none - no rabbitmq}
- **Browser:** {API base key <KEY> = <development value> - file:line | from the frontends' inventories | none - no API calls}
- **Dev hosts:** {host (route | keycloak) - file:line, ... | none}
- **HTTPS:** {required - <reason> file:line; ... | not required}
- **Proxy scheme:** {KEY=value | trusted by default | not needed | set in code - file:line | not set - no absolute URLs built | unknown - <setting> absent, absolute URLs built at file:line}
- **Unknowns:**
  - {slot}: {why} - {set `{manifest field}` in devenv.yaml | repo change: <what> | <what a person decides>}
```

`Process` names are `web` and each other name as the `Procfile` or script calls it, `release` excepted; `Command` is `default` when the profile's command applies. `Role` is `{url | host | port | user | password | database | db | issuer | client id | client secret | vhost | bootstrap servers | smtp host | other}`. `Calls` reads `none - <evidence>` when no path is found. `Dev value` in the Peer and External tables is the key's development or example value, whole (a URL, an ARN, a queue name), `-` when the repo gives none. `Env` lists only keys the service needs to boot that no other table covers, with the value the repo's own development config or example file gives. `Unknowns` reads `- none` when every slot is cited.

## Avoid

- Copying an existing Dockerfile or compose file instead of mining it for facts, or proposing a repo's certificate or key for reuse
- Reporting a library the package manifest declares but no code configures as infrastructure
- Filling a version, port, or key from what the framework usually uses
