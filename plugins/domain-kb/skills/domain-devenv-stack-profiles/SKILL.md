---
name: domain-devenv-stack-profiles
description: "Per-stack dev runtime profiles: Dockerfile stages, run, live-reload and debug commands, workers, migrations, health, volumes, memory, trust."
metadata:
  category: domain
  tags: [domain, devenv, dockerfile, live-reload, debug, rails, spring, node, python, go, nextjs]
user-invocable: false
---

# Domain Dev Environment Stack Profiles

> Load `Use skill: domain-devenv-layout` first: it owns the manifest fields these profiles read (`runtime`, `port`, `packages`, `processes`, `migrate`, `health`, the `build` map, `module`, `main`, `tools`, `base`, `web`), the Compose templates the values below fill, the header line, and the naming contract.

One profile per stack, each answering the same slots, so the Compose templates never change per stack. A stack outside this file is added as one more profile; a single service that deviates overrides a slot in its manifest entry instead.

## When to Use

- `domain-devenv-discovery` choosing a service's profile and the profile-specific evidence to look for
- `task-domain-devenv` rendering a service's Dockerfile and Compose entries

## Rules

- **Profile by detected framework**, per repo: `rails` (Rails), `spring` (Spring Boot, Gradle or Maven), `node` (NestJS, Express, Fastify, other Node servers), `python` (FastAPI, Django, Flask), `go` (Gin, net/http, other Go servers), `web` (Next.js, Vite React or Vue). Any other framework is `unknown - no profile for <Framework>` in discovery; a person then sets `profile: custom` with `base`, `build.install`, `web`, and `port` (the layout renders it), or the service stays out of the render.
- **Repo facts arrive through the manifest.** A profile never reads the repository: discovery fills the service's `build` map (`tool`, `framework`, `entry`, `debugger`, `generate`, `native`, `manifests` - extra files or directories `deps` copies, `steps` - commands the `app` stage runs after the copy; `install`, an install command replacing the profile's, is a person's), the `processes` commands (a process that needs another command in live mode as `{run: <cmd>, live: <cmd>}`, a live-only one as `{live: <cmd>}`), and the profile fields (`module`, `main`, `tools`); each profile below names the keys it reads and when. A key a profile needs for this service that is absent keeps the service out of the render, as an `unknown` value does.
- **A manifest value beats the profile.** `default` in a manifest slot means the profile's value; anything else replaces it. `packages` adds to the profile's always-installed set, never replaces it.
- **Two stages, one Dockerfile.** Each starts with the layout's header as a `#` line. `deps` is the runtime, system packages (the `apt-get` line is dropped when the package list is empty), and dependencies installed from the manifests alone, so `live` gets them without the code; `app` is `deps` plus the code (and its build), for `pinned`. Dependencies install outside `/app`, so the live bind mount never hides them, except where a profile names a live volume for them. In every template, `deps` also copies `build.manifests` (a `.` entry copies the whole source), a `build.install` replaces the install `RUN` shown, and `app` runs `build.steps` after its copy.
- **Commands.** Every command (web, live, process) begins with `exec` on its final process (a build or install step before it is chained with `&&`), so the process receives signals, uses single quotes only, and writes a shell variable as `$VAR` and the probe's `\r\n` singly: the Output Format block carries commands as written here, and the layout doubles `$` and `\` when it places them in Compose; a Dockerfile `RUN` keeps them single. The manifest's `debug_port` is the host side; the profile's debug port is the container side the layout maps it to.
- **Health probe.** A path is probed over HTTP and must answer `200`; `tcp` only opens the port. Both run under `bash`, which every profile's image has (a `custom` base must): `exec 3<>/dev/tcp/127.0.0.1/<port> && printf 'GET <path> HTTP/1.1\r\nHost: <svc>\r\nConnection: close\r\n\r\n' >&3 && head -1 <&3 | grep -q ' 200 '` (`Host: <svc>` passes the host allow-lists the profiles require), or `exec 3<>/dev/tcp/127.0.0.1/<port>`.
- **Forwarded scheme.** With TLS on, the proxy terminates HTTPS and sends `X-Forwarded-Proto: https`; a framework that ignores it builds `http://` redirect and callback URLs, which breaks OAuth. Each profile's `Scheme` slot says how its framework trusts the header: a `KEY=value` the render sets, `trusted by default`, `not needed` (the browser holds the origin, or TLS is off), or `set in code`, which discovery checks and reports as an unknown when absent while the code builds absolute URLs.
- **Trust, only with TLS on.** The CA is mounted at `/devenv/ca.pem`. A profile trusts it additively through env, or through the combined bundle its trust prestart builds, `cat /etc/ssl/certs/ca-certificates.crt /devenv/ca.pem > /tmp/ca-bundle.pem`, so public certificates keep working; the layout runs the trust prestart before the profile's own.
- **Versions come from the repo.** The runtime version is read from the files each profile names, in order, with a `ruby-`, `python-`, `v`, or `go` prefix and a Ruby patchlevel (`p32`) stripped; Java keeps only its major (`temurin-21.0.4+7.0.LTS`, `JavaVersion.VERSION_21` -> `21`); a range (`>=3.11`), an alias (`lts/*`), or nothing found is `unknown`, never a guess. The runtime tag must exist for the base image.

