---
name: task-kotlin-debug
description: "Debug Kotlin + Spring Boot errors. Handles Kotlin-specific issues: null safety violations, coroutine stack traces, MockK setup errors, and Kotlin-JPA plugin configuration problems."
agent: kotlin-architect
---

STEP 1 - INTAKE: stack trace, test failure, build error

STEP 2 - CLASSIFY (Kotlin-specific errors on top of Java ones):

- KotlinNullPointerException → !! on null, trace the null
- UninitializedPropertyAccessException → lateinit not initialized, check DI
- IllegalStateException: "Flow exception transparency" → exception in Flow collect
- kotlin-jpa "No default constructor" → missing kotlin-jpa plugin
- kotlin-allopen "Entity class is final" → missing allopen plugin config
- "Suspension functions can only be called within coroutine body" → missing suspend/runBlocking
- MockK "no answer found" → missing every { } stub
- For all Java/Spring errors: same classification as Java plugin's task-spring-debug

STEP 3 - LOCATE

STEP 4 - ROOT CAUSE

STEP 5 - FIX

STEP 6 - PREVENTION

OUTPUT: 🐛 → 📍 → 🔧 → 🛡️

## Success Criteria

A well-executed debug session passes all of these. Use as a self-check before presenting the fix.

### Completeness

- [ ] Error is classified before any code is read or fix proposed (Kotlin-specific errors checked first)
- [ ] Root cause references the specific source file and line
- [ ] A concrete before/after code fix is provided - no vague suggestions
- [ ] A prevention step is included

### Correctness

- [ ] The fix addresses the root cause, not the symptom
- [ ] Confidence level is stated - LOW lists what additional info would help
- [ ] The fix is minimal - no unrelated refactoring
- [ ] Kotlin idioms preserved - no `!!` introduced as a fix, no Java-style synchronized blocks

### Staff-Level Signal

- [ ] The "why" is explained - a developer understands how to avoid this class of Kotlin error
- [ ] For coroutine issues, the fix addresses the coroutine scope or context - not just the exception
- [ ] For kotlin-jpa / allopen plugin errors, the Gradle plugin configuration is checked as the root cause
- [ ] For MockK errors, the stub is corrected with proper `coEvery` / `coVerify` usage for suspend functions
