---
name: task-laravel-debug
description: Debug Laravel errors: classify exceptions, find root cause, minimal before/after fixes for Eloquent, controllers, jobs, migrations, Pest failures.
agent: php-architect
metadata:
  category: backend
  tags: [php, laravel, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

## When to Use

- Debugging Laravel errors from stack traces or messages
- Classifying Eloquent, controller, queue, migration, or test failures
- Tracing data-flow issues (value sent but stored as null)
- NOT for: production incident triage (use `/task-oncall-start`), perf profiling, infra/deploy issues

## Edge Cases

- **Vendor-only stack trace**: error originates from misuse of a package; check the last application-code frame that invoked the vendor method.
- **No stack trace**: check `storage/logs/laravel.log`, `failed_jobs` table, and `php artisan schedule:list`.
- **Production-only**: diff `config/app.php`, `APP_ENV`, `APP_DEBUG`, config/route caching between envs.
- **Intermittent**: likely race condition or connection pool exhaustion; check `DB_POOL` and traffic correlation.
- **No Xdebug**: use `dd()`, `dump()`, `Log::debug()`, `php artisan tinker`, or Laravel Telescope in dev.

## Debugging Tools

| Tool                     | Use When                                          | Command / Access                   |
| ------------------------ | ------------------------------------------------- | ---------------------------------- |
| `php artisan tinker`     | Interactive REPL - test queries, models, services | `php artisan tinker`               |
| Laravel Telescope        | Inspect requests, queries, jobs, events in dev    | `/telescope` route                 |
| Laravel Debugbar         | In-browser query count, timing, N+1 detection     | Auto-injects into HTML responses   |
| `storage/logs/`          | Application logs, stack traces                    | `tail -f storage/logs/laravel.log` |
| `failed_jobs` table      | Queue job failure history                         | `php artisan queue:failed`         |
| `php artisan route:list` | Verify route registration and middleware          | `php artisan route:list`           |

## Workflow

STEP 1 - INTAKE: Use skill: `stack-detect` to confirm Laravel. Ask for the full stack trace, the source file, and expected behavior. Identify the first application-code frame (skip `vendor/`) and read it.

**Partial input**: With only a description, search the codebase and ask clarifying questions. With only an error message, check `storage/logs/laravel.log` and match the classification table first.

**"No error, just wrong behavior"** (value missing in DB, email never arrives): reframe as boundary loss - at which layer does the value disappear? Trace: Form Request `rules()` -> `validated()` vs `all()` -> `$fillable` -> `casts()`/mutators -> `prepareForValidation()` -> DB column. Same shape for jobs: dispatch -> `afterCommit()` -> broker -> `handle()` -> side effect. Identify the lossy boundary before reading code.

STEP 2 - CLASSIFY:

Match the error to one category, then load the relevant atomic skill. Exception classes below omit the `Illuminate\` / `Symfony\Component\HttpKernel\Exception\` prefix.

### Eloquent / Database Errors

- `QueryException` `SQLSTATE[23000]` -> constraint violation (unique, FK, NOT NULL); column is in the message. Use skill: `laravel-eloquent-patterns`.
- `QueryException` `SQLSTATE[HY000]` -> connection/pool issue; check `config/database.php`.
- `ModelNotFoundException` -> `findOrFail()` on missing record; check route model binding or query.
- `MassAssignmentException` -> field not in `$fillable`. Use skill: `laravel-security-patterns`.
- N+1 (Debugbar or `preventLazyLoading`) -> missing `with()` eager load. Use skill: `laravel-eloquent-patterns` (section 2).
- `RelationNotFoundException` -> relationship method missing or misspelled.

### Controller / HTTP Errors

- `ValidationException` (422) -> form request rejected input; read `rules()`. Use skill: `laravel-api-patterns`.
- `AuthorizationException` (403) -> policy denied; check policy method and user state. Use skill: `laravel-security-patterns`.
- `NotFoundHttpException` (404) -> route or model binding missing; run `php artisan route:list`. Use skill: `laravel-api-patterns`.
- `MethodNotAllowedHttpException` (405) -> wrong HTTP method; check `routes/api.php`.
- `TokenMismatchException` (419) -> CSRF mismatch; check session driver and middleware.

### Data Flow Errors (No Exception)

- Value sent but stored as null -> check `$fillable`, `validated()` vs `all()`, cast/mutator. Use skill: `laravel-security-patterns`.
- Unexpected value transformation -> check `casts()`, accessor/mutator, `prepareForValidation()`. Use skill: `laravel-eloquent-patterns`.
- Related data not saving -> check relationship method type and FK column convention. Use skill: `laravel-eloquent-patterns`.

### Queue / Job Errors

- `MaxAttemptsExceededException` -> retries exhausted; check `$tries`, `$backoff`, original exception. Use skill: `laravel-queue-patterns`.
- Silent failure -> check `failed_jobs` and the job's `failed()` method.
- Stale data -> job dispatched before DB commit; check `afterCommit()`. Use skill: `laravel-queue-patterns`.
- `TimeoutExceededException` -> exceeded `$timeout`; check blocking operations in `handle()`.

### Migration Errors

- `SQLSTATE[42S01]` table exists -> migration re-run without rollback; check `php artisan migrate:status`.
- `SQLSTATE[42S22]` column not found -> order issue or missing column; check migration timestamps.
- Lock timeout -> DDL on large table. Use skill: `laravel-migration-safety`.

### Artisan / Config Errors

- `Target class [X] does not exist` -> missing service-provider binding or controller namespace; check `app/Providers/` and route namespaces.
- `Call to undefined method` -> wrong method, missing trait, or wrong import.
- Config caching -> `env()` called outside config files; run `php artisan config:clear`. Use skill: `laravel-security-patterns` (section 9).

### Test Errors

- `RefreshDatabase` not applied -> missing trait on test or `Pest.php` config. Use skill: `laravel-testing-patterns`.
- `Mockery\Exception\InvalidCountException` -> mock expectation unmet; check `shouldReceive` count.
- `assertDatabaseHas` failure -> wrong table, column, or value format.

STEP 3 - LOCATE: Read stack trace top-down, find the first application-code frame, open that file, and trace the data path controller -> service -> model. Use skill: `laravel-service-patterns` for service-layer flow. For queue errors, check whether the job was dispatched inside a DB transaction.

STEP 4 - ROOT CAUSE: Explain **why**, not just what. State confidence: **HIGH** (reproduced/obvious), **MEDIUM** (pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH] MassAssignmentException at Order.php:12 because
Order::create($request->all()) at OrderController.php:25 passes `is_admin`
which is not in $fillable. Use $request->validated() instead.
```

STEP 5 - FIX: Provide minimal before/after addressing root cause, not symptoms.

```php
// BEFORE (mass assignment risk)
$order = Order::create($request->all());

// AFTER (only validated fields)
$order = Order::create($request->validated());
```

STEP 6 - PREVENTION: Add one guard so this class of error cannot recur - Pest test exercising the path, model config (`preventSilentlyDiscardingAttributes`, `preventLazyLoading`) in dev, PHPStan/Psalm rule, or Form Request on the endpoint.

## Avoid

- `$guarded = []` to "fix" MassAssignmentException (security hole)
- `try/catch` that silently swallows exceptions
- `APP_DEBUG=true` in production
- CSRF `$except` for non-webhook routes
- `sync` queue driver as a "fix" for queue failures

## Output Format

```
## Error Classification
Category: {Eloquent/Database | Controller/HTTP | Queue/Job | Migration | Artisan/Config | Test | Data Flow}
Error Type: [specific exception or symptom]
## Root Cause
Confidence: {HIGH | MEDIUM | LOW}
File: [file:line]
[Why the error occurs - cause, not symptom]
## Fix
[Before/after code blocks - minimal change addressing root cause]
## Affected Files
[Files modified by the fix]
## Prevention
Type: {test | model-config | static-analysis | form-request}
[Specific guard to prevent recurrence]
```

## Self-Check

- [ ] STEP 1: Stack trace or error description obtained; Laravel confirmed via `stack-detect`
- [ ] STEP 2: Error classified into a category; relevant atomic skill loaded
- [ ] STEP 3: Failing source file and function located; data path traced through layers
- [ ] STEP 4: Root cause explained with confidence level and file:line reference
- [ ] STEP 5: Minimal before/after fix provided addressing root cause, not symptom
- [ ] STEP 6: Prevention guard added (Pest test, model config, or static analysis rule)
