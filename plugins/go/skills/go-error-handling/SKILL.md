---
name: go-error-handling
description: "Go errors: explicit returns, %w wrapping, sentinels, custom types, errors.Is/As, Gin error middleware, retryable classification."
metadata:
  category: backend
  tags: [go, error-handling, sentinel-errors, gin, middleware]
user-invocable: false
---

# Go Error Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing error types for a new package or service
- Reviewing error handling
- Implementing centralized error handling in a Gin HTTP service
- Wrapping third-party API errors into domain errors

## Rules

- Check every error; never discard with `_`
- Wrap with `fmt.Errorf("context: %w", err)` to preserve the chain
- Use `errors.Is` / `errors.As`; never string-match error messages
- Log OR return at each layer, never both
- Panic only for programmer bugs at startup, never for business logic
- Map errors at layer boundaries: repo -> service -> HTTP status
- Classify external API errors as retryable or permanent

## Patterns

### Sentinel Errors

For expected, checkable conditions:

```go
var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrConflict     = errors.New("conflict")
)

if errors.Is(err, ErrNotFound) { /* handle */ }
```

### Custom Error Types

When callers need structured data:

```go
type ValidationError struct {
    Field, Message string
}
func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

var ve *ValidationError
if errors.As(err, &ve) { /* ve.Field available */ }
```

### Error Wrapping

```go
// Bad - loses call site
if err != nil { return nil, err }

// Good
if err != nil { return nil, fmt.Errorf("GetUser id=%d: %w", id, err) }
```

### Layer Mapping

Each layer wraps with its context; the handler maps to HTTP:

```go
// Repository: data access error
if notFound { return nil, fmt.Errorf("userRepo.Find id=%d: %w", id, ErrNotFound) }

// Service: business error (still wraps the sentinel)
if errors.Is(err, ErrNotFound) {
    return nil, fmt.Errorf("user %d does not exist: %w", id, ErrNotFound)
}

// Handler: delegates to centralized middleware
if err != nil { c.Error(err); return }
```

### Wrapping External API Errors

Third-party SDK error types stop at the gateway; callers depend only on domain sentinels.

```go
var (
    ErrPaymentDeclined = errors.New("payment declined")
    ErrGatewayTimeout  = errors.New("payment gateway timeout")
    ErrRetryable       = errors.New("retryable")
)

func (g *stripeGateway) Charge(ctx context.Context, req ChargeRequest) error {
    _, err := charge.New(...)
    if err == nil { return nil }

    var stripeErr *stripe.Error
    if errors.As(err, &stripeErr) {
        switch stripeErr.Code {
        case stripe.ErrorCodeCardDeclined:
            return fmt.Errorf("charge %s: %w", req.ID, ErrPaymentDeclined)
        case stripe.ErrorCodeRateLimit:
            return fmt.Errorf("charge %s: %w", req.ID, ErrRetryable)
        }
    }
    if ctx.Err() != nil {
        return fmt.Errorf("charge %s: %w", req.ID, ErrGatewayTimeout)
    }
    return fmt.Errorf("charge %s: %w", req.ID, err)
}
```

### Retryable Classification (multi-`%w`, Go 1.20+)

```go
// %w twice lets one error match two sentinels
return fmt.Errorf("%w: %w", ErrRetryable, cause)
// caller: if errors.Is(err, ErrRetryable) { retry }
```

### Gin Centralized Error Middleware

```go
func ErrorMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        c.Next()
        if len(c.Errors) == 0 { return }

        err := c.Errors.Last().Err
        slog.Error("unhandled error", "err", err)

        var ve *ValidationError
        switch {
        case errors.As(err, &ve):
            c.JSON(http.StatusBadRequest, gin.H{"error": ve.Error()})
        case errors.Is(err, ErrNotFound):
            c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
        case errors.Is(err, ErrConflict):
            c.JSON(http.StatusConflict, gin.H{"error": "conflict"})
        case errors.Is(err, ErrGatewayTimeout):
            c.JSON(http.StatusServiceUnavailable, gin.H{"error": "service temporarily unavailable"})
        default:
            c.JSON(http.StatusInternalServerError, gin.H{"error": "internal server error"})
        }
    }
}
```

## Edge Cases

- `fmt.Errorf("ctx: %w", nil)` returns a non-nil error - guard before wrapping
- Custom error types must not create `Unwrap` cycles (`errors.Is` / `As` would hang)
- Some libraries return values that don't implement `error` - assert at the boundary

## Output Format

```
## Error Design

### Sentinels
| Error | Package | Used By |

### Custom Types
| Type | Fields | Used When |

### Layer Mapping
| Layer | Input | Output | HTTP |

### External Classification
| External Error | Domain Error | Retryable? |
```

## Avoid

- Discarding errors with `_`
- `panic` for flow control or expected conditions
- Logging and returning at the same layer
- Leaking DB / third-party error types past the gateway
- Generic `errors.New("failed")` with no context
