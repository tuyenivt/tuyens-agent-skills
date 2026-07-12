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

## Slice Selection

| Layer                   | Choice                                              |
| ----------------------- | --------------------------------------------------- |
| Repository              | `@DataJpaTest` + Testcontainers Postgres            |
| Controller              | `@WebMvcTest` + MockMvc, `@MockitoBean` services    |
| JSON (de)serialization  | `@JsonTest` + `JacksonTester`                       |
| Service (pure logic)    | Plain JUnit 5 + Mockito                             |
| Service (Spring wiring) | `@SpringBootTest` + `@MockitoBean` externals        |
| Full integration        | `@SpringBootTest` + Testcontainers + WebTestClient  |

"Spring wiring" means the proxy behavior itself is under test (tx rollback, `@PreAuthorize`, listener firing). Injectable collaborators (`ApplicationEventPublisher`, repos) alone don't make it Spring wiring - use plain JUnit.

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
class OrderServiceTest {
    OrderRepository repo = mock(OrderRepository.class);
    PaymentGateway gateway = mock(PaymentGateway.class);
    OrderService service = new OrderService(repo, gateway);

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
testImplementation 'org.awaitility:awaitility'   // not part of spring-boot-starter-test
// remove: testRuntimeOnly 'com.h2database:h2'
```

### Security tests

Controller slices auto-wire the filter chain but bind no user. Import your `SecurityConfig` and use Spring Security Test post-processors. `@WebMvcTest` does not pick up `@EnableMethodSecurity`, so `@PreAuthorize`/`@PostAuthorize` silently no-op unless you `@Import` the method-security config (or the test passes for the wrong reason). Method-security rules are better asserted in a `@SpringBootTest` that loads them.

Importing a resource-server `SecurityConfig` makes the slice context require a `JwtDecoder` bean - stub it, or the context fails to load (and a config using `fromIssuerLocation` would fetch the issuer over the network at startup):

```java
@WebMvcTest(OrderController.class) @Import(SecurityConfig.class)
class OrderControllerSecurityTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean OrderService orderService;
    @MockitoBean JwtDecoder jwtDecoder;   // required once SecurityConfig configures oauth2ResourceServer

    // stateless JWT resource server: use jwt(); no csrf() needed (CSRF disabled)
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

### WireMock for outbound HTTP

Exercises the real `RestClient` / `WebClient` config (timeouts, retries, deserialization) rather than bypassing it via a mocked client.

```java
@SpringBootTest(webEnvironment = RANDOM_PORT)
@WireMockTest  // dynamic port (inject WireMockRuntimeInfo, override the client base-url property); hardcoded ports collide in parallel CI
class PaymentIntegrationTest extends AbstractIntegrationTest {
    @Test
    void processesPayment() {
        stubFor(post(urlPathEqualTo("/api/charges"))
            .willReturn(okJson("""{"status":"success","chargeId":"ch_123"}""")));

        assertThat(paymentGateway.charge(new ChargeRequest(orderId, amount)).status()).isEqualTo("success");
        verify(postRequestedFor(urlPathEqualTo("/api/charges"))
            .withRequestBody(matchingJsonPath("$.amount")));
    }
}
```

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

One block per test class (a suite restructuring emits several):

```
Layer: {Controller | Service | Repository | JSON | Integration}
Slice: {@WebMvcTest | @DataJpaTest | @JsonTest | @SpringBootTest | Plain JUnit}
Containers: {Postgres | Kafka | Redis | WireMock | none}
Mocking: {mock() | @MockitoBean | WireMock | none}
Cases: {list}
```

## Avoid

- `@SpringBootTest` when a slice suffices
- H2 for apps using Postgres features
- `Thread.sleep()` in async tests
- `@DirtiesContext` (kills suite speed)
- `lenient()` to silence strict stubbing - delete the unused stub
- Testing implementation details over behavior
