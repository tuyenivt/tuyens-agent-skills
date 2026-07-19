---
name: python-security-patterns
description: Python security - JWT (python-jose/pyjwt), Pydantic mass-assignment, SSRF, file upload, pickle/eval prohibitions, secrets, subprocess.
metadata:
  category: backend
  tags: [python, fastapi, django, security, jwt, owasp, ssrf, pydantic]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Canonical "build it right" security patterns for FastAPI / Django. `task-python-review-security` delegates here and only flags deviations.

## When to Use

- Wiring auth (FastAPI `OAuth2PasswordBearer` / `HTTPBearer`, Django/DRF auth) or authz (dependencies / permission classes)
- Adding Pydantic schemas or DRF serializers that touch user-supplied data
- Implementing file upload, webhook receivers, SSRF-exposed outbound HTTP, or `subprocess` callers
- Loading secrets / typed settings with env validation
- Reviewing any code path that crosses an untrusted boundary

## Rules

- Every JWT decode declares `algorithms=[...]` explicitly - never `None` or unspecified (defeats `alg: none` / key-confusion); verify `iss` / `aud`, not just signature
- Password hashing via `passlib[bcrypt]` (rounds >=12) or `argon2-cffi`; Django via `PASSWORD_HASHERS` (Argon2 first). Never `hashlib.md5` / `sha1` for auth
- Every request body has a Pydantic schema (`ConfigDict(extra="forbid")`) or DRF serializer with explicit `fields`; privilege fields (`role`, `is_admin`, `owner_id`, `user_id`, `tenant_id`, `verified`) are server-set, never on the input contract
- `response_model` (FastAPI) / explicit serializer `fields` (DRF) filter output - never leak `password_hash`, internal columns
- Never `pickle.loads`, `yaml.load` without `SafeLoader`, `eval`, or `exec` on untrusted input - Critical RCE regardless of "controlled" framing
- Outbound `httpx` / `requests` with user-controlled URL resolves the host and rejects RFC1918, link-local, `127.0.0.0/8` / `::1`, cloud metadata `169.254.169.254` (re-resolve at request time to defeat DNS rebinding)
- Inbound webhooks verify an HMAC signature over the raw body (`hmac.compare_digest`) and reject stale timestamps - never process an unauthenticated receiver payload
- File uploads validated by magic bytes (`python-magic` / `puremagic`), not the `content_type` header; size-limited; stored outside webroot; served with `Content-Disposition: attachment`
- `subprocess.run([...])` arg list only - never `shell=True` with user input; allowlist binaries
- Secrets via `pydantic-settings` `BaseSettings` (or Django env loader), failing at startup on missing keys; source from Vault / AWS SM / GCP SM, never source literals; `.env` gitignored
- Tokens / reset codes / nonces use `secrets` (`secrets.token_urlsafe(32)`), never `random.*` or `uuid.uuid1`
- `RedirectResponse` / `HttpResponseRedirect` on user input validated against an allowlist or same-origin check
- `verify=False` on TLS clients only in documented test fixtures

## Patterns

### JWT Signing and Verification

```python
# Bad - no algorithm allowlist; accepts alg:none / key confusion
payload = jwt.decode(token, key)

# Good - python-jose / pyjwt, explicit allowlist + iss/aud
payload = jwt.decode(
    token, key,
    algorithms=["HS256"],            # or ["RS256"] cross-service (preferred)
    issuer="api", audience="web",
    options={"verify_iss": True, "verify_aud": True},
)

# Issue - set exp/iss/aud at signing; short TTL, never a static long-lived token
token = jwt.encode(
    {"sub": user.id, "iss": "api", "aud": "web", "exp": now + timedelta(minutes=15)},
    key, algorithm="HS256",
)
```

Access tokens 5-15 min; refresh tokens rotated and revocable (`jti` in a Redis/DB denylist). Django: `djangorestframework-simplejwt` with `SIGNING_KEY` from env, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`, explicit `ALGORITHM`.

### Mass-Assignment Whitelist Schemas

**FastAPI / Pydantic v2:**

```python
# Bad - privilege field on input; extra keys silently dropped
class OrderCreate(BaseModel):
    product_id: str
    owner_id: str            # client overrides server-assigned owner

# Good - forbid unknowns, server-set fields off the contract
class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    quantity: int = Field(gt=0)
# service: Order(**order_in.model_dump(), owner_id=user.id)
```

**Django / DRF:**

```python
# Bad - leaks internal columns, allows mass assignment
class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model, fields = Order, "__all__"

# Good - explicit fields, server-controlled read-only
class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "product_id", "quantity", "owner", "created_at"]
        read_only_fields = ["id", "owner", "created_at"]
```

Never `instance.__dict__.update(request.data)` - bypasses validation entirely. Admin paths use a separate schema/serializer with an explicit role guard.

### SSRF Allowlist

```python
import ipaddress, socket
from urllib.parse import urlparse

