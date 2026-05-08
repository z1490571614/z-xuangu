"""
FastAPI 应用入口
"""
import os
from datetime import datetime
tushare_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'tushare_cache')
os.makedirs(tushare_cache_dir, exist_ok=True)
os.environ.setdefault('TUSHARE_PRO_SAVE_PATH', tushare_cache_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocket
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(override=True)

from backend.core.logging_config import setup_logging, get_logger
setup_logging(
    log_dir=os.getenv("LOG_DIR", "logs"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)

from backend.api import stock, task, config, strategy, stock_detail, score_v2, anomaly, overview_brief, news_v2, backtest
from backend.auth import routes as auth_routes
from backend.database import engine, Base
from backend.models.stock_lhb import StockLhb
from backend.models.stock_risk import StockRiskBreakdown  # 确保表在 create_all 前注册
from backend.models.stock_ths_board import ThsBoardIndex, StockThsBoardMember
from backend.models.board import (
    BoardIndex,
    StockBoardMember,
    BoardDailySnapshot,
    BoardStrengthSnapshot,
    DcBoardAlias,
    DcBoardAliasObservation,
    DcBoardAliasSyncState,
)
from backend.models import (
    SelectionRecord, SelectedStock,
    StockScoreV2, StockScoreBreakdownV2, StockRiskBreakdownV2,
    StockOverviewBrief, StockAnomalyInterpretation,
    StockFeatureSnapshot, StockDetailSnapshot,
    StockAuctionOpen, LeaderMainT0TrainingSample,
)  # 确保 V3 表在 create_all 前注册
from backend.models.seal_rate import StockDailyData, SealRateCache  # 确保日线/封板率表注册
from backend.middleware.prometheus_middleware import prometheus_middleware, metrics_endpoint
from backend.middleware.security_middleware import security_headers_middleware, HTTPSRedirectMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("启动选股通知系统...")
    logger.info(f"Tushare Token: {os.getenv('TUSHARE_TOKEN', 'NOT SET')[:20]}...")
    Base.metadata.create_all(bind=engine)
    try:
        from backend.database.schema_migrations import ensure_runtime_columns
        ensure_runtime_columns(engine)
    except Exception as e:
        logger.warning(f"数据库轻量迁移失败，继续启动: {e}")
    logger.info("数据库表创建完成")

    # 启动时同步一次东财板块词典，运行期主题匹配只读本地库
    try:
        from backend.services.dc_board_service import DcBoardService
        from backend.utils.trading_date import get_latest_trading_day
        trade_date = get_latest_trading_day()
        stats = DcBoardService().sync_board_index_catalog(trade_date)
        logger.info(f"✅ 东财板块词典同步完成: fetched={stats.get('fetched', 0)}, saved={stats.get('saved', 0)}")

        try:
            from backend.services.dc_board_alias_service import DcBoardAliasService
            now = datetime.now()
            finalize_aliases = now.hour > 15 or (now.hour == 15 and now.minute >= 30)
            alias_stats = DcBoardAliasService().sync_trade_date(trade_date, finalize=finalize_aliases)
            logger.info(
                "✅ 东财动态别名同步完成: "
                f"trade_date={trade_date}, source_rows={alias_stats.get('source_rows', 0)}, "
                f"inserted={alias_stats.get('inserted_observations', 0)}"
            )
        except Exception as e:
            logger.warning(f"⚠️  东财动态别名同步失败，使用已有别名降级: {e}")
    except Exception as e:
        logger.warning(f"⚠️  东财板块词典同步失败，使用已有本地词典降级: {e}")

    # 保留同花顺词典同步作为灰度兼容层，涨停标签仍由 limit_list_ths 提供
    try:
        from backend.services.ths_board_service import ThsBoardService
        stats = ThsBoardService().sync_board_index_catalog(force=True)
        logger.info(f"✅ 同花顺板块词典同步完成: fetched={stats.get('fetched', 0)}, saved={stats.get('saved', 0)}")
    except Exception as e:
        logger.warning(f"⚠️  同花顺板块词典同步失败，使用已有本地词典降级: {e}")
    
    # 初始化新闻数据库表（独立数据库引擎）
    try:
        from backend.services.news_database import init_news_tables
        init_news_tables()
        logger.info("新闻数据库表创建完成")
    except Exception as e:
        logger.warning(f"新闻数据库表创建失败: {e}")

    # 初始化预置策略模板
    try:
        from backend.services.strategy_service import init_strategy_templates
        init_strategy_templates()
        logger.info("✅ 策略模板初始化完成")
    except Exception as e:
        logger.warning(f"⚠️  策略模板初始化失败: {e}")

    # 注入通达信MCP接口
    try:
        # 优先使用系统级 MCP 工具
        from importlib import import_module
        mcp_module = import_module("mcp_Tong_Da_Xin_MCP_tdx_wenda_quotes")
        mcp_func = mcp_module.mcp_Tong_Da_Xin_MCP_tdx_wenda_quotes
        stock.set_tdx_mcp_func(mcp_func)
        logger.info("✅ 通达信MCP接口注入成功 (系统 MCP 模式)")
    except Exception as e:
        logger.warning(f"⚠️  系统MCP工具不可用: {e}")
        try:
            # 降级到 HTTP 客户端
            from backend.services.tdx_mcp_client import mcp_query_wrapper
            stock.set_tdx_mcp_func(mcp_query_wrapper)
            logger.info("✅ 通达信MCP接口注入成功 (HTTP 模式)")
        except Exception as e2:
            logger.warning(f"⚠️  HTTP客户端也不可用: {e2}")

    # 检查本地日线数据路径（MCP降级用）
    tdx_vipdoc = os.getenv("TDX_VIPDOC_PATH", "")
    if tdx_vipdoc and os.path.isdir(tdx_vipdoc):
        logger.info(f"✅ 本地通达信数据路径就绪: {tdx_vipdoc}")
    else:
        logger.warning(f"⚠️  本地通达信数据路径不可用: {tdx_vipdoc}")

    # 启动新闻增量抓取调度器
    news_scheduler = None
    try:
        from backend.services.news_scheduler import get_news_scheduler
        news_scheduler = get_news_scheduler()
        news_scheduler.start()
        logger.info("✅ 新闻增量抓取调度器启动成功")
    except Exception as e:
        logger.warning(f"⚠️  新闻调度器启动失败: {e}")

    yield
    
    # 关闭新闻调度器
    if news_scheduler:
        news_scheduler.stop()
        logger.info("✅ 新闻增量抓取调度器已停止")
    
    logger.info("关闭选股通知系统...")


app = FastAPI(
    title="选股通知系统 API",
    description="多策略选股 + 飞书通知 + 定时任务",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>选股通知系统</title>
    <style>
        body { font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
        .card { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); text-align: center; max-width: 400px; }
        h1 { color: #1a1a1a; font-size: 22px; margin-bottom: 8px; }
        p { color: #666; margin: 6px 0; }
        .links { margin-top: 24px; }
        a { display: block; padding: 10px; margin: 8px 0; border-radius: 8px; text-decoration: none; color: white; font-weight: 500; }
        a.frontend { background: #1677ff; }
        a.docs { background: #52c41a; }
        a:hover { opacity: 0.85; }
    </style>
</head>
<body>
    <div class="card">
        <h1>选股通知系统</h1>
        <p>后端服务运行中</p>
        <div class="links">
            <a class="frontend" href="http://localhost:8080" target="_blank">打开前端页面</a>
            <a class="docs" href="/docs" target="_blank">API 文档 (Swagger)</a>
        </div>
    </div>
</body>
</html>
    """)

@app.get("/api/v1/scheduler/status", include_in_schema=False)
async def scheduler_status():
    """新闻调度器状态（独立路由）"""
    try:
        from backend.services.news_scheduler import get_news_scheduler
        s = get_news_scheduler()
        return {"code": 200, "message": "success", "data": s.get_status()}
    except Exception as e:
        return {"code": 200, "message": "scheduler not running", "data": {"running": False, "error": str(e)}}

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
app.include_router(stock_detail.router)
app.include_router(score_v2.router)
app.include_router(anomaly.router)
app.include_router(overview_brief.router)
app.include_router(news_v2.router)
app.include_router(backtest.router, prefix="/api/v1")
app.include_router(auth_routes.router)

from backend.services.websocket_service import websocket_endpoint, get_connection_stats

import os as _os

@app.get("/api/v1/model/status", tags=["模型"])
async def model_status():
    """获取LightGBM模型状态"""
    import json as _json
    from backend.database import SessionLocal
    from backend.models import ModelVersion

    model_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'models', 'active_auction_lgbm.pkl')
    exists = _os.path.exists(model_path)
    models = {}
    db = SessionLocal()
    try:
        active_versions = db.query(ModelVersion).filter(ModelVersion.is_active == 1).all()
        for mv in active_versions:
            try:
                feature_cols = _json.loads(mv.feature_cols) if mv.feature_cols else []
            except Exception:
                feature_cols = []
            try:
                metrics = _json.loads(mv.model_metrics) if mv.model_metrics else {}
            except Exception:
                metrics = {}
            models[mv.model_name] = {
                "version": mv.version,
                "model_path": mv.model_path,
                "feature_cols": feature_cols,
                "metrics": metrics,
                "train_start_date": mv.train_start_date,
                "train_end_date": mv.train_end_date,
                "created_at": mv.created_at.isoformat() if mv.created_at else None,
            }
    finally:
        db.close()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "enabled": exists,
            "model_path": model_path if exists else None,
            "models": models,
        }
    }

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
