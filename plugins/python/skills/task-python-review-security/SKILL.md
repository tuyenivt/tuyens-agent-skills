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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Python Security Review

## Purpose

Python-aware security review that names FastAPI `Depends`-based auth, OAuth2 / JWT (`python-jose`, `authlib`, `pyjwt`), Pydantic v2 validation, Django auth / DRF permission classes, ORM parameterization, password hashing (`passlib[bcrypt]`, `argon2-cffi`), and async context isolation idioms directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete Python-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Python. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a FastAPI or Django PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-validation and permission-class drift sweep across endpoints
- Auditing an OAuth2 / JWT flow, a new DRF permission, or a new FastAPI security dependency

**Not for:**

- Performance review (use `task-code-review-perf` or `task-python-review-perf`)
- General code review (use `task-code-review` or `task-python-review`)
- Production incident triage (use `/task-oncall-start`)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (auth bypass, RCE) that do not benefit from a "light" mode. If callers want a shallower pass, they should scope by file, not by depth.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, authentication bypass, mass data exfiltration, working SQL injection on a production code path, secrets / signing keys exposed in source. Must fix before deploy; blocks merge.                                                                   |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata or internal services, mass assignment of privilege-bearing fields, missing authorization on user-data endpoints. Must fix before merge.                                     |
| **Medium**   | Hardening gap with a mitigating control elsewhere (e.g., missing CORS when a reverse proxy enforces origin), missing field-level constraints, weak rate limiting on a non-critical endpoint, debug exposure on a non-prod profile. Should fix this PR or the next one. |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below the actively-exploited threshold, hardening recommendations without a concrete current attack scenario.                                                                                                       |

## Invocation

Mirrors `task-code-review-security`:

