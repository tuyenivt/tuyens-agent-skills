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

# Python Security Review

Stack-specific delegate of `task-code-review-security`. Names FastAPI `Depends`-based auth, OAuth2 / JWT (`pyjwt`, `authlib`, `python-jose`), Pydantic v2 validation, Django auth / DRF permission classes, ORM parameterization, and password hashing (`argon2-cffi`; `passlib[bcrypt]` only with `bcrypt<5`) directly.

## When to Use

- FastAPI or Django PR security regression review
- Pre-deploy hardening pass on auth, authz, file upload, payment, or PII paths
- Periodic validation / permission-class drift sweep
- Auditing an OAuth2 / JWT flow, a new DRF permission, or a new FastAPI security dependency

**Not for:** performance (`task-python-review-perf`), general review (`task-python-review`).

**Depth.** Security has cliff-edged consequences (auth bypass, RCE), so every run reads touched files in full and is written as `depth: deep`; scope by file, never by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                            | Label |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| **Critical** | Unauth RCE, auth bypass, mass exfiltration, working SQLi, secrets / signing keys in source, `pickle.loads` / `eval` on untrusted input. Blocks merge. | `[Must]` |
| **High**     | Authenticated priv-esc, IDOR on sensitive data, SSRF to metadata / internal, mass assignment of privilege fields, missing authz on user data.          | `[Must]` |
| **Medium**   | Hardening gap with a mitigating control elsewhere, missing field constraints, weak rate limit on a non-critical endpoint, debug exposure on non-prod.  | `[Recommend]` |
| **Low**      | Defense in depth, dependency advisory below the actively-exploited threshold, hardening without a concrete current attack.                            | `[Recommend]` |

## Invocation

`/task-python-review-security [<branch> | pr-<N>] [--base <branch>]` - no argument reviews the current branch and fails fast on trunk; `pr-<N>` needs the local branch the user fetched; flags compose: `/task-python-review-security pr-50273 --base release/2026.05`.

**Subagent mode** (spawned by `task-python-review` or `task-code-review-security`): the parent supplies the stack-detect block, the precondition handle and the read-once diff / name-status / log. Step 1 still applies; Steps 2-3 consume the supplied inputs instead of running; Step 10's data-protection rows and `out of lens` lines still run; its Verify / Reconcile / Write are skipped and the findings return as the subagent envelope in Output Format - the parent verifies, reconciles and writes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Framework

