---
name: regression-env-vars
description: Env-var plumbing for .regression/ compose. All sensitive values referenced via ${VAR}, .env.example shipped, override file gitignored, pre-flight validation.
metadata:
  category: testing
  tags: [regression, env-vars, config, security, compose]
user-invocable: false
---

# Regression Env Vars

Sensitive configuration reaches the compose project only through environment variables. The committed files (`services.yaml`, `docker-compose.regression.yml`, `.env.example`) reference them by name. Actual values live in the developer's local `.env` / `docker-compose.override.yml` (gitignored) or a CI secret store.

## When to Use

- During `task-regression-discover` to emit `.env.example` and document the override pattern.
- During `task-regression` preflight to validate that every required env var is resolved before `up`.

## Rules

1. **Never commit a sensitive value.** No exceptions for "test-only" passwords. Pre-commit hooks won't catch this skill's output; the skill is the gate.
2. **Reference by name in committed files.** Always `${POSTGRES_PASSWORD}`, never `password: hunter2`.
3. **Ship `.env.example` with placeholder values.** Committed. Lists every required var with a one-line description and a safe placeholder (`changeme`, `dev-only`, empty string with a comment).
4. **Local overrides via `.env` or `docker-compose.override.yml`.** Gitignored. Never both for the same var - document the precedence.
5. **CI uses a secret store, not committed files.** The runner reads env vars from the CI environment; the skill does not opine on which store (1Password / Doppler / GCP Secret Manager / AWS SSM / Vault / GitHub Actions - all wrap the runner identically).
6. **Pre-flight error on unresolved vars.** `task-regression` aborts before `up` with a precise error naming every unresolved var.

## Patterns

### `.env.example` shape

```bash
# .regression/.env.example - committed
# Copy to `.env` and fill in real values. `.env` is gitignored.
# All names must match references in services.yaml and docker-compose.regression.yml.

# --- database ---
POSTGRES_PASSWORD=changeme         # used by db service and DATABASE_URL in api
POSTGRES_DB=app                    # plain config, not sensitive; left here for cohesion

# --- backend ---
JWT_SIGNING_KEY=dev-only-32-byte-placeholder-replace
STRIPE_API_KEY=sk_test_replace_me  # use a Stripe test-mode key only

# --- frontend ---
# (no sensitive values at frontend layer in this template)
```

Comments describe *which service consumes the var*, not the value. Placeholders are obviously fake (`changeme`, `replace_me`, `dev-only-...`) so a developer who forgets to edit them fails loudly.

### `services.yaml` reference shape

Bad:

```yaml
- name: api
  env:
    - { name: DATABASE_URL, value: "postgres://postgres:hunter2@db:5432/app" }
    - { name: JWT_SIGNING_KEY, value: "actually-a-real-key-oops" }
```

Good:

```yaml
- name: api
  env:
    - { name: DATABASE_URL, value: "postgres://postgres:${POSTGRES_PASSWORD}@db:5432/app" }
    - { name: JWT_SIGNING_KEY, value: "${JWT_SIGNING_KEY}" }
```

Same rule for `docker-compose.regression.yml`. The compose `environment:` block uses `${VAR}` and Compose substitutes from the process env at `up` time.

### Local override pattern

Two equivalent options - document both, pick one per project:

**Option A: `.env` file** (simpler, Compose loads it automatically when present beside `docker-compose.regression.yml`):

```
.regression/.env             # gitignored, real values
.regression/.env.example     # committed, placeholder values
```

**Option B: `docker-compose.override.yml`** (more flexible, allows port shifts and developer-specific tweaks alongside sensitive overrides):

```yaml
# .regression/docker-compose.override.yml - gitignored
services:
  db:
    environment:
      POSTGRES_PASSWORD: my-local-password
  api:
    ports: ["8080:8080"]                          # developer-only host port
```

Document the precedence in the plugin README: Compose merges override on top of base, and `.env` substitutions resolve before merge. Do not mix the same var across both - pick one home per var.

### CI integration (wrap the runner)

The skill does not pick a secret store. CI configs wrap the runner invocation with whatever the store provides:

```bash
# 1Password
op run --env-file=.regression/.env.example -- /path/to/regression-runner

# Doppler
doppler run --project regression --config ci -- /path/to/regression-runner

# GCP Secret Manager (via gcloud)
eval "$(gcloud secrets versions access latest --secret=regression-env)" && /path/to/regression-runner

# GitHub Actions
- env:
    POSTGRES_PASSWORD: ${{ secrets.REGRESSION_POSTGRES_PASSWORD }}
    JWT_SIGNING_KEY: ${{ secrets.REGRESSION_JWT_KEY }}
  run: /path/to/regression-runner
```

The runner stays identical; only the wrapper changes. This is why the plugin does not ship CI templates - the wrapper is one line per provider and the rest is unchanged.

### Pre-flight validation

`task-regression` calls this skill before `docker compose up`. The check:

1. Parse `.env.example` for the set of required names.
2. Read process env (already merged with `.env` if present).
3. Compute the unresolved set.
4. If non-empty, abort with the format below.

Error format:

```
regression: cannot start - 2 required env vars are unresolved.

Missing:
  POSTGRES_PASSWORD       (declared in .env.example, consumed by services: db, api)
  JWT_SIGNING_KEY         (declared in .env.example, consumed by services: api)

Resolution:
  cp .regression/.env.example .regression/.env && edit it, OR
  export the vars in your shell, OR
  wrap the run with your secret store: op run / doppler run / gcloud / ...

See .regression/.env.example for placeholder values and per-var descriptions.
```

Never proceed past this check. A run that starts with a missing sensitive value fails opaquely inside the container with no audit trail.

### Detection of accidentally-committed sensitive values

A best-effort guard, not a replacement for repo-level secret scanning:

- `regression-service-inventory` rejects any `services.yaml` entry where an env `value` contains characters outside `[A-Za-z0-9_${}/.@:-]` *and* does not start with `${`. Heuristic, but catches the common case (a pasted production password).
- The skill recommends enabling the user's preferred secret scanner (`gitleaks`, `trufflehog`, GitHub secret scanning) at repo level - it does not ship one.

## Output Format

- `.regression/.env.example` (committed) - the placeholder file.
- A `.gitignore` block contribution: `.regression/.env` and `.regression/docker-compose.override.yml` (the discover workflow appends these).
- A pre-flight error message (above format) emitted by `task-regression` when validation fails.

## Avoid

- **Inline sensitive values** anywhere committed.
- **Real values in `.env.example`.** Placeholders only. A "real but expired" value tempts revival.
- **Mixing `.env` and `override.yml` for the same var.** Hard to reason about precedence; pick one home per var.
- **`.env` committed.** Always gitignored. The `.example` suffix is the committed sibling.
- **Skipping pre-flight.** A run that starts with missing values fails opaquely; the user wastes minutes debugging.
- **Picking a secret store for the user.** The plugin wraps. The user picks.
- **Storing sensitive values in Dockerfiles.** `ARG` and `ENV` in a Dockerfile bake into the image layer; reference at `services.yaml` / compose level instead.
