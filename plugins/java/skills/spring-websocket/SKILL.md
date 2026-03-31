---
name: spring-websocket
description: Spring WebSocket and STOMP messaging patterns covering configuration, handshake authentication, message-level security, connection lifecycle events, and Virtual Thread-compatible controllers.
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
