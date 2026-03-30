---
name: go-gin-patterns
description: "Gin web framework patterns: routing groups, middleware, request binding with validation, consistent JSON responses, pagination, webhook handlers, rate limiting, graceful shutdown, health endpoints."
metadata:
  category: backend
  tags: [go, gin, http, middleware, routing, pagination, webhook]
user-invocable: false
---

# Go Gin Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Structuring a new Gin HTTP service or reviewing an existing one
- Implementing middleware (auth, logging, rate limiting, error handling)
- Designing consistent API request/response contracts
- Implementing webhook endpoints that need raw body reading and signature validation
- Adding health and readiness endpoints for Kubernetes or load balancers
- Implementing graceful shutdown for zero-downtime deploys

## Rules

- No business logic in handlers - handlers orchestrate, services execute
- Never call `c.JSON` in services or repositories - only in handlers
- Never use `gin.Default()` in production - it registers logger and recovery middleware you can't control; use `gin.New()` and attach explicitly
- Never concatenate host and port as strings - use `net.JoinHostPort`
- Return consistent response envelopes for all endpoints (success and error)
- For webhook endpoints, read the raw body before any JSON binding - `ShouldBindJSON` consumes the body and breaks signature validation

## Patterns

### Router Structure with Groups

```go
func NewRouter(cfg *Config, deps *Dependencies) *gin.Engine {
    r := gin.New()
    r.Use(middleware.Logger())
    r.Use(middleware.Recovery())
    r.Use(middleware.ErrorHandler()) // centralized error mapping

    // Health endpoints - no auth required
    r.GET("/health", handlers.Health)
    r.GET("/ready", handlers.Ready(deps.DB))

    // Webhook endpoints - signature validation, no JWT auth
    webhooks := r.Group("/api/v1/webhooks")
    webhooks.POST("/stripe", middleware.WebhookSignature(cfg.StripeWebhookSecret), handlers.StripeWebhook(deps.PaymentService))

    // API endpoints - JWT auth required
    v1 := r.Group("/api/v1")
    v1.Use(middleware.Auth(cfg.JWTSecret))
    v1.Use(middleware.RateLimit(cfg.RateLimit))
    {
        users := v1.Group("/users")
        users.GET("", handlers.ListUsers(deps.UserService))
        users.GET("/:id", handlers.GetUser(deps.UserService))
        users.POST("", handlers.CreateUser(deps.UserService))
    }

    return r
}
```

### Request Binding and Validation

Use `ShouldBindJSON` (returns error) rather than `BindJSON` (writes 400 and aborts on error - less control):

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
        if err != nil {
            c.Error(err) // delegate to error middleware
            return
        }
        c.JSON(http.StatusCreated, SuccessResponse{Data: user})
    }
}

// Query param binding
type ListUsersQuery struct {
    Page     int    `form:"page"   binding:"gte=1"`
    PageSize int    `form:"size"   binding:"gte=1,lte=100"`
    Status   string `form:"status" binding:"omitempty,oneof=active inactive"`
}

func ListUsers(svc UserService) gin.HandlerFunc {
    return func(c *gin.Context) {
        var q ListUsersQuery
        q.Page, q.PageSize = 1, 20 // defaults
        if err := c.ShouldBindQuery(&q); err != nil {
            c.JSON(http.StatusBadRequest, ErrorResponse{Error: err.Error()})
            return
        }
        // ...
    }
}
```

### Consistent Response Envelope

```go
type SuccessResponse struct {
    Data any        `json:"data"`
    Meta *PaginationMeta `json:"meta,omitempty"`
}

type ErrorResponse struct {
    Error string `json:"error"`
    Code  string `json:"code,omitempty"`
}

type PaginationMeta struct {
    Page       int `json:"page"`
    PageSize   int `json:"page_size"`
    TotalItems int `json:"total_items"`
    TotalPages int `json:"total_pages"`
}
```

### Pagination

```go
func (q *ListUsersQuery) ToOffset() (limit, offset int) {
    return q.PageSize, (q.Page - 1) * q.PageSize
}

// In handler:
limit, offset := q.ToOffset()
users, total, err := svc.List(ctx, limit, offset, q.Status)
c.JSON(http.StatusOK, SuccessResponse{
    Data: users,
    Meta: &PaginationMeta{
        Page:       q.Page,
        PageSize:   q.PageSize,
        TotalItems: total,
        TotalPages: (total + q.PageSize - 1) / q.PageSize,
    },
})
```

### Webhook Handler (Raw Body + Signature Validation)

Webhook endpoints from external services (Stripe, GitHub, etc.) require reading the raw body for signature validation. `ShouldBindJSON` consumes the body, so webhook handlers must use a different pattern:

```go
// Middleware: validate webhook signature before handler runs
func WebhookSignature(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        body, err := c.GetRawData()
        if err != nil {
            c.AbortWithStatusJSON(http.StatusBadRequest, ErrorResponse{Error: "invalid body"})
            return
        }
        sig := c.GetHeader("Stripe-Signature")
        if _, err := webhook.ConstructEvent(body, sig, secret); err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, ErrorResponse{Error: "invalid signature"})
            return
        }
        c.Set("webhook_body", body)
        c.Next()
    }
}