| Invocation                              | Meaning                                                                                               |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-python-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-python-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-python-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-python-review` (parent already detected Python), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Python, stop and tell the user to invoke `/task-code-review-security` instead.

Detect framework: FastAPI (`fastapi` import + `main.py`) vs Django (`manage.py` + `settings.py`). Record `Framework: FastAPI | Django | mixed` for the Summary block. Each step that follows branches on this signal where the idiom differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

**FastAPI surface:**

- Every `Depends(get_current_user)` / `OAuth2PasswordBearer` / `HTTPBearer` definition and the modules that use them
- Every changed router / endpoint - look for `Depends(...)` security dependencies, response models, request body schemas
- Every Pydantic v2 schema with `Field(...)` constraints and `@field_validator` / `@model_validator`
- `app/core/security.py` / `app/core/auth.py` / token signing config; `pyproject.toml` for `python-jose`, `pyjwt`, `authlib`, `passlib`, `argon2-cffi`
- Middleware config - CORS, trusted hosts, HTTPS redirect
- `.env.example` / settings module for SECRET_KEY, JWT algorithm, allowed hosts

**Django surface:**

- `settings.py` - `SECRET_KEY` source, `DEBUG`, `ALLOWED_HOSTS`, `SECURE_*` flags, `CSRF_COOKIE_*`, `SESSION_COOKIE_*`, `AUTH_PASSWORD_VALIDATORS`
- Every changed `views.py` / `viewsets.py` - `permission_classes`, `authentication_classes`, custom permission classes
- Every changed serializer - `read_only_fields`, `write_only_fields`, custom validators
- URL conf for new endpoints; admin config
- `pyproject.toml` / `requirements.txt` for `django-rest-framework`, `djangorestframework-simplejwt`, `django-allauth`, `django-axes`

When the diff removes a permission class or relaxes `permission_classes`, also `git log -p` the prior revision of those lines to confirm what was protected before. The blame trail is the authoritative answer to "did this change weaken authorization."

### Step 4 - OWASP Triage (Python Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `Injection: yes`, `SSRF: yes`, `Insecure Design: no`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

The triage output funnels which downstream steps must run carefully versus which can be fast-passed. If a category shows no signal, explicitly state `No signal in diff` for that category in the Summary.

| Risk                          | Python-specific check                                                                                                                                                                                      |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every endpoint declares authorization explicitly. FastAPI: `Depends(require_role("admin"))` or `Depends(get_current_user)` chained. Django: `permission_classes = [IsAuthenticated, ...]` (never empty).   |
| Injection                     | SQLAlchemy uses `select(...).where(Model.col == value)` parameterized; no string concat. Django ORM uses `.filter(col=value)`. Raw SQL via `text(":param")` / `cursor.execute(sql, params)`.               |
| Cryptographic Failures        | `passlib[bcrypt]` or `argon2-cffi` for passwords. Django auto-uses PBKDF2 / Argon2 via `PASSWORD_HASHERS`. Never `hashlib.md5` / `hashlib.sha1` for auth.                                                  |
| Security Misconfiguration     | `DEBUG=False` in prod; `ALLOWED_HOSTS` explicit; `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`. FastAPI: `TrustedHostMiddleware`, `HTTPSRedirectMiddleware`. |
| SSRF                          | `httpx.AsyncClient` / `requests.get` validate hostnames against an allowlist before request; no user-controlled URL passed unvalidated.                                                                    |
| XSS                           | Jinja2 / Django templates auto-escape - `|safe` / `mark_safe` on user input flagged. FastAPI JSON responses set `Content-Type: application/json`.                                                          |
| Insecure Design (A04)         | Default-deny: FastAPI dependency raises 401 unless authenticated; Django `DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]`.                                                    |
| Vulnerable Components (A06)   | `pip-audit`, `safety check`, or `uv pip audit` clean; Dependabot / Renovate active. No pinned-but-stale package with known CVE.                                                                            |
| Data Integrity Failures (A08) | `pickle.loads` / `yaml.load` (without `SafeLoader`) on untrusted input flagged. JSON dumps / `orjson` is safe. `eval` / `exec` on input is a critical finding.                                             |
| Logging & Monitoring (A09)    | Logger does not log `password`, `token`, `secret`, `authorization`. Pydantic schemas use `Field(..., repr=False)` for sensitive fields. Sentry `before_send` strips PII. Auth events logged.               |

### Step 5 - Authentication

**FastAPI:**

- [ ] **JWT signing**: HS256 secret in env / Vault, never committed to repo; or RS256 with key pair (preferred for cross-service). `python-jose` or `pyjwt` - confirm version not vulnerable to known `alg=none` / key-confusion CVEs
- [ ] **`alg: none`** rejected: decoder declares `algorithms=["HS256"]` (or `["RS256"]`) explicitly; never `algorithms=None` or unspecified
- [ ] **JWT issuer / audience** validated (`options={"verify_aud": True, "verify_iss": True}`); not just signature
- [ ] **Access token lifetime** short (5-15 min); refresh token rotation; refresh tokens revocable via DB / Redis denylist
- [ ] **Password hashing**: `passlib[bcrypt]` `CryptContext(schemes=["bcrypt"])`, or `argon2-cffi` direct. Cost factor reviewed (bcrypt rounds ≥ 12)
- [ ] **`OAuth2PasswordBearer`** wired correctly; `tokenUrl` matches the issuer endpoint; `auto_error=True` so missing tokens 401 rather than silently allowing
- [ ] **Brute-force protection**: rate limiting on `/login`, `/token`, `/password-reset` via `slowapi` or upstream LB
- [ ] **No `print(token)` / `log.info(token)`** that leaks the JWT to logs

**Django:**

- [ ] **Password hashing**: `PASSWORD_HASHERS` ordered with `Argon2PasswordHasher` first (preferred) or `PBKDF2PasswordHasher` (default acceptable)
- [ ] **`AUTH_PASSWORD_VALIDATORS`** include length + common-password + similarity validators
- [ ] **JWT (`djangorestframework-simplejwt`)**: `SIGNING_KEY` from env / Vault; `ROTATE_REFRESH_TOKENS=True`; `BLACKLIST_AFTER_ROTATION=True`; `ALGORITHM="HS256"` or `"RS256"` explicit
- [ ] **Session cookies**: `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"` (or `"Strict"` for sensitive apps)
- [ ] **`django-axes` or equivalent**: brute-force lockout configured; not silently disabled in tests bleeding into prod settings
- [ ] **Password reset tokens**: `default_token_generator` (Django built-in, time-limited) - not a custom generator unless reviewed

### Step 6 - Authorization

**FastAPI:**