Use skill: `stack-detect`. If `Language` is not Python, stop and route to `/task-code-review-security`. `Framework` comes from the block (`FastAPI 0.115`, `Django 5.1`); the dependency manifest fills `unknown` and reveals a second framework - `fastapi` -> FastAPI, `django` -> Django; both named -> the one framework the name-status (Step 3) touches, else `mixed` (files under both or neither; both branches of every step run); neither names FastAPI or Django (Flask, plain Python) -> `unknown`: Step 4 reads the framework-neutral categories of both lists, and only the APIs a row names from a framework the project does not use go N/A; its framework-neutral items still run. Record `Framework: FastAPI | Django | mixed | unknown` - FastAPI / Django with a version (the block's when it names that framework with one, else its manifest pin, else omitted) - and the Python version (`Language`, else `requires-python` / `.python-version`, else `unknown`).

### Step 3 - Resolve the Diff and Decide the Round

Use skill: `review-precondition-check` with `argument`, `base` (from `--base`), and `report_type: review-security`. On failure, surface its message verbatim and stop; never run state-changing git. On success, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`.

**Round gate.** The handle's `prior_checkpoint` is this lens's checkpoint or `legacy`. A valid block whose `head_sha` equals the captured `head_sha` and whose `base_ref` equals the handle's -> print `No new commits since prior security review.` and stop: no review, no report. Otherwise a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` (Step 10 overwrites a legacy file). Then read once and reuse: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log <base_ref>..<head_ref>`.

### Step 4 - Read the Security Surface

Open the files that wire security so findings cite real lines:

- **FastAPI**: every `Depends(get_current_user)` / `OAuth2PasswordBearer` / `HTTPBearer` and its users; changed routers (security deps, response models, body schemas); Pydantic v2 schemas with `Field(...)` and `@field_validator` / `@model_validator`; `app/core/security.py` / `auth.py`, JWT signing config; `pyproject.toml` for `pyjwt`, `authlib`, `python-jose`, `argon2-cffi`, `passlib`; CORS, trusted hosts, HTTPS-redirect middleware; `.env.example` / settings for `SECRET_KEY`, JWT algorithm, allowed hosts.
- **Django**: `settings.py` (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `SECURE_*`, `CSRF_COOKIE_*`, `SESSION_COOKIE_*`, `AUTH_PASSWORD_VALIDATORS`); changed `views.py` / `viewsets.py` (`permission_classes`, `authentication_classes`); changed serializers (`read_only_fields`, `extra_kwargs`, validators); URL conf, admin config; `requirements.txt` for `djangorestframework`, `djangorestframework-simplejwt`, `django-allauth`, `django-axes`.

When the diff removes or relaxes a permission class, `git log -p` the prior revision to confirm what was protected.

### Step 5 - OWASP Triage (Python Lens)

Triage pass only: one verdict per category - `yes (file:line)` or `no signal in diff`. Findings belong to Steps 6-10; do not duplicate them here.

| Risk                          | Python-specific check                                                                                                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every endpoint declares authz: FastAPI `Depends(require_role("admin"))` / `Depends(get_current_user)` chained; Django `permission_classes = [IsAuthenticated, ...]` (never empty).                          |
| Injection                     | SQLAlchemy `select(...).where(Model.col == value)` parameterized; Django ORM `.filter(col=value)`; raw via `text(":param")` / `cursor.execute(sql, params)`. No string concat.                              |
| Cryptographic Failures        | `argon2-cffi` `PasswordHasher`, or `passlib[bcrypt]` pinned `bcrypt<5` (bcrypt 5 breaks passlib); Django `PASSWORD_HASHERS`. Never `hashlib.md5` / `sha1` for auth.                                        |
| Security Misconfiguration     | `DEBUG=False` in prod; `ALLOWED_HOSTS` explicit; `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`. FastAPI: `TrustedHostMiddleware`, `HTTPSRedirectMiddleware`.   |
| SSRF                          | `httpx.AsyncClient` / `requests.get` validate hostnames against an allowlist; reject RFC1918, link-local, metadata pre-request.                                                                              |
| XSS                           | Jinja2 / Django templates auto-escape - `\|safe` / `mark_safe` on user input flagged. FastAPI JSON sets the correct content type.                                                                           |
| Insecure Design               | Default-deny: FastAPI dep raises 401 unless authenticated; Django `DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]`.                                                            |
| Vulnerable Components         | `pip-audit` / `safety scan` / `uv audit` clean; Dependabot / Renovate active.                                                                                                                                |
| Data Integrity Failures       | `pickle.loads` / `yaml.load` (without `SafeLoader`) on untrusted = critical RCE. `eval` / `exec` on input = critical.                                                                                       |
| Logging & Monitoring          | Logger never logs `password` / `token` / `secret` / `authorization`. Pydantic `Field(..., repr=False)` on sensitive fields. Sentry `before_send` strips PII.                                                |

### Step 6 - Authentication

**FastAPI:**

- [ ] **JWT signing**: HS256 secret in env / Vault, or RS256 key pair (preferred cross-service); `pyjwt` / `authlib` / `python-jose` version not vulnerable to `alg=none` / key-confusion CVEs
- [ ] **`alg: none` rejected**: decoder declares `algorithms=["HS256"]` (or `["RS256"]`) explicitly; never `algorithms=None` or unspecified
- [ ] **Issuer / audience verified** by passing `issuer=` and `audience=` to `jwt.decode(...)` - `options={"verify_iss": True}` alone checks nothing without an expected value
- [ ] **Access token lifetime** short (5-15 min); refresh rotation with a revocable DB / Redis denylist
- [ ] **Password hashing**: `argon2-cffi` `PasswordHasher()`; a `passlib` `CryptContext(schemes=["bcrypt"])` only with `bcrypt<5` pinned
- [ ] **`OAuth2PasswordBearer`** `tokenUrl` matches the issuer endpoint; `auto_error=True` so a missing token 401s
- [ ] **Brute-force protection**: rate limit on `/login`, `/token`, `/password-reset` via `slowapi` or the upstream LB
- [ ] **No JWT in logs** (`print(token)` / `log.info(token)`)

**Django:**

- [ ] **`PASSWORD_HASHERS`** ordered with `Argon2PasswordHasher` first (preferred) or `PBKDF2PasswordHasher`
- [ ] **`AUTH_PASSWORD_VALIDATORS`** include length + common-password + similarity
- [ ] **`djangorestframework-simplejwt`**: `SIGNING_KEY` from env / Vault; `ROTATE_REFRESH_TOKENS=True`; `BLACKLIST_AFTER_ROTATION=True`; `ALGORITHM` explicit; `ACCESS_TOKEN_LIFETIME` minutes, not days
- [ ] **Session cookies**: `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE="Lax"` (or `"Strict"`)
- [ ] **`django-axes`** brute-force lockout configured; not disabled in test settings bleeding into prod
- [ ] **Password reset**: `default_token_generator` (time-limited) - custom generators flagged unless reviewed

### Step 7 - Authorization

**FastAPI:**

- [ ] **Authz drift sweep**: every new endpoint has a security dependency (`Depends(get_current_user)` or `Depends(require_role(...))`)
- [ ] **Role / scope checks** centralized in a dependency, not inline `if user.role != "admin": raise HTTPException(403)` scattered in handlers
- [ ] **IDOR**: scope lookups through the principal (`select(Order).where(Order.id == id, Order.owner_id == user.id)`) rather than `get_or_404(id)` plus a separate ownership check
- [ ] **Tenant isolation**: scope by `tenant_id` at the repository layer (SQLAlchemy `with_loader_criteria` for global filters), never only at the router
- [ ] **CORS**: `CORSMiddleware` `allow_origins` allowlist (never `["*"]` with credentials - it reflects any Origin); minimal methods / headers
- [ ] **CSRF**: not required for stateless JWT bearer; required for cookie sessions - confirm via the auth model

**Django / DRF:**

- [ ] **`permission_classes`** declared on every ViewSet / view; `DEFAULT_PERMISSION_CLASSES` defaults to `IsAuthenticated`
- [ ] **Object-level permissions** via `has_object_permission` for detail / update / delete - prevents IDOR on `/orders/<id>/`
- [ ] **`get_queryset()`** scopes by `request.user` for owned resources; never `.all()` unfiltered for non-admin
- [ ] **`permission_classes = []`** flagged, on the ViewSet or an `@action` - an explicit empty list is "anyone can access"
- [ ] **`@action` decorators** declare their own `permission_classes` when they differ from the ViewSet's
- [ ] **Django admin**: superuser-only by default; sensitive models check `has_change_permission` / `has_delete_permission`
- [ ] **CSRF**: `CsrfViewMiddleware` enabled (default); `@csrf_exempt` flagged with rationale; DRF `SessionAuthentication` enforces CSRF, `TokenAuthentication` / JWT does not (by design)

### Step 8 - Input Validation and Mass Assignment

**FastAPI / Pydantic v2:**

- [ ] **`model_config = ConfigDict(extra="forbid")`** on input schemas - the default `extra="ignore"` drops unknown keys silently, so probing for writable fields goes unnoticed; `extra="allow"` is a mass-assignment surface
- [ ] **Every `@router.post` / `.put` / `.patch`** has a Pydantic schema as body type - never `dict` / `Any` / raw `Request.json()`
- [ ] **Field constraints**: `Field(min_length=..., max_length=..., gt=..., pattern=...)` on every user-supplied field
- [ ] **`@field_validator`** for single-field rules; **`@model_validator(mode="after")`** for cross-field rules
- [ ] **No privilege fields in input schemas**: `role`, `is_admin`, `owner_id`, `user_id`, `tenant_id`, `is_active`, `verified` - a declared field is writable; server-set only, admin path uses a separate schema
- [ ] **`response_model`** declared - filters output, prevents leaking `password_hash`, `internal_notes`

**Django / DRF:**

- [ ] **`fields` declared explicitly** on every `ModelSerializer`; `fields = "__all__"` flagged - leaks audit / internal columns and makes every column writable
- [ ] **`read_only_fields`** cover server-controlled fields (`id`, `created_at`, `updated_at`, `owner`, `status`, `approver`)
- [ ] **Write-only fields** via `extra_kwargs = {"password": {"write_only": True}}` or `CharField(write_only=True)` - a `write_only_fields` Meta option is silently ignored
- [ ] **No `instance.__dict__.update(request.data)`** - bypasses serializer validation entirely
- [ ] **`SerializerMethodField`** for computed read-only fields, not as a mass-assignment workaround

**Both:**

- [ ] **File uploads**: type validated by content (`python-magic` / `puremagic` magic bytes), not `content_type` or extension; per-file size limit (FastAPI: bounded `UploadFile.read()` / proxy `client_max_body_size`; Django: `uploaded.size` in the validator - `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` do not cap file size); stored outside the webroot with `Content-Disposition: attachment`; filename sanitized via `(base / name).resolve().is_relative_to(base.resolve())`; virus scan or accepted risk documented
- [ ] **Path traversal**: `Path(base) / Path(user_input)` then `.resolve()` + base-directory check; never `os.path.join(base, user_input)` without normalization
- [ ] **Process exec**: `subprocess.run([...])` arg list, never `shell=True` with user input; allowlist binaries

### Step 9 - Common Python Vulnerability Patterns

Canonical "build it right" patterns: Use skill: `python-security-patterns`. The checks below flag deviations from it and add surface-specific risks (dynamic ORDER BY, SSTI, ReDoS, HTTP smuggling, trusted-proxy headers).

- [ ] **`pickle.loads` / `yaml.load` without `SafeLoader`** on untrusted input - critical RCE
- [ ] **`eval` / `exec` on user input** - critical regardless of "controlled" framing
- [ ] **`requests.get(verify=False)` / `httpx.AsyncClient(verify=False)`** flagged unless a documented test fixture
- [ ] **Open redirect**: `RedirectResponse(url=user_input)` / `HttpResponseRedirect(user_input)` validated against an allowlist or relative-path check
- [ ] **Dynamic ORDER BY**: `order_by(text(user_field))` is SQLi; Django `.order_by(user_input)` is column-name based, so the risk is field enumeration / related-field traversal, not raw SQLi - allowlist, or DRF `OrderingFilter` with explicit `ordering_fields`
- [ ] **SSTI**: `jinja2.Template(user_input).render(...)` = critical RCE; templates from disk only
- [ ] **`SECRET_KEY` / JWT signing key** from env / Vault, never committed; rotated on leak
- [ ] **Debug exposure**: `DEBUG=True` in any non-dev settings; debug toolbar dependency in prod builds
- [ ] **Swagger / docs**: gated behind auth in prod, or disabled - FastAPI `openapi_url=None` (`docs_url=None` alone leaves `/redoc` and `/openapi.json` live); DRF `SchemaView` permission
- [ ] **SSRF depth**: allowlist rejects every resolved address that is not `ip.is_global` - cloud metadata `169.254.169.254` / `fd00:ec2::254` / `100.100.100.200`, loopback, RFC1918, link-local, CGNAT `100.64/10` - plus multicast and NAT64 `64:ff9b::/96`, which `is_global` accepts. Validate the resolved IP across every A/AAAA record, then pin it for the fetch - re-resolving lets DNS rebinding through. Watch `urllib.parse` quirks: backslash, unicode, `::ffff:127.0.0.1`
- [ ] **Celery serializer**: `task_serializer = "json"` and `accept_content = ["json"]` - never `pickle`; a worker accepting `pickle` from any broker publisher is RCE by design
- [ ] **ReDoS**: Python `re` patterns (DRF `RegexValidator`, `re.match`, Pydantic `regex_engine="python-re"`) built from user / config input hang the worker; compile once at startup, never accept patterns from request bodies, cap input length. Pydantic's default Rust engine is linear-time
- [ ] **HTTP smuggling / desync** (`gunicorn -k uvicorn` behind nginx / ALB): proxy and worker agree on `Transfer-Encoding` / `Content-Length`; flag new ingress paths or middleware that change header forwarding without a proxy-side update
- [ ] **Cryptographic randomness**: tokens, reset codes, session IDs, nonces use `secrets` (`token_urlsafe(32)`, `choice`, `token_hex`) - never `random.*` or `uuid.uuid1` (leaks MAC + timestamp); `uuid.uuid4` is fine for non-security IDs
- [ ] **Trusted proxy headers**: `X-Forwarded-For` / `X-Real-IP` / `X-Forwarded-Proto` / `Host` read for audit, rate limiting, fraud or origin checks only from a trusted proxy chain - uvicorn `--forwarded-allow-ips=<LB_RANGE>` then `request.client.host`; Django `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` only behind a trusted LB, `django-ipware` with explicit `proxy_count` / `proxy_trusted_ips`

### Step 10 - Data Protection, Verify, Reconcile, Write

- [ ] **PII encrypted at rest** (`cryptography` Fernet or DB-native column encryption)
- [ ] **Logging filter** masks sensitive keys (`password`, `token`, `credit_card`, `ssn`, `api_key`); Pydantic `Field(repr=False)` and DRF write-only fields reinforce
- [ ] **No sensitive data in URLs** (POST body, headers, signed tokens) - URLs hit logs, history, referer
- [ ] **TLS**: HTTPS-only at the LB; HSTS via `SECURE_HSTS_SECONDS` / FastAPI middleware
- [ ] **DB backups encrypted**; access controlled
- [ ] **Secrets** from Vault / AWS SM / GCP SM; never `settings.py` / `config.py` literals; `.env` gitignored

Defects outside this lens that would corrupt data or break the build (a double refund, a lost update) become `out of lens` lines naming their owner, never findings. The rest of this step is standalone only; subagent runs return the envelope here.

**Verify.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line`, `Label`, and `Annotation`; its tally is the Summary's `Findings verified:` line.

