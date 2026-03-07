---
name: task-kotlin-debug
description: "Debug Kotlin + Spring Boot errors. Handles Kotlin-specific issues: null safety violations, coroutine stack traces, MockK setup errors, and Kotlin-JPA plugin configuration problems."
agent: kotlin-architect
metadata:
  category: backend
  tags: [kotlin, spring-boot, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
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

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Kotlin idioms preserved - no `!!` introduced, no Java-style synchronized blocks
- [ ] Prevention step included
- [ ] For coroutines: scope/context addressed; for kotlin-jpa: Gradle plugin config checked; for MockK: `coEvery`/`coVerify` used correctly

> Run `/task-skill-feedback` if output needed significant correction.