## Patterns

### rails

- **Runtime:** `.ruby-version`, `.tool-versions`, `ruby` in `Gemfile`, `RUBY VERSION` in `Gemfile.lock`; base `ruby:<runtime>-slim`
- **Packages:** always `build-essential git pkg-config libyaml-dev`; `mysql2` adds `default-libmysqlclient-dev`, `pg` adds `libpq-dev`, `ruby-vips` or `image_processing` adds `libvips-dev`, a `js` or `css` line in `Procfile.dev` adds `nodejs npm`
- **Manifests:** `Gemfile Gemfile.lock`; a `Gemfile` with `gemspec` or a `path:` gem copies the whole source before `bundle install` (`build.manifests: [.]`); with a `js` or `css` line and a `package.json`, that file and its lockfile too (`build.manifests`), and the `app` stage runs `build.steps` (`npm ci && npm run build`, `npm ci && npm run build:css` - the `yarn` forms with `yarn.lock` - or `bin/rails tailwindcss:build`, whichever the repo has)
- **Web:** `exec bin/rails server -b 0.0.0.0 -p <port>`; port 3000
- **Live:** with `build.debugger: rdbg` (discovery: `debug` in `Gemfile.lock`), `exec bundle exec rdbg -O --host 0.0.0.0 --port 12345 --nonstop -c -- bin/rails server -b 0.0.0.0 -p <port>`, debug port 12345; without it, the web command and no debug port. Code reloads per request through the Rails reloader, which works on any mount; `config.file_watcher = ActiveSupport::EventedFileUpdateChecker` can miss changes on Mac and Windows mounts and is an unknown when set
- **Prestart:** `rm -f tmp/pids/server.pid` (a restarted container keeps it, and Rails refuses to boot over it); every other profile has none
- **Migrate:** `bin/rails db:prepare` (Rails 7.1+: loads the schema and seeds the provisioned, still empty database; migrates one that has a schema)
- **Processes:** `Procfile` or `Procfile.dev` lines other than `web` and `release`, by name; `js` and `css` lines are live-only processes, `{live: exec <line>}` with a watcher that survives a closed stdin (`tailwindcss:watch[always]`, esbuild `--watch=forever`), prefixed by the lockfile's install when the repo has a `package.json` (`npm ci && ` with `package-lock.json`; `npm install -g yarn && yarn install --frozen-lockfile && ` with `yarn.lock`; the live volume below holds the result; pinned builds their output through `build.steps`); without a Procfile, by gem: `sidekiq` `exec bundle exec sidekiq`, `solid_queue` `exec bin/jobs`, `good_job` `exec bundle exec good_job start`, `resque` `exec bundle exec rake resque:work QUEUE='*'`, `sneakers` `exec bundle exec rake sneakers:run`
- **Health:** `/up` when `config/routes.rb` routes it, else `tcp`
- **Env:** `RAILS_ENV=development`, `RAILS_DEVELOPMENT_HOSTS=<svc>,<svc>.localhost` plus each route host (Rails 6.1+; the development host check blocks any other name; a `config.hosts =` assignment in `development.rb` replaces the list and is an unknown discovery reports)
- **Secrets:** `RAILS_MASTER_KEY` when development reads credentials (`config/credentials.yml.enc` or `config/credentials/development.yml.enc` exists and code calls `Rails.application.credentials`)
- **Trust:** combined bundle, `SSL_CERT_FILE=/tmp/ca-bundle.pem`
- **Scheme:** trusted by default (Rack reads `X-Forwarded-Proto`), so `force_ssl` and `Secure` cookies see HTTPS
- **Live volumes:** `<svc>-node-modules:/app/node_modules` with a `js` or `css` line, else none; **memory:** web 768m, worker 512m; **extensions:** `Shopify.ruby-lsp`, `KoichiSasada.vscode-rdbg`

