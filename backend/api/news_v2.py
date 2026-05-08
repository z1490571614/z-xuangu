"""
新闻舆情V2 API - 优先从数据库获取，情感由底层模块实时分析
"""
import logging
import re
from fastapi import APIRouter, Query
from backend.schemas.common import ApiResponse
from backend.services.integrated_news_service import get_integrated_news_service
from backend.services.news_sentiment.analyzer import analyze_news_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stock", tags=["新闻舆情V2"])


@router.get("/news-v2")
async def get_stock_news_v2(
    ts_code: str = Query(..., description="股票代码"),
    stock_name: str = Query(None, description="股票名称"),
    trade_date: str = Query(None, description="交易日期(YYYYMMDD)"),
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
    use_ai: bool = Query(False, description="是否使用AI二次校验"),
    deduplicate: bool = Query(True, description="是否去重"),
    stock_sector: str = Query(None, description="所属板块"),
    ensure_recent: bool = Query(True, description="是否确保数据最新")
):
    """
    获取个股新闻（V2版，优先从数据库获取）
    
    Returns:
        {
            code: 200,
            message: str,
            data: {
                news_list: [...],
                total_count: int,
                source_distribution: {...},
                update_time: str,
                ts_code: str,
                stock_name: str
            }
        }
    """
    try:
        # 使用集成新闻服务（优先从数据库获取）
        news_service = get_integrated_news_service()
        
        # 如果没有提供股票名称，从股票代码提取
        if not stock_name:
            stock_name = ts_code.split(".")[0]  # 从代码提取，可能不准确
        
        result = news_service.get_stock_news(
            stock_name=stock_name,
            limit=limit,
            ensure_recent=ensure_recent
        )
        
        # 用底层情感引擎实时分析（取代入库时分析）
        news_list = result.get("data", {}).get("news_list", [])
        for item in news_list:
            item["stock_name"] = stock_name
            item["ts_code"] = ts_code
            sent_result = analyze_news_event(item, debug=False)
            item["sentiment_type"] = sent_result["sentiment"]
            item["sentiment_score"] = sent_result["confidence"]
        
        # 添加股票代码到结果中
        if result.get("data"):
            result["data"]["ts_code"] = ts_code
        
        news_service.close()
        
        return ApiResponse(
            code=result["code"],
            message=result["message"],
            data=result.get("data")
        )
    except Exception as e:
        logger.error(f"获取新闻舆情V2失败: {e}", exc_info=True)
        return ApiResponse(
            code=500,
            message=f"获取新闻失败: {str(e)}",
            data={"news_list": [], "total_count": 0, "ts_code": ts_code}
        )


@router.get("/news-v2/theme-attribution")
async def get_stock_news_theme_attribution(
    ts_code: str = Query(..., description="股票代码"),
    stock_name: str = Query(..., description="股票名称"),
    trade_date: str = Query(None, description="交易日期(YYYYMMDD)"),
    limit: int = Query(300, ge=20, le=1000, description="扫描板块新闻条数"),
    ensure_recent: bool = Query(True, description="是否确保数据最新"),
    lu_desc: str = Query("", description="涨停原因"),
    stock_sector: str = Query("", description="静态概念/所属板块，逗号或加号分隔"),
    industry: str = Query("", description="行业兜底"),
    force_refresh: bool = Query(False, description="是否忽略缓存重新抽取"),
):
    """获取个股新闻主题归因。

    与新闻情感解耦：板块盘面新闻只作为板块归因证据，不判定个股利好/利空。
    """
    news_service = get_integrated_news_service()
    try:
        concepts = [
            item.strip()
            for item in re.split(r"[+＋,，/、;；|｜\s]+", stock_sector or "")
            if item.strip()
        ]
        result = news_service.get_stock_theme_attribution(
            ts_code=ts_code,
            stock_name=stock_name,
            trade_date=trade_date or datetime.now().strftime("%Y%m%d"),
            limit=limit,
            ensure_recent=ensure_recent,
            lu_desc=lu_desc,
            static_concepts=concepts,
            industry=industry,
            force_refresh=force_refresh,
        )
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error(f"获取新闻主题归因失败: {e}", exc_info=True)
        return ApiResponse(
            code=500,
            message=f"获取新闻主题归因失败: {str(e)}",
            data={
                "ts_code": ts_code,
                "stock_name": stock_name,
                "primary_theme": "",
                "theme_relations": [],
                "candidate_themes": [],
            },
        )
    finally:
        news_service.close()


@router.get("/scheduler/status")
async def get_scheduler_status():
    """获取新闻调度器状态"""
    try:
        from backend.services.news_scheduler import get_news_scheduler
        scheduler = get_news_scheduler()
        status = scheduler.get_status()
        return ApiResponse(code=200, message="success", data=status)
    except Exception as e:
        logger.warning(f"获取调度器状态失败: {e}")
        return ApiResponse(code=200, message="scheduler not running", data={
            "running": False,
            "error": str(e)
        })


@router.get("/news-v2/db-stats")
async def get_news_db_stats():
    """
    获取新闻数据库统计信息
    
    Returns:
        {
            code: 200,
            message: str,
            data: {
                total_count: int,
                cls_count: int,
                jqka_count: int,
                update_time: str
            }
        }
    """
    news_service = get_integrated_news_service()
    
    result = {
        "code": 200,
        "message": "success",
        "data": {
            "total_count": news_service.get_news_count(),
            "cls_count": news_service.get_news_count("cls"),
            "jqka_count": news_service.get_news_count("10jqka"),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }
    
    news_service.close()
    
    return result


from datetime import datetime
