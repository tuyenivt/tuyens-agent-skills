---
name: kotlin-spring-security-patterns
description: Kotlin / Spring Security DSL patterns: SecurityFilterChain, OAuth2/JWT, method security, CORS, CSRF, headers, coroutine security context propagation.
metadata:
  category: backend
  tags: [kotlin, security, spring-security, oauth2, jwt, cors, csrf, authorization, kotlin-dsl]
user-invocable: false
---

# Kotlin Spring Security Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Configuring authentication and authorization for Kotlin/Spring Boot 3.5+ APIs
- Setting up OAuth2/JWT resource server with Kotlin DSL
- Applying method-level security with SpEL expressions
- Configuring CORS for SPA frontends
- Hardening security headers and CSRF protection
- Propagating `SecurityContext` across `suspend` functions and `Flow`

## Rules

- Use `SecurityFilterChain` as `@Bean` - never extend `WebSecurityConfigurerAdapter` (removed in Spring Security 6)
- Prefer the Kotlin Security DSL (`http { ... }`) over the chained Java builder
- Use `@EnableMethodSecurity` - never `@EnableGlobalMethodSecurity` (deprecated)
- STATELESS APIs must disable CSRF and sessions
- Never store JWT in localStorage - use HttpOnly cookie or Authorization header from memory
- Never use wildcard CORS origins (`*`) in production
- Constructor injection only via primary constructor; no `lateinit` for security beans
- Externalize security configuration (issuer URIs, allowed origins) via `@ConfigurationProperties` data class
- For `suspend` controllers / WebFlux, use `ReactiveSecurityContextHolder` - blocking `SecurityContextHolder` does not propagate across coroutine boundaries

## Patterns

### Security Filter Chain (Kotlin DSL)

Multiple filter chains for different path groups, ordered by specificity. The Kotlin DSL is more concise than the Java chained builder:

```kotlin
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    @Order(1)
    fun apiSecurityFilterChain(http: HttpSecurity): SecurityFilterChain = http {
        securityMatcher("/api/**")
        authorizeHttpRequests {
            authorize("/api/public/**", permitAll)
            authorize("/api/admin/**", hasRole("ADMIN"))
            authorize(anyRequest, authenticated)
        }
        oauth2ResourceServer { jwt { } }
        sessionManagement { sessionCreationPolicy = SessionCreationPolicy.STATELESS }
        csrf { disable() }
    }.let { http.build() }

    @Bean
    @Order(2)
    fun actuatorSecurityFilterChain(http: HttpSecurity): SecurityFilterChain = http {
        securityMatcher("/actuator/**")
        authorizeHttpRequests {
            authorize("/actuator/health", permitAll)
            authorize("/actuator/info", permitAll)
            authorize(anyRequest, hasRole("OPS"))
        }
        httpBasic { }
    }.let { http.build() }
}
```

Role hierarchy configuration:

```kotlin
@Bean
fun roleHierarchy(): RoleHierarchy = RoleHierarchyImpl.withRolePrefix("ROLE_")
    .role("ADMIN").implies("MANAGER")
    .role("MANAGER").implies("USER")
    .build()
```

### JWT / OAuth2 Resource Server

JwtDecoder with issuer validation:

```kotlin
@Bean
fun jwtDecoder(@Value("\${spring.security.oauth2.resourceserver.jwt.issuer-uri}") issuerUri: String): JwtDecoder {
    val decoder = JwtDecoders.fromIssuerLocation(issuerUri) as NimbusJwtDecoder
    val audienceValidator = JwtClaimValidator<List<String>>("aud") { aud -> aud != null && "my-api" in aud }
    val withIssuer = JwtValidators.createDefaultWithIssuer(issuerUri)
    decoder.setJwtValidator(DelegatingOAuth2TokenValidator(withIssuer, audienceValidator))
    return decoder
}
```

Custom role extraction from JWT claims:

```kotlin
@Bean
fun jwtAuthenticationConverter(): JwtAuthenticationConverter {
    val grantedAuthoritiesConverter = JwtGrantedAuthoritiesConverter().apply {
        setAuthoritiesClaimName("roles")
        setAuthorityPrefix("ROLE_")
    }
    return JwtAuthenticationConverter().apply {
        setJwtGrantedAuthoritiesConverter(grantedAuthoritiesConverter)
    }
}
```

Multi-tenant JWT validation (multiple issuers):

