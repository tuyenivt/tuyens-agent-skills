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

- Handlers orchestrate; services execute. No business logic or `c.JSON` outside handlers
- Use `gin.New()` with explicit middleware; never `gin.Default()` in production
- `net.JoinHostPort(host, port)`, never string concat
- One response envelope for success and error across all endpoints
- Webhooks: read raw body before any binding (`ShouldBindJSON` consumes the body and breaks signatures)
- Webhook routes live outside the JWT auth group

## Patterns

### Router Structure

```go
func NewRouter(cfg *Config, deps *Dependencies) *gin.Engine {
    r := gin.New()
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
    return r
}
```

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

// Query params with defaults
type ListUsersQuery struct {
    Page     int    `form:"page"   binding:"gte=1"`
    PageSize int    `form:"size"   binding:"gte=1,lte=100"`
    Status   string `form:"status" binding:"omitempty,oneof=active inactive"`
}
```

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
    Page, PageSize, TotalItems, TotalPages int
}
```

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
func Run(r *gin.Engine, cfg *Config) error {
    srv := &http.Server{Addr: net.JoinHostPort(cfg.Host, cfg.Port), Handler: r}

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

- `/:id` and `/new` on the same group conflict - reorder or change prefix
- `ShouldBindJSON` with an empty body errors - skip for POSTs with no body
- Long-running handlers should poll `c.Request.Context().Err()` for client disconnects
- Validate webhook timestamps to reject replays (most libraries handle this within tolerance)

## Output Format

```
## API Design

### Endpoints
| Method | Path | Auth | Request | Response | Status |

### Middleware Stack
| Middleware | Scope | Purpose |

### Response Envelope
- Success: `{"data": ..., "meta": ...}`
- Error: `{"error": "...", "code": "..."}`
```

## Avoid

- Business logic in handlers
- `gin.Default()` in production
- Unbounded list endpoints
- `ShouldBindJSON` on webhook endpoints
- Webhook routes inside the JWT auth group
