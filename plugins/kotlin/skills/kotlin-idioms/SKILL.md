---
name: kotlin-idioms
description: "Kotlin idioms for Spring Boot: data classes, null safety, extension functions, scope functions (let/apply/run/also), sealed classes, inline value classes, and Kotlin-Java interop patterns."
user-invocable: false
---

Cover:

1. Data class for DTOs, regular class for JPA entities, sealed class for error hierarchies
2. Null safety: T? over Optional, ?. safe call, ?: elvis, !! only when guaranteed
3. Scope functions: let (transform nullable), apply (configure object), run (compute + return), also (side effect)
4. Sealed classes for restricted hierarchies: sealed class ApiResult { data class Success(...), data class Error(...) }
5. Inline value classes for type-safe wrappers: @JvmInline value class OrderId(val value: Long)
6. Kotlin-Java interop: @JvmStatic, @JvmField, @JvmOverloads for framework compatibility
7. Collection operations: prefer Kotlin stdlib (map, filter, groupBy) over Java streams
8. Anti-patterns: ❌ Optional in Kotlin, ❌ data class for JPA entities, ❌ !! everywhere,
   ❌ Java-style getter/setter (use properties)
