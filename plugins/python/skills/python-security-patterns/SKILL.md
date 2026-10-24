---
name: python-security-patterns
description: Python security - JWT (PyJWT), password hashing, Pydantic mass-assignment, authz scoping, SSRF, file upload, pickle/eval prohibitions, secrets.
metadata:
  category: backend
  tags: [python, fastapi, django, security, jwt, owasp, ssrf, pydantic]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Canonical "build it right" security patterns for FastAPI / Django. `task-python-review-security` delegates here and only flags deviations.

## When to Use

- Wiring auth (FastAPI `OAuth2PasswordBearer` / `HTTPBearer`, Django/DRF auth) or authz (dependencies / permission classes / queryset scoping)
- Adding Pydantic schemas or DRF serializers that touch user-supplied data
- Implementing file upload, webhook receivers, SSRF-exposed outbound HTTP, raw SQL, or `subprocess` callers
- Loading secrets / typed settings with env validation
- Reviewing any code path that crosses an untrusted boundary

## Rules

- JWT via PyJWT (or `python-jose >= 3.4` - 3.3 carries CVE-2024-33663/33664); every decode declares `algorithms=[...]` (python-jose without it accepts any algorithm the key supports) and verifies `iss` / `aud`; `sub` is a string
- Password hashing via `argon2-cffi` (`PasswordHasher()`); Django `PASSWORD_HASHERS` with Argon2 first. `passlib` is unmaintained and breaks with `bcrypt>=5` - if kept, pin `bcrypt<5`, rounds >= 12. Never `hashlib` for passwords
- Every request body has a Pydantic schema (`ConfigDict(extra="forbid")`) or DRF serializer with explicit `fields`; privilege fields (`role`, `is_admin`, `owner_id`, `user_id`, `tenant_id`, `verified`) are server-set, never on the input contract
- `response_model` (FastAPI) / explicit serializer `fields` (DRF) filter output - never leak `password_hash`, internal columns, or raw exception text (`str(e)` in a response body)
- Every object read or write is scoped to the caller (`where(Order.tenant_id == user.tenant_id)` / `get_queryset()` filter), not only guarded by a permission class; a foreign resource returns 404
- Never `pickle.loads`, `yaml.load(..., Loader=yaml.Loader|UnsafeLoader)`, `eval`, or `exec` on untrusted input - Critical RCE regardless of "controlled" framing
- SQL goes through the ORM or bound parameters; never f-string / `%` user input into `raw()`, `cursor.execute()`, or `text()`
- Outbound `httpx` / `requests` with a user-controlled URL resolves the host **once**, rejects any record that is not `is_global` (RFC1918, loopback, link-local `169.254.169.254`, `100.64.0.0/10` incl. `100.100.100.200`), is multicast, or is NAT64 `64:ff9b::/96`, and connects to the vetted IP with `Host`/SNI set - a second resolution at fetch time reopens DNS rebinding
- Inbound webhooks verify an HMAC signature over the raw body (`hmac.compare_digest`) and reject stale timestamps - never process an unauthenticated receiver payload
- File uploads validated by magic bytes (`puremagic` / `python-magic`), not the `content_type` header; size-capped per file in the validator and at the proxy (`client_max_body_size`); stored outside webroot under a server-generated name; served with `Content-Disposition: attachment`
- `subprocess.run([...])` arg list only - never `shell=True` with user input; allowlist binaries
- Secrets via `pydantic-settings` `BaseSettings` (or Django env loader), failing at startup on missing keys; sourced from Vault / AWS SM / GCP SM, never literals; `.env` gitignored
- Tokens / reset codes / nonces use `secrets` (`secrets.token_urlsafe(32)`), never `random.*` or `uuid.uuid1`; single-use codes are stored hashed with a TTL and consumed atomically
- Redirects on user input: resolve with `urljoin` against the app's own origin and compare the parsed `netloc`, or allowlist paths - `startswith("/")` is bypassed by `//evil.com`
- `verify=False` on TLS clients only in documented test fixtures

## Patterns

### JWT Signing and Verification

```python
import jwt                                   # PyJWT
from datetime import datetime, timedelta, timezone

# Bad: jwt.decode(token, key) - PyJWT raises DecodeError, python-jose accepts any algorithm the key supports
payload = jwt.decode(token, key, algorithms=["HS256"], issuer="api", audience="web")   # ["RS256"] cross-service
token = jwt.encode(                          # exp/iss/aud at signing; sub is a string; short TTL
    {"sub": str(user.id), "iss": "api", "aud": "web", "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
    key, algorithm="HS256")
```

Access tokens 5-15 min; refresh tokens rotated and revocable (`jti` denylist, or an allowlist of live `jti`s) and marked `"typ": "refresh"` so one cannot stand in for the other. Django: `djangorestframework-simplejwt` with `SIGNING_KEY` from env, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True` (requires `rest_framework_simplejwt.token_blacklist` in `INSTALLED_APPS` + migrate), explicit `ALGORITHM`.

### Password Hashing and Single-Use Codes

```python
import hashlib, secrets
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

ph = PasswordHasher()                                          # argon2id, sane defaults
hashed = ph.hash(password)
try: ph.verify(hashed, candidate)                              # ph.check_needs_rehash(hashed) -> rehash on login
except (VerificationError, InvalidHashError): raise InvalidCredentials()  # app-defined; mismatch, corrupt argon2 row, or legacy-scheme row

