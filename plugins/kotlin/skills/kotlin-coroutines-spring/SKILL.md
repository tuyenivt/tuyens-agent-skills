---
name: kotlin-coroutines-spring
description: "Kotlin coroutines with Spring Boot 3.5+: suspend functions in services, Flow for streaming, coroutine-aware transactions, Virtual Thread interop, and structured concurrency."
user-invocable: false
---

Cover:

1. suspend fun in @Service: Spring automatically handles coroutine context
2. Flow<T> for streaming results from repository
3. Coroutine-aware transactions: @Transactional works with suspend functions in Spring Boot 3.5+
4. Dispatchers: Dispatchers.Default for CPU work, Virtual Threads handle I/O automatically
5. Structured concurrency: coroutineScope { launch { ... } } for parallel operations within a request
6. WebClient with coroutines: awaitBody<T>(), awaitExchange()
7. Testing coroutines: runTest { }, TestDispatcher, turbine for Flow testing
8. Anti-patterns: ❌ GlobalScope.launch, ❌ Dispatchers.IO with Virtual Threads (redundant),
   ❌ runBlocking in request handlers, ❌ blocking calls inside coroutines
