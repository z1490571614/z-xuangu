"""
FastAPI 应用入口
"""
import os
import tempfile
from datetime import datetime
tushare_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'tushare_cache')
os.makedirs(tushare_cache_dir, exist_ok=True)
os.environ.setdefault('TUSHARE_PRO_SAVE_PATH', tushare_cache_dir)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocket
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(override=True)

from backend.core.logging_config import setup_logging, get_logger, RequestLoggerMiddleware
setup_logging(
    log_dir=os.getenv("LOG_DIR", "logs"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)

from backend.api import stock, task, config, strategy
from backend.auth import routes as auth_routes
from backend.database import engine, Base
from backend.middleware.prometheus_middleware import prometheus_middleware, metrics_endpoint
from backend.middleware.security_middleware import security_headers_middleware, HTTPSRedirectMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("启动选股通知系统...")
    logger.info(f"Tushare Token: {os.getenv('TUSHARE_TOKEN', 'NOT SET')[:20]}...")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表创建完成")

    # 初始化预置策略模板
    try:
        from backend.services.strategy_service import init_strategy_templates
        init_strategy_templates()
        logger.info("✅ 策略模板初始化完成")
    except Exception as e:
        logger.warning(f"⚠️  策略模板初始化失败: {e}")

    # 注入通达信MCP接口
    try:
        # 优先使用环境变量配置的 HTTP 客户端
        from backend.services.tdx_mcp_client import mcp_query_wrapper
        stock.set_tdx_mcp_func(mcp_query_wrapper)
        logger.info("✅ 通达信MCP接口注入成功 (HTTP 模式)")
    except Exception as e:
        logger.warning(f"⚠️  通达信MCP接口不可用: {e}")

    yield
    logger.info("关闭选股通知系统...")


app = FastAPI(
    title="选股通知系统 API",
    description="多策略选股 + 飞书通知 + 定时任务",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8080,http://localhost:8081,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(prometheus_middleware)
app.middleware("http")(security_headers_middleware)

from starlette.middleware.base import BaseHTTPMiddleware

class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        import time
        import uuid
        start = time.time()
        rid = str(uuid.uuid4())[:8]
        
        response = await call_next(request)
        elapsed = (time.time() - start) * 1000
        
        logger.info(
            f"[{rid}] {request.method} {request.url.path} → "
            f"{response.status_code} ({elapsed:.0f}ms)"
        )
        return response

app.add_middleware(RequestLogMiddleware)

if os.getenv("ENABLE_HTTPS_REDIRECT", "false").lower() == "true":
    app.add_middleware(HTTPSRedirectMiddleware)
    logger.info("HTTPS 重定向已启用")

app.include_router(stock.router, prefix="/api/v1", tags=["选股"])
app.include_router(task.router, prefix="/api/v1/tasks", tags=["任务"])
app.include_router(config.router, prefix="/api/v1/config", tags=["配置"])
app.include_router(strategy.router, prefix="/api/v1", tags=["选股策略"])
app.include_router(auth_routes.router)

from backend.services.websocket_service import websocket_endpoint, get_connection_stats

@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    """WebSocket实时推送端点"""
    await websocket_endpoint(websocket)


@app.get("/api/v1/ws/stats", tags=["WebSocket"])
async def websocket_stats():
    """获取WebSocket连接统计"""
    return {
        "code": 200,
        "message": "success",
        "data": get_connection_stats()
    }


@app.get("/api/v1/health", tags=["健康检查"])
async def health_check():
    """健康检查接口"""
    return {
        "code": 200,
        "message": "success",
        "data": {"status": "healthy"},
        "timestamp": int(datetime.now().timestamp())
    }


@app.get("/metrics", tags=["监控"])
async def metrics():
    """Prometheus 指标端点"""
    return metrics_endpoint()
