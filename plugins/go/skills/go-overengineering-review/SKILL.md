---
name: go-overengineering-review
description: Go necessity review - binding/service guards duplicating GORM/DB, defensive nil after non-nil constructors, single-impl interfaces at the impl.
metadata:
  category: backend
  tags: [go, gin, gorm, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a Go diff that adds `binding:` / `validate:` tags, defensive nil checks, interfaces, or new abstractions
- Catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK name, `gorm:"not null"`, `uniqueIndex`, `binding:` tag, framework guarantee, or compile-time contract.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present. Cite the cost in the `Cost:` field. Triggers:
    - Extra SELECT in a hot path
    - Silent error swallow via `if err != nil { return nil }`
    - Single-impl interface declared at the implementation
    - Naked `go fn()` wrapping a sequential call (no `errgroup` / `WaitGroup` / queue submission)
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. See `Avoid` for the canonical exceptions.

## Patterns

### Category 1: Redundant validation vs GORM / DB constraints

Validation stack: **Gin `binding:` tag (via `ShouldBindJSON`) -> service guard -> GORM column tag -> DB schema**. Binding returns 400 before the handler runs; DB is authoritative.

#### Manual presence check after `ShouldBindJSON` with `binding:"required"`

```go
// Bad - binding:"required,gt=0" already rejected CustomerID == 0
if err := c.ShouldBindJSON(&req); err != nil { ... }
if req.CustomerID == 0 {                      // dead
    c.JSON(400, gin.H{"error": "customer_id required"})
    return
}
```

#### Manual unique-check before `db.Create`

`[High]` - races (two concurrent requests both pass the SELECT) and adds a query per write; the unique index decides anyway.

```go
// Bad
var existing User
if err := db.Where("email = ?", req.Email).First(&existing).Error; err == nil {
    return ErrEmailTaken
}
if err := db.Create(&User{Email: req.Email}).Error; err != nil { return err }

// Good - let the unique index decide; translate at the catch site
if err := db.Create(&User{Email: req.Email}).Error; err != nil {
    var pgErr *pgconn.PgError
    if errors.As(err, &pgErr) && pgErr.Code == "23505" { return ErrEmailTaken }
    return fmt.Errorf("create user: %w", err)
}
```

#### Service-layer presence guard duplicating the binding tag + `gorm:"not null"`

```go
// Bad - the column is gorm:"not null"; binding:"gt=0" already enforced presence;
// no non-HTTP write path. The service guard adds nothing.
func (s *OrderService) Create(ctx context.Context, customerID, total int64) error {
    if customerID <= 0 { return errors.New("customer_id required") }   // dead
    return s.repo.Create(ctx, &Order{CustomerID: customerID, Total: total})
}
```

Justified when a non-HTTP write path (Asynq job, cron, gRPC) reaches the service without going through Gin binding.

### Category 2: Defensive code for impossible states

The compiler, `errors.Is` / `errors.As`, and `context.Context` propagation provide guarantees. Re-checking them adds noise and can hide real bugs.

#### Nil check on a non-nil-returning constructor

```go
// Bad - NewOrderService cannot return nil
func NewOrderService(repo OrderRepository) *OrderService { return &OrderService{repo: repo} }

svc := NewOrderService(repo)
if svc == nil { log.Fatal("nil service") }    // unreachable
```

Legitimate when the constructor returns `(T, error)` and the caller hasn't checked the error.

#### `if err != nil { return nil }` silently swallowing the error

`[High]`. The function reports success on failure - one of the worst Go anti-patterns.

```go
// Bad
order, err := s.repo.Find(ctx, id)
if err != nil { return nil, nil }              // swallows the error, reports "not found"
return order, nil

// Good
if err != nil { return nil, fmt.Errorf("fulfill order %d: %w", id, err) }
```

#### `recover()` in business code

```go
// Bad - swallows panics that should surface; Gin's Recovery() middleware already catches them
func (s *OrderService) Fulfill(ctx context.Context, id int64) (err error) {
    defer func() { if r := recover(); r != nil { err = fmt.Errorf("panic: %v", r) } }()
    // ...
}
```

`recover()` is legitimate in framework / middleware code (Gin's `Recovery()`). In business code, panics indicate programmer bugs; let them surface.

### Category 3: Premature abstraction

#### Single-impl interface declared at the implementation side

`[High]` when the interface lives in the same package as its only implementer and no test mock exists. The Go idiom is "accept interfaces, return structs" - the interface belongs to the **consumer**.

```go
// Bad - interface and only implementer in repository; no test mock; no second impl
package repository

type OrderRepository interface {
    Find(ctx context.Context, id int64) (*Order, error)
}
type gormOrderRepository struct{ db *gorm.DB }
func (r *gormOrderRepository) Find(ctx context.Context, id int64) (*Order, error) { /* ... */ }

// Good - export the struct; the consumer declares an interface it needs
package repository
type OrderRepository struct{ db *gorm.DB }
func (r *OrderRepository) Find(ctx context.Context, id int64) (*Order, error) { /* ... */ }

package service
type orderRepo interface {                     // idiomatic - consumer-side
    Find(ctx context.Context, id int64) (*Order, error)
}
```

Justified when: a test mock (`gomock` / `moq`) lives next to the trait, two or more concrete impls exist, or the trait is a documented public API.

#### `BaseRepository` struct embedded by one or two children

```go
// Bad - template-method scaffold via embedding for two consumers
type BaseRepository struct{ db *gorm.DB }
type OrderRepository struct{ BaseRepository }
type UserRepository  struct{ BaseRepository }
```

Inline until 3+ repositories share genuine cross-cutting behavior.

#### Custom `Result[T]` where `(T, error)` suffices

```go
// Bad - generic wrapper duplicating Go's idiomatic (T, error)
type Result[T any] struct { Value T; Err error }
func (s *OrderService) Find(ctx context.Context, id int64) Result[*Order] { ... }

// Good - the idiomatic shape
func (s *OrderService) Find(ctx context.Context, id int64) (*Order, error) { ... }
```

#### Naked `go fn()` wrapping a sequential call

`[High]` - the wrapper produces a goroutine leak (no `WaitGroup`, no error channel, no `errgroup`).

```go
// Bad - no concurrency benefit; goroutine leaks if Notify panics; error swallowed
if err := s.repo.Save(ctx, order); err != nil { return err }
go s.notifier.Notify(order)                    // fire-and-forget

// Good - call directly, or submit to a worker pool / errgroup / Asynq with retry
if err := s.notifier.Notify(ctx, order); err != nil { return fmt.Errorf("notify: %w", err) }
```

Justified when the call is genuinely async and dispatched to a worker pool / Asynq queue with retry semantics - that's not a wrapping goroutine, it's a queue submission.

#### Speculative struct tags / config keys

Flag `envconfig` keys declared (and validated) but never read. Confirm with a repo-wide grep before flagging - background jobs and CLI commands often read indirectly.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `if req.CustomerID == 0` after `binding:"required,gt=0"`}
- Redundant because: {FK name | `gorm:"not null"` | `uniqueIndex` | `binding:` tag | non-nil constructor return | framework guarantee}
- Cost: {extra SELECT per save | silent error swallow | single-impl interface at implementation | goroutine leak} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging `binding:` tags on Gin request structs - that layer owns user-facing 400 responses
- Flagging interfaces declared at the consumer (`service` package declaring an interface it needs) - that's idiomatic Go. Only flag interfaces declared at the implementation side
- Flagging `if err != nil { return err }` - that's idiomatic. The smell is `return nil` (silent swallow)
- Flagging `gorm:"not null;uniqueIndex"` tag entries - those are GORM's schema definition
- Recommending removal of `recover()` in Gin middleware - that's the legitimate use
- Flagging `context.Context` first-parameter idiom
- Confusing "duplicated" with "defense in depth across layers" when multiple write paths exist (HTTP + Asynq + cron + CLI)
- Flagging a goroutine that submits to a worker pool / Asynq / errgroup - tracked async dispatch, not a naked `go fn()`
