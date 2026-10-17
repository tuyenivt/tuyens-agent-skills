---
name: go-gin-patterns
description: "Gin patterns: routing groups, middleware, request binding, JSON envelopes, pagination, webhooks (raw body), rate limiting, graceful shutdown."
metadata:
  category: backend
  tags: [go, gin, http, middleware, routing, pagination, webhook]
user-invocable: false
---

# Go Gin Patterns

> Load `Use skill: stack-detect` first. This skill reads `Framework`: when it names another framework (Echo, Chi, net/http) stop and emit the single line `go-gin-patterns: not applicable (<framework>)` - the HTTP-layer patterns here do not transfer; on `unknown` (what a stdlib-only service also detects as) proceed as Gin only when `github.com/gin-gonic/gin` is in `go.mod`, otherwise stop the same way. The Go version is the `go` directive in `go.mod` (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). Baseline: Go 1.25+, Gin v1.10+, stripe-go v82.1+ (`stripe.NewClient`).

## When to Use

- Structuring or reviewing a Gin HTTP service
- Implementing middleware (auth, rate limiting, error handling)
- Designing consistent request/response contracts
- Webhook endpoints requiring raw body + signature validation
- Graceful shutdown / health endpoints

## Rules

- Handlers orchestrate; services execute. No business logic in handlers - a handler binds, calls one service method, and writes the response. Middleware writes only its own rejection (`AbortWithStatusJSON`) or an idempotent replay of a stored response; every other success body comes from a handler
- Use `gin.New()` with explicit middleware; never `gin.Default()` in production
- `net.JoinHostPort(host, port)`, never string concat
- One JSON envelope for success and error on every endpoint that returns a JSON body. Exempt: 204s, probe endpoints, and non-JSON content types (SSE, file downloads) - name each exemption rather than letting shapes drift. An empty body is a 204, never an empty 200
- Every `http.Server` sets `ReadHeaderTimeout`; a body-carrying route caps the body with `http.MaxBytesReader` before anything reads it
- Group middleware is additive - a child group can never remove a parent's. Build the stack as a `[]gin.HandlerFunc` value and hang divergent groups off the engine root
- Webhooks: read raw body before any binding (`ShouldBindJSON` consumes the body and breaks signatures)
- Webhook routes live outside the JWT auth group, and handlers tolerate redelivery - providers retry on non-2xx and on timeout
- A retryable write (`POST`) takes a client `Idempotency-Key` header, scoped to the principal and bound to a hash of the body: same key + same body returns the first response, same key + different body is `409`

## Patterns

### Router Structure

```go
func NewRouter(cfg *Config, deps *Dependencies) (*gin.Engine, error) {
    r := gin.New()
    // Default trusts every proxy - ClientIP() is spoofable via X-Forwarded-For until set.
    // Check the error: a typo'd CIDR otherwise starts the service wide open.
    if err := r.SetTrustedProxies(cfg.TrustedProxies); err != nil {
        return nil, fmt.Errorf("trusted proxies: %w", err)
    }
    r.Use(middleware.Logger(), middleware.Recovery(), middleware.ErrorHandler(), middleware.MaxBody(1<<20), middleware.IPRateLimit(cfg.IPRateLimit))

    r.GET("/health", handlers.Health)
    r.GET("/ready", handlers.Ready(deps.DB, deps.Ready))

    webhooks := r.Group("/api/v1/webhooks") // signature is the only auth - outside the JWT group
    webhooks.POST("/stripe", middleware.WebhookSignature(cfg.StripeWebhookSecret), handlers.StripeWebhook(deps.PaymentService))

    partner := r.Group("/api/v1/partner", middleware.APIKey(deps.Keys), middleware.PrincipalRateLimit(cfg.RateLimit))
    partner.POST("/refunds", middleware.Idempotency(deps.IdemStore), handlers.CreateRefund(deps.RefundService))

    v1 := r.Group("/api/v1")
    v1.Use(middleware.Auth(cfg.JWTSecret), middleware.PrincipalRateLimit(cfg.RateLimit))
    {
        users := v1.Group("/users")
        users.GET("", handlers.ListUsers(deps.UserService))
        users.POST("", middleware.Idempotency(deps.IdemStore), handlers.CreateUser(deps.UserService))
    }
    return r, nil
}
```

