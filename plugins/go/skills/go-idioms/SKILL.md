---
name: go-idioms
description: "Go language idioms: iota enums, struct tags, functional options, generics, type-safe IDs, embedding, defer rules, Stringer/Marshaler, go:embed."
metadata:
  category: backend
  tags: [go, idioms, generics, options, iota, embedding, defer, struct-tags]
user-invocable: false
---

# Go Idioms

> Load `Use skill: stack-detect` first. This skill reads `Framework` for the tag-key rule below; the Go version is the `go` directive in `go.mod` (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). Baseline: Go 1.25+ (`cmp.Ordered`, builtin `min`/`max`, `log/slog`, `testing/synctest`); the struct-tag examples carry GORM and sqlx tags because the plugin targets them; the tag-key rule covers Gin. Error idioms live in `go-error-handling`; concurrency idioms in `go-concurrency`. This skill owns language-level shape decisions for writing new code.

## When to Use

- Implementing a new package, type, or constructor and deciding which Go idiom fits
- Reviewing whether code reads as Go vs Java/Python translated into Go
- Choosing between generics, interface, and concrete impl; between `type` alias and new type; between embedding and composition

## Rules

- `iota` for enum-like state groups, zero value reserved for unknown/unset; pair with a string form - `stringer` with `-trimprefix` / `-linecomment` when the identifier or a line comment is the wire token (readable on slog's `TextHandler`; the `JSONHandler` needs `MarshalText`), hand-written off one `[...]string` table when the same token must round-trip through DB, JSON and logs
- Functional options (`WithTimeout(d)`-style) for constructors with 3 or more optional knobs; a positional `Config` struct for 0-2
- Generics where they collapse repetitive type-switched code; never for one or two concrete types
- New type (`type UserID int64`) over `type` alias when the boundary matters (compile-time prevents passing `OrderID` where `UserID` is expected)
- Receivers: pointer when a method mutates, the type holds a lock, or copying is costly; value for small immutable types. A mixed set is correct when the pointer methods are the decoders (`Scan`, `UnmarshalJSON`, `UnmarshalText`) - `String`/`Value`/`MarshalJSON`/`LogValue` must stay on the value, or a stored value loses them (`slog.Any(v)` and `json.Marshal(v)` see only the value's method set)
- No `I` prefix or `Impl` suffix - the interface takes the plain noun (`Store`), the implementation says what it is (`pgStore`)
- Constructors return concrete types; consumers define the interfaces they need ("accept interfaces, return structs")
- Never store `context.Context` in a struct field - contexts are call-scoped and structs outlive them; pass ctx as the first parameter
- Embedding for forwarding (`io.Reader` into a wrapper), not for inheritance; if you wanted overrides, use composition + method dispatch
- Implement the interface each boundary consumes (`String`, `MarshalText`/`UnmarshalText`, `Value`/`Scan`, `LogValue`) for types that cross logs, JSON, or the DB - see the boundary table
- `go:embed` for SQL migrations, templates, static assets - ship them in the binary; HTML goes through `html/template`, `text/template` is for non-HTML output only
- Exported identifiers have a doc comment starting with the identifier name; unexported only when non-obvious
- `log/slog` in new code over the legacy `log` package and third-party loggers; a module already standardized on logrus or zap is reported as its convention, not flagged line by line

## Patterns

### `iota` enums + Stringer

```go
type OrderStatus int

const (
    // StatusUnknown is the zero value: a missing column never reads as a valid state.
    StatusUnknown OrderStatus = iota // unknown
    StatusPending                    // pending
    StatusPaid                       // paid
    StatusShipped                    // shipped
    StatusCancelled                  // cancelled
)

//go:generate stringer -type=OrderStatus -linecomment
// -linecomment makes String() return the comment token ("pending"); -trimprefix=Status would return "Pending".
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

Crossing DB, JSON and logs with one vocabulary - a hand-written table when the token must parse back:

```go
var statusNames = [...]string{"unknown", "pending", "paid", "shipped", "cancelled"}

func (s OrderStatus) String() string {
    if int(s) < 0 || int(s) >= len(statusNames) { return fmt.Sprintf("OrderStatus(%d)", int(s)) }
    return statusNames[s]
}
func (s OrderStatus) valid() bool { return int(s) > 0 && int(s) < len(statusNames) } // zero is never a wire value
func (s OrderStatus) MarshalText() ([]byte, error) { // encoding/json and slog's JSONHandler both honour TextMarshaler
    if !s.valid() { return nil, fmt.Errorf("invalid OrderStatus %d", int(s)) } // json.Marshal of an unset status fails loudly
    return []byte(statusNames[s]), nil
}
func (s *OrderStatus) UnmarshalText(b []byte) error { return s.parse(string(b)) }
func (s OrderStatus) Value() (driver.Value, error) {
    if !s.valid() { return nil, fmt.Errorf("invalid OrderStatus %d", int(s)) }
    return statusNames[s], nil
}
func (s *OrderStatus) Scan(v any) error {
    switch t := v.(type) {
    case string: return s.parse(t)
    case []byte: return s.parse(string(t))
    }
    return fmt.Errorf("OrderStatus: cannot scan %T", v)
}
func (s *OrderStatus) parse(tok string) error {
    for i, n := range statusNames {
        if n == tok && i != 0 { *s = OrderStatus(i); return nil }
    }
    return fmt.Errorf("unknown OrderStatus %q", tok)
}
```

`encoding/json` never calls `Value`/`Scan`, and `database/sql` never calls `MarshalText` - each boundary needs its own method, all reading one table so the vocabulary cannot drift. Reject out-of-range values in `Value()` and `MarshalText()` rather than persisting `OrderStatus(9)`.

### Struct tag conventions

One struct often carries tags for multiple consumers - keep the order consistent so they scan top-to-bottom:

```go
type User struct {
    ID        int64  `json:"id"          gorm:"primaryKey"             db:"id"`
    Email     string `json:"email"       gorm:"uniqueIndex;not null"   db:"email"`
    Password  string `json:"-"           gorm:"not null"               db:"password"`
    CreatedAt time.Time `json:"created_at" gorm:"autoCreateTime"     db:"created_at"`
}
```

- `json:"-"` to drop a field from JSON (passwords, internal IDs)
- `json:",omitempty"` only when the zero value is semantically "absent" (often surprising for `int`; it never omits a struct such as `time.Time` - `omitzero`, Go 1.24+, does)
- `mapstructure:` is read by `viper`, `envconfig:` by `envconfig` - different keys, so a config field needs both when both load it; never decode a request body into a domain model (see `go-security-patterns`)
- Tag key follows the consumer: Gin `ShouldBind*` reads `binding:`; a standalone `validator.New()` reads `validate:`; Echo's `Bind` reads `json:`/`query:`/`param:` and never validates - validation runs only when the handler calls `c.Validate(v)` against a configured `e.Validator`. The wrong key compiles and silently skips validation

### Functional options

```go
type Server struct {
    addr     string
    timeout  time.Duration
    workers  int
    logger   *slog.Logger
    now      func() time.Time // clock injection: a func field when tests only need Now(); a Clock interface when they also need After/Ticker
}

type Option func(*Server)

func WithTimeout(d time.Duration) Option { return func(s *Server) { s.timeout = d } }
func WithWorkers(n int) Option           { return func(s *Server) { s.workers = n } }
func WithClock(now func() time.Time) Option { return func(s *Server) { s.now = now } }
func WithLogger(l *slog.Logger) Option {
    return func(s *Server) {
        if l == nil { return } // nil-guard: keep the default
        s.logger = l
    }
}

func New(addr string, opts ...Option) (*Server, error) {
    if addr == "" { return nil, errors.New("addr required") }
    s := &Server{addr: addr, timeout: 30 * time.Second, workers: 4, logger: slog.Default(), now: time.Now}
    for _, opt := range opts { opt(s) }
    if s.workers < 1 { return nil, fmt.Errorf("workers must be >= 1, got %d", s.workers) } // validate after options
    return s, nil
}

srv, err := New(":8080", WithTimeout(5*time.Second), WithLogger(customLog))
```

Three or more optional knobs with sensible defaults. For 0-2 knobs a `Config` struct is simpler. Required args stay positional; constructors return `error` for invalid required args and for option values that fail validation, instead of panicking.

### Generics: when they help

Threshold: 3+ real instantiations, or an `interface{}` + type switch the generic removes. One or two instantiations is the Bad case (`Result[T]`, `Repo[T]` alike - any generic type or function); a family of near-identical types (11 repositories over one storage API) is the Good case even with no type switch in sight. One instantiation visible in the files under review is a `[Recommend]` that names the file to check for others.

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

Constraints worth knowing: `comparable` for map keys / equality, `cmp.Ordered` (Go 1.21+) for anything `<` works on - with the builtin `min`/`max` there is no reason to hand-roll either:

```go
func Clamp[T cmp.Ordered](v, lo, hi T) T { return min(max(v, lo), hi) }
```

If your generic function calls a method, use an interface constraint - generics aren't a substitute for interfaces, but a constraint lets the caller pass a `[]User` directly and get a `User` back, where an interface parameter would force a `[]Identifiable` conversion and return the interface:

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

`type UserID = int64` (with `=`) is an **alias**, identical to `int64` - no safety; an alias of a struct or interface (`type IOrderRepository = orderRepository`) is the same non-type and the same finding. Drop the `=` to create a new type whose underlying type is the storage type (`int64` for a serial key, `string` for an external id such as Stripe's `re_...`). When an existing package already exposes the alias, convert once at the boundary (`refund.OrderID(order.ID)`) rather than spreading the alias into new code.

### Embedding vs composition

Embedding forwards the embedded type's methods to the outer type:

```go
type loggingStore struct {
    Store            // forwards Get, List, Delete untouched
    log *slog.Logger
}

func (l *loggingStore) Put(ctx context.Context, k string, v []byte) error { // the one method it changes
    l.log.InfoContext(ctx, "put", "key", k)
    return l.Store.Put(ctx, k, v)
}
```

Embedding is **forwarding**, not inheritance - there is no virtual dispatch. A method the wrapper declares itself (`Put` above) replaces the promoted one for the wrapper's callers only: an embedded method calling a sibling method calls the embedded one, not the wrapper's, and a forwarded method that returns the embedded type (`*gorm.DB` chains) escapes the wrapper entirely. If you wanted overrides that every path honours, use composition (hold the dependency as a field) and expose only the methods you mean to.

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
func DoWork(paths []string) error {
    for _, p := range paths {
        f, err := os.Open(p)
        if err != nil { return err }
        defer f.Close() // all stay open until DoWork returns
        process(f)
    }
    return nil
}

// Good - wrap each iteration so defer scopes to the inner func
for _, p := range paths {
    if err := func() error {
        f, err := os.Open(p)
        if err != nil { return err }
        defer f.Close()
        return process(f)
    }(); err != nil {
        return err
    }
}
```

LIFO order: last `defer` runs first.

### Stringer / Marshaler / Unmarshaler

When a type crosses a boundary (log, JSON, DB), implement the interface the consumer uses - it's the only way to control rendering at the call site:

| Boundary | Interface |
|----------|-----------|
| `fmt.Println` / `%v`, slog `TextHandler` (`Any` values, after trying `TextMarshaler`) | `String() string` |
| `slog.LogValuer` (redaction, every handler) | `LogValue() slog.Value` |
| `encoding/json`, slog `JSONHandler` (`Any` values) | `MarshalText`/`UnmarshalText`, or `MarshalJSON`/`UnmarshalJSON` for non-string shapes |
| `database/sql` | `Value() (driver.Value, error)` / `Scan(v any) error` |
| `encoding.TextMarshaler` consumers (env, YAML, query strings) | `MarshalText` / `UnmarshalText` |

slog's `JSONHandler` encodes `Any` values with `encoding/json`, so an `iota` enum logs as a number unless it has `MarshalText` - `String()` alone makes logs readable only on the `TextHandler`.

`LogValue()` on a secret-holding type redacts it from every `slog` call without per-call effort - and `String()` covers `fmt`, which otherwise prints a named basic type's underlying value verbatim:

```go
type Token string
func (t Token) LogValue() slog.Value   { return slog.StringValue("[REDACTED]") }
func (t Token) String() string         { return "[REDACTED]" }
func (t Token) GoString() string       { return "[REDACTED]" } // %#v bypasses String()
func (t Token) MarshalJSON() ([]byte, error) { return []byte(`"[REDACTED]"`), nil } // if it can reach a response or config dump
```

A `String()` that formats its own receiver (`fmt.Sprintf("%+v", s)`) recurses until the stack overflows - format the fields, never the receiver.

### `go:embed`

```go
import "embed" // regular import for embed.FS; the blank `import _ "embed"` form only works for string / []byte

//go:embed migrations/*.sql
var migrationsFS embed.FS

//go:embed templates/email/welcome.html
var welcomeTemplate string
```

The embedded file lives beside the package that parses it (`internal/notify/templates/*.html`), never in a shared top-level directory another package reaches into. Parse embedded templates in a constructor that returns `error`, not a package-level `template.Must` - init-time work turns a malformed template into a panic the caller cannot handle; an existing `template.Must` on an embedded file is a `[Recommend]` (the panic is a deliberate fail-fast at start), an `init()` that opens connections or starts goroutines is a `[Must]`. HTML output parses with `html/template` (contextual escaping); `text/template` on HTML is an XSS vector.

Ships SQL migrations, HTML/email templates, OpenAPI specs, default config inside the binary. Eliminates "where is the file in prod" class of bugs.

## Output Format

Implementation or written recommendation - one row per shape decision, ordered as the concerns were asked:

```
| Concern | Decision | Rationale | Rejected |
|---------|----------|-----------|----------|
| Status field | iota, zero = unknown, one `[...]string` table behind String/MarshalText/Value/Scan | DB, JSON and log crossing share one vocabulary | stringer alone (no Value/Scan, no parse-back) |
| ID types | `type UserID int64`, `type OrderID int64` | compile-time swap detection | alias (no safety) |
| Server config | functional options | 4 optional knobs with defaults | Config struct (3+ knobs read worse positionally) |
| Embedded file | `go:embed migrations/*.sql` | ship in binary | - |
```

`Rejected` names the alternative and why it loses, or `-` when none was in play. Code for a decision goes below the table under a `### <Concern>` heading repeating the row's `Concern` text exactly, in the same order as the rows. A secret-holding field changes type in place (`APIKey Token`), not behind a wrapper struct. An implementation handed existing code that violates a Rule emits `## Findings` first, then the table.

Review - one block per non-idiomatic shape. A convention the input establishes (logrus throughout, `validate:` tags) is one line above the first finding: `Convention: <what>, kept`. Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Code: {one-line citation}
- Non-idiomatic because: {what the Go idiom is}
- Recommendation: {concrete edit}
```

`[Must]` when the shape is a live defect - it loses data, crashes on a request path (a start-time fail-fast is not a crash), leaks a secret, makes a code path unreachable, or holds a resource past its scope (a `context.Context` field, a `defer` in a loop over many files). Those are examples, not the whole set: judge by consequence, not by matching the list. `[Recommend]` when the shape only costs clarity or future flexibility (an alias, a constructor returning an interface, a one-instantiation generic); a zero value that is a live state is `[Must]` when a missing or unset column then reads as that state. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not (a missing doc comment cites the identifier); a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then by start line. One shape at several sites, in one file or many, is one heading citing the first site, with the rest named on the `Code:` line. A defect in a file the input did not name is still a block, its heading suffixed `_(out of scope)_`. A defect this skill does not own (an unparameterised query, `InsecureSkipVerify`, a sentinel built as a function, an ignored error) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Non-idiomatic because:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`. With no findings, emit `No non-idiomatic shapes found.`

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
- A hand-written `String()` when `//go:generate stringer -type=T` (run by `go generate ./...`) produces the same tokens and no other boundary (`Value`/`Scan`, `MarshalText`) needs the table
- `time.Sleep` for synchronization - channels or `testing/synctest`
- `panic` in library or service code (only `main` for unrecoverable startup); constructors return `error` for bad required args
- Legacy `log` package in new code - use `log/slog`