// Handler: reads pre-validated body from context
func StripeWebhook(svc PaymentService) gin.HandlerFunc {
    return func(c *gin.Context) {
        body := c.MustGet("webhook_body").([]byte)
        var event stripe.Event
        if err := json.Unmarshal(body, &event); err != nil {
            c.JSON(http.StatusBadRequest, ErrorResponse{Error: "invalid event"})
            return
        }
        if err := svc.HandleWebhookEvent(c.Request.Context(), event); err != nil {
            c.Error(err)
            return
        }
        c.JSON(http.StatusOK, gin.H{"received": true})
    }
}
```

Webhook endpoints should NOT be behind JWT auth middleware - they use their own signature-based authentication.

### Custom Middleware

```go
func Auth(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        token := c.GetHeader("Authorization")
        claims, err := parseJWT(token, secret)
        if err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, ErrorResponse{Error: "unauthorized"})
            return
        }
        c.Set("user_id", claims.UserID)
        c.Next()
    }
}

func Logger() gin.HandlerFunc {
    return func(c *gin.Context) {
        start := time.Now()
        c.Next()
        slog.Info("request",
            "method", c.Request.Method,
            "path", c.Request.URL.Path,
            "status", c.Writer.Status(),
            "duration", time.Since(start),
        )
    }
}
```

### Rate Limiting Middleware

```go
func RateLimit(rps int) gin.HandlerFunc {
    limiter := rate.NewLimiter(rate.Limit(rps), rps)
    return func(c *gin.Context) {
        if !limiter.Allow() {
            c.AbortWithStatusJSON(http.StatusTooManyRequests, ErrorResponse{Error: "rate limit exceeded"})
            return
        }
        c.Next()
    }
}

// Per-client rate limiting (by IP or API key)
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

### Health and Readiness Endpoints

```go
func Health(c *gin.Context) {
    c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

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
func Run(r *gin.Engine, cfg *Config) error {
    addr := net.JoinHostPort(cfg.Host, cfg.Port) // not cfg.Host + ":" + cfg.Port
    srv := &http.Server{
        Addr:    addr,
        Handler: r,
    }

    go func() {
        if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
            slog.Error("server error", "err", err)
        }
    }()

    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit

    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()
    return srv.Shutdown(ctx)
}
```

## Edge Cases

- **Path parameter conflicts**: `/:id` and `/new` on the same group conflict - Gin treats `/new` as a value for `:id`. Use different prefixes or reorder routes
- **Empty body on POST**: `ShouldBindJSON` with an empty body returns an error. If a POST endpoint accepts no body, don't use `ShouldBindJSON`
- **Context cancellation in middleware**: if the client disconnects mid-request, `c.Request.Context()` is cancelled. Long-running handlers should check `ctx.Err()` periodically
- **Webhook replay attacks**: validate webhook timestamp (Stripe includes `t=` in the signature header) to reject old events. Most webhook libraries handle this automatically within a tolerance window

## Output Format

```
## API Design

### Endpoints
| Method | Path | Auth | Request | Response | Status |
|--------|------|------|---------|----------|--------|
| GET    | /api/v1/{resource} | JWT | query params | SuccessResponse{[]T} + PaginationMeta | 200 |
| POST   | /api/v1/{resource} | JWT | CreateRequest | SuccessResponse{T} | 201 |
| POST   | /api/v1/webhooks/{provider} | Signature | raw body | {"received": true} | 200 |

### Middleware Stack
| Middleware | Scope | Purpose |
|-----------|-------|---------|
| Logger | global | request logging |
| Recovery | global | panic recovery |
| ErrorHandler | global | centralized error mapping |
| Auth | /api/v1 | JWT validation |
| WebhookSignature | /webhooks | signature validation |

### Response Envelope
- Success: `{"data": ..., "meta": ...}`
- Error: `{"error": "...", "code": "..."}`
```

## Avoid

- Business logic or database access in handler functions
- Calling `c.JSON` outside of handler layer
- `gin.Default()` - use `gin.New()` with explicit middleware
- Concatenating host:port as strings - use `net.JoinHostPort`
- No pagination limits (unbounded list endpoints)
- Missing graceful shutdown (in-flight requests dropped on SIGTERM)
- Using `ShouldBindJSON` on webhook endpoints (consumes body, breaks signature validation)
- Putting webhook endpoints behind JWT auth middleware (they use signature-based auth)
