"""
Prometheus 监控中间件
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
import time


REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP Request Latency',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_in_progress',
    'HTTP Requests In Progress',
    ['method', 'endpoint']
)


async def prometheus_middleware(request: Request, call_next):
    start_time = time.time()
    
    ACTIVE_REQUESTS.labels(
        method=request.method,
        endpoint=request.url.path
    ).inc()
    
    try:
        response = await call_next(request)
        
        duration = time.time() - start_time
        
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        
        return response
    finally:
        ACTIVE_REQUESTS.labels(
            method=request.method,
            endpoint=request.url.path
        ).dec()


def metrics_endpoint():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