```dockerfile
# generated by task-domain-devenv from devenv.yaml - edit devenv.yaml or compose.local.yaml
FROM ruby:<runtime>-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends <packages> && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=src Gemfile Gemfile.lock .ruby-version* <build.manifests> ./
RUN bundle install
FROM deps AS app
COPY --from=src . .
RUN <build.steps, when any>
```

### spring

- **Runtime:** Gradle toolchain `languageVersion`, `sourceCompatibility`, Maven `<java.version>` or `maven.compiler.release`, `.java-version`, `.tool-versions`; base `eclipse-temurin:<runtime>-jdk`
- **Packages:** none
- **Manifests:** the whole source (multi-module builds need every build file); dependency downloads are cached with a BuildKit cache mount, not a layer; `build.tool` is `gradle` or `maven`
- **Module:** a multi-module build names its boot module in the manifest (`module`); the wrappers run at the build root, the module's tasks and outputs are addressed through it: Gradle `:<module>:bootJar` and `<module>/build/libs`, Maven `-pl <module> -am` and `<module>/target`; a single-module build has no `module`: the task is `bootJar`, the `-pl <module> -am` is dropped, and the paths lose the `<module>/` prefix
- **Web:** `exec java -jar /app.jar`; port 8080 (`server.port` when set)
- **Live:** Gradle `./gradlew --no-daemon :<module>:bootJar -x test && exec java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar $(ls -t <module>/build/libs/*.jar | grep -v -E -- '-(plain|sources|javadoc)\.jar$' | head -1)`; Maven `./mvnw -q -DskipTests -pl <module> -am package && exec java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar $(ls -t <module>/target/*.jar | grep -v -E -- '-(sources|javadoc)\.jar$' | head -1)`; debug port 5005. A change is picked up by `bin/dev restart <svc>` (incremental build from the cached volumes); hot swap comes from the IDE in the Dev Container
- **Migrate:** `none` - Flyway and Liquibase run at startup
- **Processes:** `none` - listeners run in-process; a separate main class or module is a second service in the manifest
- **Health:** `<context-path><base-path>/health` when `spring-boot-starter-actuator` is declared (`server.servlet.context-path`, default empty; `management.endpoints.web.base-path`, default `/actuator`); `tcp` when `management.server.port` is set (the probe reaches only `<port>`) or actuator is absent
- **Env:** `JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=75 -XX:TieredStopAtLevel=1 -XX:+UseSerialGC`; config keys use relaxed binding (`spring.datasource.url` is `SPRING_DATASOURCE_URL`), so every property has an env path
- **Trust:** prestart `keytool -importcert -noprompt -cacerts -storepass changeit -alias devenv -file /devenv/ca.pem >/dev/null 2>&1 || true` (a restarted container already holds the alias)
- **Scheme:** env `SERVER_FORWARD_HEADERS_STRATEGY=framework` (Boot trusts forwarded headers only on a detected cloud platform)
- **Live volumes:** `<svc>-gradle:/root/.gradle` or `<svc>-m2:/root/.m2`, anonymous `/app/<module>/build` or `/app/<module>/target`; **memory:** 1536m (the in-container build runs a Gradle or Maven JVM beside the app); **extensions:** `vscjava.vscode-java-pack`, `vmware.vscode-boot-dev-pack`

