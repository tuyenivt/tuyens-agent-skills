---
name: go-security-patterns
description: "Go/Gin security: JWT (RS256, iss/aud), default-deny router, IDOR scoping, mass-assignment, SQL params, path traversal, webhook sigs, secrets, SSRF."
metadata:
  category: backend
  tags: [go, gin, security, jwt, authorization, validation, mass-assignment, secrets, webhook, ssrf]
user-invocable: false
---

# Go Security Patterns

> Load `Use skill: stack-detect` first. This skill reads `Framework` and `Database`: the binder facts are Gin's (`binding:` tags, `ShouldBind*`) and do not apply under another framework, everything else does; on `Database` `unknown` the examples keep `$1`; placeholders are `$1` on PostgreSQL and `?` on MySQL/SQLite (GORM always takes `?`; sqlx passes SQL through unchanged, so write the driver's style). Baseline: Go 1.25+ (`os.Root`, `crypto/rand.Read` never returns an error, `math/rand` top-level is ChaCha8), Gin v1.10+, GORM v1.25+, golang-jwt/jwt v5, stripe-go v82.1+. SQL parameterization mechanics live in `go-data-access`; error-response shape in `go-error-handling`; router/middleware wiring in `go-gin-patterns`. This skill owns only the security-specific decisions.

## When to Use

- Implementing or reviewing authentication, authorization, input validation, secrets, or crypto in a Go/Gin service
- Hardening webhook endpoints, file uploads, or outbound HTTP that takes user-controlled URLs
- Auditing JWT setup, password hashing, or `crypto/*` usage

## Rules

- Default-deny via authed router group; public endpoints listed explicitly in a separate `public` group
- JWT: HS256 key in env/Vault (never committed) or asymmetric RS256/ES256 for cross-service; `golang-jwt/jwt/v5` (v4 is maintenance only); validate `iss`, `aud`, `exp`; pin the exact algorithm with `jwt.WithValidMethods` - v5 already rejects `alg: none` unless the key is `jwt.UnsafeAllowNoneSignatureType`, so the pin is against HS/RS confusion and family-wide acceptance
- Request DTOs are explicit structs with validation tags; never decode a request body into a domain model (`json.Unmarshal(body, &user)`, or JSON -> `map` -> `mapstructure.Decode(m, &user)`) on write paths - that is mass assignment. The tag key follows the consumer: Gin's `ShouldBind*` reads `binding:`, a standalone `validator.New()` reads `validate:`. The wrong key compiles, looks right, and validates nothing
- Authorize after authenticating: scope every per-owner lookup by principal at the repository layer (`WHERE id = ? AND user_id = ?`), not just route grouping. An admin override is a second repository method chosen by role, not a flag that widens the scoped one
- SQL via `?` / `$1` / `:name` placeholders only; never `fmt.Sprintf` interpolation
- `exec.Command(name, args...)` with arg slice - never `sh -c` / `cmd /c` with user input; user input never becomes an argument that the binary could read as an option or a coder prefix
- `crypto/rand` (NOT `math/rand`) for tokens, nonces, secrets; `crypto/subtle.ConstantTimeCompare` (or `hmac.Equal`, which wraps it) for HMAC/signature comparison
- Password hashing: `bcrypt.GenerateFromPassword(pw, 12)` (cost >= 10) or `argon2.IDKey(...)`
- API keys: never store plaintext; hash with sha256 at issuance, compare with `subtle.ConstantTimeCompare`
- Load secrets from env/secret manager into a typed config struct at startup; fail fast on absence **and** on empty; never log tokens, passwords, JWTs, or PII
- A retryable write takes a client `Idempotency-Key`, scoped to the principal and bound to a hash of the body: same key + same body replays the first response, same key + different body is `409`, a key from another principal is unknown. The record holds body hash, state (`in_flight | done`), status and response, kept 24h; a same-key request while `in_flight` is `409`, and a `5xx` releases the key. An API-key principal carries its merchant - a request naming another merchant's resource is `404`, exactly as for a JWT principal. The record holds body hash, state (`in_flight | done`), status and response, kept 24h; a same-key request while `in_flight` is `409`, and a `5xx` releases the key. An API-key principal carries its merchant - a request naming another merchant's resource is `404`, exactly as for a JWT principal

