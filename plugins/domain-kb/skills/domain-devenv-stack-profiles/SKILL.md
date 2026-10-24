---
name: domain-devenv-stack-profiles
description: "Per-stack dev runtime profiles: Dockerfile stages, run, live-reload and debug commands, workers, migrations, health, volumes, memory, trust."
metadata:
  category: domain
  tags: [domain, devenv, dockerfile, live-reload, debug, rails, spring, node, python, go, nextjs]
user-invocable: false
---

# Domain Dev Environment Stack Profiles

> Load `Use skill: domain-devenv-layout` first: it owns the manifest fields these profiles read (`runtime`, `port`, `debug_port`, `kind`, `packages`, `processes`, `migrate`, `health`, `secrets`, `tls.issuer`, the `build` map, `module`, `main`, `tools`, `base`, `web`), the Compose templates the values below fill, the header line, and the naming contract.

One profile per stack, each answering the same slots, so the Compose templates never change per stack. A stack outside this file is added as one more profile; a single service that deviates overrides a slot in its manifest entry instead.

## When to Use

- `domain-devenv-discovery` choosing a service's profile and the profile-specific evidence to look for
- `task-domain-devenv` rendering a service's Dockerfile and Compose entries

## Rules

- **Profile by detected framework**, per repo: `rails` (Rails), `spring` (Spring Boot, Gradle or Maven), `node` (NestJS, Express, Fastify, other Node servers), `python` (FastAPI, Django, Flask), `go` (Gin, net/http, other Go servers), `web` (Next.js, Vite React or Vue). Any other framework is `unknown - no profile for <Framework>` in discovery; a person then sets `profile: custom` with `base`, `build.install`, `web`, and `port` (the layout renders it), or the service stays out of the render.
- **Repo facts arrive through the manifest.** A profile never reads the repository: discovery fills the service's `build` map (`tool`, `framework`, `entry`, `debugger`, `generate`, `native`, `bundler`, `node`, `js_tool`, `framework_version`, `secrets`, `ssh`, `manifests` - extra files or directories `deps` copies, `steps` - commands the `app` stage runs after the copy; `install`, an install command replacing the profile's, is a person's), the `processes` commands (a process that needs another command in live mode as `{run: <cmd>, live: <cmd>}`, a live-only one as `{live: <cmd>}`), and the profile fields (`module`, `main`, `tools`); each profile below names the keys it reads and when. A profile line conditioned on repo evidence (a gem, a Procfile line, a routed path, a credentials file, a lockfile) is a check discovery runs and records in the manifest (`packages`, `processes`, `health`, `migrate`, `secrets`, `build`); rendering reads the recorded field and never re-applies the condition: a `<dependency> adds <package>` line below is such a check, discovery writes the package into `packages`, and rendering installs the profile's always-installed set plus `packages`; a line conditioned on a `build.*` key reads that key directly. A key a profile needs for this service that is absent keeps the service out of the render, as an `unknown` value does; an absent `build.framework_version` reads as Rails 7.1 or later.
- **A manifest value beats the profile.** `default` in a manifest slot means the profile's value; anything else replaces it. `packages` adds to the profile's always-installed set, never replaces it.
- **Two stages, one Dockerfile.** Each Dockerfile starts with the layout's header as a `#` line. `deps` is the runtime, system packages (the `apt-get` line is dropped when the package list is empty), and dependencies installed from the manifests alone, so `live` gets them without the code; `app` is `deps` plus the code (and its build), for `pinned`. Dependencies install outside `/app`, so the live bind mount never hides them, except where a profile names a live volume for them. In every template, `deps` also copies `build.manifests` (an empty list adds nothing to the `COPY` line; a `.` entry copies the whole source; an entry inside a subdirectory, or a directory entry, gets its own `COPY --from=src <path> <dir>/` line between the `<manifests>` line and the install `RUN`, so a workspace keeps its layout), a `build.install` replaces the install `RUN` shown, and `app` runs `build.steps` after its copy. Every `RUN` that installs dependencies or runs `build.steps`, the spring build `RUN` included and the python venv `RUN` (which installs only the tool) excluded, adds `--mount=type=secret,id=<KEY>` per `build.secrets` entry and starts `export <KEY>=$(cat /run/secrets/<KEY>) && `, and with `build.ssh` adds `--mount=type=ssh` and starts `export GIT_SSH_COMMAND='ssh -o StrictHostKeyChecking=accept-new' && ` (a build has no `known_hosts`), and `build.ssh` adds `openssh-client git` to the packages of every profile but `go` (the slim and temurin images ship no SSH client; `golang` ships both); the secret never lands in a layer. A live command that installs (the rails web prefix with a `js` or `css` line, the spring live build) runs at container start without the build secrets, so with `build.secrets` set it adds the `Unknowns` entry `build.secrets: <KEY> needed by the live install - a person exports it in sources.env`.
- **Commands.** Every command (web, live, process) begins with `exec` on its final process (a build or install step before it is chained with `&&`), so the process receives signals, uses single quotes only, and writes a shell variable as `$VAR` and the probe's `\r\n` singly: the Output Format block carries commands as written here, and the layout doubles `$` and `\` when it places them in Compose; a Dockerfile `RUN` keeps them single. The manifest's `debug_port` is the host side; the profile's debug port is the container side the layout maps it to.
- **Health probe.** A path is probed over HTTP and must answer `200`; `tcp` only opens the port. Both run under `bash`, which every profile's image has (a `custom` base must): `exec 3<>/dev/tcp/127.0.0.1/<port> && printf 'GET <path> HTTP/1.1\r\nHost: <svc>\r\nX-Forwarded-Proto: https\r\nConnection: close\r\n\r\n' >&3 && head -1 <&3 | grep -q ' 200 '` (`Host: <svc>` passes the host allow-lists the profiles require, Vite's once `server.allowedHosts` lists `<svc>`; the forwarded scheme keeps a service that forces HTTPS from redirecting the probe), or `exec 3<>/dev/tcp/127.0.0.1/<port>`.
- **Forwarded scheme.** With TLS on, the proxy terminates HTTPS and sends `X-Forwarded-Proto: https`; a framework that ignores it builds `http://` redirect and callback URLs, which breaks OAuth. Each profile's `Scheme` slot says how its framework trusts the header: a `KEY=value` the render sets, `trusted by default`, `not needed` (the browser holds the origin), or `set in code`, which discovery checks and reports as an unknown when absent while the code builds absolute URLs; with TLS off every profile's `Scheme` reads `not needed - TLS off`.
- **Trust, only with TLS on.** The CA is mounted at `/devenv/ca.pem`. A profile trusts it additively through env, or through the combined bundle its trust prestart builds, `cat /etc/ssl/certs/ca-certificates.crt /devenv/ca.pem > /tmp/ca-bundle.pem`, so public certificates keep working; the layout runs the trust prestart before the profile's own.
- **Versions come from the repo.** The runtime version is read from the files each profile names, in order, with a `ruby-`, `ruby ` (`Gemfile.lock` `RUBY VERSION ruby 3.3.0p0`), `python-`, `==`, `v`, or `go` prefix, a `.tool-versions` tool name and its space (`ruby`, `nodejs`, `python`, `golang`, `java`), and a Ruby patchlevel (`p32`) stripped; Java keeps only its major (`temurin-21.0.4+7.0.LTS`, `JavaVersion.VERSION_21` -> `21`); a range (`>=3.11`), an alias (`lts/*`), or nothing found is `unknown`, never a guess. The runtime tag must exist for the base image.