Both `Auth` and `APIKey` end in `c.Set("principal", Principal{ID, MerchantID, Role, Via})`, so handlers read one key and never care which credential arrived. `MaxBody` is `c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, n)` then `c.Next()`. `Idempotency` keys on `(principal, Idempotency-Key)`: a stored row holds `body_hash`, `state (in_flight | done)`, `status`, `response`; a hit with the same hash replays the stored response (the one case where middleware writes a success body), a different hash is `409`, `in_flight` is `409` too, and a `5xx` releases the row so the client can retry. Building the stack as a `[]gin.HandlerFunc` value lets two groups on the same prefix carry different chains - but build each with a fresh slice (`slices.Concat`, or copy before appending). Two `append(base, ...)` calls share `base`'s backing array whenever `cap(base) > len(base)`, and the second then overwrites the first group's last handler.

### Request Binding

`ShouldBindJSON` returns the error; `BindJSON` writes 400 and aborts (lost control).

```go
type CreateUserRequest struct {
    Name  string `json:"name"  binding:"required,min=2,max=100"`
    Email string `json:"email" binding:"required,email"`
    Age   int    `json:"age"   binding:"gte=0,lte=130"`
}

func CreateUser(svc UserService) gin.HandlerFunc {
    return func(c *gin.Context) {
        var req CreateUserRequest
        if err := c.ShouldBindJSON(&req); err != nil {
            c.JSON(http.StatusBadRequest, ErrorResponse{Error: err.Error()})
            return
        }
        user, err := svc.Create(c.Request.Context(), req)
        if err != nil { c.Error(err); return }
        c.JSON(http.StatusCreated, SuccessResponse{Data: user})
    }
}

// Query params - `default` fills omitted fields BEFORE validation, so bare GET /users passes gte=1
type ListUsersQuery struct {
    Page     int    `form:"page,default=1"  binding:"gte=1"`
    PageSize int    `form:"size,default=20" binding:"gte=1,lte=100"`
    Status   string `form:"status" binding:"omitempty,oneof=active inactive"`
}
```

Raw validator `err.Error()` names Go struct fields - acceptable internally; public APIs map it to a ValidationError (see go-error-handling). Validation that `binding:` already enforced is not repeated in the handler.

### Response Envelope

```go
type SuccessResponse struct {
    Data any `json:"data"`
    Meta any `json:"meta,omitempty"` // *OffsetMeta or *CursorMeta - one shape per endpoint, never both
}
type ErrorResponse struct {
    Error string `json:"error"`
    Code  string `json:"code,omitempty"`
}
type OffsetMeta struct {
    Page       int `json:"page"`
    PageSize   int `json:"page_size"`
    TotalItems int `json:"total_items"` // 0 on an empty page is a real value - no omitempty
    TotalPages int `json:"total_pages"`
}
type CursorMeta struct {
    PageSize   int    `json:"page_size"`
    NextCursor string `json:"next_cursor,omitempty"` // absent on the last page
    HasMore    bool   `json:"has_more"`
}
```

Offset and keyset are different types, not one struct with `omitempty` on the mode-specific fields - `omitempty` would also drop a legitimate `total_items: 0`, and a keyset response emitting `"page":0` is a contract clients code against and that cannot be removed later.

Untagged fields serialize as `Page` / `PageSize`, which no client expects and which cannot be corrected later without breaking them. Tag every response struct at creation.

### Pagination

```go
limit, offset := q.PageSize, (q.Page-1)*q.PageSize
users, total, err := svc.List(ctx, limit, offset, q.Status)
c.JSON(http.StatusOK, SuccessResponse{
    Data: users,
    Meta: &OffsetMeta{
        Page: q.Page, PageSize: q.PageSize, TotalItems: total,
        TotalPages: (total + q.PageSize - 1) / q.PageSize,
    },
})
```

### Webhook (Raw Body + Signature)