- [ ] **Authorization drift sweep**: every new endpoint added in the diff has a security dependency (`Depends(get_current_user)` or `Depends(require_role(...))`)
- [ ] **Role / scope checks** centralized in a dependency, not inline `if user.role != "admin": raise HTTPException(403)` scattered in handlers
- [ ] **IDOR**: lookups scope through the principal (`session.scalar(select(Order).where(Order.id == id, Order.owner_id == user.id))`) rather than `get_or_404(id)` then a separate ownership check
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `tenant_id` at the repository layer (not just at the router); SQLAlchemy `with_loader_criteria` for global filters
- [ ] **CORS**: `CORSMiddleware` `allow_origins` explicit (not `["*"]` for credentialed requests); `allow_methods` and `allow_headers` minimal
- [ ] **CSRF**: not required for stateless JWT-bearer APIs; required for cookie-session apps - confirm via auth model

**Django / DRF:**

- [ ] **`permission_classes`** declared on every ViewSet / view; `DEFAULT_PERMISSION_CLASSES` defaults to `IsAuthenticated`
- [ ] **Object-level permissions** via `has_object_permission` for detail / update / delete endpoints - prevents IDOR on `/orders/<id>/`
- [ ] **`get_queryset()`** scopes by `request.user` for user-owned resources; never returns `.all()` unfiltered for non-admin users
- [ ] **`@permission_classes([])` or `permission_classes = []`** flagged - explicit empty list is "anyone can access"
- [ ] **`@action` decorators** declare their own `permission_classes` if they differ from the ViewSet's
- [ ] **Django admin**: superuser-only by default; sensitive models check `has_change_permission` / `has_delete_permission`
- [ ] **CSRF**: `CsrfViewMiddleware` enabled (default); `@csrf_exempt` flagged with rationale; DRF `SessionAuthentication` enforces CSRF, `TokenAuthentication` / JWT does not (by design)

### Step 7 - Input Validation and Mass Assignment

**FastAPI / Pydantic v2:**

- [ ] **Every `@router.post` / `.put` / `.patch`** has a Pydantic v2 schema as the request body type - never `dict` / `Any` / raw `Request.json()` without validation
- [ ] **Field constraints**: `Field(min_length=..., max_length=..., gt=..., regex=...)` on every user-supplied field
- [ ] **`@field_validator`** for cross-field or business rules (e.g., "end date after start date")
- [ ] **No privilege-bearing fields in user-facing input schemas**: `role`, `is_admin`, `owner_id`, `user_id`, `tenant_id`, `is_active`, `verified` - server-set only. If present in `OrderCreate`, reject and require admin-only path with a separate schema
- [ ] **`model_config = ConfigDict(extra="forbid")`** on input schemas - rejects unknown fields rather than silently dropping them; without this, an attacker submitting unknown fields gets 200 OK and the field is ignored, masking exploitation attempts
- [ ] **`response_model`** declared - filters output fields and prevents accidental leakage of `password_hash`, `internal_notes`, etc.

**Django / DRF:**

- [ ] **`fields`** declared explicitly on every `ModelSerializer`; `fields = "__all__"` flagged - leaks every column including audit / internal fields
- [ ] **`read_only_fields`** include server-controlled fields (`id`, `created_at`, `updated_at`, `owner`, `status`)
- [ ] **`write_only_fields`** include sensitive fields that go in but never come out (`password`)
- [ ] **No `instance.__dict__.update(request.data)`** patterns - bypasses serializer validation entirely
- [ ] **`SerializerMethodField`** used for computed read-only fields, not as a mass-assignment workaround

**Both:**

- [ ] **File uploads**:
  - File type validated by content (`python-magic`, `puremagic`), not just `content_type` header (client-controlled) or extension
  - Per-file size limit enforced (FastAPI: middleware or manual `UploadFile.read()` with size check; Django: `DATA_UPLOAD_MAX_MEMORY_SIZE`, `FILE_UPLOAD_MAX_MEMORY_SIZE`)
  - Saved files stored outside the webroot; `Content-Disposition: attachment` on serve
  - Filename sanitized via `pathlib.Path` and base-directory check (`(base / name).resolve().is_relative_to(base.resolve())`) before write
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: `Path(base) / Path(user_input)` followed by `.resolve()` and base-directory check; never `os.path.join(base, user_input)` without normalization
- [ ] **Process execution**: `subprocess.run([...])` with arg list (not `shell=True` and not `subprocess.run(f"... {user_input} ...", shell=True)`); strict allowlist of allowed binaries

### Step 8 - Common Python Vulnerability Patterns

