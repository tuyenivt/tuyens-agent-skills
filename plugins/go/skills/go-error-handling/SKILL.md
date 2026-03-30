---
name: go-error-handling
description: "Go error patterns: explicit returns, wrapping with %w, sentinel errors, custom error types, errors.Is/As, Gin error middleware, and external API error classification. Never swallow errors."
metadata:
  category: backend
  tags: [go, error-handling, sentinel-errors, gin, middleware]
user-invocable: false
---

# Go Error Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing error types for a new package or service
- Reviewing error handling in a code review
- Debugging unexpected error behavior (swallowed errors, lost context)
- Implementing centralized error handling in a Gin HTTP service
- Wrapping third-party API errors (Stripe, payment gateways) into domain errors

## Rules

- Always check errors - never use `_` to discard an error return
- Wrap errors with context using `fmt.Errorf("context: %w", err)` - preserve the chain
- Use `errors.Is` and `errors.As` for checking, never string matching
- Log OR return an error at each layer - never both (log-and-return duplicates noise)
- Panic only for programmer bugs (nil dereference of required dependency at startup) - never for business logic
- Map errors at the boundary: repo errors -> service errors -> HTTP status codes
- Classify external API errors as retryable or permanent - callers need this to decide on retry behavior

## Patterns

### Sentinel Errors

Use for expected, checkable conditions:

```go
var (
    ErrNotFound          = errors.New("not found")
    ErrUnauthorized      = errors.New("unauthorized")
    ErrConflict          = errors.New("conflict")
    ErrInvalidTransition = errors.New("invalid state transition")
)

// Check with errors.Is (works through wrapping chains)
if errors.Is(err, ErrNotFound) {
    // handle
}
```

### Custom Error Types

Use when callers need to extract structured data from the error:

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

// Check with errors.As
var ve *ValidationError
if errors.As(err, &ve) {
    // ve.Field and ve.Message are available
}
```

### Error Wrapping

Always add context when propagating errors up the call stack:

```go
// Bad - caller has no context where the error originated
func GetUser(id int) (*User, error) {
    user, err := db.Query(...)
    if err != nil {
        return nil, err
    }
    return user, nil
}

// Good - each layer adds its context
func GetUser(id int) (*User, error) {
    user, err := db.Query(...)
    if err != nil {
        return nil, fmt.Errorf("GetUser id=%d: %w", id, err)
    }
    return user, nil
}
```

### Error Chain: Repo -> Service -> Handler

Map errors at each layer boundary rather than leaking implementation details:

```go
// Repository layer: returns data access errors
func (r *userRepo) Find(id int) (*User, error) {
    if notFound {
        return nil, fmt.Errorf("userRepo.Find id=%d: %w", id, ErrNotFound)
    }
    // ...
}

// Service layer: maps to business errors
func (s *userService) GetUser(id int) (*User, error) {
    user, err := s.repo.Find(id)
    if errors.Is(err, ErrNotFound) {
        return nil, fmt.Errorf("user %d does not exist: %w", id, ErrNotFound)
    }
    if err != nil {
        return nil, fmt.Errorf("userService.GetUser: %w", err)
    }
    return user, nil
}

// Handler layer: maps to HTTP responses
func (h *userHandler) GetUser(c *gin.Context) {
    user, err := h.service.GetUser(id)
    if errors.Is(err, ErrNotFound) {
        c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
        return
    }
    if err != nil {
        c.Error(err) // delegate to centralized Gin error middleware
        return
    }
    c.JSON(http.StatusOK, user)
}
```

### Wrapping External API Errors

Third-party APIs (Stripe, payment gateways, etc.) return their own error types. Wrap them into domain errors at the integration boundary so callers never depend on the external library:

```go
// Bad: leaking Stripe error types into domain layer
func (g *stripeGateway) Charge(ctx context.Context, req ChargeRequest) error {
    _, err := charge.New(...)
    return err // caller must import stripe to check error type
}

// Good: classify and wrap at the boundary
var (
    ErrPaymentDeclined = errors.New("payment declined")
    ErrGatewayTimeout  = errors.New("payment gateway timeout")
)

