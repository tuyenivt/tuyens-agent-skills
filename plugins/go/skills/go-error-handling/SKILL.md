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

- Check every error; never discard with `_`. Best-effort work still logs its error - `_ =` is reserved for a value already handled
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

When callers read fields off the error. Identity alone (`errors.Is`) means a sentinel - a field-less struct type is overspecification, and one sentinel per distinct handling decision beats one per distinct message.

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

Error strings: lowercase, no trailing punctuation. Wrap context names the operation (`"GetUser id=%d"`), never "failed to ..." - the chain already implies failure and the prefix stutters when every layer adds it.

### Layer Mapping

Each layer wraps with its context; the handler maps to HTTP:

```go
// Repository: data access error
if notFound { return nil, fmt.Errorf("userRepo.Find id=%d: %w", id, ErrNotFound) }

// Service: adds its own context, sentinel preserved through the chain
if err != nil { return nil, fmt.Errorf("promote user %d: %w", id, err) }

// Handler: delegates to centralized middleware
if err != nil { c.Error(err); return }
```

### Wrapping External API Errors

Third-party SDK error types stop at the gateway; callers depend only on domain sentinels.

```go
var (
    ErrPaymentDeclined = errors.New("payment declined")
    ErrGatewayTimeout  = errors.New("payment gateway timeout")
    ErrGatewayFailure  = errors.New("payment gateway failure")
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
    if errors.Is(ctx.Err(), context.DeadlineExceeded) {
        return fmt.Errorf("charge %s: %w: %w", req.ID, ErrRetryable, ErrGatewayTimeout)
    }
    if ctx.Err() != nil { // Canceled: caller gave up - never retryable
        return fmt.Errorf("charge %s: %w", req.ID, ctx.Err())
    }
    // Unmatched: %v, not %w - wrapping keeps *stripe.Error matchable by every
    // caller, which is the leak this gateway exists to stop. The text survives for logs.
    return fmt.Errorf("charge %s: %w: %v", req.ID, ErrGatewayFailure, err)
}
```

### Code-Based SDK Errors

Not every dependency exposes a matchable type. Extract the code first, then map it:

```go
// gRPC - status.Code returns codes.Unknown for non-status errors, so it is safe as the discriminator
switch status.Code(err) {
case codes.NotFound:    return fmt.Errorf("%s: %w", op, ErrNotFound)
case codes.Unavailable: return fmt.Errorf("%s: %w: %w", op, ErrRetryable, ErrUpstreamDown)
}

// Postgres - SQLSTATE off the driver error
var pgErr *pgconn.PgError
if errors.As(err, &pgErr) && pgErr.Code == pgerrcode.UniqueViolation { // "23505"
    return fmt.Errorf("%s: %w", op, ErrConflict)
}
```

### Retryable Classification (multi-`%w`, Go 1.20+)

```go
// %w twice lets one error match two sentinels
return fmt.Errorf("%w: %w", ErrRetryable, cause)
// caller: if errors.Is(err, ErrRetryable) { retry }
```

Markers come first, the cause last. When the last `%w` is a domain sentinel rather than the original error, keep the cause with a trailing `%v` (`"%s: %w: %w: %v", op, ErrRetryable, ErrUpstreamDown, err`) - a chain of markers alone leaves the operator nothing to log.

### Aggregate Errors (`errors.Join`, Go 1.20+)

Collect-all semantics (batch items, multi-field validation, parallel results). Carry the item's identity in a typed wrapper so the aggregate can be decomposed without parsing text:

```go
type ItemError struct { ID string; Err error }
func (e *ItemError) Error() string { return fmt.Sprintf("record %s: %s", e.ID, e.Err) }
func (e *ItemError) Unwrap() error { return e.Err }

var errs []error
for _, rec := range records {
    if err := process(rec); err != nil {
        errs = append(errs, &ItemError{ID: rec.ID, Err: err})
    }
}
return errors.Join(errs...) // nil when errs is empty
```

