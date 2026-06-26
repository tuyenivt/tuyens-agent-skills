---
name: task-python-review-security
description: "Python security review: FastAPI OAuth2/JWT, Django/DRF permissions, Pydantic validation, mass assignment, ORM injection, OWASP Top 10."
agent: python-security-engineer
metadata:
  category: backend
  tags: [python, fastapi, django, security, oauth2, jwt, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Python Security Review

Stack-specific delegate of `task-code-review-security`. Names FastAPI `Depends`-based auth, OAuth2 / JWT (`python-jose`, `pyjwt`, `authlib`), Pydantic v2 validation, Django auth / DRF permission classes, ORM parameterization, and password hashing (`passlib[bcrypt]`, `argon2-cffi`) directly.

## When to Use

- FastAPI or Django PR security regression review
- Pre-deploy hardening pass on auth, authz, file upload, payment, or PII paths
- Periodic validation / permission-class drift sweep
- Auditing OAuth2 / JWT flow, new DRF permission, or new FastAPI security dependency

**Not for:** performance (`task-python-review-perf`), general review (`task-python-review`), incident triage (`/task-oncall-start`).

**Depth.** Always full. Security has cliff-edged consequences (auth bypass, RCE); scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                            |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauth RCE, auth bypass, mass exfiltration, working SQLi, secrets / signing keys in source, `pickle.loads` / `eval` on untrusted input. Blocks merge. |
| **High**     | Authenticated priv-esc, IDOR on sensitive data, SSRF to metadata / internal, mass assignment of privilege fields, missing authz on user-data.         |
| **Medium**   | Hardening gap with mitigating control elsewhere, missing field constraints, weak rate limit on non-critical endpoint, debug exposure on non-prod.     |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited threshold, hardening without concrete current attack.                                  |

## Invocation

Mirrors `task-code-review-security`:

| Invocation                              | Meaning                                                |
| --------------------------------------- | ------------------------------------------------------ |
| `/task-python-review-security`          | Current branch vs base; fails fast on trunk            |
| `/task-python-review-security <branch>` | `<branch>` vs its base (3-dot)                         |
| `/task-python-review-security pr-<N>`   | PR head in local branch `pr-<N>` (user fetches first)  |

When invoked as a subagent of `task-code-review-security`, Step 2 is skipped and pre-read artifacts are reused.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If invoked as a delegate (parent already detected), accept pre-confirmed stack. If not Python, stop and route to `/task-code-review-security`.

Detect framework: FastAPI (`fastapi` import + `main.py`) vs Django (`manage.py` + `settings.py`). Record `Framework: FastAPI | Django | mixed`. Steps branch on this where idioms differ.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip entirely as a subagent when parent passes the handle.

If `review-precondition-check` fails fast, surface verbatim and stop. Never run state-changing git from this workflow.

### Step 3 - Read the Security Surface

Open files that actually wire security so findings cite real lines:

- **FastAPI**: every `Depends(get_current_user)` / `OAuth2PasswordBearer` / `HTTPBearer` and its users; changed routers / endpoints (security deps, response models, body schemas); Pydantic v2 schemas with `Field(...)` and `@field_validator` / `@model_validator`; `app/core/security.py` / `auth.py`, JWT signing config; `pyproject.toml` for `python-jose`, `pyjwt`, `authlib`, `passlib`, `argon2-cffi`; CORS, trusted hosts, HTTPS-redirect middleware; `.env.example` / settings for `SECRET_KEY`, JWT algorithm, allowed hosts.
- **Django**: `settings.py` (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `SECURE_*`, `CSRF_COOKIE_*`, `SESSION_COOKIE_*`, `AUTH_PASSWORD_VALIDATORS`); changed `views.py` / `viewsets.py` (`permission_classes`, `authentication_classes`); changed serializers (`read_only_fields`, `write_only_fields`, validators); URL conf, admin config; `requirements.txt` for `djangorestframework`, `djangorestframework-simplejwt`, `django-allauth`, `django-axes`.

When the diff removes a permission class or relaxes `permission_classes`, `git log -p` prior revision to confirm what was protected.

### Step 4 - OWASP Triage (Python Lens)

Triage pass only. One verdict per category (`yes` / `no signal in diff`). Findings go in Steps 5-9; do not duplicate here.

| Risk                          | Python-specific check                                                                                                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every endpoint declares authz: FastAPI `Depends(require_role("admin"))` / `Depends(get_current_user)` chained; Django `permission_classes = [IsAuthenticated, ...]` (never empty).                          |
| Injection                     | SQLAlchemy `select(...).where(Model.col == value)` parameterized; Django ORM `.filter(col=value)`; raw via `text(":param")` / `cursor.execute(sql, params)`. No string concat.                              |
| Cryptographic Failures        | `passlib[bcrypt]` (rounds >=12) or `argon2-cffi`; Django auto via `PASSWORD_HASHERS`. Never `hashlib.md5` / `sha1` for auth.                                                                                |
| Security Misconfiguration     | `DEBUG=False` in prod; `ALLOWED_HOSTS` explicit; `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`. FastAPI: `TrustedHostMiddleware`, `HTTPSRedirectMiddleware`.   |
| SSRF                          | `httpx.AsyncClient` / `requests.get` validate hostnames against allowlist; reject RFC1918, link-local, metadata pre-request.                                                                                |
| XSS                           | Jinja2 / Django templates auto-escape - `|safe` / `mark_safe` on user input flagged. FastAPI JSON sets correct content type.                                                                                |
| Insecure Design               | Default-deny: FastAPI dep raises 401 unless authenticated; Django `DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]`.                                                            |
| Vulnerable Components         | `pip-audit` / `safety check` / `uv pip audit` clean; Dependabot / Renovate active.                                                                                                                          |
| Data Integrity Failures       | `pickle.loads` / `yaml.load` (without `SafeLoader`) on untrusted = critical RCE. `eval` / `exec` on input = critical.                                                                                       |
| Logging & Monitoring          | Logger never logs `password` / `token` / `secret` / `authorization`. Pydantic `Field(..., repr=False)` on sensitive fields. Sentry `before_send` strips PII.                                                |

### Step 5 - Authentication

**FastAPI:**

- [ ] **JWT signing**: HS256 secret in env / Vault, or RS256 key pair (preferred cross-service); `python-jose` / `pyjwt` version not vulnerable to `alg=none` / key-confusion CVEs
- [ ] **`alg: none` rejected**: decoder declares `algorithms=["HS256"]` (or `["RS256"]`) explicitly; never `algorithms=None` or unspecified
- [ ] **`issuer` / `audience` verified** (`options={"verify_aud": True, "verify_iss": True}`), not just signature
- [ ] **Access token lifetime** short (5-15 min); refresh rotation with revocable DB / Redis denylist
- [ ] **Password hashing**: `passlib[bcrypt]` `CryptContext(schemes=["bcrypt"])` (rounds >=12) or `argon2-cffi`
- [ ] **`OAuth2PasswordBearer`** `tokenUrl` matches issuer endpoint; `auto_error=True` so missing token 401s
- [ ] **Brute-force protection**: rate limit on `/login`, `/token`, `/password-reset` via `slowapi` or upstream LB
- [ ] **No JWT in logs** (`print(token)` / `log.info(token)`)

**Django:**

- [ ] **`PASSWORD_HASHERS`** ordered with `Argon2PasswordHasher` first (preferred) or `PBKDF2PasswordHasher`
- [ ] **`AUTH_PASSWORD_VALIDATORS`** include length + common-password + similarity
- [ ] **`djangorestframework-simplejwt`**: `SIGNING_KEY` from env / Vault; `ROTATE_REFRESH_TOKENS=True`; `BLACKLIST_AFTER_ROTATION=True`; `ALGORITHM` explicit
- [ ] **Session cookies**: `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE="Lax"` (or `"Strict"`)
- [ ] **`django-axes`** brute-force lockout configured; not disabled in test settings bleeding into prod
- [ ] **Password reset**: `default_token_generator` (time-limited) - custom generators flagged unless reviewed

### Step 6 - Authorization

**FastAPI:**

- [ ] **Authz drift sweep**: every new endpoint has a security dependency (`Depends(get_current_user)` or `Depends(require_role(...))`)
- [ ] **Role / scope checks** centralized in a dependency, not inline `if user.role != "admin": raise HTTPException(403)` scattered in handlers
- [ ] **IDOR**: scope lookups through principal (`session.scalar(select(Order).where(Order.id == id, Order.owner_id == user.id))`) rather than `get_or_404(id)` + separate ownership check
- [ ] **Tenant isolation**: scope by `tenant_id` at repository layer (SQLAlchemy `with_loader_criteria` for global filters), not just router
- [ ] **CORS**: `CORSMiddleware` `allow_origins` allowlist (never `["*"]` for credentialed); minimal methods / headers
- [ ] **CSRF**: not required for stateless JWT-bearer; required for cookie-session - confirm via auth model

**Django / DRF:**

- [ ] **`permission_classes`** declared on every ViewSet / view; `DEFAULT_PERMISSION_CLASSES` defaults to `IsAuthenticated`
- [ ] **Object-level permissions** via `has_object_permission` for detail / update / delete - prevents IDOR on `/orders/<id>/`
- [ ] **`get_queryset()`** scopes by `request.user` for owned resources; never `.all()` unfiltered for non-admin
- [ ] **`permission_classes = []`** flagged - explicit empty list is "anyone can access"
- [ ] **`@action` decorators** declare their own `permission_classes` if they differ from ViewSet's
- [ ] **Django admin**: superuser-only by default; sensitive models check `has_change_permission` / `has_delete_permission`
- [ ] **CSRF**: `CsrfViewMiddleware` enabled (default); `@csrf_exempt` flagged with rationale; DRF `SessionAuthentication` enforces CSRF, `TokenAuthentication` / JWT does not (by design)

### Step 7 - Input Validation and Mass Assignment

**FastAPI / Pydantic v2:**

- [ ] **`model_config = ConfigDict(extra="forbid")`** on input schemas - without it, unknown fields are silently dropped and exploitation is masked
- [ ] **Every `@router.post` / `.put` / `.patch`** has a Pydantic schema as body type - never `dict` / `Any` / raw `Request.json()`
- [ ] **Field constraints**: `Field(min_length=..., max_length=..., gt=..., regex=...)` on every user-supplied field
- [ ] **`@field_validator`** for cross-field rules
- [ ] **No privilege fields in input schemas**: `role`, `is_admin`, `owner_id`, `user_id`, `tenant_id`, `is_active`, `verified` - server-set only; admin path uses a separate schema
- [ ] **`response_model`** declared - filters output, prevents leaking `password_hash`, `internal_notes`

**Django / DRF:**

- [ ] **`fields` declared explicitly** on every `ModelSerializer`; `fields = "__all__"` flagged - leaks audit / internal columns
- [ ] **`read_only_fields`** cover server-controlled fields (`id`, `created_at`, `updated_at`, `owner`, `status`)
- [ ] **`write_only_fields`** cover sensitive write-only fields (`password`)
- [ ] **No `instance.__dict__.update(request.data)`** - bypasses serializer validation entirely
- [ ] **`SerializerMethodField`** for computed read-only fields, not as a mass-assignment workaround

**Both:**

- [ ] **File uploads**: type validated by content (`python-magic` / `puremagic` magic bytes), not `content_type` header or extension; per-file size limit (FastAPI middleware or `UploadFile.read()` size check; Django `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE`); stored outside webroot with `Content-Disposition: attachment`; filename sanitized via `(base / name).resolve().is_relative_to(base.resolve())`; virus scan or accepted-risk documented
- [ ] **Path traversal**: `Path(base) / Path(user_input)` then `.resolve()` + base-directory check; never `os.path.join(base, user_input)` without normalization
- [ ] **Process exec**: `subprocess.run([...])` arg list, never `shell=True` with user input; allowlist binaries

### Step 8 - Common Python Vulnerability Patterns

- [ ] **`pickle.loads` / `yaml.load` without `SafeLoader`** on untrusted input - critical RCE
- [ ] **`eval` / `exec` on user input** - critical regardless of "controlled" framing
- [ ] **`requests.get(verify=False)` / `httpx.AsyncClient(verify=False)`** flagged unless documented test fixture
- [ ] **Open redirect**: `RedirectResponse(url=user_input)` / `HttpResponseRedirect(user_input)` validated against allowlist or relative-path check
- [ ] **Dynamic ORDER BY**: `order_by(text(user_field))` is SQLi; Django `Order.objects.order_by(user_input)` is column-name-based so the risk is field enumeration / data exposure (and related-field traversal), not raw SQLi - allowlist `user_field`, or in DRF use `OrderingFilter` with explicit `ordering_fields`
- [ ] **SSTI**: `Jinja2.Template(user_input).render(...)` = critical RCE; templates from disk only
- [ ] **`SECRET_KEY` / JWT signing key** from env / Vault, never committed; rotated on leak
- [ ] **Debug exposure**: `DEBUG=True` flagged in any non-dev settings; debug toolbar dep flagged in prod builds
- [ ] **Swagger / `/docs`**: gated behind auth in prod, or disabled (FastAPI `docs_url=None`; DRF `SchemaView` permission)
- [ ] **SSRF depth**: allowlist rejects (a) cloud metadata `169.254.169.254` + IPv6 `fd00:ec2::254`, (b) localhost / `127.0.0.0/8` / `::1`, (c) RFC1918 (`10/8`, `172.16/12`, `192.168/16`), (d) link-local `169.254/16`. Re-resolve host at request time (DNS rebinding bypasses string-only allowlists). Watch `urllib.parse` quirks: backslash, unicode, `::ffff:127.0.0.1`
- [ ] **Celery serializer**: `task_serializer` / `accept_content` set to `["json"]` only - never `pickle`. A worker accepting `pickle` from any source that can publish to the broker is RCE by design
- [ ] **ReDoS**: `Field(pattern=...)` / DRF `RegexValidator(...)` built from user / config input hangs the event loop. Compile patterns once at startup; never accept patterns from request bodies; bound with `re.match` + length cap
- [ ] **HTTP smuggling / desync** (`gunicorn -k uvicorn` behind nginx / ALB): confirm proxy and worker agree on `Transfer-Encoding` / `Content-Length`; flag new ingress paths or middleware that change header forwarding without proxy-side update
- [ ] **Cryptographic randomness**: tokens, reset codes, session IDs, nonces use `secrets` (`secrets.token_urlsafe(32)`, `secrets.choice`, `secrets.token_hex`) - **never** `random.*` (predictable seed, brute-forceable) or `uuid.uuid1` (leaks MAC + timestamp). `uuid.uuid4` OK for non-security IDs
- [ ] **Trusted proxy headers**: when reading `X-Forwarded-For` / `X-Real-IP` / `X-Forwarded-Proto` / `Host` for audit, rate limiting, fraud, or origin checks, value must come from a trusted proxy chain. FastAPI / uvicorn: `--forwarded-allow-ips=<LB_RANGE>` then `request.client.host` after `ProxyHeadersMiddleware`. Django: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` only behind a trusted LB; `django-ipware` with explicit `proxy_count` / `proxy_trusted_ips`. Naive header reads let any client spoof source IP and poison logs / bypass rate limits

### Step 9 - Data Protection

- [ ] **PII encrypted at rest** (`cryptography` Fernet, `django-fernet-fields`, or DB-native column encryption)
- [ ] **Logging filter** masks sensitive keys (`password`, `token`, `credit_card`, `ssn`, `api_key`); Pydantic `Field(repr=False)` and DRF `write_only_fields` reinforce
- [ ] **No sensitive data in URLs** (use POST body, headers, signed tokens) - URLs hit logs, history, referer
- [ ] **TLS**: HTTPS-only at LB; HSTS via `SECURE_HSTS_SECONDS` / FastAPI middleware
- [ ] **DB backups encrypted**; access controlled
- [ ] **Secrets** from Vault / AWS SM / GCP SM; never `settings.py` / `config.py` literals; `.env` gitignored

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled review to file and print the confirmation line.

## Output Format

```markdown
## Python Security Review Summary

**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Auth:** OAuth2 / JWT (python-jose) | OAuth2 / JWT (pyjwt) | DRF SimpleJWT | Django Session | Custom | Hybrid
**Authorization:** FastAPI Depends-based | DRF permission_classes | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment calling out Python-specific risks: missing `permission_classes`, absent `extra="forbid"`, `pickle.loads` on untrusted input, exposed `/docs` in prod.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | yes / no signal in diff |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF                      | ...                     |
| XSS                       | ...                     |
| Insecure Design           | ...                     |
| Vulnerable Components     | ...                     |
| Data Integrity Failures   | ...                     |
| Logging & Monitoring      | ...                     |

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability in Python terms - e.g., "OrderCreate schema lacks `extra='forbid'`; client submits `{\"owner_id\": 999}` and overrides server-assigned owner via mass assignment"]
- **Attack scenario:** [pick one and label: (a) concrete exploit walkthrough; (b) "Regression risk: ..." for test / monitoring gaps; (c) "Topology-dependent: ..." for infra-flavored. Do NOT invent exploits when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [specific Python remediation with code - `ConfigDict(extra='forbid')`, `read_only_fields`, `Depends(require_role)`, etc.]

### High / Medium / Low

[Same structure. Omit sections with no findings. If all omitted, state "No security issues found."]

## Recommendations

[Prioritized hardening not tied to a specific finding - e.g., "Add slowapi rate limit on /token", "Migrate from python-jose to pyjwt", "Move SECRET_KEY to Vault"]

## Next Steps

Tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting hardening, dependency upgrade, threat model). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Omit if no security issues found._
```

## Self-Check

**Verifiable from diff:**

- [ ] Step 1: Python confirmed; `Framework: FastAPI | Django | mixed` recorded
- [ ] Step 2: `review-precondition-check` ran (or handle received); `base_ref` / `head_ref` / `current_branch` / `head_matches_current` captured; diff + log read once and reused; user approval obtained when `head_matches_current` was false (skipped as subagent)
- [ ] Step 3: security surface read directly; prior revision consulted when permission classes / security deps were removed
- [ ] Step 4: OWASP triage produced one verdict per category (`yes` / `no signal in diff`); not duplicated as findings
- [ ] Steps 5-6: authz drift sweep covered every new endpoint
- [ ] Step 7: Pydantic / DRF validation reviewed; mass-assignment fields, `extra="forbid"` / `read_only_fields` confirmed
- [ ] Step 8: `pickle.loads`, `yaml.load`, `eval` / `exec`, raw SQL via `text(...)` / `cursor.execute`, `verify=False`, dynamic ORDER BY, SSRF, Celery serializer, `secrets` randomness, trusted-proxy headers checked when touched
- [ ] Severity rubric applied consistently (not invented)
- [ ] Every finding has attack scenario, regression-risk, or topology-dependent framing - never "input not validated" alone
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend > Question (omit if no findings)

**Requires repo / infra access (note "could not verify from diff alone - flag for separate audit" if not visible):**

- [ ] Step 5: auth mechanism in use reviewed (FastAPI OAuth2 / JWT, Django session, DRF JWT) - applies when auth module in scope
- [ ] Steps 6-8: CORS, rate limiting, debug toolbar / `/docs` exposure, password hashing config (bcrypt rounds >=12), Sentry `before_send` - applies when middleware / settings in scope
- [ ] `pip-audit` / `safety check` - run separately; this workflow does not execute tools
- [ ] Step 10: review report written via `review-report-writer`; confirmation printed

## Avoid

- Running state-changing git from this workflow (user runs fetches / checkouts)
- Reporting vulnerabilities without an attack scenario - "input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment because `extra='forbid'` is missing"
- Skipping clean OWASP categories - explicitly state `no signal in diff`
- Generic advice when a Python idiom applies ("add `permission_classes = [IsAuthenticated]`", not "add an auth check")
- Suggesting `@csrf_exempt` / disabling `permission_classes` to silence a failing test - fix the test
- Recommending `algorithms=None` / unspecified for JWT decode - explicit allowlist only
- Approving `pickle` / `yaml.load` / `eval` / `exec` / `verify=False` outside fully trusted server input or test fixtures
- Approving `DEBUG=True` or open `/docs` in any non-dev settings module
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
