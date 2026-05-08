"""
股票详情 API - 新闻、公告、研报、龙虎榜、评分拆解、次日报等
"""
import asyncio
import json as _json
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Depends, Body
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import SelectedStock, SelectionRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stock/detail", tags=["股票详情"])

# 内存缓存（可后续扩展到Redis）
class StockDetailCache:
    def __init__(self):
        self.cache = {}
        self.cache_ttl = timedelta(minutes=30)
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0
        }
    
    def get(self, ts_code: str):
        entry = self.cache.get(ts_code)
        if entry:
            if datetime.now() - entry['timestamp'] < self.cache_ttl:
                self.stats['hits'] += 1
                return entry['data']
            else:
                del self.cache[ts_code]
        self.stats['misses'] += 1
        return None
    
    def set(self, ts_code: str, data: dict):
        self.cache[ts_code] = {
            'data': data,
            'timestamp': datetime.now()
        }
        self.stats['sets'] += 1
    
    def clear(self):
        self.cache.clear()
        self.stats = {'hits': 0, 'misses': 0, 'sets': 0}
    
    def clear_stock(self, ts_code: str):
        if ts_code in self.cache:
            del self.cache[ts_code]
    
    def get_stats(self):
        return dict(self.stats)
    
    def get_size(self):
        return len(self.cache)

# 全局缓存实例
stock_detail_cache = StockDetailCache()


def _fetch_stock_detail_data(
    ts_code: str,
    stock_name: str,
    trade_date: Optional[str],
    record_id: Optional[int],
    db: Session
) -> dict:
    """获取股票详情数据（实际数据获取逻辑）"""
    # 获取新闻数据（使用数据库版集成新闻服务，速度快且不会阻塞）
    try:
        from backend.services.integrated_news_service import get_integrated_news_service
        news_svc = get_integrated_news_service()
        news_result = news_svc.get_stock_news(stock_name, limit=10, ensure_recent=False)
        news_data = news_result.get("data", {})
        news = {
            "success": True,
            "articles": [{
                "title": n.get("title", ""),
                "content": n.get("content", ""),
                "publish_time": n.get("publish_time", ""),
                "source": n.get("source_name", ""),
            } for n in news_data.get("news_list", [])],
            "total": news_data.get("total_count", 0),
        }
        announcements = {"success": False, "articles": [], "total": 0, "error": "公告功能已合并到新闻模块"}
        research = {"success": False, "articles": [], "total": 0, "error": "研报功能已合并到新闻模块"}
        news_svc.close()
    except Exception as e:
        logger.warning(f"新闻服务调用失败 (不影响主流程): {e}")
        news = {"success": False, "articles": [], "total": 0, "error": str(e)}
        announcements = {"success": False, "articles": [], "total": 0, "error": str(e)}
        research = {"success": False, "articles": [], "total": 0, "error": str(e)}

    score_data = {}
    next_day_plan_data = {}
    limitup_data = {}
    stock_basic = {"ts_code": ts_code, "name": stock_name}

    if record_id:
        stock_db = db.query(SelectedStock).filter(
            SelectedStock.record_id == record_id,
            SelectedStock.ts_code == ts_code,
        ).first()
        if stock_db:
            stock_basic = {
                "ts_code": stock_db.ts_code,
                "name": stock_db.name,
                "close_price": stock_db.close_price,
                "change_pct": stock_db.change_pct,
                "pre_change_pct": stock_db.pre_change_pct,
                "open_change_pct": stock_db.open_change_pct,
                "circ_mv": stock_db.circ_mv,
                "industry": stock_db.industry,
                "trade_date": trade_date or getattr(stock_db.record, 'trade_date', None) if hasattr(stock_db, 'record') else trade_date,
            }
            score_data = {
                "rule_score": float(stock_db.rule_score) if stock_db.rule_score else None,
                "model_score": float(stock_db.model_score) if stock_db.model_score else None,
                "final_score": float(stock_db.final_score) if stock_db.final_score else None,
                "score_level": stock_db.score_level,
                "score_breakdown": _json.loads(stock_db.score_breakdown) if stock_db.score_breakdown else {},
                "reasons": stock_db.reasons.split("; ") if stock_db.reasons else [],
                "risk_tags": _json.loads(stock_db.risk_tags) if stock_db.risk_tags else [],
            }
            try:
                next_day_plan_data = _json.loads(stock_db.next_day_plan) if stock_db.next_day_plan else {}
            except Exception:
                next_day_plan_data = {}
            limitup_data = {
                "limit_up_count": stock_db.limit_up_count,
                "touch_days": stock_db.touch_days,
                "limit_up_days": stock_db.limit_up_days,
                "seal_rate": stock_db.seal_rate,
                "rise_10d_pct": stock_db.rise_10d_pct,
                "pre_change_pct": stock_db.pre_change_pct,
                "tags": [],
                "summary": "",
            }
            if stock_db.seal_rate is not None:
                if stock_db.seal_rate >= 90:
                    limitup_data["tags"].append("封板率高")
                elif stock_db.seal_rate >= 70:
                    limitup_data["tags"].append("封板率一般")
                if stock_db.limit_up_count and stock_db.limit_up_count >= 5:
                    limitup_data["tags"].append("活跃涨停股")
                limitup_data["summary"] = (
                    f"近100日涨停{stock_db.limit_up_count or 0}次，触板{stock_db.touch_days or 0}次，"
                    f"封板率{stock_db.seal_rate:.1f}%"
                )

    return {
        "ts_code": ts_code,
        "trade_date": trade_date,
        "basic": stock_basic,
        "score": score_data,
        "news": news,
        "announcements": announcements,
        "research": research,
        "limitup": limitup_data,
        "lhb": {"data_status": "not_integrated", "message": "龙虎榜功能暂未接入，数据源未配置（not_integrated）"},
        "earnings": {"data_status": "not_integrated", "message": "业绩排雷功能暂未接入，财务数据源未配置（not_integrated）"},
        "risk": {},
        "next_day_plan": next_day_plan_data,
        "source_status": {
            "news": "ok" if news.get("success") else news.get("error", "unavailable"),
            "announcements": "ok" if announcements.get("success") else announcements.get("error", "unavailable"),
            "research": "ok" if research.get("success") else research.get("error", "unavailable"),
            "score": "ok" if score_data else "not_found",
        },
    }


