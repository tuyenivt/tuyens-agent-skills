---
name: spring-websocket
description: "Spring WebSocket / STOMP patterns: configuration, handshake auth, message-level security, lifecycle events, Virtual Thread controllers."
metadata:
  category: backend
  tags: [websocket, stomp, messaging, real-time, spring]
user-invocable: false
---

# Spring WebSocket

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Real-time bidirectional communication (chat, notifications, live updates)
- Server-sent events to connected clients (e.g., order status updates, payment confirmations)
- Implementing STOMP messaging over WebSocket
- Live dashboard updates for admin or monitoring panels

## Rules

- Use STOMP over WebSocket for structured messaging
- Always configure message broker (simple or external like RabbitMQ)
- Authenticate WebSocket handshake, not individual messages
- Use `/topic` for broadcast, `/queue` for user-specific messages
- Handle connection/disconnection events for cleanup
- Set heartbeat intervals to detect stale connections
- Limit message size and rate to prevent abuse
- Use Virtual Thread-compatible patterns (no synchronized)
- Prefer STOMP `CONNECT`-frame JWT via `ChannelInterceptor` over handshake query-param tokens (avoids token leakage to nginx access logs and browser history)
- For more than one app instance, use an external STOMP relay (RabbitMQ / ActiveMQ Artemis) - `enableSimpleBroker` is in-process only and silently fails to fan out across nodes

## Patterns

### Configuration

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[]{10000, 10000});
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("${app.cors.origins}")
                .withSockJS();
    }
}
```

### Controller

Bad - No authentication, blocking operations:

```java
@MessageMapping("/chat")
public void handleMessage(ChatMessage message) {
    synchronized (messages) { // Blocks Virtual Threads
        messages.add(message);
    }
    template.convertAndSend("/topic/chat", message);
}
```

Good - Authenticated, non-blocking:

```java
@Controller
public class ChatController {

    private final SimpMessagingTemplate messagingTemplate;
    private final ChatService chatService;

    @MessageMapping("/chat.send")
    public void sendMessage(@Payload ChatMessageDTO message,
                            Principal principal) {
        ChatMessageDTO saved = chatService.save(message, principal.getName());
        messagingTemplate.convertAndSend("/topic/chat." + message.roomId(), saved);
    }

    @MessageMapping("/chat.private")
    public void sendPrivateMessage(@Payload PrivateMessageDTO message,
                                   Principal principal) {
        messagingTemplate.convertAndSendToUser(
            message.recipientId(),
            "/queue/messages",
            message
        );
    }
}
```

### CONNECT-Frame Auth via ChannelInterceptor

Authenticating in the STOMP `CONNECT` frame keeps tokens out of the upgrade URL (which nginx logs and the browser keeps in history). The interceptor reads the `Authorization` header from the CONNECT frame and binds an `Authentication` to the session that downstream `@MessageMapping` controllers see via `Principal`.

```java
@Configuration
@EnableWebSocketMessageBroker
@RequiredArgsConstructor
public class WebSocketSecurityConfig implements WebSocketMessageBrokerConfigurer {

    private final JwtDecoder jwtDecoder;

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                    MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);
                if (accessor != null && StompCommand.CONNECT.equals(accessor.getCommand())) {
                    String bearer = accessor.getFirstNativeHeader("Authorization");
                    if (bearer == null || !bearer.startsWith("Bearer ")) {
                        throw new MessageDeliveryException("Missing Bearer token");
                    }
                    Jwt jwt = jwtDecoder.decode(bearer.substring(7));
                    var auth = new JwtAuthenticationToken(
                        jwt, AuthorityUtils.createAuthorityList("ROLE_" + jwt.getClaimAsString("role")));
                    accessor.setUser(auth);
                }
                return message;
            }
        });
    }
}
```

### Role-Based Destination Security

```java
@Configuration
@EnableWebSocketSecurity
public class WebSocketAuthorizationConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        return messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
            .simpDestMatchers("/app/admin/**").hasRole("ADMIN")
            .simpSubscribeDestMatchers("/user/queue/**").authenticated()
            .anyMessage().authenticated()
            .build();
    }
}
```

### Reverse Proxy (nginx)

WebSocket needs the `Upgrade` / `Connection` headers passed through and a long read timeout, otherwise nginx kills idle connections at the default 60s.

```nginx
location /ws {
    proxy_pass http://app:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 3600s;
}
```

When clients connect via X-Forwarded-Host, switch `setAllowedOrigins(...)` to `setAllowedOriginPatterns(...)` so the origin check accepts the forwarded host.

### Scaling: External STOMP Broker

`enableSimpleBroker(...)` is in-process only - subscriptions on instance A never receive sends from instance B. For more than one node, run RabbitMQ (or ActiveMQ Artemis) as a STOMP relay:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("rabbitmq")
            .setRelayPort(61613)
            .setClientLogin("app")
            .setClientPasscode("${broker.password}");
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user");
}
```

