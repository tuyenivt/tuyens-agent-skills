---
name: kotlin-testing-patterns
description: "Kotlin testing with MockK, kotest, and Spring test integration. Mocking Kotlin classes (no open requirement), coroutine testing, Kotlin-friendly assertions."
user-invocable: false
---

Cover:

1. MOCKK (preferred over Mockito for Kotlin):
   - mockk<MyService>() — works with final classes (no need for open)
   - every { service.findOrder(any()) } returns order
   - coEvery { service.findOrder(any()) } returns order (for suspend functions)
   - verify { service.save(any()) }
   - slot<Order>() to capture arguments

2. KOTEST (optional, alternative to JUnit 5):
   - StringSpec, FunSpec, BehaviorSpec styles
   - Property-based testing with Arb generators
   - Kotest + Spring extension for @SpringBootTest integration

3. SPRING TEST WITH KOTLIN:
   - Same test slices as Java plugin (@DataJpaTest, @WebMvcTest, etc.)
   - WebTestClient with Kotlin DSL: client.get().uri("/api/orders").exchange().expectStatus().isOk
   - @MockkBean instead of @MockBean for Kotlin mocking

4. COROUTINE TESTING:
   - runTest { } for suspend function tests
   - TestDispatcher for controlling coroutine timing
   - turbine library for Flow testing: flow.test { awaitItem() shouldBe expected }

5. Anti-patterns: ❌ Mockito with final Kotlin classes (use MockK),
   ❌ JUnit assertions in Kotlin (use kotest matchers or assertk), ❌ forgetting coEvery for suspend mocks