func (g *stripeGateway) Charge(ctx context.Context, req ChargeRequest) error {
    _, err := charge.New(...)
    if err == nil {
        return nil
    }

    var stripeErr *stripe.Error
    if errors.As(err, &stripeErr) {
        switch stripeErr.Code {
        case stripe.ErrorCodeCardDeclined:
            return fmt.Errorf("charge %s: %w", req.ID, ErrPaymentDeclined)
        case stripe.ErrorCodeRateLimit:
            return fmt.Errorf("charge %s: %w", req.ID, ErrRetryable)
        default:
            return fmt.Errorf("charge %s: stripe error %s: %w", req.ID, stripeErr.Code, err)
        }
    }

    if ctx.Err() != nil {
        return fmt.Errorf("charge %s: %w", req.ID, ErrGatewayTimeout)
    }
    return fmt.Errorf("charge %s: %w", req.ID, err)
}
```

### Retryable vs Permanent Error Classification

When calling external services, callers need to know whether to retry. Use a sentinel or interface:

```go
var ErrRetryable = errors.New("retryable")

// Wrap retryable errors so callers can check:
// if errors.Is(err, ErrRetryable) { retry }
func classifyHTTPError(statusCode int, err error) error {
    switch {
    case statusCode == 429, statusCode >= 500:
        return fmt.Errorf("%w: %w", ErrRetryable, err) // Go 1.20+ multi-wrap
    default:
        return err // permanent failure, do not retry
    }
}
```

### Gin Centralized Error Middleware

```go
func ErrorMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        c.Next()

        if len(c.Errors) == 0 {
            return
        }

        err := c.Errors.Last().Err
        log.Error("unhandled error", "error", err)

        var ve *ValidationError
        switch {
        case errors.As(err, &ve):
            c.JSON(http.StatusBadRequest, gin.H{"error": ve.Error()})
        case errors.Is(err, ErrNotFound):
            c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
        case errors.Is(err, ErrConflict):
            c.JSON(http.StatusConflict, gin.H{"error": "conflict"})
        case errors.Is(err, ErrInvalidTransition):
            c.JSON(http.StatusUnprocessableEntity, gin.H{"error": "invalid state transition"})
        case errors.Is(err, ErrGatewayTimeout):
            c.JSON(http.StatusServiceUnavailable, gin.H{"error": "service temporarily unavailable"})
        default:
            c.JSON(http.StatusInternalServerError, gin.H{"error": "internal server error"})
        }
    }
}
```

## Edge Cases

- **nil error wrapping**: `fmt.Errorf("context: %w", nil)` returns a non-nil error with text "context: <nil>" - always check `if err != nil` before wrapping
- **errors.Is on nil**: `errors.Is(nil, ErrNotFound)` returns false, which is correct - no guard needed
- **Multiple wrapping**: wrapping with `%w` twice in the same format string (Go 1.20+) creates a multi-error; use `errors.Is` / `errors.As` which traverse all wrapped errors
- **Unwrap loop**: custom error types implementing `Unwrap() error` must not create cycles - an infinite unwrap chain will hang `errors.Is` / `errors.As`
- **Third-party errors without Error interface**: some libraries return error-like values that don't implement `error`. Check the library's documentation and use type assertions at the boundary

## Output Format

```
## Error Design

### Sentinel Errors
| Error | Package | Used By |
|-------|---------|---------|
| ErrNotFound | domain | repo, service |

### Custom Error Types
| Type | Fields | Used When |
|------|--------|-----------|
| ValidationError | Field, Message | request validation |

### Error Mapping Chain
| Layer | Input Error | Output | HTTP Status |
|-------|-------------|--------|-------------|
| Repository | sql.ErrNoRows | ErrNotFound | - |
| Service | ErrNotFound | ErrNotFound (wrapped) | - |
| Handler | ErrNotFound | 404 JSON response | 404 |

### External Error Classification
| External Error | Domain Error | Retryable? |
|----------------|-------------|------------|
| {api error} | {domain error} | {yes/no} |
```

## Avoid

- Discarding errors with `_`
- Using panic for flow control or expected conditions
- String matching on error messages
- Logging and returning at the same layer
- Leaking database or internal error details to HTTP clients
- Leaking third-party library error types into the domain layer
- Returning generic `errors.New("failed")` without context