### Connection Events

```java
@Component
public class WebSocketEventListener {

    private final SimpMessagingTemplate messagingTemplate;
    private final UserPresenceService presenceService;

    @EventListener
    public void handleConnect(SessionConnectedEvent event) {
        String userId = event.getUser().getName();
        presenceService.markOnline(userId);
    }

    @EventListener
    public void handleDisconnect(SessionDisconnectEvent event) {
        String userId = event.getUser().getName();
        presenceService.markOffline(userId);
        messagingTemplate.convertAndSend("/topic/presence",
            new PresenceEvent(userId, "OFFLINE"));
    }
}
```

### Handshake Authentication

Authenticate at the WebSocket handshake using a `HandshakeInterceptor`. This is the correct place to validate tokens - the `Principal` set here is available in all `@MessageMapping` methods:

```java
@Component
public class JwtHandshakeInterceptor implements HandshakeInterceptor {

    private final JwtService jwtService;

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                   WebSocketHandler wsHandler, Map<String, Object> attributes) {
        String token = extractToken(request); // from query param or header
        if (token == null || !jwtService.isValid(token)) {
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false; // reject handshake
        }
        String userId = jwtService.extractSubject(token);
        attributes.put("userId", userId); // available in session attributes
        return true;
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
                               WebSocketHandler wsHandler, Exception exception) {}
}

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    private final JwtHandshakeInterceptor jwtInterceptor;

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .addInterceptors(jwtInterceptor) // authenticate at handshake
                .setAllowedOrigins("${app.cors.origins}")
                .withSockJS();
    }
}
```

### Message-Level Security

```java
@Configuration
public class WebSocketSecurityConfig {

    @Bean
    public AuthorizationManager<Message<?>> messageAuthorizationManager() {
        return MessageMatcherDelegatingAuthorizationManager.builder()
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").authenticated()
            .simpSubscribeDestMatchers("/topic/**", "/queue/**").authenticated()
            .anyMessage().denyAll()
            .build();
    }
}
```

### Error Handling

Handle exceptions in `@MessageMapping` methods to prevent silent failures. Unhandled exceptions close the WebSocket session without client notification:

```java
@MessageExceptionHandler
@SendToUser("/queue/errors")
public String handleException(Exception ex) {
    log.error("WebSocket message error", ex);
    return ex.getMessage();
}
```

### Message Size and Rate Limiting

Configure limits on the broker to prevent abuse:

```java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registry) {
    registry.setMessageSizeLimit(64 * 1024)       // 64 KB max message
            .setSendBufferSizeLimit(512 * 1024)    // 512 KB send buffer
            .setSendTimeLimit(20 * 1000);           // 20 sec send timeout
}
```

## Output Format

When implementing WebSocket patterns, document the configuration:

```
Endpoint: {WebSocket path}
Protocol: {STOMP | raw WebSocket}
Auth: {handshake JWT | session | none}
Topics: {list of /topic and /queue destinations}
Heartbeat: {interval in ms}
Message Limit: {max size}
```

## Avoid

- `synchronized` blocks in message handlers - blocks Virtual Threads; use `ReentrantLock` or concurrent collections
- Missing heartbeat configuration - stale connections consume resources indefinitely
- Unauthenticated WebSocket endpoints - authenticate at handshake, not per-message
- Broadcasting sensitive data to all `/topic` subscribers - use `/queue` for user-specific messages
- Unbounded message queues - configure `messageSizeLimit` and buffer size on the broker registry
- Omitting `@MessageExceptionHandler` - unhandled exceptions silently close the session