- [ ] **`pickle.loads` / `yaml.load(...)` without `Loader=SafeLoader`** on untrusted input - critical RCE vector
- [ ] **`eval` / `exec`** on user input - any occurrence is a critical finding regardless of "controlled" framing
- [ ] **`requests.get(verify=False)`** / `httpx.AsyncClient(verify=False)` flagged unless behind a documented test fixture
- [ ] **Open redirect**: `RedirectResponse(url=user_input)` / `HttpResponseRedirect(user_input)` validated against an allowlist or relative-path check
- [ ] **SQL injection via dynamic ORDER BY**: `select(...).order_by(text(user_field))` - validate `user_field` against an allowlist; for Django, `Order.objects.order_by(user_input)` similarly
- [ ] **Server-side template injection**: Jinja2 `Template(user_input).render(...)` is a critical RCE vector; templates must come from disk, not request bodies
- [ ] **`SECRET_KEY` / JWT signing key** sourced from env / Vault, never committed; rotated when leaked
- [ ] **Debug toolbar / Django debug**: `DEBUG=True` flagged in any non-dev settings file; debug toolbar dependency flagged in `requirements.txt` for prod builds
- [ ] **Swagger UI / `/docs`**: gated behind auth in prod, or disabled (`docs_url=None` for FastAPI; DRF `SchemaView` permission)
- [ ] **SSRF depth**: when a user-controlled value flows into an outbound URL or hostname, the allowlist must reject (a) cloud metadata IP `169.254.169.254` and IPv6 equivalent `fd00:ec2::254`, (b) localhost / `127.0.0.0/8` / `::1`, (c) private RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), (d) link-local `169.254.0.0/16`. Resolve the host **after** parsing (DNS rebinding bypasses string-only allowlists - re-resolve at request time and re-check). `urllib.parse` quirks: backslash, unicode normalization, IPv4-in-IPv6 (`::ffff:127.0.0.1`) all defeat naive checks.
- [ ] **Celery serializer**: `task_serializer` / `accept_content` set to `["json"]` only - never `pickle`. A worker accepting `pickle` from any source that can publish to the broker is a remote code execution by design.
- [ ] **ReDoS via user-supplied regex**: `Field(pattern=...)` / DRF `RegexValidator(...)` constructed from user input or config-driven patterns can hang the event loop on adversarial inputs. Compile patterns once at startup; never accept patterns from request bodies; bound matches with `re.match` plus a length cap, not unbounded `re.search`.
- [ ] **HTTP request smuggling / desync** (`gunicorn -k uvicorn` behind nginx / ALB): confirm reverse proxy and worker agree on `Transfer-Encoding` / `Content-Length` handling; flag when a new ingress path or middleware changes header forwarding without a corresponding proxy-side update.
- [ ] **Cryptographic randomness**: any token, reset code, session ID, password-reset PIN, or signed payload nonce uses `secrets` module (`secrets.token_urlsafe(32)`, `secrets.choice(...)`, `secrets.token_hex(...)`) - **never** `random.randint` / `random.choice` / `uuid.uuid1` (predictable from MAC + timestamp). `random` is seeded predictably and can be brute-forced once a few outputs are observed. `uuid.uuid4` is acceptable for non-security-critical IDs but `secrets.token_urlsafe` is preferred for security-critical paths.
- [ ] **Trusted proxy / forwarded-header safety**: when the app reads `X-Forwarded-For`, `X-Real-IP`, `X-Forwarded-Proto`, or `Host` for audit logging, rate limiting, fraud signals, or origin checks, the value must come from a trusted proxy chain - not from the raw header. FastAPI / uvicorn: `--forwarded-allow-ips=<LB_IP_RANGE>` and read `request.client.host` after `ProxyHeadersMiddleware` parses it; Django: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` only when behind a trusted LB, and use `django-ipware` with explicit `proxy_count` / `proxy_trusted_ips`. Reading the header naively (`request.headers.get("X-Real-IP")`) on a non-proxied or misconfigured deployment lets any client spoof the source IP and bypass rate limits / poison audit logs.

### Step 9 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (`cryptography` Fernet, `django-fernet-fields`, or DB-native column encryption)
- [ ] **Logging filter** masks sensitive keys (`password`, `token`, `credit_card`, `ssn`, `api_key`); Pydantic `Field(repr=False)` and Django serializer `write_only_fields` reinforce
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens) - URLs hit logs, browser history, referer headers
- [ ] **TLS enforcement**: HTTPS-only at LB; HSTS via `SECURE_HSTS_SECONDS` / FastAPI middleware
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: env vars from a secret store (Vault / AWS Secrets Manager / GCP Secret Manager), never `settings.py` / `config.py` literals committed; `.env` gitignored


### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries (FastAPI request body, Celery task args, external API responses, message payloads)
- Never disable CSRF or permission classes to silence a failing test - fix the test
- Never widen `permission_classes` (e.g., from `[IsAdminUser]` to `[]`) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny via `IsAuthenticated` / `Depends(get_current_user)`

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as Python; framework (FastAPI / Django / mixed) recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Security surface (auth dependencies / settings, changed routers / views, schemas / serializers, middleware, dependencies) read directly before applying checklists; prior revision consulted when permission classes or security dependencies were removed
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Authorization drift sweep**: every new endpoint in the diff has a matching security dependency or `permission_classes`
- [ ] Pydantic v2 / DRF serializer validation reviewed; mass-assignment fields and `extra="forbid"` / `read_only_fields` confirmed for changed schemas
- [ ] File upload, path traversal, and process-execution checks run if the diff touches uploads / file paths / `subprocess`
- [ ] `pickle.loads`, `yaml.load`, `eval` / `exec`, raw SQL via `text(...)` / `cursor.execute`, SSL-verify-False, dynamic ORDER BY checked when the diff touches them
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented)
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for test-coverage gaps), or "topology-dependent" framing (for infra-flavored findings) - not just "input not validated"
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Authentication step run for the auth mechanism in use (FastAPI OAuth2 / JWT or Django session / DRF JWT) - applies when the auth module is in scope
- [ ] CSRF, CORS, rate limiting, debug-toolbar / `/docs` exposure verified - applies when middleware / settings are in scope
- [ ] Password hashing config reviewed (bcrypt rounds ≥ 12, Argon2 preferred) - skip if `CryptContext` config not in diff
- [ ] Sentry `before_send` strips PII - skip if Sentry init module not in diff
- [ ] `pip-audit` / `safety check` clean - run separately; this workflow does not execute tools
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Python Security Review Summary

**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Auth:** OAuth2 / JWT (python-jose) | OAuth2 / JWT (pyjwt) | DRF SimpleJWT | Django Session | Custom | Hybrid
**Authorization:** FastAPI Depends-based | DRF permission_classes | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Python-specific risks like missing `permission_classes`, `extra="forbid"` absent on input schemas, `pickle.loads` on untrusted input, or exposed `/docs` in prod.]

## OWASP Triage

_The Step 4 verdicts. One row per category, `yes` (signal present, see Findings) or `no signal in diff`._

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

- **Location:** [file:line, or comma-separated list for multi-site findings: `schemas/order.py:12-19, routers/orders.py:54`]
- **Issue:** [vulnerability described in Python terms - e.g., "OrderCreate schema lacks `extra='forbid'`; client can submit `{\"owner_id\": 999}` and override the server-assigned owner via mass assignment"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough — e.g., "Attacker POSTs `{\"items\": [...], \"owner_id\": 1}` and reassigns the order to user 1"; (b) "Regression risk: the next refactor silently removes one of these protections" — for test-coverage / monitoring gaps; (c) "Topology-dependent: depends on whether the reverse proxy strips X-Forwarded-Proto correctly" — for infra-flavored findings like missing CORS / TrustedHost. Pick one and label which. Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies, e.g., "High - authenticated privilege escalation"]
- **Fix:** [specific Python remediation with code example - `model_config = ConfigDict(extra='forbid')`, `read_only_fields`, `Depends(require_role)`, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add slowapi rate limit on /token", "Migrate from python-jose to pyjwt (more actively maintained)", "Move SECRET_KEY from settings.py literal to env var"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Add `model_config = ConfigDict(extra='forbid')` to OrderCreate; remove `owner_id` from accepted fields"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `pip-audit` and upgrade flagged packages - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment because the input schema accepts unknown fields")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a Python idiom applies (say "add `permission_classes = [IsAuthenticated]`", not "add an authorization check")
- Suggesting `@csrf_exempt` as a fix for a failing form submission - validate the test sends a CSRF token instead
- Disabling permission classes to silence a missing-auth warning - add the missing class
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Recommending `algorithms=None` / unspecified algorithms for JWT decode - explicit allowlist is the only safe form
- Recommending `pickle` / `yaml.load` / `eval` / `exec` as acceptable on any input not under full server control
- Approving `verify=False` on TLS clients outside test fixtures
- Approving `DEBUG=True` or open `/docs` in any non-dev settings module