@router.get("/news")
async def get_stock_news(
    stock_name: str = Query(..., description="股票名称（必填，用于新闻搜索）"),
    ts_code: str = Query(None, description="股票代码（可选）"),
    limit: int = Query(10, ge=1, le=50, description="返回条数"),
    trade_date: str = Query(None, description="交易日期（用于确定新闻时间范围）"),
):
    """
    获取股票相关新闻（数据来源：财联社+同花顺，按股票名称匹配，默认近5个交易日）
    """
    from backend.services.integrated_news_service import get_integrated_news_service
    from backend.services.news_sentiment.analyzer import analyze_news_event
    svc = get_integrated_news_service()
    result = svc.get_stock_news(stock_name, limit=limit, ensure_recent=False)
    news_list = result.get("data", {}).get("news_list", [])
    for item in news_list:
        sent_result = analyze_news_event(item, debug=False)
        item["sentiment_type"] = sent_result["sentiment"]
        item["sentiment_score"] = sent_result["confidence"]
    svc.close()
    return {
        "code": 0,
        "message": "success",
        "data": {
            "success": True,
            "articles": news_list,
            "total": len(news_list),
        }
    }


@router.get("/announcements")
async def get_stock_announcements(
    ts_code: str = Query(...),
    stock_name: str = Query(None),
    limit: int = Query(10, ge=1, le=50),
    trade_date: str = Query(None, description="交易日期"),
):
    return {"code": 1, "message": "公告功能已合并到新闻舆情模块", "data": {"success": False, "articles": [], "total": 0}}


@router.get("/research")
async def get_stock_research(
    ts_code: str = Query(...),
    stock_name: str = Query(None),
    limit: int = Query(10, ge=1, le=50),
    trade_date: str = Query(None, description="交易日期"),
):
    return {"code": 1, "message": "研报功能已合并到新闻舆情模块", "data": {"success": False, "articles": [], "total": 0}}