`errors.Is`/`As` traverse the joined tree but stop at the **first** match - they answer "does this contain X", never "which items failed". Enumerating means walking both `Unwrap() []error` and `Unwrap() error` yourself.

**Collect-all or fail-fast:** keep going when the failure is scoped to the item (validation, not-found, conflict); abort when it is infrastructure-wide (connection lost, context cancelled, credentials revoked) - one of those means every remaining item fails identically. Mark the abort with its own sentinel so the caller can tell "500 bad rows" from "we stopped at row 12".

### Gin Centralized Error Middleware

```go
func ErrorMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        c.Next()
        if len(c.Errors) == 0 { return }

        err := c.Errors.Last().Err
        if c.Writer.Written() { // handler already responded - a second write corrupts the response
            slog.ErrorContext(c.Request.Context(), "error after response written", "err", err)
            return
        }

        status, msg := http.StatusInternalServerError, "internal server error"
        var ve *ValidationError
        switch {
        case errors.As(err, &ve):
            status, msg = http.StatusBadRequest, ve.Error()
        case errors.Is(err, ErrNotFound):
            status, msg = http.StatusNotFound, "not found"
        case errors.Is(err, ErrConflict):
            status, msg = http.StatusConflict, "conflict"
        case errors.Is(err, ErrGatewayTimeout):
            status, msg = http.StatusServiceUnavailable, "service temporarily unavailable"
        }
        if status >= 500 { // expected conditions (4xx) are not error-level noise
            slog.ErrorContext(c.Request.Context(), "request failed", "err", err)
        } else {
            slog.WarnContext(c.Request.Context(), "request rejected", "err", err)
        }
        c.JSON(status, gin.H{"error": msg})
    }
}
```

`gin.Recovery()` handles panics without touching `c.Errors`, so this middleware never sees them - a business panic reaches the client as Gin's generic 500. Return errors instead of panicking. A handler with partial-success semantics (batch import) writes its own multi-status response and does not call `c.Error` at all; one `c.Errors.Last()` cannot express "412 of 500 rows succeeded".

## Edge Cases

- `fmt.Errorf("ctx: %w", nil)` returns a non-nil error - guard before wrapping
- Custom error types must not create `Unwrap` cycles (`errors.Is` / `As` would hang)
- Some libraries return values that don't implement `error` - assert at the boundary

## Output Format

Emit the sections for the engagement, in this order:

| Engagement | Emits |
|------------|-------|
| Design / implementation | Sentinels, Custom Types, Layer Mapping, External Classification |
| Review | Findings, then Layer Mapping for the code under review |

```
## Error Design

### Sentinels
| Error | Declared In | Matched By |
|-------|-------------|------------|

### Custom Types
| Type | Fields | Used When |
|------|--------|-----------|

### Layer Mapping
| Layer | Input | Output | Surface Result |
|-------|-------|--------|----------------|

### External Classification
| External Error | Domain Error | Retryable? |
|----------------|--------------|------------|
```

Cell values: `Retryable?` is `Yes | No`. `Surface Result` is what the outermost caller sees on that path - an HTTP status, a worker decision (`Retry | Drop | DeadLetter`), or a CLI exit code; when a package serves several entry points, one row per entry point. `External Error` covers anything crossing into the package: third-party SDK, gRPC status, driver/SQLSTATE, `context` errors. A table with no rows emits `None.` rather than being dropped; a value the input does not supply is `unknown`.

Findings go under a `## Findings` heading, ordered `[Must]` first then by file and line. Every finding carries exactly one label:

```
## Findings

### [Must] file:line

- Defect: {the rule broken}
- Consequence: {what the caller or the operator loses}
- Fix: {concrete edit}
```

`[Must]` when the defect loses information the caller needs (severed chain, swallowed error, string-matched status), corrupts state, or reaches the client with internal detail; `[Recommend]` otherwise. Cite `file:line` when the input has line numbers, `file:<symbol>` when it does not.

## Avoid

- Discarding errors with `_`
- `panic` for flow control or expected conditions
- Logging and returning at the same layer
- Leaking DB / third-party error types past the gateway
- Generic `errors.New("failed")` with no context
