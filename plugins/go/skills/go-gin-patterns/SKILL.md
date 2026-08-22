---
name: go-gin-patterns
description: "Gin patterns: routing groups, middleware, request binding, JSON envelopes, pagination, webhooks (raw body), rate limiting, graceful shutdown."
metadata:
  category: backend
  tags: [go, gin, http, middleware, routing, pagination, webhook]
user-invocable: false
---

# Go Gin Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Structuring or reviewing a Gin HTTP service
- Implementing middleware (auth, rate limiting, error handling)
- Designing consistent request/response contracts
- Webhook endpoints requiring raw body + signature validation
- Graceful shutdown / health endpoints

## Rules

- Handlers orchestrate; services execute. No business logic in handlers - a handler binds, calls one service method, and writes the response. Middleware writes only its own rejection (`AbortWithStatusJSON`); success bodies come from handlers
- Use `gin.New()` with explicit middleware; never `gin.Default()` in production
- `net.JoinHostPort(host, port)`, never string concat
- One JSON envelope for success and error on every endpoint that returns a JSON body. Exempt: 204s, probe endpoints, and non-JSON content types (SSE, file downloads) - name each exemption rather than letting shapes drift
- Every `http.Server` sets `ReadHeaderTimeout`; a body-carrying route caps the body with `http.MaxBytesReader`
- Group middleware is additive - a child group can never remove a parent's. Build the stack as a `[]gin.HandlerFunc` value and hang divergent groups off the engine root
- Webhooks: read raw body before any binding (`ShouldBindJSON` consumes the body and breaks signatures)
- Webhook routes live outside the JWT auth group, and handlers tolerate redelivery - providers retry on non-2xx and on timeout

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
    r.Use(middleware.Logger(), middleware.Recovery(), middleware.ErrorHandler())

    r.GET("/health", handlers.Health)
    r.GET("/ready", handlers.Ready(deps.DB))

    webhooks := r.Group("/api/v1/webhooks")
    webhooks.POST("/stripe", middleware.WebhookSignature(cfg.StripeWebhookSecret), handlers.StripeWebhook(deps.PaymentService))

    v1 := r.Group("/api/v1")
    v1.Use(middleware.Auth(cfg.JWTSecret), middleware.RateLimit(cfg.RateLimit))
    {
        users := v1.Group("/users")
        users.GET("", handlers.ListUsers(deps.UserService))
        users.POST("", handlers.CreateUser(deps.UserService))
    }
    return r, nil
}
```

Building the stack as a `[]gin.HandlerFunc` value lets two groups on the same prefix carry different chains - but build each with a fresh slice (`slices.Concat`, or copy before appending). Two `append(base, ...)` calls share `base`'s backing array, and the second silently overwrites the first group's last handler.

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

Raw validator `err.Error()` names Go struct fields - acceptable internally; public APIs map it to a ValidationError (see go-error-handling).

### Response Envelope

```go
type SuccessResponse struct {
    Data any             `json:"data"`
    Meta *PaginationMeta `json:"meta,omitempty"`
}
type ErrorResponse struct {
    Error string `json:"error"`
    Code  string `json:"code,omitempty"`
}
type PaginationMeta struct {
    PageSize   int    `json:"page_size"`
    Page       int    `json:"page,omitempty"`        // offset mode only
    TotalItems int    `json:"total_items,omitempty"` // offset mode only
    TotalPages int    `json:"total_pages,omitempty"` // offset mode only
    NextCursor string `json:"next_cursor,omitempty"` // keyset mode only
}
```

The two modes are mutually exclusive, so every field but `PageSize` carries `omitempty` - a keyset response emitting `"page":0,"total_pages":0` is a contract clients will code against and that cannot be removed later.

Untagged fields serialize as `Page` / `PageSize`, which no client expects and which cannot be corrected later without breaking them. Tag every response struct at creation.

### Pagination

```go
limit, offset := q.PageSize, (q.Page-1)*q.PageSize
users, total, err := svc.List(ctx, limit, offset, q.Status)
c.JSON(http.StatusOK, SuccessResponse{
    Data: users,
    Meta: &PaginationMeta{
        Page: q.Page, PageSize: q.PageSize, TotalItems: total,
        TotalPages: (total + q.PageSize - 1) / q.PageSize,
    },
})
```

### Webhook (Raw Body + Signature)

```go
func WebhookSignature(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        body, err := c.GetRawData()
        if err != nil {
            c.AbortWithStatusJSON(http.StatusBadRequest, ErrorResponse{Error: "invalid body"})
            return
        }
        if _, err := webhook.ConstructEvent(body, c.GetHeader("Stripe-Signature"), secret); err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, ErrorResponse{Error: "invalid signature"})
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
        if err := svc.HandleWebhookEvent(c.Request.Context(), event); err != nil {
            c.Error(err); return
        }
        c.JSON(http.StatusOK, gin.H{"received": true})
    }
}
```

`webhook.ConstructEvent` is Stripe's SDK; generic providers verify with `hmac.New(sha256.New, secret)` + `hmac.Equal(expected, received)` - never `==` on MACs.

### Custom Middleware

```go
func Auth(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        claims, err := parseJWT(c.GetHeader("Authorization"), secret)
        if err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, ErrorResponse{Error: "unauthorized"})
            return
        }
        c.Set("user_id", claims.UserID)
        c.Next()
    }
}