@router.get("")
async def get_stock_detail(
    ts_code: str = Query(..., description="股票代码"),
    stock_name: str = Query(None, description="股票名称"),
    trade_date: str = Query(None, description="交易日期"),
    record_id: int = Query(None, description="选股记录ID"),
    use_cache: bool = Query(True, description="是否使用缓存"),
    db: Session = Depends(get_db),
):
    """
    获取个股综合详情（支持缓存优先）

    返回结构:
      basic / score / news / announcements / research / limitup / lhb / earnings / risk / next_day_plan / source_status
    """
    if not stock_name:
        logger.warning(f"股票详情查询缺少股票名称: ts_code={ts_code}")
        return {
            "code": 1,
            "message": "缺少股票名称参数",
            "data": {}
        }

    # 尝试从缓存读取
    if use_cache:
        cached_data = stock_detail_cache.get(ts_code)
        if cached_data:
            logger.debug(f"缓存命中: {ts_code}")
            return {
                "code": 0,
                "message": "success (cached)",
                "data": cached_data
            }

    # 实际获取数据（带超时保护，避免阻塞事件循环）
    try:
        loop = asyncio.get_event_loop()
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_stock_detail_data, ts_code, stock_name, trade_date, record_id, db),
            timeout=25.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"股票详情获取超时: {ts_code}")
        return {
            "code": 1,
            "message": "获取超时，请稍后重试",
            "data": {
                "ts_code": ts_code,
                "basic": {"ts_code": ts_code, "name": stock_name},
                "news": {"success": False, "articles": [], "total": 0, "error": "超时"},
            }
        }
    
    # 写入缓存
    if use_cache:
        stock_detail_cache.set(ts_code, data)
    
    return {
        "code": 0,
        "message": "success",
        "data": data
    }


@router.post("/batch")
async def batch_get_stock_detail(
    requests: List[Dict[str, Any]] = Body(..., description="批量请求列表"),
    db: Session = Depends(get_db),
):
    """
    批量获取股票详情（用于预加载）
    
    请求格式:
    [
        {"ts_code": "000001.SZ", "stock_name": "平安银行", "record_id": 1},
        {"ts_code": "000002.SZ", "stock_name": "万科A", "record_id": 1}
    ]
    """
    results = []
    for req in requests:
        ts_code = req.get("ts_code")
        stock_name = req.get("stock_name")
        record_id = req.get("record_id")
        trade_date = req.get("trade_date")
        
        if not ts_code or not stock_name:
            results.append({
                "ts_code": ts_code,
                "code": 1,
                "message": "缺少必要参数",
                "data": {}
            })
            continue
        
        try:
            cached_data = stock_detail_cache.get(ts_code)
            if cached_data:
                results.append({
                    "ts_code": ts_code,
                    "code": 0,
                    "message": "success (cached)",
                    "data": cached_data
                })
            else:
                data = _fetch_stock_detail_data(ts_code, stock_name, trade_date, record_id, db)
                stock_detail_cache.set(ts_code, data)
                results.append({
                    "ts_code": ts_code,
                    "code": 0,
                    "message": "success",
                    "data": data
                })
        except Exception as e:
            logger.error(f"批量获取股票详情失败 {ts_code}: {e}")
            results.append({
                "ts_code": ts_code,
                "code": 1,
                "message": str(e),
                "data": {}
            })
    
    return {
        "code": 0,
        "message": "批量查询完成",
        "data": results,
        "total_count": len(results),
        "success_count": sum(1 for r in results if r["code"] == 0)
    }


@router.delete("/cache")
async def clear_stock_detail_cache(
    ts_code: str = Query(None, description="股票代码（为空则清空全部缓存）")
):
    """
    清空股票详情缓存
    """
    if ts_code:
        stock_detail_cache.clear_stock(ts_code)
        return {"code": 0, "message": f"已清空股票 {ts_code} 的缓存"}
    else:
        stock_detail_cache.clear()
        return {"code": 0, "message": "已清空全部股票详情缓存"}


@router.post("/preload-ai")
async def batch_preload_ai(
    requests: List[Dict[str, Any]] = Body(..., description="批量预加载请求"),
):
    """
    批量预加载AI数据（综合概览+异动解读）- 后台执行，不阻塞响应
    用于选股完成后批量预热，用户点开个股详情时直接命中缓存
    """
    loop = asyncio.get_event_loop()
    results = []

    for req in requests:
        ts_code = req.get("ts_code")
        stock_name = req.get("stock_name")
        trade_date = req.get("trade_date")
        record_id = req.get("record_id")

        if not ts_code or not stock_name:
            results.append({"ts_code": ts_code, "code": 1, "message": "缺少参数"})
            continue

        # 后台异步预热（不阻塞响应，不需要立即完成）
        loop.run_in_executor(None, _warm_ai_for_stock, ts_code, stock_name, trade_date, record_id)
        results.append({"ts_code": ts_code, "code": 0, "message": "已加入预热队列", "stock_name": stock_name})

    return {
        "code": 0,
        "message": f"已提交 {len(requests)} 条预热任务",
        "data": results
    }


