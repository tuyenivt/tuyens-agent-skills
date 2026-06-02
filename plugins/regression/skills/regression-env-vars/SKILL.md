---
name: regression-env-vars
description: Env-var plumbing for .regression/ compose. All sensitive values referenced via ${VAR}, .env.example shipped, override file gitignored, pre-flight validation.
metadata:
  category: testing
  tags: [regression, env-vars, config, security, compose]
user-invocable: false
---

# Regression Env Vars

Sensitive configuration reaches the compose project only through environment variables. Committed files (`services.yaml`, `docker-compose.regression.yml`, `.env.example`) reference them by name. Values live in the developer's `.env` / `docker-compose.override.yml` (gitignored) or a CI secret store.

## When to Use

- During `task-regression-discover`: emit `.env.example`, document override mechanism.
- During `task-regression` preflight: validate that every required name is resolvable.

## Rules

1. **No sensitive values in committed files** - including `.env.example`. Placeholders only (`changeme`, `dev-only-...`, `replace_me`).
2. **Reference by name in committed files.** Always `${POSTGRES_PASSWORD}`, never the literal value.
3. **`.env.example` is the required-names manifest.** Every name listed there is preflight-required. Names of non-sensitive Compose config that need a value at run time (e.g. `POSTGRES_DB=app`) belong in committed files directly (compose `environment:` literal, not `${VAR}`), not in `.env.example` "for cohesion".
4. **Local overrides via `.env` OR `docker-compose.override.yml`.** Both gitignored. Pick one home per var: `.env` for plain compose substitution, override file when the override needs to add ports / build args / volumes too.
5. **CI uses a secret store.** The plugin does not pick one; the wrapper is one line per provider, the runner stays unchanged.
6. **Preflight is fail-closed.** `task-regression` aborts before `docker compose up` if any name from `.env.example` is unresolved.

## Patterns

### `.env.example` shape

```bash
# .regression/.env.example - committed; copy to .env and fill in real values.
# Every name listed here is preflight-required.

POSTGRES_PASSWORD=changeme         # consumed by services: db, api (via DATABASE_URL)
JWT_SIGNING_KEY=dev-only-replace
STRIPE_API_KEY=sk_test_replace_me  # use Stripe test-mode keys only
```

Comments describe which services consume the var. Placeholders are obviously fake so forgetting to edit fails loudly.

### Reference shape

```yaml
# BAD
- { name: DATABASE_URL, value: "postgres://postgres:hunter2@db:5432/app" }
- { name: JWT_SIGNING_KEY, value: "real-key" }

# GOOD
- { name: DATABASE_URL, value: "postgres://postgres:${POSTGRES_PASSWORD}@db:5432/app" }
- { name: JWT_SIGNING_KEY, value: "${JWT_SIGNING_KEY}" }
```

### Resolution order for preflight

`task-regression` calls this skill before `docker compose up`. The check, in order:

1. Parse `.regression/.env.example` for the required-names set.
2. Read the runner's process env.
3. If `.regression/.env` exists, parse it (KEY=VALUE lines, no shell expansion) and merge - **process env wins over `.env`**. This matches how Compose's later `--env-file` resolution works once `up` runs.
4. Compute the unresolved set.
5. If non-empty, abort.

```
regression: cannot start - 2 required env vars unresolved (exit 2).

Missing:
  POSTGRES_PASSWORD     declared in .env.example
  JWT_SIGNING_KEY       declared in .env.example

Resolution:
  cp .regression/.env.example .regression/.env && edit, OR
  export the vars in your shell, OR
  wrap the run with your secret store (op run / doppler run / gcloud / GH Actions env:).

Note: process env wins over .env.
```

Names only, never values. Pluralization (`1 required env var unresolved`) follows the count.

### CI integration (wrap the runner, do not template)

```bash
# 1Password
op run --env-file=.regression/.env.example -- /path/to/regression-runner
# Doppler
doppler run --project regression --config ci -- /path/to/regression-runner
# GitHub Actions
- env:
    POSTGRES_PASSWORD: ${{ secrets.REGRESSION_POSTGRES_PASSWORD }}
    JWT_SIGNING_KEY: ${{ secrets.REGRESSION_JWT_KEY }}
  run: /path/to/regression-runner
```

### Detection of accidentally-committed sensitive values

The plugin does **not** ship an inline-secret scanner; lexically, a leaked Stripe key (`sk_test_4eC3...`) is indistinguishable from a benign DB name. Recommend a repo-level secret scanner (`gitleaks`, `trufflehog`, GitHub secret scanning) in `.regression/`'s host repo. This skill's gate is structural (Rule 2: reference, never inline), not heuristic.

## Output Format

- `.regression/.env.example` (committed).
- `.gitignore` recommendation surfaced to the discover workflow: `.regression/.env`, `.regression/docker-compose.override.yml`. The discover workflow appends; this skill does not auto-edit `.gitignore`.
- The preflight error message above when validation fails. Exit code `2`.

## Avoid

- Inline sensitive values anywhere committed.
- Real values in `.env.example`. Even "expired" tempts revival.
- Mixing `.env` and `override.yml` for the same var.
- `.env` committed.
- Skipping preflight.
- Picking a secret store for the user.
- Sensitive values in Dockerfiles (`ARG`/`ENV` bake into image layers).
