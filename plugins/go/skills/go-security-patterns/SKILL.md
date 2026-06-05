---
name: go-security-patterns
description: "Go/Gin security: JWT (RS256, iss/aud), router-group default-deny, IDOR scoping, mass-assignment, SQL params, path traversal, webhook sigs, secrets, SSRF."
metadata:
  category: backend
  tags: [go, gin, security, jwt, authorization, validation, mass-assignment, secrets, webhook, ssrf]
user-invocable: false
---

# Go Security Patterns

> Load `Use skill: stack-detect` first. SQL parameterization mechanics live in `go-data-access`; error-response shape in `go-error-handling`; router/middleware wiring in `go-gin-patterns`. This skill owns only the security-specific decisions.

## When to Use

- Implementing or reviewing authentication, authorization, input validation, secrets, or crypto in a Go/Gin service
- Hardening webhook endpoints, file uploads, or outbound HTTP that takes user-controlled URLs
- Auditing JWT setup, password hashing, or `crypto/*` usage

## Rules

- Default-deny via authed router group; public endpoints listed explicitly in a separate `public` group
- JWT: HS256 key in env/Vault (never committed) or asymmetric RS256/ES256 for cross-service; `golang-jwt/jwt/v5` (v4 is maintenance only); validate `iss`, `aud`, `exp`; pin algorithm in `keyFunc` to prevent `alg: none` and HS/RS confusion
- Request DTOs are explicit structs with `validate:` tags; never `interface{}` / `map[string]any` / `mapstructure.Decode(req.Body, &domainModel)` on write paths - that is mass assignment
- Authorize after authenticating: scope every per-owner lookup by principal at the repository layer (`WHERE id = ? AND user_id = ?`), not just route grouping
- SQL via `?` / `$1` / `:name` placeholders only; never `fmt.Sprintf` interpolation
- `exec.Command(name, args...)` with arg slice - never `sh -c` / `cmd /c` with user input
- `crypto/rand` (NOT `math/rand`) for tokens, nonces, secrets; `crypto/subtle.ConstantTimeCompare` for HMAC/signature comparison
- Password hashing: `bcrypt.GenerateFromPassword(pw, 12)` (cost >= 10) or `argon2.IDKey(...)`
- API keys: never store plaintext; hash with sha256 at issuance, compare with `subtle.ConstantTimeCompare`
- Load secrets from env/secret manager into a typed config struct at startup; fail fast on absence; never log tokens, passwords, JWTs, or PII

## Patterns

### Default-deny router with explicit public allowlist

```go
// Bad - auth is opt-in; new endpoint added outside `authed` is silently public
r := gin.New()
r.POST("/auth/login", h.Login)
authed := r.Group("/", auth.Required())
authed.GET("/orders", h.ListOrders)
r.GET("/internal/debug", h.Debug) // forgot auth

// Good - public allowlist named; everything else is under authed
r := gin.New()
public := r.Group("/")
public.POST("/auth/login", h.Login)
public.POST("/webhooks/stripe", stripeSig.Verify(), h.StripeWebhook)
public.GET("/healthz", h.Health)

authed := r.Group("/", auth.Required())
authed.GET("/orders", h.ListOrders)
authed.GET("/internal/debug", auth.RequireRole("admin"), h.Debug)
```

### JWT validation (golang-jwt/jwt/v5)

```go
func keyFunc(t *jwt.Token) (any, error) {
    // Pin algorithm at verification time - rejects alg=none and HS<->RS confusion
    if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
        return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
    }
    return []byte(cfg.JWTSecret), nil
}

token, err := jwt.ParseWithClaims(raw, &Claims{}, keyFunc,
    jwt.WithIssuer(cfg.JWTIssuer),
    jwt.WithAudience(cfg.JWTAudience),
    jwt.WithExpirationRequired(),
)
if err != nil || !token.Valid {
    c.AbortWithStatus(http.StatusUnauthorized)
    return
}
```