def resolve_and_check(raw_url: str) -> str:
    url = urlparse(raw_url)
    if url.scheme not in ("http", "https"):
        raise ValueError("scheme")
    port = url.port or (443 if url.scheme == "https" else 80)
    addrs = {ai[4][0] for ai in socket.getaddrinfo(url.hostname, port)}  # every A/AAAA record
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        ip = ip.ipv4_mapped or ip                       # unwrap ::ffff:127.0.0.1
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("blocked")
    return addrs.pop()                                   # the vetted IP to connect to
```

**Pin the vetted IP for the actual connection** - a plain `httpx.get(raw_url)` re-resolves the hostname and can rebind past the check (validate-then-fetch is TOCTOU). Connect to the returned IP with `Host`/SNI set to the hostname, or route outbound through an egress-allowlist proxy. Check **every** resolved record, not just the first. Watch `urllib.parse` quirks: backslash, unicode, `::ffff:127.0.0.1` (IPv4-mapped IPv6).

### File Upload Validation

```python
import puremagic
from pathlib import Path

ALLOWED = {"image/jpeg", "image/png", "application/pdf"}
UPLOAD_DIR = Path("/srv/uploads").resolve()

async def save_upload(file: UploadFile) -> Path:
    data = await file.read()                            # bound size upstream (middleware / limit)
    kind = puremagic.from_string(data, mime=True)       # trust bytes, not content_type header
    if kind not in ALLOWED:
        raise HTTPException(400, "type")
    target = (UPLOAD_DIR / f"{secrets.token_hex(16)}").resolve()
    if not target.is_relative_to(UPLOAD_DIR):           # traversal guard
        raise HTTPException(400, "path")
    target.write_bytes(data)
    return target
```

Django: cap `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE`. Serve with `Content-Disposition: attachment`; generate filenames server-side.

### Dangerous Deserialization / Eval

Treat any of these as Critical when reachable from user input:

```python
pickle.loads(user_bytes)                # RCE
yaml.load(user_str)                     # RCE - use yaml.safe_load
eval(user_str); exec(user_str)          # RCE
Template(user_str).render(...)          # Jinja2 SSTI - templates from disk only
```

Celery: `task_serializer` / `accept_content = ["json"]` only - a worker accepting `pickle` from any broker publisher is RCE by design.

### Secrets and Typed Settings

```python
# Bad - literal secret; raw os.getenv scattered through business logic
SECRET_KEY = "hardcoded"

# Good - pydantic-settings; fails at startup on missing/malformed
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str
    jwt_secret: str = Field(min_length=32)

settings = Settings()   # raises at import if unset
```

Django: `django-environ` - `SECRET_KEY = env("SECRET_KEY")` in `settings.py`, raising if unset; never a literal default. Secrets from Vault / AWS SM / GCP SM; `.env` for local dev only and gitignored. Mark sensitive Pydantic fields `Field(repr=False)` so they never surface in logs / tracebacks.

### Open Redirect / Subprocess / TLS

```python
# Bad - open redirect
return RedirectResponse(request.query_params["next"])
# Good - resolve against own origin, compare, fall back to a safe path
target = urljoin(str(request.base_url), next_param)
return RedirectResponse(target if target.startswith(str(request.base_url)) else "/")

# Bad - shell injection
subprocess.run(f"convert {user_input} out.png", shell=True)
# Good - arg list, no shell; allowlist binaries
subprocess.run(["convert", user_input, "out.png"])

# Bad - disables TLS verification (test fixtures only, with a comment)
httpx.Client(verify=False)
```

## Output Format

```
Pattern: {JWT | Mass Assignment | SSRF | Webhook Auth | File Upload | Deserialization | Secrets | Open Redirect | Subprocess | TLS}
Surface: {file:line - endpoint/service/settings}
Change: {what was applied}
Risk Mitigated: {auth bypass | mass assignment | SSRF | webhook forgery | RCE | secret exposure | open redirect | TLS bypass}
```

## Avoid

- `jwt.decode(token, key)` without an `algorithms` allowlist
- Input schemas without `extra="forbid"` / serializers with `fields = "__all__"` - mass-assignment vector
- SSRF allowlists that check the raw URL string instead of the resolved IP, or re-resolve for the fetch instead of pinning the vetted IP
- Inbound webhooks processed without verifying an HMAC signature over the raw body - forgeable
- File-type validation by the `content_type` header
- `pickle.loads` / `yaml.load` / `eval` / `exec` / `Template(...).render` on untrusted input
- Celery `accept_content` including `pickle`
- Reading secrets via raw `os.getenv` in business logic - go through validated settings
- `random.*` / `uuid.uuid1` for tokens, reset codes, or nonces - use `secrets`
- Same-origin open redirects masquerading as "internal" - allowlist paths, not `startswith("/")`