```go
func WebhookSignature(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 1<<20) // cap before the read
        body, err := c.GetRawData()
        if err != nil {
            status := http.StatusBadRequest
            var tooBig *http.MaxBytesError
            if errors.As(err, &tooBig) { status = http.StatusRequestEntityTooLarge }
            c.AbortWithStatusJSON(status, ErrorResponse{Error: "invalid body"})
            return
        }
        // Stripe signs "{t}.{payload}" in Stripe-Signature: t=...,v1=... with a timestamp tolerance.
        // ConstructEvent also rejects an API-version mismatch; IgnoreAPIVersionMismatch keeps a valid
        // signature from turning into a 400 that Stripe retries for days.
        if _, err := webhook.ConstructEventWithOptions(body, c.GetHeader("Stripe-Signature"), secret,
            webhook.ConstructEventOptions{IgnoreAPIVersionMismatch: true}); err != nil {
            c.AbortWithStatusJSON(http.StatusBadRequest, ErrorResponse{Error: "invalid signature"})
            return
        }
        c.Set("webhook_body", body)
        c.Next()
    }
}

func StripeWebhook(svc PaymentService) gin.HandlerFunc {
    return func(c *gin.Context) {
        body := c.MustGet("webhook_body").([]byte)
        var event stripe.Event
        if err := json.Unmarshal(body, &event); err != nil {
            c.JSON(http.StatusBadRequest, ErrorResponse{Error: "invalid event"})
            return
        }
        if err := svc.HandleWebhookEvent(c.Request.Context(), event); err != nil { // idempotent on event.ID
            c.Error(err); return
        }
        c.JSON(http.StatusOK, SuccessResponse{Data: gin.H{"received": true}})
    }
}
```

Generic providers verify with `mac := hmac.New(sha256.New, []byte(secret))` over the raw body and `hmac.Equal(mac.Sum(nil), decoded)` where `decoded` is the header value hex- or base64-decoded (GitHub: `X-Hub-Signature-256: sha256=<hex>`, strip the prefix) - never `==` on MACs, never compare against the raw header string. The handler's status is a protocol: `2xx` stops redelivery, `5xx` asks for it, a bad signature is `400` and must never become a `2xx`.

### Custom Middleware

```go
func Auth(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        claims, err := parseJWT(c.GetHeader("Authorization"), secret)
        if err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, ErrorResponse{Error: "unauthorized"})
            return
        }
        c.Set("principal", Principal{ID: claims.UserID, MerchantID: claims.MerchantID, Role: claims.Role, Via: "jwt"})
        c.Next()
    }
}

// Pre-auth, keyed on IP: sheds unauthenticated floods. Post-auth, keyed on the principal: the real quota.
func rateLimitBy(key func(*gin.Context) string, rps int) gin.HandlerFunc {
    var mu sync.Mutex
    clients := make(map[string]*rate.Limiter) // grows one entry per key forever - evict via last-seen sweep or LRU
    return func(c *gin.Context) {
        k := key(c)
        mu.Lock()
        lim, ok := clients[k]
        if !ok {
            lim = rate.NewLimiter(rate.Limit(rps), rps)
            clients[k] = lim
        }
        mu.Unlock()
        if !lim.Allow() {
            c.AbortWithStatusJSON(http.StatusTooManyRequests, ErrorResponse{Error: "rate limit exceeded"})
            return
        }
        c.Next()
    }
}
func IPRateLimit(rps int) gin.HandlerFunc        { return rateLimitBy(func(c *gin.Context) string { return c.ClientIP() }, rps) }
func PrincipalRateLimit(rps int) gin.HandlerFunc { return rateLimitBy(func(c *gin.Context) string { return c.MustGet("principal").(Principal).Key() }, rps) }
```

