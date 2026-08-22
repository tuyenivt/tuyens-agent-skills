---
name: go-idioms
description: "Go language idioms: iota enums, struct tags, functional options, generics, type-safe IDs, embedding, defer rules, Stringer/Marshaler, go:embed."
metadata:
  category: backend
  tags: [go, idioms, generics, options, iota, embedding, defer, struct-tags]
user-invocable: false
---

# Go Idioms

> Load `Use skill: stack-detect` first. Error idioms live in `go-error-handling`; concurrency idioms in `go-concurrency`. This skill owns language-level shape decisions for writing new code.

## When to Use

- Implementing a new package, type, or constructor and deciding which Go idiom fits
- Reviewing whether code reads as Go vs Java/Python translated into Go
- Choosing between generics, interface, and concrete impl; between `type` alias and new type; between embedding and composition

## Rules

- `iota` for enum-like state groups; pair with a `String()` method (stringer-generated) so logs are readable
- Functional options (`WithTimeout(d)`-style) for constructors with > 2 optional knobs; positional struct config for the rest
- Generics where they collapse repetitive type-switched code; never to abstract a single concrete type
- New type (`type UserID int64`) over `type` alias when the boundary matters (compile-time prevents passing `OrderID` where `UserID` is expected)
- Receivers: pointer when a method mutates, the type holds a lock, or copying is costly; value for small immutable types. A mixed set is correct when the pointer methods are the decoders (`Scan`, `UnmarshalJSON`, `UnmarshalText`) - `String`/`Value`/`MarshalJSON`/`LogValue` must stay on the value, or a stored value loses them (`slog.Any(v)` and `json.Marshal(v)` see only the value's method set)
- No `I` prefix or `Impl` suffix - the interface takes the plain noun (`Store`), the implementation says what it is (`pgStore`)
- Constructors return concrete types; consumers define the interfaces they need ("accept interfaces, return structs")
- Never store `context.Context` in a struct field - contexts are call-scoped and structs outlive them; pass ctx as the first parameter
- Embedding for forwarding (`io.Reader` into a wrapper), not for inheritance; if you wanted overrides, use composition + method dispatch
- Implement `String()`, `MarshalJSON`, `UnmarshalJSON`, `Value`/`Scan` (`database/sql`) for types that cross boundaries (logs, JSON, DB)
- `go:embed` for SQL migrations, templates, static assets - ship them in the binary
- Exported identifiers have a doc comment starting with the identifier name; unexported only when non-obvious
- Prefer `log/slog` over the legacy `log` package for structured output and `LogValue`-based redaction

## Patterns

### `iota` enums + Stringer

```go
type OrderStatus int

const (
    StatusPending OrderStatus = iota
    StatusPaid
    StatusShipped
    StatusCancelled
)

//go:generate stringer -type=OrderStatus
// stringer generates: func (i OrderStatus) String() string { ... }
```

For bit flags, `1 << iota`:

```go
type Perm uint
const (
    PermRead Perm = 1 << iota
    PermWrite
    PermAdmin
)
```

DB / JSON crossing: implement `Value()` and `Scan()` so the enum survives the boundary:

```go
func (s OrderStatus) Value() (driver.Value, error) { return s.String(), nil }
func (s *OrderStatus) Scan(v any) error            { /* parse string -> enum */ }
```

`stringer` emits the Go identifier (`StatusPending`). When the DB or JSON token differs (`pending`), hand-write `String()` off a `[...]string` table and parse back through the same table - one vocabulary, no drift. Never ship an enum without a string form.

Reserve the zero value for unknown/unset so a missing column does not read as a valid state, and reject out-of-range values in `Value()` rather than persisting `OrderStatus(9)`.

### Struct tag conventions

One struct often carries tags for multiple consumers - keep the order consistent so they scan top-to-bottom:

```go
type User struct {
    ID        int64  `json:"id"          gorm:"primaryKey"             db:"id"`
    Email     string `json:"email"       gorm:"uniqueIndex;not null"   db:"email"     validate:"required,email"`
    Password  string `json:"-"           gorm:"not null"               db:"password"`
    CreatedAt time.Time `json:"created_at" gorm:"autoCreateTime"     db:"created_at"`
}
```

- `json:"-"` to drop a field from JSON (passwords, internal IDs)
- `json:",omitempty"` only when the zero value is semantically "absent" (often surprising for `int`)
- `mapstructure:` is read by `viper`, `envconfig:` by `envconfig` - different keys, so a config field needs both when both load it; do not use `mapstructure.Decode(req.Body, &domain)` (see `go-security-patterns`)
- Tag key follows the consumer: Gin binds with `binding:`, the standalone validator reads `validate:` - the wrong key silently skips validation

### Functional options

```go
type Server struct {
    addr     string
    timeout  time.Duration
    logger   *slog.Logger
}

type Option func(*Server)

func WithTimeout(d time.Duration) Option { return func(s *Server) { s.timeout = d } }
func WithLogger(l *slog.Logger) Option {
    return func(s *Server) {
        if l == nil { return } // nil-guard: keep the default
        s.logger = l
    }
}

func New(addr string, opts ...Option) (*Server, error) {
    if addr == "" { return nil, errors.New("addr required") }
    s := &Server{addr: addr, timeout: 30 * time.Second, logger: slog.Default()}
    for _, opt := range opts { opt(s) }
    return s, nil
}

srv, err := New(":8080", WithTimeout(5*time.Second), WithLogger(customLog))
```

Use when there are more than 2-3 optional parameters and defaults make sense. For 1-2 knobs, a `Config` struct is simpler. Required args stay positional; constructors return `error` for invalid required args instead of panicking.

### Generics: when they help

Threshold: 3+ real instantiations, or an `interface{}` + type switch the generic removes. One instantiation is the Bad case; a family of near-identical types (11 repositories over one storage API) is the Good case even with no type switch in sight.

```go
// Bad - generics for a single concrete type (no callers benefit)
type Repo[T any] struct{ db *gorm.DB }
func (r *Repo[T]) Find(id int64) (*T, error) { ... }
// only ever instantiated as Repo[Order]

// Good - generic helper used across many types
func MapSlice[T, U any](in []T, f func(T) U) []U {
    out := make([]U, len(in))
    for i, v := range in { out[i] = f(v) }
    return out
}
ids := MapSlice(users, func(u User) int64 { return u.ID })
```

Constraints worth knowing: `comparable` for map keys / equality, `~T` (underlying type) for "any type whose underlying is T":

```go
type Ordered interface { ~int | ~int64 | ~float64 | ~string }
func Max[T Ordered](a, b T) T { if a > b { return a }; return b }
```

If your generic function calls a method, use an interface constraint - generics aren't a substitute for interfaces, but they let an interface be used as the element type of a slice without losing the concrete type:

```go
type Identifiable interface{ GetID() string }

// Bad - caller must convert []User to []Identifiable at every call
func FindByID(items []Identifiable, id string) (Identifiable, bool)

// Good - constraint reuses the interface, return type stays concrete
func FindByID[T Identifiable](items []T, id string) (T, bool) {
    for _, x := range items { if x.GetID() == id { return x, true } }
    var zero T
    return zero, false
}
```

### Type-safe IDs

```go
// Bad - any int64 can be passed; mixing OrderID and UserID compiles
func Charge(orderID, userID int64) error
Charge(userID, orderID) // silently wrong

// Good - new types catch the swap at compile time
type OrderID int64
type UserID  int64
func Charge(orderID OrderID, userID UserID) error
```

`type UserID = int64` (with `=`) is an **alias**, identical to `int64` - no safety. Drop the `=` to create a new type.

### Embedding vs composition

Embedding forwards methods of the embedded type to the outer:

```go
type LoggingDB struct {
    *gorm.DB // forwards Find, Create, ... to outer
}

func (l *LoggingDB) Find(out any, where ...any) *gorm.DB {
    start := time.Now()
    res := l.DB.Find(out, where...)
    slog.Info("db.find", "dur", time.Since(start))
    return res
}
```

Embedding is **forwarding**, not inheritance - there is no virtual dispatch. An embedded method calling a sibling method calls the embedded one, not an outer override. If you wanted that, use composition (hold the dependency as a field) instead.

### `defer` rules

Arguments to a deferred call evaluate **at the defer statement**, but the call runs at function return:

```go
i := 1
defer fmt.Println("deferred:", i) // prints "deferred: 1"
i = 2
```

`for { defer x }` is a common bug - defers accumulate until the enclosing **function** returns, not the loop iteration:

```go
// Bad - file handles leak until DoWork returns
func DoWork(paths []string) {
    for _, p := range paths {
        f, _ := os.Open(p)
        defer f.Close() // all stay open until DoWork returns
        process(f)
    }
}

// Good - wrap each iteration so defer scopes to the inner func
for _, p := range paths {
    func() {
        f, _ := os.Open(p)
        defer f.Close()
        process(f)
    }()
}
```

LIFO order: last `defer` runs first.

### Stringer / Marshaler / Unmarshaler

When a type crosses a boundary (log, JSON, DB), implement the interface the consumer uses - it's the only way to control rendering at the call site:

| Boundary | Interface |
|----------|-----------|
| `fmt.Println` / `slog` (via `%v`) | `String() string` |
| `slog.LogValuer` (redaction) | `LogValue() slog.Value` |
| `encoding/json` | `MarshalJSON() ([]byte, error)` / `UnmarshalJSON([]byte) error` |
| `database/sql` | `Value() (driver.Value, error)` / `Scan(v any) error` |
| `encoding.TextMarshaler` (env, YAML, query strings) | `MarshalText` / `UnmarshalText` |

`LogValue()` on a secret-holding type redacts it from every `slog` call without per-call effort:

```go
type Token string
func (t Token) LogValue() slog.Value { return slog.StringValue("[REDACTED]") }
```

`slog` prefers `LogValue()`; `fmt` and `%v` still call `String()`. A secret type implements both - omitting `String()` does not protect a named basic type, because `%v` then prints the underlying value verbatim. Add `MarshalJSON` when the type can reach a response body or a config dump.

A `String()` that formats its own receiver (`fmt.Sprintf("%+v", s)`) recurses until the stack overflows - format the fields, never the receiver.

### `go:embed`

```go
import "embed" // regular import for embed.FS; the blank `import _ "embed"` form only works for string / []byte

//go:embed migrations/*.sql
var migrationsFS embed.FS

//go:embed templates/email/welcome.html
var welcomeTemplate string
```

Parse embedded templates in a constructor that returns `error`, not a package-level `template.Must` - init-time work turns a malformed template into a panic the caller cannot handle.

Ships SQL migrations, HTML/email templates, OpenAPI specs, default config inside the binary. Eliminates "where is the file in prod" class of bugs.

## Output Format

Implementation or written recommendation - one row per shape decision, ordered as the concerns were asked:

```
| Concern | Decision | Rationale | Rejected |
|---------|----------|-----------|----------|
| Status field | iota + hand-written String + Value/Scan | DB and log crossing; wire token != identifier | stringer (emits `StatusPending`) |
| ID types | `type UserID int64`, `type OrderID int64` | compile-time swap detection | alias (no safety) |
| Server config | functional options | 4 optional knobs | Config struct |
| Embedded file | `go:embed migrations/*.sql` | ship in binary | - |
```

`Rejected` names the alternative and why it loses, or `-` when none was in play. Code for a decision goes below the table under a `### <Concern>` heading, in the same order as the rows.

Review - one block per non-idiomatic shape, ordered `[Must]` before `[Recommend]` then by line. Every finding carries exactly one label:

```
### [Must] file:line

- Code: {one-line citation}
- Non-idiomatic because: {what the Go idiom is}
- Recommendation: {concrete edit}
```

`[Must]` when the shape is a live defect - it loses data, crashes, leaks a secret, makes a code path unreachable, or holds a resource past its scope. Those are examples, not the whole set: judge by consequence, not by matching the list. `[Recommend]` when the shape only costs clarity or future flexibility. A shape recurring at several sites is one block citing the first site and naming the rest in `Code:`. With no findings, emit `No non-idiomatic shapes found.`

## Avoid

- `type FooID = int64` (alias) when you want type safety - use `type FooID int64`
- Generics with one concrete instantiation - inline the type
- Functional options for 0-2 knobs - struct config is simpler
- `defer f.Close()` inside `for` - wrap in an inner func
- Embedding to "inherit" - Go has no virtual dispatch; use composition
- `init()` doing real work - constructor injection is the Go answer
- `context.Context` as a struct field - pass it per call
- Constructors returning same-package interfaces - return the struct; interfaces belong to consumers
- `interface{}` / `any` to silence a type error - find the actual type
- A duration as a bare `int` - `time.Duration` carries the unit
- Stringer hand-written when `go generate stringer -type=...` exists
- `time.Sleep` for synchronization - channels or `testing/synctest`
- `panic` in library or service code (only `main` for unrecoverable startup); constructors return `error` for bad required args
- Legacy `log` package in new code - use `log/slog`
