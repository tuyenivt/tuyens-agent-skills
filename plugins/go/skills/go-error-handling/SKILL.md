---
name: go-error-handling
description: "Go error patterns: explicit returns, wrapping with %w, sentinel errors, custom error types, errors.Is/As, Gin error middleware. Never swallow errors."
metadata:
  category: backend
  tags: [go, error-handling, sentinel-errors, gin, middleware]
user-invocable: false
---

# Go Error Handling

## When to Use

- Designing error types for a new package or service
- Reviewing error handling in a code review
- Debugging unexpected error behavior (swallowed errors, lost context)
- Implementing centralized error handling in a Gin HTTP service

## Rules

- Always check errors - never use `_` to discard an error return
- Wrap errors with context using `fmt.Errorf("context: %w", err)` - preserve the chain
- Use `errors.Is` and `errors.As` for checking, never string matching
- Log OR return an error at each layer - never both (log-and-return duplicates noise)
- Panic only for programmer bugs (nil dereference of required dependency at startup) - never for business logic
- Map errors at the boundary: repo errors -> service errors -> HTTP status codes

## Patterns

### Sentinel Errors

Use for expected, checkable conditions:

```go
var (
    ErrNotFound   = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
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
        default:
            c.JSON(http.StatusInternalServerError, gin.H{"error": "internal server error"})
        }
    }
}
```

## Anti-Patterns

```go
// Bad: swallowing the error
result, _ := doSomething()

// Bad: log AND return (double-reporting)
if err != nil {
    log.Error("failed", err)
    return err
}

// Bad: string matching (breaks with refactoring)
if strings.Contains(err.Error(), "not found") { ... }

// Bad: panic for expected business conditions
if user == nil {
    panic("user not found")
}

// Bad: returning generic errors without context
return errors.New("failed")
```

## Edge Cases

- **nil error wrapping**: `fmt.Errorf("context: %w", nil)` returns a non-nil error with text "context: <nil>" - always check `if err != nil` before wrapping
- **errors.Is on nil**: `errors.Is(nil, ErrNotFound)` returns false, which is correct - no guard needed
- **Multiple wrapping**: wrapping with `%w` twice in the same format string (Go 1.20+) creates a multi-error; use `errors.Is` / `errors.As` which traverse all wrapped errors
- **Unwrap loop**: custom error types implementing `Unwrap() error` must not create cycles - an infinite unwrap chain will hang `errors.Is` / `errors.As`

## Avoid

- Discarding errors with `_`
- Using panic for flow control or expected conditions
- String matching on error messages
- Logging and returning at the same layer
- Leaking database or internal error details to HTTP clients