- `rate.Limit` is per second; a per-minute quota is `rate.Every(time.Minute/N)` with burst `N`.
- `ClientIP()` puts a whole NAT behind one bucket and gives one API key N buckets - which is why the principal limiter runs after auth and the IP limiter is only a flood shed.
- `ClientIP()` needs `SetTrustedProxies` covering **every** hop (ingress *and* CDN ranges) - listing only the nearest proxy stops the `X-Forwarded-For` walk at the CDN edge. Gin's default `RemoteIPHeaders` also reads `X-Real-IP` when `X-Forwarded-For` is missing or unparseable; a proxy sets it to the address of the peer that connected to it, so it is only as trustworthy as that proxy. `TrustedPlatform` skips the proxy check entirely and is forgeable by anything that can reach the origin directly.
- In-process buckets are per replica: the effective ceiling is `rps * replicas`. Move to Redis when the quota is contractual.

### Health and Readiness

```go
func Health(c *gin.Context) { c.JSON(http.StatusOK, gin.H{"status": "ok"}) }

func Ready(db *sql.DB, ready *atomic.Bool) gin.HandlerFunc {
    return func(c *gin.Context) {
        if !ready.Load() { // flipped false by Run during shutdown
            c.JSON(http.StatusServiceUnavailable, gin.H{"status": "draining"})
            return
        }
        if err := db.PingContext(c.Request.Context()); err != nil {
            c.JSON(http.StatusServiceUnavailable, gin.H{"status": "not ready", "reason": "db"})
            return
        }
        c.JSON(http.StatusOK, gin.H{"status": "ready"})
    }
}
```

### Graceful Shutdown

```go
func Run(r *gin.Engine, cfg *Config, ready *atomic.Bool) error {
    srv := &http.Server{
        Addr:              net.JoinHostPort(cfg.Host, cfg.Port),
        Handler:           r,
        ReadHeaderTimeout: 10 * time.Second, // Slowloris; gosec G112 flags its absence
        ReadTimeout:       cfg.ReadTimeout,
        IdleTimeout:       cfg.IdleTimeout, // set above the load balancer's idle timeout so the LB closes first
        // WriteTimeout is absolute from the start of the request, so any finite value
        // truncates long polls, SSE, and slow downloads. Bound those per handler instead.
    }

    serveErr := make(chan error, 1)
    go func() { serveErr <- srv.ListenAndServe() }()

    ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
    defer stop()
    select {
    case err := <-serveErr: // port in use, bad address: fail now, do not sit on ctx.Done()
        return fmt.Errorf("listen: %w", err)
    case <-ctx.Done():
    }
    stop() // a second signal now kills the process outright

    ready.Store(false)             // /ready fails; the LB stops routing once the probe notices
    time.Sleep(cfg.PreStopDelay)   // cover endpoint-removal propagation, while still serving
    close(cfg.Drain)               // long-lived handlers (SSE, streams) end themselves

    sctx, cancel := context.WithTimeout(context.Background(), cfg.DrainTimeout)
    defer cancel()
    if err := srv.Shutdown(sctx); err != nil { // returns ctx.Err() once DrainTimeout passes
        _ = srv.Close()                        // the floor: drop what did not drain
        return fmt.Errorf("drain: %w", err)    // and report it - a silent nil hides every truncated request
    }
    return nil
}
```

`PreStopDelay + DrainTimeout` must be under the platform's kill deadline (k8s `terminationGracePeriodSeconds`), and `DrainTimeout` above the slowest normal request. On Kubernetes a terminating pod's EndpointSlice `ready` condition goes false at once (the readiness probe drives only `serving`), so for Service routing `PreStopDelay` covers endpoint-removal propagation (~5s); only an external load balancer that probes `/ready` itself adds `failureThreshold * periodSeconds` (default 3 probes) on top. `Shutdown` waits on connections but never on goroutines a handler detached - drain those separately.

## Edge Cases