## Patterns

### Default-deny router with explicit public allowlist

```go
// Bad - auth is opt-in; new endpoint added outside `authed` is silently public
r := gin.New()
r.POST("/auth/login", h.Login)
authed := r.Group("/", auth.Required(verifyJWT))
authed.GET("/orders", h.ListOrders)
r.GET("/internal/debug", h.Debug) // forgot auth

// Good - public allowlist named; everything else is under authed. Nothing registers on r itself:
// a later r.GET is the regression a review flags.
r := gin.New()
public := r.Group("/")
public.POST("/auth/login", h.Login)
public.POST("/webhooks/stripe", h.StripeWebhook) // verifies the raw body inside the handler - see Webhook signature verification
public.GET("/healthz", h.Health)

authed := r.Group("/", auth.Required(verifyJWT))
authed.GET("/orders", h.ListOrders)
authed.GET("/internal/debug", auth.RequireRole("admin"), h.Debug)
```

### JWT validation (golang-jwt/jwt/v5)

```go
token, err := jwt.ParseWithClaims(raw, &Claims{},
    func(t *jwt.Token) (any, error) { return []byte(cfg.JWTSecret), nil },
    jwt.WithValidMethods([]string{"HS256"}), // exact algorithm, not the HMAC family
    jwt.WithIssuer(cfg.JWTIssuer),
    jwt.WithAudience(cfg.JWTAudience),
    jwt.WithExpirationRequired(),
)
if err != nil || !token.Valid {
    c.AbortWithStatus(http.StatusUnauthorized)
    return
}
```

- Access tokens 5-15 min, revocable through a denylist keyed on `jti`. Refresh tokens are opaque random strings (not nested JWTs), stored **hashed** server-side, rotated on every use, and revoked by deleting or marking their row
- For RS256/ES256: load the public key from a trusted source; cache JWKS with TTL
- Never `slog.Info("token", token)` / `fmt.Println(token)` - logs leak the bearer
- Transport: send JWTs via `Authorization: Bearer` (API) or `Secure; HttpOnly; SameSite=Lax` cookies (browser). Never put a JWT in a URL query string or fragment - logs, browser history, and Referer headers capture it

### Gin auth middleware shape

```go
func Required(verify func(raw string) (*Claims, error)) gin.HandlerFunc { // verify wraps the ParseWithClaims call above
    return func(c *gin.Context) {
        h := c.GetHeader("Authorization")
        raw, ok := strings.CutPrefix(h, "Bearer ")
        if !ok {
            c.AbortWithStatus(http.StatusUnauthorized)
            return
        }
        claims, err := verify(raw)
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
        // c.Get, not c.MustGet: MustGet panics on a missing key, so mounting this before
        // Required() would 500 under gin.Recovery() - and drop the connection without it.
        v, exists := c.Get("claims")
        claims, ok := v.(*Claims)
        if !exists || !ok {
            c.AbortWithStatus(http.StatusUnauthorized)
            return
        }
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
// Rate-limit by IP and by email (separate buckets) before doing crypto work.
// ClientIP() is spoofable via X-Forwarded-For until engine.SetTrustedProxies is set.
if !rl.Allow(c.ClientIP(), req.Email) { c.AbortWithStatus(http.StatusTooManyRequests); return }

// Always bcrypt - even when the user doesn't exist - so timing doesn't leak existence
u, err := repo.FindByEmail(ctx, req.Email) // returns nil, err on not-found
hash := dummyBcryptHash // pre-computed at startup
if err == nil { hash = u.PasswordHash }
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
    b := make([]byte, 32)
    crand.Read(b) // never returns an error since Go 1.24
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

Store a key prefix (`sk_xxxx...`) in plaintext alongside the hash so users can identify keys in the dashboard. Bcrypt is overkill for high-entropy random keys; sha256 + constant-time compare is sufficient. Migrating a plaintext table: add `key_hash`, backfill it from the plaintext column, switch lookups to the hash, then null and drop the plaintext column - no key rotation needed.

### IDOR: scope at the repository, not the handler

```go
// Bad - ownership is a per-handler afterthought: the row is loaded for anyone, the check
// is easy to forget on the next endpoint, and the 404 arrives after the read
order, _ := repo.FindByID(ctx, id)
if order.UserID != claims.UserID {
    c.AbortWithStatus(http.StatusNotFound)
    return
}