- Access tokens 5-15 min; refresh tokens are opaque random strings (not nested JWTs - they ride in cookies and don't need self-description), rotated on every use; revocation via DB/Redis denylist keyed on `jti` for access tokens or refresh-token UUID
- For RS256/ES256: load the public key from a trusted source; cache JWKS with TTL
- Never `slog.Info("token", token)` / `fmt.Println(token)` - logs leak the bearer
- Transport: send JWTs via `Authorization: Bearer` (API) or `Secure; HttpOnly; SameSite=Lax` cookies (browser). Never put a JWT in a URL query string or fragment - logs, browser history, and Referer headers capture it.

### Gin auth middleware shape

```go
func Required() gin.HandlerFunc {
    return func(c *gin.Context) {
        h := c.GetHeader("Authorization")
        raw, ok := strings.CutPrefix(h, "Bearer ")
        if !ok {
            c.AbortWithStatus(http.StatusUnauthorized)
            return
        }
        claims, err := jwt.Verify(raw)
        if err != nil {
            c.AbortWithStatus(http.StatusUnauthorized) // no body details
            return
        }
        c.Set("claims", claims)
        c.Next()
    }
}

func RequireRole(role string) gin.HandlerFunc {
    return func(c *gin.Context) {
        claims := c.MustGet("claims").(*Claims)
        if claims.Role != role {
            c.AbortWithStatus(http.StatusForbidden)
            return
        }
        c.Next()
    }
}
```

### Login flow hardening

Beyond hashing the password, the login handler is the credential-stuffing target. Address all three:

```go
// Rate-limit by IP and by email (separate buckets) before doing crypto work
if !rl.Allow(c.ClientIP(), req.Email) { c.AbortWithStatus(http.StatusTooManyRequests); return }

// Always bcrypt - even when the user doesn't exist - so timing doesn't leak existence
var hash []byte
if u, err := repo.FindByEmail(ctx, req.Email); err == nil {
    hash = u.PasswordHash
} else {
    hash = dummyBcryptHash // pre-computed at startup
}
if err := bcrypt.CompareHashAndPassword(hash, []byte(req.Password)); err != nil || u == nil {
    c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid credentials"}) // generic, no "user not found"
    return
}
```

Failure response is the same string and same status for "user missing" and "wrong password" - any divergence is a user-enumeration oracle.

### API key storage

```go
// Bad - lookup by plaintext key; DB compromise leaks every customer's key
db.Where("key = ?", c.GetHeader("X-API-Key")).First(&k)

// Good - hash at issuance, store the hash, look up by hash, constant-time compare
func IssueAPIKey() (plaintext string, hash [32]byte) {
    b := make([]byte, 32); crand.Read(b)
    plaintext = "sk_" + base64.RawURLEncoding.EncodeToString(b)
    return plaintext, sha256.Sum256([]byte(plaintext))
}

func Verify(c *gin.Context) {
    raw := c.GetHeader("X-API-Key")
    h := sha256.Sum256([]byte(raw))
    var k APIKey
    if err := db.Where("key_hash = ?", h[:]).First(&k).Error; err != nil {
        c.AbortWithStatus(http.StatusUnauthorized); return
    }
    if subtle.ConstantTimeCompare(k.KeyHash, h[:]) != 1 || k.RevokedAt != nil {
        c.AbortWithStatus(http.StatusUnauthorized); return
    }
}
```

Store a key prefix (`sk_xxxx...`) in plaintext alongside the hash so users can identify keys in the dashboard. Bcrypt is overkill for high-entropy random keys; sha256 + constant-time compare is sufficient.

### IDOR: scope at the repository, not the handler

```go
// Bad - handler-side ownership check races with repository load
order, _ := repo.FindByID(ctx, id)
if order.UserID != claims.UserID {
    c.AbortWithStatus(http.StatusNotFound)
    return
}

// Good - principal flows into the query; impossible to forget
func (r *orderRepo) FindByOwner(ctx context.Context, id, ownerID int64) (*Order, error) {
    var o Order
    err := r.db.WithContext(ctx).
        Where("id = ? AND user_id = ?", id, ownerID).First(&o).Error
    return &o, err
}
```

GORM scope for multi-tenant isolation:

```go
func TenantScoped(tenantID int64) func(*gorm.DB) *gorm.DB {
    return func(db *gorm.DB) *gorm.DB { return db.Where("tenant_id = ?", tenantID) }
}
db.Scopes(TenantScoped(claims.TenantID)).Find(&orders)
```

### Mass-assignment prevention

```go
// Bad - mapstructure.Decode writes any field the client sends, including Role/IsAdmin/OwnerID
var u model.User
mapstructure.Decode(req.Body, &u)
db.Save(&u)

// Bad - same shape with json.Unmarshal into a domain model
json.Unmarshal(body, &user) // user.Role overridable

// Good - request DTO with explicit fields; server controls privileged ones
type CreateUserRequest struct {
    Name  string `json:"name" validate:"required,min=1,max=100"`
    Email string `json:"email" validate:"required,email"`
    // Role, IsAdmin, OwnerID, UserID, TenantID, IsActive, Verified deliberately absent
}
var req CreateUserRequest
if err := c.ShouldBindJSON(&req); err != nil {
    c.JSON(http.StatusBadRequest, errResp(err))
    return
}
u := model.User{
    Name:  req.Name,
    Email: req.Email,
    Role:  "user",                 // server-set
    OwnerID: claims.UserID,        // server-set
}
```

If GORM's `Updates` is called with a struct, only non-zero fields update (which can also be abused). Prefer `db.Model(&u).Select("name", "email").Updates(req)` to declare the allowlist. Never pass `map[string]any` from the request body straight into `Updates` - same shape as `mapstructure.Decode` on writes.

### Input validation

```go
type UpdateOrderRequest struct {
    Quantity int    `json:"quantity" validate:"required,gt=0,lte=999"`
    Status   string `json:"status" validate:"required,oneof=pending paid shipped"`
}

if err := c.ShouldBindJSON(&req); err != nil { ... }      // controls 400 response
uuid.Parse(c.Param("id"))                                 // not raw c.Param
c.ShouldBindUri(&pathDTO)                                 // path params validated too
c.ShouldBindQuery(&queryDTO)                              // query params validated too
```

- Use `ShouldBindJSON` (not `BindJSON`) so the handler shapes the error response
- Reject unknown fields where strictness matters: `decoder.DisallowUnknownFields()` (raw `json.Decoder` only - Gin's binder does not enforce by default)

### SQL parameterization

```go
// Bad - concat / fmt.Sprintf is SQL injection
db.Exec(fmt.Sprintf("UPDATE users SET role='%s' WHERE id=%d", role, id))

// Good - GORM
db.Where("id = ?", id).Updates(map[string]any{"role": role})

// Good - sqlx positional or named
db.ExecContext(ctx, "UPDATE users SET role=$1 WHERE id=$2", role, id)
db.NamedExecContext(ctx, "UPDATE users SET role=:role WHERE id=:id", args)
```

`db.Where("name LIKE ?", "%"+input+"%")` is parameterized and safe; the smell is unparameterized interpolation, not the `LIKE` itself.

### Path traversal

```go
// Bad - filepath.Join alone does not contain ".."
target := filepath.Join(baseDir, c.Param("filename"))
os.Open(target)

// Good - clean + base-prefix check
cleaned := filepath.Clean(c.Param("filename"))
target := filepath.Join(baseDir, cleaned)
if !strings.HasPrefix(target, filepath.Clean(baseDir)+string(filepath.Separator)) {
    c.AbortWithStatus(http.StatusBadRequest)
    return
}
```

For uploads: detect type via `http.DetectContentType(headerBytes)` (not the `Content-Type` header or extension); cap size with `http.MaxBytesReader` and `router.MaxMultipartMemory`; serve with `Content-Disposition: attachment` from outside the webroot.

### Command injection

```go
// Bad - shell interprets metacharacters in user input -> RCE
exec.Command("sh", "-c", "convert "+userFile+" out.png")

// Good - arg slice, no shell; strict allowlist of binaries
exec.Command("convert", userFile, "out.png")
```

### Webhook signature verification

```go
// Read raw body BEFORE ShouldBindJSON (binding consumes the body)
raw, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, 1<<20))
if err != nil { c.AbortWithStatus(http.StatusBadRequest); return }

mac := hmac.New(sha256.New, []byte(cfg.WebhookSecret))
mac.Write(raw)
expected := mac.Sum(nil)
got, _ := hex.DecodeString(c.GetHeader("X-Signature"))

// Constant-time compare defeats timing attacks
if !hmac.Equal(expected, got) {                  // wraps subtle.ConstantTimeCompare
    c.AbortWithStatus(http.StatusUnauthorized)
    return
}

var evt WebhookEvent
if err := json.Unmarshal(raw, &evt); err != nil { ... }

// Idempotency - providers retry; persist (provider, event_id) and short-circuit duplicates
if seen, _ := store.SeenEvent(ctx, "stripe", evt.ID); seen {
    c.Status(http.StatusOK); return
}
```

Route the webhook outside the JWT auth group; the signature is the only auth. Idempotency is not optional - Stripe and GitHub both retry on non-2xx and on timeout, so handlers must tolerate duplicates without double-applying side effects.

### Password hashing

```go
// Hash
hash, err := bcrypt.GenerateFromPassword([]byte(pw), 12) // cost >= 10
// or argon2 (preferred for new code)
salt := make([]byte, 16); crand.Read(salt)
hash := argon2.IDKey([]byte(pw), salt, 1, 64*1024, 4, 32)

// Verify
err := bcrypt.CompareHashAndPassword(stored, []byte(pw)) // constant-time internally
```

Never `sha256.Sum256(pw)` / `md5.Sum(pw)` - fast hashes are crackable; constant-time compare matters even for hash equality (use `subtle.ConstantTimeCompare` on raw bytes).

### Secrets and config

```go
// Bad - os.Getenv scattered, no fail-fast on missing
secret := os.Getenv("JWT_SECRET")
if secret == "" { secret = "dev-default" } // silently insecure in prod

// Good - typed config loaded once; missing fails fast at startup
type Config struct {
    JWTSecret  string `envconfig:"JWT_SECRET" required:"true"`
    DBURL      string `envconfig:"DB_URL"     required:"true"`
    StripeKey  string `envconfig:"STRIPE_KEY" required:"true"`
}
var cfg Config
if err := envconfig.Process("", &cfg); err != nil { log.Fatal(err) }
```

Secrets live in Vault / AWS Secrets Manager / GCP Secret Manager / Doppler; `.env` files for local dev only, gitignored. Implement `LogValue()` on secret-holding types so `slog` redacts them.

### SSRF defence

When a user-controlled value flows into an outbound URL/host:

1. `url.Parse` and reject obvious smuggling (backslash, IPv4-in-IPv6 like `::ffff:127.0.0.1`)
2. Resolve the host via `net.LookupIP` (DNS rebinding defeats string-only checks)
3. Reject any resolved IP in:
   - cloud metadata: `169.254.169.254`, IPv6 metadata range
   - loopback: `127.0.0.0/8`, `::1`
   - RFC1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
   - link-local: `169.254.0.0/16`, `fe80::/10`
4. Dial against the resolved IP (not re-resolved at connect time)

```go
ips, err := net.LookupIP(host)
if err != nil { return ErrBadHost }
for _, ip := range ips {
    if ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() ||
        ip.Equal(net.ParseIP("169.254.169.254")) {
        return ErrBlocked
    }
}
```

Cap response size with `http.MaxBytesReader` on the response body to defeat oversized-response DoS. Re-check on every redirect via a custom `CheckRedirect`.

### `crypto/rand` and `InsecureSkipVerify`

```go
// Bad - math/rand is deterministic; tokens are guessable
token := strconv.Itoa(mrand.Int())

// Good
b := make([]byte, 32)
if _, err := crand.Read(b); err != nil { return err }
token := base64.RawURLEncoding.EncodeToString(b)

// Bad in any non-test path - disables TLS verification
http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}}
```

`InsecureSkipVerify: true` is acceptable only behind a documented test fixture; flag every other occurrence.

## Output Format

When invoked from a review workflow, emit one block per finding so the consuming workflow merges them:

```
### [Severity] file:line

- Category: {AuthN | AuthZ | Validation | Injection | Crypto | Secrets | Transport}
- Code: {one-line citation}
- Attack scenario: {concrete exploit, regression risk, or topology-dependent note}
- Fix: {concrete Go change with code}
```

When invoked from an implementation workflow, emit a decision table:

```
| Concern | Decision | Rationale |
|---------|----------|-----------|
| JWT alg | RS256 via JWKS | cross-service |
| Request DTO | `CreateUserRequest` no Role/OwnerID | mass-assignment guard |
| ...     | ...      | ...       |
```

## Avoid

- `BindJSON` over `ShouldBindJSON` (loses error-response control)
- `mapstructure.Decode(req.Body, &domainModel)` / `json.Unmarshal(body, &user)` into domain models
- Raw GORM model returned from handlers (`c.JSON(200, user)` leaks `PasswordHash`, `MFASecret`, audit columns)
- `fmt.Sprintf` interpolation into SQL
- `sh -c` / `cmd /c` / `bash -c` with any user-controlled segment
- `math/rand` for tokens, nonces, IDs, or secrets
- `bytes.Equal` / `==` for HMAC, signature, or hash comparison (timing attack)
- API keys stored or looked up in plaintext
- `InsecureSkipVerify: true` outside a test fixture
- `gin.DebugMode` in production (leaks request bodies in logs)
- `pprof` exposed in production without admin auth
- `gob.Decode` / `xml.Unmarshal` on untrusted input
- `text/template` (not `html/template`) for HTML output
- JWT in URL query string or session cookie without `Secure; HttpOnly; SameSite`
- Logging `password`, `token`, `authorization`, `credit_card`, `ssn`, `api_key`
- Login responses that differ between "user missing" and "wrong password"
