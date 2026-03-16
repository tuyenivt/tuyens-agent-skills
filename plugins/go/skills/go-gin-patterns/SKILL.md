---
name: go-gin-patterns
description: "Gin web framework patterns: routing groups, middleware, request binding with validation, consistent JSON responses, pagination, graceful shutdown, health endpoints."
metadata:
  category: backend
  tags: [go, gin, http, middleware, routing, pagination]
user-invocable: false
---

# Go Gin Patterns

## When to Use

- Structuring a new Gin HTTP service or reviewing an existing one
- Implementing middleware (auth, logging, rate limiting, error handling)
- Designing consistent API request/response contracts
- Adding health and readiness endpoints for Kubernetes or load balancers
- Implementing graceful shutdown for zero-downtime deploys

## Rules

- No business logic in handlers - handlers orchestrate, services execute
- Never call `c.JSON` in services or repositories - only in handlers
- Never use `gin.Default()` in production - it registers logger and recovery middleware you can't control; use `gin.New()` and attach explicitly
- Never concatenate host and port as strings - use `net.JoinHostPort`
- Return consistent response envelopes for all endpoints (success and error)

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

    v1 := r.Group("/api/v1")
    v1.Use(middleware.Auth(cfg.JWTSecret))
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

## Anti-Patterns

```go
// Bad: business logic in handler
func GetUser(c *gin.Context) {
    id := c.Param("id")
    var user User
    db.Where("id = ? AND deleted_at IS NULL", id).First(&user) // DB logic in handler
    c.JSON(200, user) // no error handling, no envelope
}

// Bad: c.JSON in service layer
func (s *UserService) Create(req CreateUserRequest) {
    // ...
    c.JSON(201, user) // service cannot access gin context
}

// Bad: gin.Default() in production
r := gin.Default() // Logger and Recovery middlewares you can't configure

// Bad: string concatenation for address
srv.Addr = cfg.Host + ":" + cfg.Port // use net.JoinHostPort instead
```

## Avoid

- Business logic or database access in handler functions
- Calling `c.JSON` outside of handler layer
- `gin.Default()` - use `gin.New()` with explicit middleware
- Concatenating host:port as strings
- No pagination limits (unbounded list endpoints)
- Missing graceful shutdown (in-flight requests dropped on SIGTERM)

## Self-Check

- [ ] Handlers contain no business logic or direct DB access - they orchestrate services
- [ ] All endpoints return a consistent response envelope (`SuccessResponse` / `ErrorResponse`)
- [ ] List endpoints implement pagination with defaults and upper-bound limits
- [ ] `gin.New()` used instead of `gin.Default()` with explicit middleware registration
- [ ] Graceful shutdown implemented with `signal.Notify` and `srv.Shutdown`
- [ ] Health and readiness endpoints present at `/health` and `/ready`
- [ ] `net.JoinHostPort` used for address construction
