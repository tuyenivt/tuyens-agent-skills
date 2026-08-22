---
name: spring-test-integration
description: "Spring Boot 3.5 test slices and Testcontainers: @DataJpaTest, @WebMvcTest, @JsonTest, @ServiceConnection, Awaitility, security."
metadata:
  category: backend
  tags: [testing, spring-boot, testcontainers, integration-test, test-slices]
user-invocable: false
---

# Spring Integration Testing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing the right Spring test slice
- Setting up Testcontainers with `@ServiceConnection`
- Async / Virtual Thread-safe tests
- Reusable fixtures and security tests

## Rules

- Match slice to layer (see table); avoid `@SpringBootTest` when a slice fits
- Testcontainers with the production DB engine - H2 silently passes Postgres-only syntax (JSONB, partial indexes, `ON CONFLICT`, window functions)
- `@MockitoBean` (Boot 3.4+), not `@MockBean`
- Mockito strict stubbing (default in JUnit 5 extension); fix `UnnecessaryStubbingException` by deleting the stub, not by `lenient()`
- AssertJ over `assertEquals`; `@ActiveProfiles("test")` always explicit
- No `Thread.sleep()` in async tests - use Awaitility
- No `@DirtiesContext` - redesign or use `@Sql` cleanup
- Context-cache fragmentation is the dominant cost in a slow suite, ahead of containers. Every distinct combination of `@MockitoBean`, `@TestPropertySource` and `@DynamicPropertySource` is a separate cache key and a separate context build - declare them on a shared base class so classes collapse onto a handful of contexts, and count the target number before restructuring

## Slice Selection

| Layer                   | Choice                                              |
| ----------------------- | --------------------------------------------------- |
| Repository              | `@DataJpaTest` + Testcontainers Postgres            |
| Controller              | `@WebMvcTest` + MockMvc, `@MockitoBean` services    |
| JSON (de)serialization  | `@JsonTest` + `JacksonTester`                       |
| Service (pure logic)    | Plain JUnit 5 + Mockito                             |
| Service (Spring wiring) | `@SpringBootTest` + `@MockitoBean` externals        |
| Full integration        | `@SpringBootTest` + Testcontainers + WebTestClient  |

"Spring wiring" means the proxy behavior itself is under test (tx rollback, `@PreAuthorize`, listener firing). Injectable collaborators (`ApplicationEventPublisher`, repos) alone don't make it Spring wiring - use plain JUnit. A commit-gated path (`AFTER_COMMIT` listener, outbox relay) is Spring wiring *and* needs the container, because the commit has to be real: `@SpringBootTest` + Testcontainers, no `@Transactional`.

## Patterns

### `@DataJpaTest` with `@ServiceConnection`

`@ServiceConnection` (Boot 3.1+) auto-wires the container to Spring's datasource - no `@DynamicPropertySource` glue. The same annotation works on `KafkaContainer`, `RabbitMQContainer`, and Redis (`GenericContainer<>("redis:7")`) - every pattern below generalizes beyond Postgres.

```java
@Testcontainers @DataJpaTest
class OrderRepositoryTest {
    @Container @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderRepository orderRepository;

    @Test
    void findsByStatus() {
        orderRepository.save(OrderFixtures.anOrder(PAID));
        assertThat(orderRepository.findByStatus(PAID)).hasSize(1);
    }
}
```

`@DataJpaTest` defaults to in-memory DB; `@ServiceConnection` on the container overrides that (no `@AutoConfigureTestDatabase(replace = NONE)` needed). It runs Flyway/Liquibase by default, so tests exercise the real schema - required for JSONB columns, generated columns, or anything `ddl-auto` cannot reproduce. Disable migrations only deliberately (`spring.flyway.enabled=false` + `ddl-auto: create-drop`).

### `@WebMvcTest` controller slice

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean OrderService orderService;

    @Test
    void returnsOrder() throws Exception {
        when(orderService.findById(1L)).thenReturn(OrderFixtures.anOrderDto());
        mockMvc.perform(get("/api/orders/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PAID"));
    }
}
```

### `@JsonTest` for serialization contracts

```java
@JsonTest
class OrderDtoJsonTest {
    @Autowired JacksonTester<OrderDto> json;

    @Test
    void serializesAmount() throws Exception {
        // BigDecimal serializes as a JSON number by default; assert StringValue only
        // when the field declares @JsonFormat(shape = STRING) (money-as-string contract)
        assertThat(json.write(new OrderDto(1L, 1L, PAID, new BigDecimal("99.99"))))
            .extractingJsonPathNumberValue("$.totalAmount").isEqualTo(99.99);
    }
}
```

### Plain JUnit for service logic

```java
@ExtendWith(MockitoExtension.class)   // bare mock() gets no strict stubbing - only the extension does
class OrderServiceTest {
    @Mock OrderRepository repo;
    @Mock PaymentGateway gateway;
    @InjectMocks OrderService service;