// Per-client rate limiting; for global use a single rate.NewLimiter
func PerClientRateLimit(rps int) gin.HandlerFunc {
    var mu sync.Mutex
    clients := make(map[string]*rate.Limiter)
    return func(c *gin.Context) {
        key := c.ClientIP()
        mu.Lock()
        lim, ok := clients[key]
        if !ok {
            lim = rate.NewLimiter(rate.Limit(rps), rps)
            clients[key] = lim
        }
        mu.Unlock()
        if !lim.Allow() {
            c.AbortWithStatusJSON(http.StatusTooManyRequests, ErrorResponse{Error: "rate limit exceeded"})
            return
        }
        c.Next()
    }
}
```

The `clients` map grows one entry per unique key forever - scanner traffic makes it a slow leak. Evict via a last-seen sweep or LRU.

- `rate.Limit` is per second; a per-minute quota is `rate.Every(time.Minute/N)` with burst `N`.
- Key on the authenticated principal once one exists (`user:<id>`, `key:<id>`); `ClientIP()` puts a whole NAT behind one bucket and gives one API key N buckets. That means the limiter runs *after* auth; put a cheap IP limiter before auth to shed unauthenticated floods.
- `ClientIP()` needs `SetTrustedProxies` covering **every** hop (ingress *and* CDN ranges) - listing only the nearest proxy stops the `X-Forwarded-For` walk at the CDN edge. Gin's default `RemoteIPHeaders` also trusts `X-Real-IP`, which a proxy typically sets to its own address; drop it when `X-Forwarded-For` is authoritative. `TrustedPlatform` skips the proxy check entirely and is forgeable by anything that can reach the origin directly.
- In-process buckets are per replica: the effective ceiling is `rps * replicas`. Move to Redis when the quota is contractual.

### Health and Readiness

```go
func Health(c *gin.Context) { c.JSON(http.StatusOK, gin.H{"status": "ok"}) }

func Ready(db *sql.DB) gin.HandlerFunc {
    return func(c *gin.Context) {
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

    go func() {
        if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
            slog.Error("server error", "err", err)
        }
    }()

    ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
    defer stop()
    <-ctx.Done()
    stop() // a second signal now kills the process outright

    ready.Store(false)             // /ready fails first so the LB stops routing
    time.Sleep(cfg.PreStopDelay)   // one probe interval, while still serving
    close(cfg.Drain)               // long-lived handlers (SSE, streams) end themselves

    sctx, cancel := context.WithTimeout(context.Background(), cfg.DrainTimeout)
    defer cancel()
    if err := srv.Shutdown(sctx); err != nil {
        return srv.Close() // Shutdown waits forever on a stuck connection; Close is the floor
    }
    return nil
}
```

`PreStopDelay + DrainTimeout` must be under the platform's kill deadline (k8s `terminationGracePeriodSeconds`), and `DrainTimeout` above the slowest normal request. `Shutdown` waits on connections but never on goroutines a handler detached - drain those separately.

## Edge Cases

- A static route and a wildcard sibling (`/orders/export` next to `/orders/:id`) are supported from Gin v1.7 (mixed static/param routing, gin#2663); earlier versions panic at registration with `conflicts with existing wildcard`. Registration order changes neither outcome - on a version that panics the only fix is a different prefix
- `ShouldBindJSON` with an empty body errors - skip for POSTs with no body
- **Client disconnect: decide abandon or survive.** Abandon (reads, queries) - poll `c.Request.Context().Err()` and return; the request context is cancelled both on hangup and when the handler returns. Survive (a submitted job, a payment already taken) - hand the work to a durable queue and return 202. If it must stay in-process, `c.Copy()` first (Gin recycles `*gin.Context` through a pool the moment the handler returns) and derive from `context.WithoutCancel(cp.Request.Context())` plus your own timeout, so trace and tenant values survive but the cancellation does not
- Cap request bodies with `http.MaxBytesReader` before anything reads them; `*http.MaxBytesError` maps to 413. `MaxMultipartMemory` only decides heap-vs-tempfile, it is not a size limit
- Validate webhook timestamps to reject replays (most libraries handle this within tolerance)

## Output Format

Design or change-set engagements emit `## API Design`; review engagements emit `## Findings` first, then `## API Design` describing the surface **as it exists today**.

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

Cell values: `Status` lists the HTTP codes the endpoint returns. `Change` is `New | Changed | Unchanged | Removed` - omit the column entirely on a greenfield design. `Order` is the execution position within `Scope`, numbered from 1. `Scope` is `engine | group <prefix> | route <method path>`. `Response Envelope` rows are the shapes actually emitted, one row per distinct shape, with any exemption (204, probe, SSE, file) named as its own row. Anything the input does not supply is `unknown`; a handler not provided is `not supplied`.

```
## Findings

### [Must] file:line

- Defect: {what breaks - wrong status, lost request, spoofable input, dropped work}
- Rule: {the Gin rule or pattern violated}
- Fix: {concrete edit}
```

`[Must]` when the service fails to start, a security control is void, work is silently lost, or a client-visible contract is wrong; `[Recommend]` otherwise. Order `[Must]` first, then by file and line. A defect this skill does not own (transactions, goroutines, crypto choice) is still reported, in one closing `[Recommend]` block naming the owning concern - never dropped.

## Avoid

- Business logic in handlers
- `gin.Default()` in production
- Unbounded list endpoints, and deep `OFFSET` paging on a growing table - switch to a keyset cursor
- `ShouldBindJSON` on webhook endpoints
- Webhook routes inside the JWT auth group
- Detaching a goroutine from a handler without `c.Copy()` - Gin pools and reuses `*gin.Context` the moment the handler returns