- A static route and a wildcard sibling (`/orders/export` next to `/orders/:id`) coexist (mixed static/param routing since Gin v1.7); registration order does not matter
- `ShouldBindJSON` with an empty body errors - skip for POSTs with no body
- **Client disconnect: decide abandon or survive.** Abandon (reads, queries) - poll `c.Request.Context().Err()` and return; the request context is cancelled both on hangup and when the handler returns. Survive (a submitted job, a payment already taken) - hand the work to a durable queue and return 202. If it must stay in-process, `c.Copy()` first (Gin recycles `*gin.Context` through a pool the moment the handler returns) and derive from `context.WithoutCancel(cp.Request.Context())` plus your own timeout, so trace and tenant values survive but the cancellation does not
- Cap request bodies with `http.MaxBytesReader` before anything reads them; `*http.MaxBytesError` maps to 413. `MaxMultipartMemory` only decides heap-vs-tempfile, it is not a size limit
- Validate webhook timestamps to reject replays (most libraries handle this within tolerance)

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design / change-set | `## API Design` with `### Endpoints`, `### Middleware Stack`, `### Response Envelope`; code for new handlers and wiring follows under `### <Endpoint or middleware>` headings in table order; a concern this skill does not own (transactions, authorization rules, crypto choice) is one sentence under the tables naming the owning concern |
| Review | `## Findings`, then `## API Design` describing the surface as it exists today, scoped to the routes and middleware the input supplied |

```
## API Design

### Endpoints
| Method | Path | Auth | Request | Response | Status | Change |
|--------|------|------|---------|----------|--------|--------|

### Middleware Stack
| Order | Middleware | Scope | Purpose |
|-------|------------|-------|---------|

### Response Envelope
| Shape | Body |
|-------|------|
```

Cell values: every cell describes the surface as wired; a defect in it is a Finding, never a cell annotation. `Auth` is what the route actually requires - `JWT | API key | signature | inline <kind> | none` - so a webhook inside the JWT group reads `JWT` and the finding says why that is wrong, and a check done inside the handler body reads `inline signature` plus a `[Recommend]` to lift it into middleware. `Request` is the DTO name plus any required header (`CreateRefundRequest + Idempotency-Key`), or `none`. `Response` is the envelope shape name (`SuccessResponse{Refund}`, `SuccessResponse{[]Refund} + CursorMeta`), `204`, the exemption, or the literal shape when a handler returns a bare struct. `Status` lists the HTTP codes the endpoint returns. `Change` is `New | Changed | Unchanged | Removed`; a route that keeps its path but changes group or middleware is `Changed`; a moved path is `Removed` at the old path and `New` at the new one; the column is omitted on a greenfield design and on a review. Every registered route is a row, including those on the default mux (`pprof`). `Order` is the execution position within `Scope`, numbered from 1 per scope; a child group's inherited middleware is not re-listed; when the engine stack is not supplied its rows are `unknown` and numbering still starts at 1. `Scope` is `engine | group <prefix> | route <method path> | unmounted`. `Purpose` is one phrase (`reject missing bearer`, `shed unauthenticated floods`). A middleware defined but mounted nowhere gets a row with `Scope` = `unmounted` and `Order` = `-`. `Response Envelope` rows are the shapes actually emitted, one row per distinct shape, with any exemption (204, probe, SSE, file) named as its own row; `Body` is the JSON skeleton with field names (`{"data": <T>, "meta": {"next_cursor", "has_more"}}`). A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what breaks - wrong status, lost request, spoofable input, dropped work}
- Rule: {the Gin rule or pattern violated}
- Fix: {concrete edit}
```

`[Must]` when the service fails to start, a security control is void or bypassable (a spoofable `ClientIP`, a webhook behind the wrong auth, a non-constant-time compare), work is silently lost, a response makes the sender redeliver an event already processed, or a client-visible contract is wrong; `[Recommend]` otherwise. A deployment manifest is a file like any other (`k8s/api-deployment.yaml:41`). Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site, with the rest named on the `Defect:` line. An incident question is answered inside the `Defect:` line of the finding it concerns. A defect this skill does not own (transactions, goroutines, crypto choice, authorization rules) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Business logic in handlers
- `gin.Default()` in production
- Unbounded list endpoints, and deep `OFFSET` paging on a growing table - switch to a keyset cursor
- `ShouldBindJSON` on webhook endpoints
- Webhook routes inside the JWT auth group
- Detaching a goroutine from a handler without `c.Copy()` - Gin pools and reuses `*gin.Context` the moment the handler returns