    @Test
    void completesOrder() {
        when(repo.findById(1L)).thenReturn(Optional.of(OrderFixtures.anOrder(PENDING)));
        when(gateway.charge(any())).thenReturn(PaymentResult.success());

        assertThat(service.complete(1L).status()).isEqualTo(PAID);
        verify(repo).save(any(Order.class));
    }
}
```

### Singleton containers across the suite

`@Container` stops/starts per test class - the main cost in multi-class suites. For one container per JVM, start it manually in a base class and skip the `@Testcontainers`/`@Container` lifecycle entirely; multi-class suites always extend this base (the per-class `@Container` form above is for isolated examples):

```java
public abstract class AbstractIntegrationTest {
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine").withReuse(true);
    static { POSTGRES.start(); }  // manual start = JVM singleton; @Container would restart it per class
}
```

`withReuse(true)` + `testcontainers.reuse.enable=true` in `~/.testcontainers.properties` additionally keeps the container across JVM exits. Local-only; CI runs clean.

### Test dependencies (H2 -> Testcontainers migration)

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'  // @ServiceConnection
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
testImplementation 'org.awaitility:awaitility'          // not part of spring-boot-starter-test
testImplementation 'org.wiremock:wiremock-standalone:3.10.0'  // not in the Boot BOM - pin it
testImplementation 'org.springframework.boot:spring-boot-starter-webflux'  // WebTestClient only
// remove: testRuntimeOnly 'com.h2database:h2'
```

Removing the H2 dependency is the enforcement step: any test still pointing at an H2 URL then fails loudly instead of passing on the wrong engine.

### Security tests

Controller slices auto-wire the filter chain but bind no user. Import your `SecurityConfig` and use Spring Security Test post-processors. `@WebMvcTest` does not pick up `@EnableMethodSecurity`, so `@PreAuthorize`/`@PostAuthorize` silently no-op unless you `@Import` the method-security config (or the test passes for the wrong reason). Method-security rules are better asserted in a `@SpringBootTest` that loads them.

Importing a resource-server `SecurityConfig` makes the slice context require a `JwtDecoder` bean - stub it, or the context fails to load (and a config using `fromIssuerLocation` would fetch the issuer over the network at startup):

```java
@WebMvcTest(OrderController.class) @Import(SecurityConfig.class)
class OrderControllerSecurityTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean OrderService orderService;
    @MockitoBean JwtDecoder jwtDecoder;   // required once SecurityConfig configures oauth2ResourceServer

    // stateless JWT resource server: use jwt(); no csrf() needed (CSRF disabled).
    // jwt() maps only the scope/scp claim to SCOPE_* authorities, so a role-based rule
    // (hasRole('ADMIN')) needs .authorities(...) - or the production converter, which is
    // the only form that also covers a broken claim mapping.
    @Test
    void jwt_scope_allows_read() throws Exception {
        mockMvc.perform(get("/api/orders/1")
                .with(jwt().jwt(j -> j.claim("scope", "orders:read"))))
            .andExpect(status().isOk());
    }

    @Test
    void anonymous_unauthorized() throws Exception {
        mockMvc.perform(get("/api/orders/1")).andExpect(status().isUnauthorized());
    }

    // session-based apps instead use @WithMockUser(roles = ...) and .with(csrf()) on writes
    @Test @WithMockUser(roles = "ADMIN")
    void admin_can_delete_session_style() throws Exception {
        mockMvc.perform(delete("/api/orders/1").with(csrf())).andExpect(status().isNoContent());
    }
}
```

### Transactional rollback gotcha

`@DataJpaTest` auto-rolls back. `@SpringBootTest` does not - add `@Transactional` on the test class for cheap cleanup. But `@Transactional` on the test wraps the whole method in one open tx, so a test exercising `@TransactionalEventListener(AFTER_COMMIT)`, `@Async`, `REQUIRES_NEW`, or any commit-gated path will never see it fire - the commit never happens. For those flows, drop `@Transactional` and clean up explicitly with `@Sql(executionPhase = AFTER_TEST_METHOD)` or an `@AfterEach` truncate; then poll for the post-commit effect with Awaitility (below).

Use `@Sql(executionPhase = AFTER_TEST_METHOD)` when a script already exists; otherwise an `@AfterEach` `TRUNCATE ... RESTART IDENTITY CASCADE` avoids inventing a file. Either way keep `maxParallelForks = 1` while cleanup truncates a shared container, or forks wipe each other's rows mid-test.

### Concurrency and schema assertions

Two things a slice cannot see. `FOR UPDATE SKIP LOCKED` needs two real committed transactions, so the test-managed one must go (`@Transactional(propagation = NOT_SUPPORTED)` on a `@DataJpaTest`) and the second claimant runs on its own thread. And a migration's DDL is asserted from the catalog, not from a query plan - `SELECT indexdef FROM pg_indexes WHERE indexname = ?` proves a partial index kept its predicate, whereas an `EXPLAIN` assertion fails on a ten-row fixture table because the planner correctly prefers a seq scan.

### Kafka round trips

