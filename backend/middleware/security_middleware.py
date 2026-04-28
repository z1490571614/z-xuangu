"""
安全中间件模块

提供 HTTPS 重定向和安全响应头
"""
from fastapi import Request, Response
from starlette.types import ASGIApp
import os


class HTTPSRedirectMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            x_forwarded_proto = headers.get(b"x-forwarded-proto", b"").decode()
            if x_forwarded_proto == "http":
                path = scope.get("path", "/")
                query = scope.get("query_string", b"").decode()
                url = f"https://{headers.get(b'host', b'').decode()}{path}"
                if query:
                    url += f"?{query}"

                async def send_redirect(message):
                    if message["type"] == "http.response.start":
                        await send({
                            "type": "http.response.start",
                            "status": 301,
                            "headers": [
                                [b"location", url.encode()],
                                [b"content-length", b"0"],
                            ],
                        })
                    elif message["type"] == "http.response.body":
                        await send({
                            "type": "http.response.body",
                            "body": b"",
                        })

                await self.app(scope, receive, send_redirect)
                return

        await self.app(scope, receive, send)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    if os.getenv("ENABLE_HTTPS_REDIRECT", "false").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
