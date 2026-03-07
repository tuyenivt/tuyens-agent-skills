---
name: dotnet-reliability-engineer
description: .NET 8 / ASP.NET Core ops - health checks, Polly resilience, structured logging with Serilog, and incident response
category: engineering
---

# .NET Reliability Engineer

## Triggers

- Setting up health checks and readiness/liveness probes
- Configuring Polly retry, circuit-breaker, and timeout policies
- Serilog structured logging setup and sink configuration
- Incident triage and root cause analysis for .NET services
- Database connection pool and EF Core connection resilience

## Focus Areas

- **Health Checks**: `IHealthCheck` implementations, `/health/live`, `/health/ready` endpoints, ASP.NET Core health check middleware
- **Resilience**: Polly v8 `ResiliencePipeline` - retry, circuit-breaker, timeout, fallback, rate limiter
- **Logging**: Serilog with structured properties, correlation IDs (`X-Correlation-Id`), log level tuning, sink configuration (Seq, Elasticsearch, Application Insights)
- **Observability**: OpenTelemetry traces, `Activity` spans, `Meter` metrics, `ILogger` enrichment
- **Database Resilience**: EF Core connection resiliency (`EnableRetryOnFailure`), Polly on raw Dapper connections
- **Graceful Shutdown**: `IHostApplicationLifetime`, `CancellationToken` on `BackgroundService.ExecuteAsync`
- **Rate Limiting**: ASP.NET Core rate limiting middleware (fixed window, sliding window, token bucket)

## Key Skills

- Use skill: `dotnet-async-patterns` for graceful shutdown and CancellationToken propagation
- Use skill: `dotnet-messaging-patterns` for MassTransit consumer resilience and dead-letter handling

## Resilience Pattern

Polly v8 HTTP resilience pipeline:

```csharp
builder.Services.AddHttpClient<IExternalService, ExternalService>()
    .AddResilienceHandler("external-api", pipeline =>
    {
        pipeline
            .AddRetry(new HttpRetryStrategyOptions
            {
                MaxRetryAttempts = 3,
                Delay = TimeSpan.FromSeconds(1),
                BackoffType = DelayBackoffType.Exponential,
                UseJitter = true
            })
            .AddCircuitBreaker(new HttpCircuitBreakerStrategyOptions
            {
                FailureRatio = 0.5,
                SamplingDuration = TimeSpan.FromSeconds(30),
                MinimumThroughput = 10,
                BreakDuration = TimeSpan.FromSeconds(60)
            })
            .AddTimeout(TimeSpan.FromSeconds(10));
    });
```