**Reconcile (round 2+).** Project the prior report at the handle's `report_path` into reconcile's shape: `## High-Impact Findings`, one `### [Label] file:line` heading per finding (the label and bare `file:line` from its `####` heading - a pre-revision report with `- **Location:**` lines gives the Location's bare `file:line` and its own label when it wrote one, else `[Must]` under Critical / High, `[Recommend]` otherwise; annotations as separate `_(...)_` groups - `_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`), each followed by an `Issue:` line. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, and `head_sha`; its output renders verbatim under `## Prior Round Reconciliation`. A `Still open` / `Needs re-check` row this round did not re-derive publishes in its prior severity section at its prior label (`[Blocker]` / `[High]` / `[Critical]` -> `[Must]`; other legacy labels -> `[Recommend]`; `[Praise]` never carried) with `_(carried from round <N>)_` after its `file:line` and any annotation; a re-derived row publishes once, as this round's finding.

**Write.** Use skill: `review-report-writer` with `report_type: review-security`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `mode: full`, `round` + `prior_head_sha` from the gate, `scope: +sec`, `depth: deep`, `stack` from `Framework` (`python-fastapi | python-django | python-mixed | python`), and `pr_url` when the prior checkpoint has it. Print the confirmation line.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a fence. Every finding carries exactly one label, `[Must]` or `[Recommend]`: the rubric's Label column sets the draft and verify's published `Label` governs every slot naming one. A finding sits in the section of its severity; a `[Recommend]` under Critical after de-escalation of a pre-existing defect is correct and counts toward `<C> Critical`. A standalone finding on a file absent from the name-status whose Annotation has no group opening `pre-existing` gets `_(pre-existing)_`, written first; an `Unverified` row gets none, and an old line in a touched file takes verify's attribution. A defect spanning files anchors at the sink and names the other sites in its Issue. Subagent runs return only `## OWASP Triage` and `## Findings` (severity sections, `out of lens` lines, no annotations).

```markdown
## Python Security Review Summary

- **Stack:** Python <version>
- **Framework:** FastAPI{ <version>} | Django{ <version>} | mixed | unknown
- **Auth:** <scheme + library, e.g. OAuth2 / JWT (pyjwt), DRF SimpleJWT + Django Session> | Custom | none
- **Authorization:** FastAPI Depends-based | DRF permission_classes | Custom
- **Round:** <N>   {round 2+ only}
- **Overall Posture:** Clean | Issues Found - <C> Critical / <H> High / <M> Medium / <L> Low
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}

[2-3 sentences naming the Python-specific risks: missing `permission_classes`, absent `extra="forbid"`, `pickle.loads` on untrusted input, exposed docs in prod.]

## OWASP Triage

| Category                  | Verdict                              |
| ------------------------- | ------------------------------------ |
| Broken Access Control     | yes (file:line) \| no signal in diff |
| Injection                 | ...                                  |
| Cryptographic Failures    | ...                                  |
| Security Misconfiguration | ...                                  |
| SSRF                      | ...                                  |
| XSS                       | ...                                  |
| Insecure Design           | ...                                  |
| Vulnerable Components     | ...                                  |
| Data Integrity Failures   | ...                                  |
| Logging & Monitoring      | ...                                  |

## Findings

### Critical

#### [Must] file:line{ _(annotation)_}{ _(carried from round <N>)_}

- **Issue:** [vulnerability in Python terms - "`ShipmentCreate` declares `tenant_id`, so a client submits `{"tenant_id": 2}` and writes into another tenant"]
- **Attack scenario:** [one, labelled: (a) concrete exploit walkthrough; (b) "Regression risk: ..." for test / monitoring gaps; (c) "Topology-dependent: ..." for infra-flavored. Never invent an exploit when the realistic threat is regression or topology]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [specific Python remediation with code - `ConfigDict(extra="forbid")`, `read_only_fields`, `Depends(require_role)`]

### High / Medium / Low
[Same structure; omit empty sections]

- **out of lens:** file:line - [defect in one sentence] - owner: task-python-review-perf | task-python-review-reliability | task-python-review   {one per such defect}

## Recommendations

[Prioritized hardening not tied to a finding - "Add slowapi rate limit on /token", "Migrate python-jose to pyjwt", "Move SECRET_KEY to Vault"]

- **Could not verify from diff alone - flag for separate audit:** [CORS, rate limiting, hashing config, Sentry `before_send`, `pip-audit`]   {when any}

## Prior Round Reconciliation   {round 2+ only}

[reconcile's output verbatim]

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] file:line [scope: dependencies] - [action]
```

Within a section `[Must]` first, then by `file:line`. `[Implement]` = a localized fix; `[Delegate]` = cross-cutting hardening, a dependency upgrade or a threat model, `[scope: <owner>]` free text. Nothing found writes `No security issues found.` under `## Findings`.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed Python; `Framework` and Python version taken from stack-detect or the manifest; `mixed` settled from the name-status
- [ ] Step 3: precondition called with `argument` / `base` / `report_type: review-security`; SHAs captured; round gate decided before the diff was read (skipped on subagent runs)
- [ ] Step 4: security surface read; prior revision consulted when permission classes / security deps were removed
- [ ] Step 5: one `yes (file:line)` / `no signal in diff` verdict per OWASP category; not duplicated as findings
- [ ] Steps 6-7: auth mechanism reviewed when the auth module is in scope; authz drift sweep covered every new endpoint
- [ ] Step 8: Pydantic / DRF validation reviewed; declared privilege fields, `extra="forbid"`, `read_only_fields`, write-only via `extra_kwargs`, upload size checks confirmed
- [ ] Step 9: `python-security-patterns` consulted; `pickle` / `yaml.load` / `eval`, raw SQL, `verify=False`, dynamic ORDER BY, SSRF, Celery serializer, `secrets`, trusted-proxy headers checked when touched
- [ ] Step 10: data protection checked; `out of lens` lines emitted; verify ran and `file:line` / `Label` / `Annotation` published with the tally in Summary; round 2+ projected, reconciled, carried; report written with every writer field, or the gate stop line printed (verify / reconcile / write skipped on subagent runs)
- [ ] Every finding has an attack scenario, regression-risk, or topology framing - never "input not validated" alone; rubric applied, not invented
- [ ] Items needing repo / infra access not visible in the diff listed on the Recommendations "could not verify" line

## Avoid

- State-changing git from this workflow (the user runs fetches / checkouts)
- Skipping clean OWASP categories - state `no signal in diff` explicitly
- Generic advice when a Python idiom applies ("add `permission_classes = [IsAuthenticated]`", not "add an auth check")
- Suggesting `@csrf_exempt` / emptying `permission_classes` to silence a failing test - fix the test
- Recommending `algorithms=None` / unspecified for JWT decode - explicit allowlist only
- Approving `pickle` / `yaml.load` / `eval` / `exec` / `verify=False` outside fully trusted server input or test fixtures
- Approving `DEBUG=True` or open docs in any non-dev settings module
