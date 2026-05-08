"""
异动解读 API
"""
import asyncio
import logging
from fastapi import APIRouter, Query
from backend.schemas.common import ApiResponse
from backend.services.anomaly_interpretation.interpreter_service import get_anomaly_interpretation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stock", tags=["异动解读"])


@router.get("/anomaly-interpretation")
async def anomaly_interpretation(
    ts_code: str = Query(..., description="股票代码"),
    stock_name: str = Query(None, description="股票名称"),
    trade_date: str = Query(None, description="交易日期"),
    force_refresh: bool = Query(False, description="是否强制刷新，忽略缓存"),
):
    """获取个股异动解读（同花顺1:1复刻版，含AI分析，带缓存）"""
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, get_anomaly_interpretation, ts_code, stock_name, trade_date, force_refresh),
            timeout=60.0
        )
        return ApiResponse(code=200, message="success", data=result)
    except asyncio.TimeoutError:
        logger.warning(f"异动解读生成超时: {ts_code}")
        return ApiResponse(code=408, message="生成超时，请稍后重试", data={
            "stock_code": ts_code,
            "data_status": "timeout",
            "core_tags_line": "无明确催化",
            "company_reasons": ["服务超时"],
        })