```dockerfile
# generated by task-domain-devenv from devenv.yaml - edit devenv.yaml or compose.local.yaml
FROM eclipse-temurin:<runtime>-jdk AS deps
RUN apt-get update && apt-get install -y --no-install-recommends <packages> && rm -rf /var/lib/apt/lists/*
WORKDIR /app
FROM deps AS app
COPY --from=src . .
RUN --mount=type=cache,target=/root/.gradle ./gradlew --no-daemon :<module>:bootJar -x test \
 && cp $(ls <module>/build/libs/*.jar | grep -v -E -- '-(plain|sources|javadoc)\.jar$' | head -1) /app.jar
```

Maven replaces the `RUN` with `RUN --mount=type=cache,target=/root/.m2 ./mvnw -q -DskipTests -pl <module> -am package && cp $(ls <module>/target/*.jar | grep -v -E -- '-(sources|javadoc)\.jar$' | head -1) /app.jar`.

### node

- **Runtime:** `.nvmrc`, `.node-version`, `.tool-versions`, `engines.node`; base `node:<runtime>-slim`
- **Packages:** `python3 make g++` with `build.native: true` (discovery: a dependency with `binding.gyp` or a `gypfile` lockfile entry); `openssl` with `prisma`
- **Manifests:** `package.json` and the lockfile of `build.tool` (`npm` `package-lock.json`, `pnpm` `pnpm-lock.yaml`, `yarn` and `yarn1` `yarn.lock`), plus the `build.manifests` discovery lists (`.npmrc`, `pnpm-workspace.yaml`, `.yarnrc.yml`, `.yarn/`, `prisma/`, `prisma.config.ts` when present; a directory gets its own `COPY --from=src <dir>/ <dir>/` line; a workspace monorepo lists `.`). Install: `npm ci`; `npm install -g corepack@latest && corepack enable && pnpm install --frozen-lockfile`; `npm install -g corepack@latest && corepack enable && yarn install --immutable` (`yarn`, 2+, which needs `nodeLinker: node-modules` - Plug'n'Play is an unknown) or `--frozen-lockfile` (`yarn1`); with `build.generate: prisma`, `&& npx prisma generate` follows the install (a Prisma 7 `output` inside the source tree is an unknown: the live mount hides the generated client; so is a `prisma.config.ts` that reads env at load, since `generate` runs with none)
- **Web:** `exec npm start` (discovery writes `processes.web: exec npm run start:prod` when that script exists); the `app` stage runs `build.steps` (`npm run build` when a `build` script exists); port 3000 (the `listen` argument or `PORT` default)
- **Live:** by `build.framework`: `nest` `exec npx nest start --watch --debug 0.0.0.0:9229`; `tsx` `exec npx tsx watch --inspect=0.0.0.0:9229 <build.entry>`; `node` `exec node --watch --inspect=0.0.0.0:9229 <build.entry>` (no polling: `node --watch` reloads only where the mount delivers file events); debug port 9229. `NODE_OPTIONS=--inspect` is never used: npm and the CLI are Node processes too and would race for the port
- **Migrate:** `npx prisma migrate deploy` with Prisma; `npm run migration:run` with TypeORM; `npx knex migrate:latest` with a knexfile; else `none`
- **Processes:** `Procfile` lines other than `web` and `release`; else a `start:worker` or `worker` script, run as `exec npm run <script>`; a process that runs built output (`dist/`) needs the `app` stage, so discovery writes it as `{run: <cmd>, live: <cmd>}` with the live command `exec npx nest start --watch --entryFile <its entry>` (`nest`), `exec npx tsx watch <its source entry>` (`tsx`), else the run command
- **Health:** the route a `@nestjs/terminus` controller or a health handler serves, else `tcp`
- **Env:** `NODE_ENV=development`; live adds `CHOKIDAR_USEPOLLING=true`, `TSC_WATCHFILE=DynamicPriorityPolling`
- **Trust:** `NODE_EXTRA_CA_CERTS=/devenv/ca.pem`, no prestart
- **Scheme:** set in code (Express `app.set('trust proxy', ...)`, Fastify `trustProxy`, NestJS through its adapter); an unknown when the code builds absolute URLs and sets neither
- **Live volumes:** anonymous `/app/node_modules`, and one per `packages/*/node_modules` in a workspace monorepo; **memory:** 512m; **extensions:** `dbaeumer.vscode-eslint`

