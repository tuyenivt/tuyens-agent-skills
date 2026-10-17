---
name: backend-coding-standards
description: Review code for language-appropriate naming, layering, dependency injection, and anti-patterns. Adapts to the detected stack.
metadata:
  category: governance
  tags: [standards, conventions, style, multi-stack]
user-invocable: false
---

# Coding Standards

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Code review for naming, layering, and framework conventions
- Writing new code to match established project patterns
- Onboarding to understand a codebase's style expectations

## Rules

- Apply the detected language's identifier convention (camelCase, snake_case, PascalCase) and its file-naming convention (snake_case, kebab-case where the ecosystem uses it). Do not mix styles within a codebase. Where an established codebase-wide convention already differs from the language norm, consistency with the codebase wins - new code matches what is there. A convention is established when the project's instruction file documents it or the majority of files in the module follow it; a single file that deviates is a violation, not a convention. Raise an established divergence once, as `[Recommend]`, anchored on the instruction file or the module's first occurrence rather than the file that followed it. In polyglot repos, each file follows its own language's convention; the `**Stack:**` line names the primary stack.
- Short names in small scopes; descriptive names in larger scopes.
- One responsibility per file/class/module. Functions/methods over 50 lines are decomposed (80 where idiomatic boilerplate inflates counts - Java's type ceremony, Go's `if err != nil` blocks), with one exemption: a flat exhaustive dispatch (uniform short branches, no nesting, no shared state) is one responsibility at any length, and splitting it scatters a table across functions.
- Files live in directories matching their architectural role (no service classes in `controllers/`).
- Presentation layer stays thin - business logic belongs in the service or domain layer.
- Responses use DTOs / serializers / response structs, never data-layer entities.
- Use the framework's dependency-injection container where one exists (Spring, NestJS, ASP.NET Core, Laravel); otherwise inject dependencies explicitly through constructors or closures rather than reaching for package-level singletons. Depend on abstractions where the framework supports it.
- No emojis in code, logs, comments, commit messages, or documentation.
- Idiomatic error handling for the language: no bare or blanket catches that swallow errors, no discarded error returns, no `panic` for recoverable failures in request paths (net/http and Gin's `Recovery` recover it per request, so the client sees a dropped connection or a bare 500; a panic in a goroutine the handler spawned terminates the process), and no process-terminating exits (`os.Exit`, `log.Fatal`, `System.exit`) in request paths; in exception-based languages, raise typed exceptions that a defined boundary handles. When the codebase's own precedents conflict (a named error class in one module, a builtin in another), the more specific precedent is the convention to follow.
- No magic numbers - extract named constants. Sample data in a demo or test entry point and unit divisors that are the domain's standard (`/100` for percent, `/10_000` for basis points) are not magic numbers.
- No dead code - delete it.
- Comments explain why, not what.
- A rule the project's instruction file states (money is never a float) is checked like these Rules and cited by its file and line.

Transaction-boundary and dispatch-ordering defects (I/O inside a transaction, a job enqueued before commit, a relay marking work done before publishing) are `backend-transaction-patterns`' findings, not anti-patterns here.

## Patterns

### Naming finding (specific, fixable)

```
# Bad - vague style comment
- [Recommend] The naming could be more consistent across the codebase.

# Good - specific finding with fix
- [Recommend] src/handlers/user_handler.go:12 - Initialism cased as a word: `getUserById` in a Go codebase that writes `ID` elsewhere
  - Rule: Go initialisms keep one case throughout - `ID`/`URL` mid-name or exported, `id`/`url` when they lead an unexported name
  - Fix: Rename to `getUserByID` (the identifier is unexported; keep its visibility)
```

### Anti-pattern categories to scan

After stack-detect, check for ecosystem-appropriate instances of:

- **Concurrency**: deprecated or unsafe primitives for the detected runtime
- **Testing**: deprecated test utilities the framework has superseded
- **Performance**: connection pool misconfiguration, N+1 queries, missing query bounds
- **Security**: disabled framework safeguards, exposed internals, missing input validation, a missing authorization or ownership check
- **Structural**: circular imports, package structure that contradicts the documented architecture

When `Language` is `unknown`, infer the language from file extensions and syntax and mark the Stack line `(inferred)`; when inference fails too (config or data files, an unrecognised extension), the Stack line is `unknown` and only the language-agnostic rules apply. Write `<language> (no framework detected)` when stack-detect reports a known `Language` and `Framework: unknown`. A stack is unfamiliar when the review cannot name its naming convention, DI idiom, and error-handling idiom with confidence - the reviewer's knowledge, not the marker table, is the test. When the stack is unfamiliar, apply the language-agnostic rules (responsibility, layering, DTO boundaries, no swallowed or discarded errors, magic numbers, dead code, no emojis, comments explain why) and recommend the user verify naming and DI conventions against the framework's docs and linters.

## Output Format

When authoring, apply Rules as constraints and emit the code alone - the block below is the review deliverable, never a self-assessment of code just written. When asked for the conventions themselves (onboarding, a brief for a new module), emit `## Coding Standards Conventions`, the Stack line, and one bullet per convention naming what establishes it: the instruction file and line when documented, otherwise the module and its file count (`src/handlers/ - 14 of 16 files`). When reviewing, emit the block with every finding - never trim to the highest-signal ones; within each section order `[Must]` first. A defect whose cause and symptom sit in two files anchors as `cause.ext:line -> symptom.ext:line`. The same rule broken the same way at several sites is one finding anchored at the first, the others on its `Sites:` line. Consuming workflows parse this structure.

```
## Coding Standards Findings

**Stack:** {language / framework | <language> (no framework detected) | <language> (inferred) | unknown}{ - unfamiliar stack, verify against framework docs}

### Violations                                  {when at least one violation}

- [Must | Recommend] {file:line} - {description}
  - Rule: {the rule violated; for a rule the instruction file states, its file:line (CLAUDE.md:12)}
  - Fix: {concrete correction}
  - Sites: {every further file:line}       {when the same rule is broken the same way at several sites}
  - Assumption: {the assumption made and the question for the author}       {only for an ambiguous case}

### Anti-Patterns Detected                      {when the scan found entries, or could not run}

- [Must | Recommend] {file:line} - {anti-pattern name}: {impact}
  - Rule: {the scan category and the ecosystem rule or idiom it breaks}
  - Fix: {concrete correction}
  - Sites: {every further file:line}       {when the same rule is broken the same way at several sites}
  - Assumption: {the assumption made and the question for the author}       {only for an ambiguous case}

### No Issues Found                             {instead of both sections above, when Violations is empty and the scan ran and found none: one sentence}
```

**Intent:**

- **[Must]**: Breaks correctness, security, or layering at runtime - entity exposed in API, business logic in the presentation layer, swallowed or discarded errors, a process exit or panic in a request path, a disabled security feature
- **[Recommend]**: Structural drift that compounds - a god class or over-long function, mixed naming, magic numbers, dead code, what-not-why comments, emojis, package-level singletons instead of injection, a file placed in the wrong layer directory with its logic still in the right layer
- **[Recommend]**: Ambiguous case where the rule may or may not apply - fill the `Assumption:` line

A defect matching both a Rule and an anti-pattern category is one entry under Violations with its intent label; Anti-Patterns holds only ecosystem-scan findings no Rule covers, graded by the same test: `[Must]` when it fails or exposes something today (an unbounded query on a request path, a lock that cannot hold across processes), `[Recommend]` when it is latent. When the scan could not run, keep the Anti-Patterns section with the single line `not assessed - <reason>` (`{stack} anti-patterns require ecosystem knowledge; verify with the stack's linter` for an unfamiliar stack; the actual reason otherwise) and never emit `No Issues Found` - an omitted section reads as a clean result, which is a stronger claim than "not checked."

## Avoid

- Applying one language's naming or idioms to a file in a different language