def _warm_ai_for_stock(ts_code: str, stock_name: str, trade_date: Optional[str], record_id: Optional[int]):
    """在后台线程中预热AI数据（概览+异动解读并行）"""
    from concurrent.futures import ThreadPoolExecutor

    def _warm_overview():
        from backend.services.ai_brief.overview_brief_service import OverviewBriefService
        OverviewBriefService.get_or_build(ts_code, stock_name, trade_date, record_id)
        logger.info(f"[预热] 综合概览完成: {ts_code}")

    def _warm_anomaly():
        from backend.services.anomaly_interpretation.interpreter_service import get_anomaly_interpretation
        get_anomaly_interpretation(ts_code, stock_name, trade_date, force_refresh=False)
        logger.info(f"[预热] 异动解读完成: {ts_code}")

    logger.info(f"[预热] 并行启动 AI 生成: {ts_code} {stock_name}")
    pool = ThreadPoolExecutor(max_workers=2)
    pool.submit(_warm_overview)
    pool.submit(_warm_anomaly)
    pool.shutdown(wait=False)


@router.get("/cache/stats")
async def get_cache_stats():
    """
    获取缓存统计信息
    """
    return {
        "code": 0,
        "message": "success",
        "data": {
            "stats": stock_detail_cache.get_stats(),
            "cache_size": stock_detail_cache.get_size(),
            "cache_ttl_minutes": stock_detail_cache.cache_ttl.total_seconds() / 60
        }
    }


@router.get("/lhb")
async def get_stock_lhb(
    ts_code: str = Query(..., description="股票代码"),
    trade_date: str = Query(None, description="交易日期"),
    force_refresh: bool = Query(False, description="是否强制刷新"),
):
    """获取个股龙虎榜数据"""
    from backend.services.lhb_service import analyze_lhb
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, analyze_lhb, ts_code, trade_date, force_refresh),
            timeout=30.0
        )
        # 清洗所有 NaN 为 None，确保 JSON 序列化不会报错
        result = _clean_nan(result)
        return {
            "code": 0,
            "message": "success",
            "data": result
        }
    except asyncio.TimeoutError:
        return {"code": 1, "message": "获取超时", "data": {"data_status": "timeout"}}
    except Exception as e:
        return {"code": 1, "message": str(e), "data": {"data_status": "error"}}


def _clean_nan(obj):
    """递归清洗 NaN → None + numpy类型→Python原生类型，确保 JSON 安全"""
    import math
    # numpy 类型兜底：转 Python 原生类型
    try:
        if hasattr(obj, 'dtype') and hasattr(obj, 'item'):
            item = obj.item()
            if isinstance(item, float) and math.isnan(item):
                return None
            return item
    except Exception:
        pass
    if isinstance(obj, float) and math.isnan(obj):
        return None
    elif isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(_clean_nan(v) for v in obj)
    return obj


@router.get("/risk")
async def get_stock_risk(
    ts_code: str = Query(..., description="股票代码"),
    trade_date: str = Query(None, description="交易日期"),
    force_refresh: bool = Query(False, description="是否强制刷新"),
    strategy_type: str = Query("normal", description="策略类型: normal(普通) / dragon_leader(龙头战法)"),
    stock_name: str = Query(None, description="股票名称(龙头战法模式需要)"),
):
    """获取个股风险拆解（支持普通风险模型和龙头战法模型）"""
    if strategy_type == "dragon_leader":
        from backend.services.dragon_leader import calculate_dragon_leader_score
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, calculate_dragon_leader_score, ts_code, trade_date, stock_name, force_refresh),
                timeout=60.0
            )
            return {"code": 0, "message": "success", "data": result}
        except asyncio.TimeoutError:
            return {"code": 1, "message": "获取超时", "data": {"data_status": "timeout"}}
        except Exception as e:
            return {"code": 1, "message": str(e), "data": {"data_status": "error"}}

    from backend.services.risk_breakdown_service import calculate_risk
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, calculate_risk, ts_code, trade_date, force_refresh),
            timeout=30.0
        )
        result = _clean_nan(result)
        return {"code": 0, "message": "success", "data": result}
    except asyncio.TimeoutError:
        return {"code": 1, "message": "获取超时", "data": {"data_status": "timeout"}}
    except Exception as e:
        return {"code": 1, "message": str(e), "data": {"data_status": "error"}}