## Patterns

### rails

- **Runtime:** `.ruby-version`, `.tool-versions`, `ruby` in `Gemfile`, `RUBY VERSION` in `Gemfile.lock`; base `ruby:<runtime>-slim`
- **Packages:** always `build-essential git pkg-config libyaml-dev`; `mysql2` adds `default-libmysqlclient-dev`, `pg` adds `libpq-dev`, `ruby-vips` or `image_processing` adds `libvips-dev`, a `js` line in `Procfile.dev`, or a `css` line with a `package.json` (a tailwindcss-rails `css` line alone uses the gem's standalone binary and needs no Node), adds `nodejs npm`, unless `build.node` pins a version: `deps` then takes Node from `node:<build.node>-slim` (`COPY --from=node:<build.node>-slim /usr/local/bin/node /usr/local/bin/`, `COPY --from=node:<build.node>-slim /usr/local/lib/node_modules/ /usr/local/lib/node_modules/`, `RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx`), before the `apt-get` line
- **Manifests:** `Gemfile Gemfile.lock`; a `Gemfile` with `gemspec` or a `path:` gem copies the whole source before `bundle install` (`build.manifests: [.]`); with a `js` or `css` line and a `package.json`, that file and its lockfile too (`build.manifests`), and the `app` stage runs `build.steps` (`<install> && npm run build`, `<install> && npm run build:css` - `<install>` the `node` profile's install for the lockfile's tool, the `yarn` script forms with `yarn.lock` - or `bin/rails tailwindcss:build`, whichever the repo has)
- **Web:** `exec bin/rails server -b 0.0.0.0 -p <port>`; port 3000; the explicit `-b` and `-p` take precedence over the binds in the server config, a TLS bind included
- **Live:** with `build.debugger: rdbg` (discovery: `debug` in `Gemfile.lock`), `exec bundle exec rdbg -O --host 0.0.0.0 --port 12345 --nonstop -c -- bin/rails server -b 0.0.0.0 -p <port>`, debug port 12345; without it, the web command and no debug port; with `build.js_tool` set (discovery: a `js` or `css` Procfile line and a `package.json`), the command is prefixed by the `node` profile's install for that tool and `&& ` (`npm ci`; `yarn1`, `yarn`, and `pnpm` through corepack, `export COREPACK_ENABLE_DOWNLOAD_PROMPT=0 && ` before `corepack enable` included, as the `node` install writes it). Code reloads per request through the Rails reloader, which works on any mount; `config.file_watcher = ActiveSupport::EventedFileUpdateChecker` can miss changes on Mac and Windows mounts and is an unknown when set
- **Prestart:** `rm -f tmp/pids/server.pid` (a restarted container keeps it, and Rails refuses to boot over it); every other profile has none
- **Migrate:** `bin/rails db:prepare` (Rails 7.1+: loads the schema and seeds the provisioned, still empty database; migrates one that has a schema). Below 7.1 it only migrates a database that exists, so `Database create` reads `false - Rails below 7.1` and the workflow writes `create: false` on the service's database engine: the database is absent at first boot, and `db:prepare` creates it, loads the schema, and seeds
- **Processes:** `Procfile` or `Procfile.dev` lines other than `web` and `release`, by name; `js` and `css` lines are live-only processes, `{live: exec <line>}` with a watcher that survives a closed stdin (`tailwindcss:watch[always]`, esbuild `--watch=forever`), their JS dependencies installed by the web `Live` prefix above into the live volume below, which a process, starting only once the service is healthy, finds done (pinned builds their output through `build.steps`); without a Procfile, by gem: `sidekiq` `exec bundle exec sidekiq`, `solid_queue` `exec bin/jobs`, `good_job` `exec bundle exec good_job start`, `resque` `exec bundle exec rake resque:work QUEUE='*'`, `sneakers` `exec bundle exec rake sneakers:run`
- **Health:** `/up` when `config/routes.rb` routes it, else a discovered health route, else `tcp`
- **Env:** `RAILS_ENV=development`, `DISABLE_SPRING=1`, `RAILS_DEVELOPMENT_HOSTS=<svc>,<svc>.localhost` plus each route host, Rails 7.0+ by `build.framework_version` (the development host check blocks any other name; below 7.0 the variable does not exist and is not emitted, so the repo's own `config.hosts` must admit those names, else a repo-change unknown discovery reports; a `config.hosts =` assignment in `development.rb` replaces the list and is an unknown discovery reports)
- **Secrets:** `RAILS_MASTER_KEY` when development reads credentials (`config/credentials.yml.enc` or `config/credentials/development.yml.enc` exists and code calls `Rails.application.credentials`), a discovery check written to the manifest's `secrets`
- **Trust:** combined bundle, `SSL_CERT_FILE=/tmp/ca-bundle.pem`
- **Scheme:** trusted by default (Rack reads `X-Forwarded-Proto`), so `force_ssl` and `Secure` cookies see HTTPS
- **Live volumes:** `<svc>-node-modules:/app/node_modules` when the web `Live` command carries the install prefix, else none; **memory:** web 768m, worker 512m; **extensions:** `Shopify.ruby-lsp`, `KoichiSasada.vscode-rdbg`

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
- **Packages:** `python3 make g++` with `build.native: true` (discovery: the lockfile marks an install script); `openssl` with `build.generate: prisma`
- **Manifests:** `package.json` and the lockfile of `build.tool` (`npm` `package-lock.json`, `pnpm` `pnpm-lock.yaml`, `yarn` and `yarn1` `yarn.lock`), plus the `build.manifests` discovery lists (`.npmrc`, `pnpm-workspace.yaml`, `.yarnrc.yml`, `.yarn/`, `prisma/`, `prisma.config.ts` when present; a directory gets its own `COPY --from=src <dir>/ <dir>/` line; a workspace monorepo lists `.`). Install: `npm ci`; `npm install -g corepack@latest && export COREPACK_ENABLE_DOWNLOAD_PROMPT=0 && corepack enable && pnpm install --frozen-lockfile`; `npm install -g corepack@latest && export COREPACK_ENABLE_DOWNLOAD_PROMPT=0 && corepack enable && yarn install --immutable` (`yarn`, 2+, which needs `nodeLinker: node-modules` - Plug'n'Play is an unknown) or `--frozen-lockfile` (`yarn1`); with `build.generate: prisma`, `&& npx prisma generate` follows the install (a Prisma 7 `output` inside the source tree is an unknown: the live mount hides the generated client; so is a `prisma.config.ts` that calls `env()` from `prisma/config`, since `generate` runs with none)
- **Web:** `exec npm start` (discovery writes `processes.web: exec npm run start:prod` when that script exists); the `app` stage runs `build.steps` (`npm run build` when a `build` script exists); port 3000 (the `listen` argument or `PORT` default)
- **Live:** by `build.framework`: `nest` `exec npx nest start --watch --debug 0.0.0.0:9229`; `tsx` `exec npx tsx watch --inspect=0.0.0.0:9229 <build.entry>`; `node` `exec node --watch --inspect=0.0.0.0:9229 <build.entry>` (no polling: `node --watch` reloads only where the mount delivers file events); debug port 9229. `NODE_OPTIONS=--inspect` is never used: npm and the CLI are Node processes too and would race for the port
- **Migrate:** `npx prisma migrate deploy` with Prisma; `npm run migration:run` with TypeORM when that script exists, else, when the repo declares `ts-node`, `npx typeorm-ts-node-commonjs migration:run -d <data-source file>` (`typeorm-ts-node-esm` with `"type": "module"`), `npx typeorm migration:run -d <file>` for a built `.js` data source, a TypeScript data source without `ts-node` being an unknown; `npx knex migrate:latest` with a knexfile; else `none`
- **Processes:** `Procfile` lines other than `web` and `release`; else a `start:worker` or `worker` script, run as `exec npm run <script>`; a process that runs built output (`dist/`) needs the `app` stage, so discovery writes it as `{run: <cmd>, live: <cmd>}` with the live command `exec npx nest start --watch --entryFile <its entry>` (`nest`), `exec npx tsx watch <its source entry>` (`tsx`), else the run command
- **Health:** the route a `@nestjs/terminus` controller or a health handler serves, else `tcp`
- **Env:** `NODE_ENV=development`; live adds `CHOKIDAR_USEPOLLING=true`, `TSC_WATCHFILE=DynamicPriorityPolling`
- **Trust:** `NODE_EXTRA_CA_CERTS=/devenv/ca.pem`, no prestart
- **Scheme:** set in code (Express `app.set('trust proxy', ...)`, Fastify `trustProxy`, NestJS through its adapter); discovery's unknown when the code builds absolute URLs and sets neither
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
- **Scheme:** env `FORWARDED_ALLOW_IPS=*` for uvicorn (proxy headers are its default); Django `SECURE_PROXY_SSL_HEADER` and Flask `ProxyFix` are set in code, discovery's unknown when absent and the code builds absolute URLs
- **Live volumes:** none; **memory:** 512m; **extensions:** `ms-python.python`, `ms-python.debugpy`
- **Unknowns:** Django `ALLOWED_HOSTS` and Flask or FastAPI trusted-host settings must admit `<svc>` and the route hosts; when settings do not read them from env, that is a repo-change unknown discovery reports

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
- **Packages:** none (the image ships git and openssh-client; `build.ssh` adds nothing)
- **Manifests:** `go.mod go.sum*`; install `go mod download` (with `build.ssh`: preceded, per distinct host of the `build.ssh` prefixes, by `git config --global url.'ssh://git@<host>/'.insteadOf 'https://<host>/' && ` and run with `GOPRIVATE=<prefix>,<prefix>`, the manifest's `build.ssh` list, since the public module proxy never uses the SSH agent), then `GOTOOLCHAIN=auto go install <module>@<version>` for each CLI the manifest's `tools` pins: `air` (`github.com/air-verse/air`) always, `goose` (`github.com/pressly/goose/v3/cmd/goose`) or `migrate` (`-tags 'mysql,postgres' github.com/golang-migrate/migrate/v4/cmd/migrate`) when the Makefile's migrate target runs it
- **Web:** `exec /usr/local/bin/app`, built in `app` from the manifest's `main` (discovery: `./cmd/<svc>`, else the only `./cmd/*`, else `.` for a root `main.go`); port from the listen address, else 8080
- **Live:** `exec air --build.cmd 'go build -o ./tmp/app <main>' --build.bin ./tmp/app --build.poll true`; no debug port, the Go extension in the Dev Container launches Delve
- **Migrate:** the `migrate` or `goose` command a `Makefile` target runs, else `none`
- **Processes:** each other `cmd/*` the `Procfile` or `Makefile` runs, built in `app` to `/usr/local/bin/<name>` and run as `exec /usr/local/bin/<name>`; live process command `exec go run ./cmd/<name>`
- **Health:** a discovered health route, else `tcp`
- **Trust:** combined bundle, `SSL_CERT_FILE=/tmp/ca-bundle.pem`
- **Scheme:** set in code (the handler reads `X-Forwarded-Proto` itself); discovery's unknown when the code builds absolute URLs from `r.TLS` and reads no header
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
- **Web and live** by `build.framework`: the dev server in both modes, because public env (`NEXT_PUBLIC_*`, `VITE_*`) is inlined at build time and a dev server reads it at start: `next` `exec npx next dev -H 0.0.0.0 -p <port>` (`--webpack` appended with `build.bundler: webpack-flag`), `vite` `exec npx vite --host 0.0.0.0 --port <port> --strictPort`; port 3000 (Vite 5173); no debug port (browser devtools)
- **Migrate, processes:** `none`; a Next.js app with an ORM carries the `node` rule's migrate command in the manifest's `migrate`
- **Health:** a discovered health route, else `tcp`
- **Env:** `NODE_ENV=development`; live adds `CHOKIDAR_USEPOLLING=true` (Vite) and `WATCHPACK_POLLING=true` with `build.bundler: webpack-flag` or `webpack`; Turbopack adds none: it has no polling env (only `watchOptions.pollIntervalMs` in `next.config`, a repo change) and relies on the mount's file events
- **API base URL:** the key the browser uses is set to the API's origin, which also resolves inside the container (server components, route handlers) through the proxy alias; the layout reads routes from the manifest, never from a profile
- **Trust:** as `node`
- **Scheme:** `not needed` (the browser holds the HTTPS origin, and HMR runs over `wss` through the proxy)
- **Live volumes:** anonymous `/app/node_modules`, `/app/.next`; **memory:** Next.js 1g, Vite 512m; **extensions:** `dbaeumer.vscode-eslint`
- **Unknowns:** a route host other than `*.localhost` must be listed in the dev server's allow-list - Next.js `allowedDevOrigins` (15.2.4 to 16.1 warn when it is unset; 15.2.2, 15.2.3, and 16.2+ block) and Vite `server.allowedHosts` (4.5.6+, 5.4.12+, and 6.0.9+ block), which must also list `<svc>` for the health probe; when the repo's config lacks a name, that is a repo-change unknown discovery reports

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
- **Database create:** {true | false - Rails below 7.1 | none}
- **Processes:** {name: command{ | live: command}{ (live only)}; ... | none}          {every process but web}
- **Health probe:** {bash probe | none - worker}
- **Env:** {KEY=value; ... | none}
- **Live env:** {KEY=value; ... | none}
- **Trust:** {prestart: <command>; env: KEY=value{, KEY=value} | prestart: <command> | env: KEY=value{, KEY=value} | none - TLS off | none}
- **Scheme:** {KEY=value | trusted by default | not needed{ - TLS off} | set in code}
- **Live volumes:** {volume; ... | none}
- **Memory:** {web}; worker {n | none - no worker process}
- **Extensions:** {ids | none}
- **Unknowns:** {slot - why, ... | none}          {only the entries rendering itself raises; the manifest's unknowns are the layout's}
```

A slot the service's profile does not name reads `none`. `Trust` carries the parts the layout places, split on `; `: the prestart command and the env, several keys joined with `, ` (rails: `prestart: cat /etc/ssl/certs/ca-certificates.crt /devenv/ca.pem > /tmp/ca-bundle.pem; env: SSL_CERT_FILE=/tmp/ca-bundle.pem`; python's env `SSL_CERT_FILE=/tmp/ca-bundle.pem, REQUESTS_CA_BUNDLE=/tmp/ca-bundle.pem`). `Database create` is read by the layout for `uses.<engine>.create`. `Database create` is `true` for Rails 7.1+ and `none` for every other profile. A worker is every process but web; `Live volumes` writes an anonymous volume as its container path (`/app/node_modules`) and a named one as `<name>:<path>`.

## Avoid

- Putting dependencies under `/app`, where the live bind mount hides them, without the profile's live volume
- Building a frontend for production in `pinned` mode, which bakes one environment's public URLs into the bundle
- A debugger flag in an env variable every process inherits
- A double quote, or an `exec` before a build step, in a command