```kotlin
@Bean
fun multiTenantJwtDecoder(@Value("\${jwt.issuer-uris}") issuerUris: List<String>): JwtDecoder {
    val decoders: Map<String, JwtDecoder> = issuerUris.associateWith { JwtDecoders.fromIssuerLocation(it) }
    return JwtDecoder { token ->
        val issuer = JWTParser.parse(token).jwtClaimsSet.issuer
        decoders[issuer]?.decode(token) ?: throw JwtException("Unknown issuer: $issuer")
    }
}
```

### Method-Level Security

Enable and use `@PreAuthorize` / `@PostAuthorize`. Note: in Kotlin, escape `$` in SpEL with `\$`:

```kotlin
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig

@Service
@Transactional(readOnly = true)
class OrderService(private val orderRepository: OrderRepository) {

    @PreAuthorize("hasRole('ADMIN') or #userId == authentication.name")
    fun findByUser(userId: String): List<OrderDTO> =
        orderRepository.findByUserId(userId).map { OrderDTO.from(it) }

    @PostAuthorize("returnObject.ownerId == authentication.name or hasRole('ADMIN')")
    fun findById(id: Long): OrderDTO =
        orderRepository.findById(id).map { OrderDTO.from(it) }.orElseThrow { NotFoundException("Order not found") }
}
```

Custom permission evaluator for domain-object authorization:

```kotlin
@Component
class ProjectPermissionEvaluator : PermissionEvaluator {

    override fun hasPermission(auth: Authentication, target: Any?, permission: Any?): Boolean = when (target) {
        is Project -> target.ownerId == auth.name || auth.authorities.any { it.authority == "ROLE_ADMIN" }
        else -> false
    }

    override fun hasPermission(auth: Authentication, targetId: Serializable?, targetType: String?, permission: Any?): Boolean = false
}

// Usage:
@PreAuthorize("hasPermission(#project, 'WRITE')")
fun updateProject(project: Project) { /* ... */ }
```

### CORS Configuration

`CorsConfigurationSource` bean for JWT-based SPAs. Externalize allowed origins via `@ConfigurationProperties`:

```kotlin
@ConfigurationProperties(prefix = "app.cors")
data class CorsProperties(val allowedOrigins: List<String> = emptyList())

@Bean
fun corsConfigurationSource(props: CorsProperties): CorsConfigurationSource {
    val config = CorsConfiguration().apply {
        allowedOrigins = props.allowedOrigins
        allowedMethods = listOf("GET", "POST", "PUT", "DELETE", "OPTIONS")
        allowedHeaders = listOf("Authorization", "Content-Type", "X-XSRF-TOKEN")
        exposedHeaders = listOf("X-Total-Count")
        allowCredentials = true
        maxAge = 3600L
    }
    return UrlBasedCorsConfigurationSource().apply {
        registerCorsConfiguration("/api/**", config)
    }
}
```

Wire into the security DSL via `cors { }`.

### CSRF Handling

STATELESS APIs - disable CSRF (no session to protect):

```kotlin
http {
    csrf { disable() }
    sessionManagement { sessionCreationPolicy = SessionCreationPolicy.STATELESS }
}
```

Stateful apps - CookieCsrfTokenRepository for SPA (XSRF-TOKEN cookie + X-XSRF-TOKEN header):

```kotlin
http {
    csrf {
        csrfTokenRepository = CookieCsrfTokenRepository.withHttpOnlyFalse()
        csrfTokenRequestHandler = SpaCsrfTokenRequestHandler()
    }
}
```

### Security Headers

Configure via the Kotlin DSL `headers { }` block:

```kotlin
http {
    headers {
        contentSecurityPolicy {
            policyDirectives = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
        }
        httpStrictTransportSecurity {
            includeSubDomains = true
            maxAgeInSeconds = 31536000
        }
        contentTypeOptions { }
        frameOptions { deny = true }
    }
}
```

### Webhook Endpoint Security

Webhook endpoints from external services (Stripe, GitHub) use signature-based authentication instead of JWT/OAuth2. Exclude them from the standard security filter chain:

```kotlin
@Bean
@Order(0) // highest priority - before API security chain
fun webhookSecurityFilterChain(http: HttpSecurity): SecurityFilterChain = http {
    securityMatcher("/webhooks/**")
    authorizeHttpRequests { authorize(anyRequest, permitAll) }
    csrf { disable() }
    sessionManagement { sessionCreationPolicy = SessionCreationPolicy.STATELESS }
}.let { http.build() }
```

Signature validation happens in the webhook service (HMAC comparison via `MessageDigest.isEqual` for timing-safety).

### `@AuthenticationPrincipal` in Controllers

Inject the JWT principal directly into a controller method instead of reaching into `SecurityContextHolder`:

```kotlin
@RestController
class OrderController(private val service: OrderService) {

    @GetMapping("/orders")
    suspend fun list(@AuthenticationPrincipal jwt: Jwt): List<OrderResponse> =
        service.listForUser(userId = jwt.subject).map { it.toResponse() }

    // For custom user details, type-narrow the principal
    @GetMapping("/me")
    fun me(@AuthenticationPrincipal user: AppUserDetails): UserResponse = user.toResponse()
}
```

This is the cleanest option for `suspend` controllers because it sidesteps the ThreadLocal-vs-coroutine-context question entirely - the principal is passed as a method argument and stays valid across dispatcher switches.

### Custom Authorization with `AuthorizationManager`

Spring Security 6 replaces the deprecated `AccessDecisionManager` with `AuthorizationManager<RequestAuthorizationContext>`. Use it inside the DSL when an authorization rule needs more context than `hasRole` / `hasAuthority` can express:

```kotlin
@Bean
fun ownsTenantManager(): AuthorizationManager<RequestAuthorizationContext> =
    AuthorizationManager { authentication, ctx ->
        val tenantId = ctx.request.getHeader("X-Tenant-Id")
        val authority = "TENANT_$tenantId"
        AuthorizationDecision(authentication.get().authorities.any { it.authority == authority })
    }

http {
    authorizeHttpRequests {
        authorize("/api/tenants/**", access(ownsTenantManager()))    // composes with the DSL
        authorize(anyRequest, authenticated)
    }
}
```

Use `@PreAuthorize` for method-level checks and `AuthorizationManager` for filter-chain-level rules that depend on the request.

### Coroutine Security Context

`SecurityContextHolder` uses ThreadLocal and does not propagate across `suspend` boundaries. For coroutine-based services, use the reactive holder or pass the principal explicitly:

```kotlin
// Bad: SecurityContextHolder.getContext() inside suspend - returns empty after dispatcher switch
suspend fun getCurrentUser(): String? = SecurityContextHolder.getContext().authentication?.name

// Good: ReactiveSecurityContextHolder.getContext().awaitFirstOrNull()
suspend fun getCurrentUser(): String? =
    ReactiveSecurityContextHolder.getContext().awaitFirstOrNull()?.authentication?.name

// Best: pass the principal as a method parameter so the suspend function is stateless
suspend fun listUserOrders(principal: String): List<Order> =
    orderRepo.findByUserId(principal)
```

For `@Async` (non-coroutine) Kotlin code, configure `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` or wrap the executor with a `DelegatingSecurityContextExecutor`.

### Testing Security

Simple role-based test with `@WithMockUser`:

```kotlin
@WebMvcTest(UserController::class)
class UserControllerSecurityTest {

    @Autowired lateinit var mockMvc: MockMvc

    @Test
    @WithMockUser(roles = ["ADMIN"])
    fun `admin endpoint with admin role returns 200`() {
        mockMvc.get("/api/admin/users").andExpect { status { isOk() } }
    }

    @Test
    fun `admin endpoint unauthenticated returns 401`() {
        mockMvc.get("/api/admin/users").andExpect { status { isUnauthorized() } }
    }
}
```

JWT-based test:

```kotlin
@Test
fun `jwt endpoint with valid jwt returns 200`() {
    mockMvc.get("/api/orders") {
        with(jwt().authorities(SimpleGrantedAuthority("ROLE_USER")).jwt { it.claim("sub", "user-123") })
    }.andExpect { status { isOk() } }
}
```

## Output Format

When applying security patterns, document the configuration:

```
Endpoint: {path pattern}
Auth: {permitAll | authenticated | hasRole(X) | @PreAuthorize(expr)}
CSRF: {enabled | disabled - reason}
Session: {STATELESS | IF_REQUIRED}
CORS Origins: {list or "N/A"}
JWT Issuer: {issuer URI or "N/A"}
DSL: {Kotlin DSL | Java builder}
```

## Avoid

- `WebSecurityConfigurerAdapter` - removed in Spring Security 6
- `@EnableGlobalMethodSecurity` - replaced by `@EnableMethodSecurity`
- `@Secured` - limited; prefer `@PreAuthorize` with SpEL
- Disabling CSRF on stateful (session-based) applications
- Storing JWT in `localStorage` - vulnerable to XSS; use HttpOnly cookie or keep in memory
- Wildcard CORS origins (`*`) in production
- Hardcoded secrets or issuer URIs - externalize to `@ConfigurationProperties` data class
- `SecurityContextHolder.getContext()` inside `suspend` functions - use `ReactiveSecurityContextHolder` or pass principal explicitly
- Forgetting to escape `$` in SpEL strings - Kotlin string templates collide with `${...}` SpEL syntax