```java
@BeforeEach
void waitForAssignment() {   // publishing before the consumer owns its partition is the classic flake
    registry.getListenerContainers().forEach(c -> ContainerTestUtils.waitForAssignment(c, 1));
}
```

Also set `spring.kafka.consumer.auto-offset-reset: earliest` and declare the topic as a `@TestConfiguration` `NewTopic` bean - relying on broker auto-creation makes partition assignment a race.

### Async with Awaitility

```java
@Test
void processesAsync() {
    orderService.processAsync(orderId);

    await().atMost(Duration.ofSeconds(5)).pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> assertThat(orderRepository.findById(orderId).orElseThrow().getStatus())
            .isEqualTo(COMPLETED));
}
```

Asserting that async work did *not* happen needs a window, not an instant: `await().during(Duration.ofMillis(500)).atMost(...).untilAsserted(...)` requires the condition to hold throughout, where a bare assertion passes even if the listener fires 50ms later.

### WireMock for outbound HTTP

Exercises the real `RestClient` / `WebClient` config (timeouts, retries, deserialization) rather than bypassing it via a mocked client.

`@WireMockTest` alone does not work under `@SpringBootTest`: SpringExtension loads the context - evaluating `@DynamicPropertySource` - before WireMock's extension has started and assigned a port, so the base-url override sees nothing. Register the server statically and publish its port instead. Put both on a base class so every HTTP test shares one context customizer, and therefore one context.

```java
public abstract class AbstractHttpIntegrationTest extends AbstractIntegrationTest {
    @RegisterExtension                              // dynamic port: a hardcoded one collides in parallel CI
    protected static final WireMockExtension WIREMOCK = WireMockExtension.newInstance()
        .options(wireMockConfig().dynamicPort())
        .failOnUnmatchedRequests(true)              // an unstubbed call fails the test, not returns 404
        .build();

    @DynamicPropertySource
    static void gatewayUrl(DynamicPropertyRegistry registry) {
        registry.add("payment.base-url", () -> WIREMOCK.getRuntimeInfo().getHttpBaseUrl());
    }
}
```

```java
@SpringBootTest   // no RANDOM_PORT - nothing inbound is under test here
class PaymentIntegrationTest extends AbstractHttpIntegrationTest {
    @Test
    void processesPayment() {
        // WIREMOCK.stubFor, not the static stubFor: WireMockExtension does not point the static
        // DSL at itself unless .configureStaticDsl(true) is set, so a bare stubFor() silently
        // targets localhost:8080 and matches nothing.
        WIREMOCK.stubFor(post(urlPathEqualTo("/api/charges"))
            .willReturn(okJson("""
                {"status":"success","chargeId":"ch_123"}""")));   // a text block needs the newline

        assertThat(paymentGateway.charge(new ChargeRequest(orderId, amount)).status()).isEqualTo("success");
        WIREMOCK.verify(postRequestedFor(urlPathEqualTo("/api/charges"))
            .withRequestBody(matchingJsonPath("$.amount")));
    }
}
```

Assert the timeout itself with a `withFixedDelay` longer than it: if the read timeout is ever widened or dropped, the call returns normally and the test fails on the missing exception. That is the regression a mocked client cannot catch.

### Fixtures

Static factories on a `*Fixtures` class per aggregate. Use `@TestConfiguration` only when fixtures need Spring-managed beans.

```java
public class OrderFixtures {
    public static Order anOrder(OrderStatus status) {
        return Order.builder().customerId(1L).status(status).totalAmount(new BigDecimal("99.99")).build();
    }
    public static OrderDto anOrderDto() { return new OrderDto(1L, 1L, PAID, new BigDecimal("99.99")); }
}
```

For entity comparison, ignore generated fields:

```java
assertThat(actual).usingRecursiveComparison()
    .ignoringFields("id", "createdAt", "updatedAt").isEqualTo(expected);
```

## Output Format

Emit suite-level artifacts first - build-file changes, test properties, shared base classes - then one block per test class (a suite restructuring emits several). Base classes and fixtures are not test classes and get no block.

```
Layer: {Controller | Service | Repository | JSON | Integration}
Slice: {@WebMvcTest | @DataJpaTest | @JsonTest | @SpringBootTest | Plain JUnit}
Containers: {Postgres | Kafka | Redis | WireMock | none - list all the class uses, inherited from a base class or not}
Mocking: {mock() | @MockitoBean | WireMock | none}
Cases: {list}
```

A suite restructuring closes with `Contexts: {n}` - the number of distinct Spring context cache keys the new layout produces. Count one per distinct merged configuration: each slice annotation counts separately, `@WebMvcTest(A.class)` and `@WebMvcTest(B.class)` are two, and any class adding its own `@MockitoBean` or property override forks another. Verify with `logging.level.org.springframework.test.context.cache=DEBUG`, which prints the live cache size.

## Avoid

- `@SpringBootTest` when a slice suffices
- H2 for apps using Postgres features
- `Thread.sleep()` in async tests
- `@DirtiesContext` (kills suite speed)
- `lenient()` to silence strict stubbing - delete the unused stub
- Testing implementation details over behavior
