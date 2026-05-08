"""
综合概览API路由
"""
import asyncio
import logging
from fastapi import APIRouter, Query
from backend.schemas.common import ApiResponse
from backend.services.ai_brief.overview_brief_service import OverviewBriefService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stock", tags=["综合概览"])


@router.get("/overview-brief")
async def get_overview_brief(
    ts_code: str = Query(..., description="股票代码"),
    stock_name: str = Query(None, description="股票名称"),
    trade_date: str = Query(None, description="交易日期"),
    record_id: int = Query(None, description="选股记录ID"),
):
    """获取个股综合概览（AI生成/fallback，带缓存）"""
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, OverviewBriefService.get_or_build, ts_code, stock_name, trade_date, record_id),
            timeout=60.0
        )
        return ApiResponse(code=200, message="success", data=result)
    except asyncio.TimeoutError:
        logger.warning(f"综合概览生成超时: {ts_code}")
        return ApiResponse(code=408, message="生成超时，请稍后重试", data={
            "stock_code": ts_code,
            "data_status": "timeout",
            "brief": "综合概览生成超时，请稍后重试",
            "ai_suggestion": "只观察",
            "positive_tags": [],
            "negative_tags": [],
        })