// Good - principal flows into the query; impossible to forget
func (r *orderRepo) FindByOwner(ctx context.Context, id, ownerID int64) (*Order, error) {
    var o Order
    if err := r.db.WithContext(ctx).
        Where("id = ? AND user_id = ?", id, ownerID).First(&o).Error; err != nil {
        return nil, err // never &o, err: a non-nil zero Order misleads every nil check upstream
    }
    return &o, nil
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
// Bad - any decode of the request body into a domain model writes whatever the client sends,
// including Role/IsAdmin/OwnerID
json.Unmarshal(body, &user)
mapstructure.Decode(bodyAsMap, &user)

// Good - request DTO with explicit fields; server controls privileged ones
type CreateUserRequest struct {
    Name  string `json:"name"  binding:"required,min=1,max=100"` // binding:, because ShouldBindJSON binds it
    Email string `json:"email" binding:"required,email"`
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

// Good - response DTO; never c.JSON(200, user) on a model with PasswordHash / MFASecret / audit columns
type UserResponse struct {
    ID    int64  `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}
```

If GORM's `Updates` is called with a struct, only non-zero fields update (which can also be abused). Prefer `db.Model(&u).Select("name", "email").Updates(req)` to declare the allowlist. Never pass `map[string]any` from the request body straight into `Updates` - same shape as the decode above.

### Input validation

```go
type UpdateOrderRequest struct {
    Quantity int    `json:"quantity" binding:"required,gt=0,lte=999"`
    Status   string `json:"status"   binding:"required,oneof=pending paid shipped"`
}

if err := c.ShouldBindJSON(&req); err != nil { ... }      // controls 400 response
uuid.Parse(c.Param("id"))                                 // not raw c.Param
c.ShouldBindUri(&pathDTO)                                 // path params validated too
c.ShouldBindQuery(&queryDTO)                              // query params validated too
```

- Use `ShouldBindJSON` (not `BindJSON`) so the handler shapes the error response
- Reject unknown fields where strictness matters: `binding.EnableDecoderDisallowUnknownFields = true` globally for Gin's binder, or `decoder.DisallowUnknownFields()` on a raw `json.Decoder` - off by default in both

### SQL parameterization

```go
// Bad - concat / fmt.Sprintf is SQL injection
db.Exec(fmt.Sprintf("UPDATE users SET role='%s' WHERE id=%d", role, id))

// Bad - no Sprintf in sight, still injection: GORM's inline-condition slot treats a
// non-numeric string as a raw SQL fragment. /users/1%20OR%201=1 becomes WHERE 1 OR 1=1.
db.First(&user, c.Param("id"))
// Good - parse first, then bind
id, err := strconv.ParseInt(c.Param("id"), 10, 64)
if err != nil { c.AbortWithStatus(http.StatusBadRequest); return }
db.Where("id = ?", id).First(&user)

// Good - GORM
db.Model(&User{}).Where("id = ?", id).Updates(map[string]any{"role": role})

// Good - sqlx positional or named
db.ExecContext(ctx, "UPDATE users SET role=$1 WHERE id=$2", role, id)
db.NamedExecContext(ctx, "UPDATE users SET role=:role WHERE id=:id", args)
```

`db.Where("name LIKE ?", "%"+input+"%")` is parameterized and safe; the smell is unparameterized interpolation, not the `LIKE` itself.

Placeholders bind **values**, never identifiers. A user-chosen sort column or direction cannot be parameterized, so map it through an allowlist and fall back to a default on a miss:

```go
sortable := map[string]string{"created": "created_at", "name": "name"}
col, ok := sortable[c.Query("sort")]
if !ok { col = "created_at" }
db.Order(col + " DESC").Find(&rows) // col came from the map, never from the request
```

### Path traversal

```go
// Bad - filepath.Join alone does not contain ".."
target := filepath.Join(baseDir, c.Param("filename"))
os.Open(target)

// Good (Go 1.24+) - os.Root makes escape impossible at the API level
root, err := os.OpenRoot(baseDir)
if err != nil { return err }
f, err := root.Open(c.Param("filename")) // traversal or symlink escape -> error
```

For uploads: detect type via `http.DetectContentType(headerBytes)` (not the `Content-Type` header or extension); cap size with `http.MaxBytesReader` on the request body - `router.MaxMultipartMemory` only decides heap-vs-tempfile and caps nothing; serve with `Content-Disposition: attachment` from outside the webroot.

### Command injection

```go
// Bad - shell interprets metacharacters in user input -> RCE
exec.Command("sh", "-c", "convert "+userFile+" out.png")

// Still bad - no shell, but a userFile of "-delay" or "msl:evil" is read by convert as an option or coder
exec.Command("convert", userFile, "out.png")

// Good - the path is server-generated (the upload's stored name), the binary is from an allowlist,
// and an explicit format prefix stops the tool reading the name as a coder (convert has no "--")
exec.Command("convert", "png:"+storedPath, "out.png")
```

### Webhook signature verification

```go
// Read raw body BEFORE ShouldBindJSON (binding consumes the body)
raw, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, 1<<20))
if err != nil { c.AbortWithStatus(http.StatusBadRequest); return }

// Provider-specific: Stripe signs "{t}.{payload}" into Stripe-Signature: t=...,v1=... with a
// timestamp tolerance - use webhook.ConstructEventWithOptions; GitHub sends
// X-Hub-Signature-256: sha256=<hex> - strip the prefix, hex-decode, HMAC the raw body.
mac := hmac.New(sha256.New, []byte(cfg.WebhookSecret))
mac.Write(raw)
got, _ := hex.DecodeString(strings.TrimPrefix(c.GetHeader("X-Hub-Signature-256"), "sha256="))
if !hmac.Equal(mac.Sum(nil), got) {               // constant-time; compares the decoded MAC, never the header string
    c.AbortWithStatus(http.StatusBadRequest) // 400, as the providers document; never a 2xx
    return
}
// Replay: reject a signed timestamp older than the provider's tolerance (Stripe: 5 min) when one exists.

var evt WebhookEvent
if err := json.Unmarshal(raw, &evt); err != nil { ... }

// Idempotency - insert (provider, event_id) under a unique index in the same transaction as the
// state change; a duplicate-key error means already applied -> 200 without acting. A SeenEvent
// check followed by a later mark is check-then-act and double-applies under concurrent retries.
```

Route the webhook outside the JWT auth group; the signature is the only auth. Stripe retries on non-2xx and on timeout for up to 3 days (GitHub does not redeliver automatically), so handlers must tolerate duplicates without double-applying side effects. Keep inbox rows past the provider's redelivery window (Stripe: 3 days; 30 days is a safe default). Outbound callbacks you send to partners get the same treatment in reverse: `X-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">` with a per-partner secret provisioned out of band, rotated by dual-signing (`v1=` and `v2=`) through the overlap.

### Password hashing

```go
// bcrypt
hash, err := bcrypt.GenerateFromPassword([]byte(pw), 12) // cost >= 10
// ...
err = bcrypt.CompareHashAndPassword(stored, []byte(pw)) // constant-time internally
```

```go
// argon2id (preferred for new code) - no CompareHash helper: store salt and params with the hash
salt := make([]byte, 16)
crand.Read(salt)
hash := argon2.IDKey([]byte(pw), salt, 1, 64*1024, 4, 32)
// verify: re-derive with the stored params, compare in constant time
derived := argon2.IDKey([]byte(pw), rec.Salt, rec.Time, rec.Memory, rec.Threads, uint32(len(rec.Hash)))
ok := subtle.ConstantTimeCompare(derived, rec.Hash) == 1
```

Pick one and use it everywhere - argon2id for new code, bcrypt when an existing table already holds bcrypt hashes (rehash on next successful login rather than forcing a reset). The dummy-hash trick in Login flow hardening applies to either: pre-compute a record with the same parameters at startup so a missing user costs the same work as a wrong password.

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
for name, v := range map[string]string{"JWT_SECRET": cfg.JWTSecret, "DB_URL": cfg.DBURL, "STRIPE_KEY": cfg.StripeKey} {
    if v == "" { log.Fatalf("%s is empty", name) } // required:"true" accepts an empty value
}
if len(cfg.JWTSecret) < 32 { log.Fatal("JWT_SECRET too short") }
```

Secrets live in Vault / AWS Secrets Manager / GCP Secret Manager / Doppler; `.env` files for local dev only, gitignored. Implement `LogValue()` on secret-holding types so `slog` redacts them.

### SSRF defence

When a user-controlled value flows into an outbound URL/host:

1. `url.Parse` and reject obvious smuggling (backslash, IPv4-in-IPv6 like `::ffff:127.0.0.1`), unexpected schemes, and non-standard ports
2. A pre-flight `net.LookupIP` check gives the user a friendly error - it is **not** the defence, because DNS rebinding (short TTL, alternating answers) changes the address between check and dial
3. Enforce the block **in the dialer**, on the resolved connection address: cloud metadata (`169.254.169.254`, `fd00:ec2::254`), loopback, RFC1918, link-local, and the unspecified address (`0.0.0.0` / `::` reach loopback on Linux)

```go
dialer := &net.Dialer{Control: func(network, address string, _ syscall.RawConn) error {
    host, _, _ := net.SplitHostPort(address) // address is the RESOLVED IP:port
    ip := net.ParseIP(host)
    if ip == nil || ip.IsUnspecified() || ip.IsLoopback() || ip.IsPrivate() || // IsPrivate covers fc00::/7, so fd00:ec2::254
        ip.IsLinkLocalUnicast() { // 169.254.169.254 is link-local
        return ErrBlocked
    }
    return nil
}}
client := &http.Client{Transport: &http.Transport{DialContext: dialer.DialContext}, Timeout: 10 * time.Second}
```

Cap the response body with `io.LimitReader(resp.Body, max)` to defeat oversized-response DoS (`http.MaxBytesReader` is for incoming request bodies). Re-check on every redirect via a custom `CheckRedirect`.

### `crypto/rand` and `InsecureSkipVerify`

```go
// Bad - math/rand carries no security guarantee: a seeded source (rand.New(rand.NewSource(seed)))
// is fully predictable, and nothing in the API promises otherwise even for the ChaCha8 global.
token := strconv.Itoa(mrand.Int())

// Good
b := make([]byte, 32)
crand.Read(b) // never returns an error since Go 1.24
token := base64.RawURLEncoding.EncodeToString(b)

// Bad in any non-test path - disables TLS verification
http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}}
```

`InsecureSkipVerify: true` is acceptable only behind a documented test fixture; flag every other occurrence. A partner sandbox with a self-signed certificate gets its CA pinned via `RootCAs`, not verification turned off.

## Output Format

A **review** targets supplied code: emit `## Findings` and close with one coverage line naming what was not examined (routes, files, or layers the input did not supply), so silence is not read as a clean bill. An **audit** targets a named surface or a whole service: `## Findings`, then `## Remediation` with the table below, then `**Verdict:**` one line answering "are we ready" with the condition, then the coverage line. When invoked from an **implementation** workflow, emit the decision table, one row per decision the brief asked for plus any prerequisite the code needs first (marked `(prerequisite)`), with code for each decision that needs it under `### <Concern>` headings in row order; existing code handed with the brief that violates a Rule emits `## Findings` first; close with the coverage line naming the surfaces the brief did not supply (callers, routes, config).

Every finding carries exactly one severity:

```
## Findings

### [{Critical | High | Medium | Low}] {file:line | file:start-end | file:<symbol> | <area>}{ (unverified)}

- Category: {AuthN | AuthZ | Validation | Injection | Crypto | Secrets | SSRF | Traversal | Exposure | Availability}
- Code: {one-line citation}
- Attack scenario: {concrete exploit, regression risk, or topology-dependent note}
- Chain: {locator of the finding this one compounds with}
- Fix: {concrete Go change with code}
```

`Critical` = unauthenticated compromise, cross-tenant or cross-account data access, arbitrary file or command execution; `High` = authenticated privilege escalation, credential disclosure, or a security control that is present but inert; `Medium` = defense-in-depth gap or an information oracle; `Low` = hardening. Judge by what an attacker gains, not by matching the wording. `(unverified)` marks a finding whose impact depends on code the input did not supply - keep the severity the exploit would have and say what to check. `Exposure` covers debug surfaces, profiling endpoints, over-serialized responses, PII, and sensitive values in logs; a correct check at the wrong layer (handler instead of repository) is `Low`; severity is judged at exploit time - a control that makes the path unreachable today goes in `Attack scenario:`, not the label; `Availability` covers missing rate limits, uncapped bodies, and request-path panics. Order by severity, then by file in the order the input listed them, then line; with no findings, `## Findings` holds the single line `None.`; cite `file:line` when the input carries line numbers, `file:<symbol>` or `<area>` when it is a snippet or prose (say so once at the top rather than inventing numbers); a range is `file:start-end`. One root cause at several sites is one heading citing the first site, with the rest named on the `Code:` line. A `Chain:` line exists only on compounding findings - on both of them, each naming the other by locator - and marks them as such (a forged token that then reaches a tenant-scoping gap); each keeps its own severity, and partial remediation of a chain buys much less than the finding count suggests. A defect this skill does not own (a detached goroutine, a transaction held open) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Attack scenario:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

```
## Remediation
| # | Finding | Severity | Effort | Ship first? |
|---|---------|----------|--------|-------------|
```

One row per finding heading, `Finding` being the heading's locator plus a short title, ordered by what removes an exploitable path first. `Effort` is `S | M | L` (hours / a day / a sprint). `Ship first?` is `Yes` on every row that closes an exploitable path on its own, `No` otherwise - an `(unverified)` row is judged by the exploit it would have. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries.

```
| Concern | Decision | Rationale |
|---------|----------|-----------|
| JWT alg | HS256 pinned via WithValidMethods | single service, shared secret in Vault |
| Request DTO | `CreateUserRequest` without Role/OwnerID | mass-assignment guard |
```

## Avoid

- `BindJSON` over `ShouldBindJSON` (loses error-response control)
- Decoding a request body into a domain model (`json.Unmarshal(body, &user)`, JSON -> map -> `mapstructure.Decode`)
- Raw GORM model returned from handlers (`c.JSON(200, user)` leaks `PasswordHash`, `MFASecret`, audit columns)
- `fmt.Sprintf` interpolation into SQL
- `sh -c` / `cmd /c` / `bash -c` with any user-controlled segment
- `math/rand` for tokens, nonces, IDs, or secrets
- `bytes.Equal` / `==` for HMAC, signature, or hash comparison (timing attack)
- API keys stored or looked up in plaintext
- `InsecureSkipVerify: true` outside a test fixture
- `gin.DebugMode` in production (prints the route table and warnings to stdout; pair with a prod log level)
- `pprof` exposed in production without admin auth
- `gob.NewDecoder(r).Decode` on untrusted input (not hardened against adversarial data)
- `text/template` (not `html/template`) for HTML output
- JWT in URL query string or session cookie without `Secure; HttpOnly; SameSite`
- Logging `password`, `token`, `authorization`, `credit_card`, `ssn`, `api_key`
- Login responses that differ between "user missing" and "wrong password"