```dockerfile
# generated by task-domain-devenv from devenv.yaml - edit devenv.yaml or compose.local.yaml
FROM node:<runtime>-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends <packages> && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=src <manifests> ./
RUN <install>
FROM deps AS app
COPY --from=src . .
RUN <build.steps, when any>
```

### python

- **Runtime:** `.python-version`, `.tool-versions`, `requires-python` (an exact version only), `runtime.txt`; base `python:<runtime>-slim`
- **Packages:** `build-essential` always; `mysqlclient` adds `default-libmysqlclient-dev pkg-config`; `psycopg2` (not `-binary`) adds `libpq-dev`; `psycopg` (not `[binary]`) adds `libpq5`
- **Manifests and install** by `build.tool`: the tool is installed with the image's pip, outside the venv, before the venv goes on `PATH`; the app installs into `/opt/venv`; `debugpy` is added last with the venv's pip. `uv` (`uv.lock`): manifests `pyproject.toml uv.lock`, install `UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-install-project`; `poetry` (`poetry.lock`): manifests `pyproject.toml poetry.lock`, install `POETRY_VIRTUALENVS_CREATE=false poetry install --no-root`; `pip`: manifests `requirements*.txt`, no tool, install `pip install -r requirements.txt` (and the dev requirements file when `build.manifests` lists it); `debugpy` goes in through `uv pip install --python /opt/venv/bin/python debugpy` with `uv` (its sync may have removed the venv's pip), else `/opt/venv/bin/pip install debugpy`
- **Web** by `build.framework`, `build.entry` the `<module>:<app>` or `<module>`: `fastapi` `exec uvicorn <module>:<app> --host 0.0.0.0 --port <port>`; `django` `exec python manage.py runserver 0.0.0.0:<port>`; `flask` `exec flask --app <module> run --host 0.0.0.0 --port <port>`; port 8000 (Flask 5000)
- **Live:** `exec python -m debugpy --listen 0.0.0.0:5678` followed by the web command's own arguments: `-m uvicorn <module>:<app> --host 0.0.0.0 --port <port> --reload`, `manage.py runserver 0.0.0.0:<port>` (Django reloads by default), `-m flask --app <module> run --host 0.0.0.0 --port <port> --debug` (Flask reloads only with `--debug`); debug port 5678
- **Migrate:** `alembic upgrade head` with `alembic.ini`; `python manage.py migrate` with Django; else `none`
- **Processes:** `Procfile` lines other than `web` and `release`; else `exec celery -A <app> worker -l info` with Celery, `exec rq worker <queue> --url $<redis key>` with RQ (the rq CLI reads `--url` or `RQ_REDIS_URL`, not the app's key); discovery fills `<app>`, `<queue>`, and the key into the manifest's process command
- **Health:** a discovered health route, else `tcp`
- **Env:** `PYTHONUNBUFFERED=1`, `PYTHONPATH=/app:/app/src` (the project itself is never installed, so a `src/` layout imports through the path); live adds `WATCHFILES_FORCE_POLLING=true`
- **Trust:** combined bundle, `SSL_CERT_FILE=/tmp/ca-bundle.pem`, `REQUESTS_CA_BUNDLE=/tmp/ca-bundle.pem`
- **Scheme:** env `FORWARDED_ALLOW_IPS=*` for uvicorn (proxy headers are its default); Django `SECURE_PROXY_SSL_HEADER` and Flask `ProxyFix` are set in code, an unknown when absent and the code builds absolute URLs
- **Live volumes:** none; **memory:** 512m; **extensions:** `ms-python.python`, `ms-python.debugpy`
- **Unknowns:** Django `ALLOWED_HOSTS` and Flask or FastAPI trusted-host settings must admit `<svc>` and the route hosts; when settings do not read them from env, that is an unknown

```dockerfile
# generated by task-domain-devenv from devenv.yaml - edit devenv.yaml or compose.local.yaml
FROM python:<runtime>-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends <packages> && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv && pip install --no-cache-dir <tool>
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY --from=src <manifests> ./
RUN <install> && <debugpy install>
FROM deps AS app
COPY --from=src . .
```

Without a tool the venv `RUN` is `python -m venv /opt/venv` alone.

### go

- **Runtime:** `toolchain`, then `go` in `go.mod`; base `golang:<runtime>`
- **Manifests:** `go.mod go.sum*`; install `go mod download`, then `GOTOOLCHAIN=auto go install <module>@<version>` for each CLI the manifest's `tools` pins: `air` (`github.com/air-verse/air`) always, `goose` (`github.com/pressly/goose/v3/cmd/goose`) or `migrate` (`-tags 'mysql,postgres' github.com/golang-migrate/migrate/v4/cmd/migrate`) when the Makefile's migrate target runs it
- **Web:** `exec /usr/local/bin/app`, built in `app` from the manifest's `main` (discovery: `./cmd/<svc>`, else the only `./cmd/*`, else `.` for a root `main.go`); port from the listen address, else 8080
- **Live:** `exec air --build.cmd 'go build -o ./tmp/app <main>' --build.bin ./tmp/app --build.poll true`; no debug port, the Go extension in the Dev Container launches Delve
- **Migrate:** the `migrate` or `goose` command a `Makefile` target runs, else `none`
- **Processes:** each other `cmd/*` the `Procfile` or `Makefile` runs, built in `app` to `/usr/local/bin/<name>` and run as `exec /usr/local/bin/<name>`; live process command `exec go run ./cmd/<name>`
- **Health:** a discovered health route, else `tcp`
- **Trust:** combined bundle, `SSL_CERT_FILE=/tmp/ca-bundle.pem`
- **Scheme:** set in code (the handler reads `X-Forwarded-Proto` itself); an unknown when the code builds absolute URLs from `r.TLS` and reads no header
- **Live volumes:** `<svc>-gomod:/go/pkg/mod`, `<svc>-gocache:/root/.cache/go-build`; **memory:** 512m (air rebuilds in the container); **extensions:** `golang.go`

```dockerfile
# generated by task-domain-devenv from devenv.yaml - edit devenv.yaml or compose.local.yaml
FROM golang:<runtime> AS deps
RUN apt-get update && apt-get install -y --no-install-recommends <packages> && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=src go.mod go.sum* ./
RUN go mod download && GOTOOLCHAIN=auto go install github.com/air-verse/air@<tools.air> && <GOTOOLCHAIN=auto go install per other tools entry>
FROM deps AS app
COPY --from=src . .
RUN go build -o /usr/local/bin/app <main> && <go build -o /usr/local/bin/<name> ./cmd/<name> per process>
```

### web

- **Runtime, packages, manifests, install:** as `node`
- **Web and live** by `build.framework`: the dev server in both modes, because public env (`NEXT_PUBLIC_*`, `VITE_*`) is inlined at build time and a dev server reads it at start: `next` `exec npx next dev -H 0.0.0.0 -p <port>`, `vite` `exec npx vite --host 0.0.0.0 --port <port> --strictPort`; port 3000 (Vite 5173); no debug port (browser devtools)
- **Migrate, processes:** `none`; a Next.js app with an ORM carries the `node` rule's migrate command in the manifest's `migrate`
- **Health:** `tcp`
- **Env:** `NODE_ENV=development`; live adds `CHOKIDAR_USEPOLLING=true` (Vite) and `WATCHPACK_POLLING=true` (Next.js with webpack; Turbopack, the Next.js 16 default, has no polling switch and relies on the mount's file events)
- **API base URL:** the key the browser uses is set to the API's origin, which also resolves inside the container (server components, route handlers) through the proxy alias; the layout reads routes from the manifest, never from a profile
- **Trust:** as `node`
- **Scheme:** not needed - the browser holds the HTTPS origin, and HMR runs over `wss` through the proxy
- **Live volumes:** anonymous `/app/node_modules`, `/app/.next`; **memory:** Next.js 1g, Vite 512m; **extensions:** `dbaeumer.vscode-eslint`
- **Unknowns:** a route host other than `*.localhost` must be listed in the dev server's allow-list - Next.js `allowedDevOrigins` (15.2+ warns, 16 blocks the request) and Vite `server.allowedHosts` (5.4.12+ and 6.0.9+ block); when the repo's config lacks the host, that is a repo-change unknown discovery reports

```dockerfile
# generated by task-domain-devenv from devenv.yaml - edit devenv.yaml or compose.local.yaml
FROM node:<runtime>-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends <packages> && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=src <manifests> ./
RUN <install>
FROM deps AS app
COPY --from=src . .
```

### custom

A person's profile for a framework without one; the manifest supplies `base` (an image with `bash`), `build.install`, `web`, and `port`. Deps: `FROM <base> AS deps`, the `apt-get` line when `packages` is set, `WORKDIR /app`, `COPY --from=src . .`, `RUN <build.install>`; app: `FROM deps AS app`. Web and live `<web>`, written with its own `exec`; no debug port, prestart, migrate (unless the manifest sets one), or processes beyond the manifest's; health `tcp`; env, live env, trust, and extensions none; scheme `set in code`; memory 512m.

## Output Format

The rendered `services/<svc>/Dockerfile` (the header line, then the profile's stages with every slot filled) and these values for the Compose templates, one block per service; `Prestart`, `Env`, and `Live env` are the profile's own (the layout adds the trust prestart, the manifest env, and the secrets):

```
- **Profile:** {rails | spring | node | python | go | web | custom}
- **Base:** {image}:{tag}
- **Port:** {container port}
- **Web:** {command}
- **Live:** {command}
- **Debug port:** {container port | none}
- **Prestart:** {command | none}
- **Migrate:** {command | none}
- **Processes:** {name: command{ | live: command}{ (live only)}; ... | none}
- **Health probe:** {bash probe | none - worker}
- **Env:** {KEY=value; ... | none}
- **Live env:** {KEY=value; ... | none}
- **Secrets:** {KEY, ... | none}
- **Trust:** {prestart | prestart; env | env | none - TLS off}
- **Scheme:** {KEY=value | trusted by default | not needed{ - TLS off} | set in code - file:line | not set - no absolute URLs built | unknown - <setting> absent, absolute URLs built at file:line}
- **Live volumes:** {volume; ... | none}
- **Memory:** {web}; worker {n | same}
- **Extensions:** {ids}
- **Unknowns:** {slot - why, ... | none}
```

## Avoid

- Putting dependencies under `/app`, where the live bind mount hides them, without the profile's live volume
- Building a frontend for production in `pinned` mode, which bakes one environment's public URLs into the bundle
- A debugger flag in an env variable every process inherits
- A double quote, or an `exec` before a build step, in a command