# Reset code: random, stored hashed, expiring, consumed once
code = secrets.token_urlsafe(32)
await repo.store_reset(user.id, hashlib.sha256(code.encode()).hexdigest(), expires_in=timedelta(minutes=15))
# confirm: UPDATE reset_codes SET used_at = now() WHERE code_hash = :h AND used_at IS NULL AND expires_at > now() RETURNING user_id
```

The confirm step's `UPDATE ... RETURNING` is the atomic consume - two concurrent confirms cannot both succeed. Respond identically whether or not the email exists, and rate-limit the request endpoint.

### Mass-Assignment Whitelist Schemas

```python
from pydantic import BaseModel, ConfigDict, Field
from rest_framework import serializers
# FastAPI / Pydantic v2 - forbid unknowns (default silently drops them), server-set fields off the contract
class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    quantity: int = Field(gt=0)
# service: Order(**order_in.model_dump(), owner_id=user.id)

# Django / DRF - explicit fields (never "__all__"), server-controlled read-only; admin paths: separate serializer + explicit role guard
class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "product_id", "quantity", "owner", "created_at"]
        read_only_fields = ["id", "owner", "created_at"]
```

### SSRF Allowlist

```python
import ipaddress, socket
from urllib.parse import urljoin, urlparse

NAT64 = ipaddress.ip_network("64:ff9b::/96")

def resolve_and_check(raw_url: str) -> str:
    url = urlparse(raw_url)
    if url.scheme not in ("http", "https"):
        raise ValueError("scheme")
    port = url.port or (443 if url.scheme == "https" else 80)
    addrs = {ai[4][0] for ai in socket.getaddrinfo(url.hostname, port)}  # every A/AAAA record
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped                              # unwrap ::ffff:127.0.0.1
        if not ip.is_global or ip.is_multicast or ip in NAT64:  # RFC1918, loopback, link-local, 100.64/10, reserved, NAT64
            raise ValueError("blocked")
    return addrs.pop()                                       # the vetted IP to connect to
```

**Pin the vetted IP for the connection** - a plain `httpx.get(raw_url)` re-resolves and can rebind past the check (TOCTOU): connect to the returned IP with `Host`/SNI set to the hostname, or route outbound through an egress-allowlist proxy. Watch `urllib.parse` quirks: backslash, unicode, `::ffff:127.0.0.1`.

### File Upload Validation

```python
import puremagic, secrets
from pathlib import Path
from fastapi import HTTPException, UploadFile

ALLOWED = {"image/jpeg", "image/png", "application/pdf"}
UPLOAD_DIR = Path("/srv/uploads").resolve()
MAX_BYTES = 10 * 1024 * 1024

async def save_upload(file: UploadFile) -> Path:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES: raise HTTPException(413, "too large")
    if not data: raise HTTPException(400, "empty")           # puremagic raises ValueError, not PureError, on b""
    try: kind = puremagic.from_string(data, mime=True)      # trust bytes, not content_type header
    except puremagic.PureError: raise HTTPException(400, "type")
    if kind not in ALLOWED: raise HTTPException(400, "type")
    target = (UPLOAD_DIR / secrets.token_hex(16)).resolve()
    if not target.is_relative_to(UPLOAD_DIR): raise HTTPException(400, "path")   # traversal guard
    target.write_bytes(data)
    return target
```

Django: `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` do **not** cap file size (they govern non-file data and the spill-to-disk threshold) - check `uploaded.size` in the form/serializer validator.

### Dangerous Deserialization / Eval

Treat any of these as Critical when reachable from user input:

```python
pickle.loads(user_bytes)                         # RCE
yaml.load(user_str, Loader=yaml.UnsafeLoader)    # RCE (also yaml.Loader) - use yaml.safe_load
Template(user_str).render(...)                   # Jinja2 SSTI - templates from disk only
```

Celery: `task_serializer = "json"`, `accept_content = ["json"]` (the 5.x defaults) - adding `pickle` lets any broker publisher run code on the worker.

### Secrets and Typed Settings

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
# pydantic-settings; fails at startup on missing/malformed (never a literal default, never raw os.getenv in business logic)
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str
    jwt_secret: str = Field(min_length=32, repr=False)   # repr=False keeps it out of logs / tracebacks

settings = Settings()   # raises at import if unset
```

Django: `django-environ` - `SECRET_KEY = env("SECRET_KEY")` in `settings.py`, raising if unset; never a literal default. `.env` for local dev only and gitignored.

### Open Redirect / SQL / Subprocess

```python
import subprocess
from fastapi.responses import RedirectResponse
# Bad - open redirect
return RedirectResponse(request.query_params["next"])
# Good - resolve against own origin and compare the host; fall back to a safe path
target = urljoin(str(request.base_url), next_param)
return RedirectResponse(target if urlparse(target).netloc == request.base_url.netloc else "/")

# Bad - SQL injection
cursor.execute(f"SELECT id FROM orders WHERE reference LIKE '%{q}%'")
# Good - bound parameter
cursor.execute("SELECT id FROM orders WHERE reference LIKE %s", [f"%{q}%"])

# Bad - shell injection: subprocess.run(f"convert {user_input} out.png", shell=True)
subprocess.run(["convert", user_input, "out.png"])          # arg list, no shell; allowlist binaries
```

## Output Format

When authoring, emit one block per Pattern the change touches plus the code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit one block per deviation with `Change` as the required fix.

```
Pattern: {JWT | Password Hashing | Token Randomness | Authz Scoping | Mass Assignment | SQL Injection | SSRF | Webhook Auth | File Upload | Deserialization | Secrets | Open Redirect | Subprocess | TLS | Response Exposure}

Surface: {file:line - endpoint/service/settings}

Change: {what was applied}

Risk Mitigated: {auth bypass | credential cracking | predictable token | authz bypass | mass assignment | SQL injection | SSRF | webhook forgery | malicious upload | path traversal | RCE | secret exposure | data exposure | open redirect | TLS bypass}
```

## Avoid

- `instance.__dict__.update(request.data)` or `setattr` loops over raw request data
