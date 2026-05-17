"""
选股 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from backend.database import get_db
from backend.schemas import (
    ApiResponse,
    SelectRequest,
)
from backend.services.stock_selector import select_stocks
from backend.models import SelectionRecord, SelectedStock
from backend.models.stock_risk import DragonLeaderScore
from backend.utils.trading_date import get_latest_trading_day
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

T0_MODEL_DISCLAIMER = "T+0成功率由历史样本模型估算，仅作排序参考，不构成投资建议；模型不可用时显示为空且不影响最终评分。"

# 注入的 MCP 函数
_tdx_mcp_func = None


def _float_or_none(value):
    return float(value) if value is not None else None


def set_tdx_mcp_func(func):
    """设置通达信 MCP 函数"""
    global _tdx_mcp_func
    _tdx_mcp_func = func


def _get_stock_display_fallback(
    db: Session,
    ts_code: str,
    trade_date: str,
    cache: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """补齐最新选股记录缺失的涨停标签/题材展示字段"""
    if ts_code in cache:
        return cache[ts_code]

    fallback: Dict[str, Any] = {}

    previous = db.query(SelectedStock).join(
        SelectionRecord, SelectedStock.record_id == SelectionRecord.id
    ).filter(
        SelectionRecord.trade_date == trade_date,
        SelectionRecord.status == "success",
        SelectedStock.ts_code == ts_code,
    ).order_by(
        (SelectedStock.lu_desc.isnot(None)).desc(),
        (SelectedStock.concept.isnot(None)).desc(),
        SelectionRecord.id.desc(),
    ).first()

    if previous:
        fallback.update({
            "industry": previous.industry,
            "concept": previous.concept,
            "board_type": previous.board_type,
            "lu_desc": previous.lu_desc,
            "lu_tag": previous.lu_tag,
            "lu_status": previous.lu_status,
            "lu_open_num": previous.lu_open_num,
            "limit_up_suc_rate": previous.limit_up_suc_rate,
            "latest_lu_date": previous.latest_lu_date,
        })

    if not fallback.get("lu_desc") or not fallback.get("lu_tag"):
        try:
            from backend.services.data_collector import TushareDataCollector
            df = TushareDataCollector().get_limit_list_ths(
                ts_code=ts_code,
                trade_date=trade_date,
                limit_type="涨停池",
            )
            if df is not None and not df.empty:
                row = df.iloc[0]
                fallback.update({
                    "lu_desc": row.get("lu_desc"),
                    "lu_tag": row.get("tag"),
                    "lu_status": row.get("status"),
                    "lu_open_num": int(row.get("open_num", 0) or 0),
                    "limit_up_suc_rate": float(row.get("limit_up_suc_rate", 0) or 0),
                    "latest_lu_date": str(row.get("trade_date", "") or ""),
                })
        except Exception as e:
            logger.warning(f"涨停字段展示兜底失败 {ts_code}: {e}")

    if not fallback.get("concept") and not fallback.get("board_type"):
        try:
            from backend.services.dragon_leader.data.theme_context import ThemeContext
            concepts = ThemeContext().get_stock_concepts(ts_code, trade_date)
            names = [c.get("name", "") for c in concepts if c.get("name")]
            if names:
                fallback["concept"] = "、".join(names[:5])
        except Exception as e:
            logger.warning(f"题材字段展示兜底失败 {ts_code}: {e}")

    cache[ts_code] = fallback
    return fallback


@router.get("/stock/trading-date", tags=["选股"])
async def get_trading_date():
    """获取最新交易日"""
    try:
        trading_date = get_latest_trading_day()
        return ApiResponse(
            code=200,
            message="success",
            data={"trading_date": trading_date}
        )
    except Exception as e:
        logger.error(f"获取交易日失败: {e}")
        return ApiResponse(
            code=500,
            message=f"获取交易日失败: {e}"
        )


@router.post("/stock/select", response_model=None, tags=["选股"])
async def execute_selection(
    request: SelectRequest,
    db: Session = Depends(get_db)
):
    """执行选股任务"""
    try:
        # 记录请求参数
        logger.info(f"选股请求参数: strategy_id={request.strategy_id}, task_template={request.task_template}, min_seal_rate={request.min_seal_rate}, min_open_change_pct={request.min_open_change_pct}")
        
        # 根据 strategy_id 获取策略配置
        min_seal_rate = request.min_seal_rate
        min_open_change_pct = request.min_open_change_pct
        
        if request.strategy_id:
            from backend.services.strategy_service import StrategyTemplateService
            service = StrategyTemplateService(db)
            strategy = service.get_strategy(request.strategy_id)
            if strategy:
                config = strategy.conditions_config or {}
                # 从策略配置中提取参数
                if min_seal_rate is None:
                    min_seal_rate = config.get("limit_up", {}).get("min_seal_rate")
                if min_open_change_pct is None:
                    min_open_change_pct = config.get("open_change", {}).get("min_open_change_pct")
                logger.info(f"从策略 {strategy.name} 提取参数: min_seal_rate={min_seal_rate}, min_open_change_pct={min_open_change_pct}")
        
        # 确保任务模板正确
        task_template = request.task_template
        if request.strategy_id and not task_template:
            from backend.services.strategy_service import StrategyTemplateService
            service = StrategyTemplateService(db)
            strategy = service.get_strategy(request.strategy_id)
            if strategy:
                task_template = strategy.task_template
                logger.info(f"从策略 {strategy.name} 提取任务模板: {task_template}")

        # 使用注入的 MCP 函数
        result = select_stocks(
            trade_date=request.trade_date,
            task_template=task_template or "default",
            custom_tasks=request.custom_tasks,
            save_result=True,
            tdx_mcp_func=_tdx_mcp_func,
            min_seal_rate=min_seal_rate,
            period_days=request.period_days,
            min_open_change_pct=min_open_change_pct
        )

        if request.notify and result.get("passed_count", 0) > 0:
            from backend.services.notification import FeishuNotifier
            notifier = FeishuNotifier()
            notification_sent = notifier.send_selection_result(result)
            result["notification_sent"] = notification_sent

        return ApiResponse(code=200, message="选股完成", data=result)

    except Exception as e:
        logger.error(f"选股执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"选股执行失败: {str(e)}")


@router.get("/stock/results", response_model=None, tags=["选股"])
async def get_selection_results(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取选股结果列表"""
    try:
        offset = (page - 1) * page_size
        
        # 计算总数
        total_count = db.query(func.count(SelectionRecord.id)).scalar()

        # 获取记录
        records = db.query(SelectionRecord)\
            .order_by(SelectionRecord.created_at.desc())\
            .offset(offset)\
            .limit(page_size)\
            .all()

        result_records = []
        for record in records:
            result_records.append({
                "id": record.id,
                "execute_time": record.execute_time.isoformat() if record.execute_time else None,
                "trade_date": record.trade_date,
                "total_count": record.total_count,
                "status": record.status,
                "execution_time": record.execution_time,
                "notification_sent": record.notification_sent
            })

        return ApiResponse(
            code=200,
            message="success",
            data={
                "records": result_records,
                "total": total_count,
                "page": page,
                "page_size": page_size
            }
        )
    except Exception as e:
        logger.error(f"查询选股记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/stock/results/{record_id}", response_model=None, tags=["选股"])
async def get_selection_detail(
    record_id: int,
    db: Session = Depends(get_db)
):
    """获取选股结果详情"""
    try:
        record = db.query(SelectionRecord).filter(SelectionRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")

        stocks = db.query(SelectedStock).filter(SelectedStock.record_id == record_id).all()

        stock_list = []
        fallback_cache: Dict[str, Dict[str, Any]] = {}
        for stock in stocks:
            import json as _json
            fallback = _get_stock_display_fallback(db, stock.ts_code, record.trade_date, fallback_cache)
            stock_list.append({
                "ts_code": stock.ts_code,
                "name": stock.name,
                "close_price": stock.close_price,
                "change_pct": stock.change_pct,
                "pre_change_pct": stock.pre_change_pct,
                "open_change_pct": stock.open_change_pct,
                "auction_ratio": stock.auction_ratio,
                "auction_turnover_rate": stock.auction_turnover_rate,
                "limit_up_count": stock.limit_up_count,
                "touch_days": stock.touch_days,
                "limit_up_days": stock.limit_up_days,
                "seal_rate": stock.seal_rate,
                "rise_10d_pct": stock.rise_10d_pct,
                "circ_mv": stock.circ_mv,
                "industry": stock.industry or fallback.get("industry"),
                "concept": stock.concept or fallback.get("concept"),
                "board_type": stock.board_type or fallback.get("board_type"),
                "rule_score": _float_or_none(stock.rule_score),
                "model_score": _float_or_none(stock.model_score),
                "t0_limit_success_prob": _float_or_none(stock.t0_limit_success_prob),
                "t0_limit_success_model_version": stock.t0_limit_success_model_version,
                "default_t0_limit_prob": _float_or_none(stock.default_t0_limit_prob),
                "default_t1_premium_prob": _float_or_none(stock.default_t1_premium_prob),
                "default_t1_continue_prob": _float_or_none(stock.default_t1_continue_prob),
                "default_relay_score": _float_or_none(stock.default_relay_score),
                "default_relay_model_version": stock.default_relay_model_version,
                "final_score": _float_or_none(stock.final_score),
                "score_level": stock.score_level,
                "reasons": stock.reasons.split("; ") if stock.reasons else [],
                "risk_tags": _json.loads(stock.risk_tags) if stock.risk_tags else [],
                "record_id": record_id,
                # 龙头战法评分
                "leader_strength_score": None,
                "retreat_risk_score": None,
                "health_score": None,
                "leader_level": None,
                "cycle_stage": None,
                # 同花顺涨停榜单数据
                "lu_desc": stock.lu_desc or fallback.get("lu_desc"),
                "lu_tag": stock.lu_tag or fallback.get("lu_tag"),
                "lu_status": stock.lu_status or fallback.get("lu_status"),
                "lu_open_num": stock.lu_open_num if stock.lu_open_num is not None else fallback.get("lu_open_num"),
                "limit_up_suc_rate": _float_or_none(stock.limit_up_suc_rate) if stock.limit_up_suc_rate is not None else fallback.get("limit_up_suc_rate"),
                "latest_lu_date": stock.latest_lu_date or fallback.get("latest_lu_date"),
                # 上一日换手率
                "prev_turnover_rate": _float_or_none(stock.prev_turnover_rate),
            })

        result = {
            "id": record.id,
            "execute_time": record.execute_time.isoformat() if record.execute_time else None,
            "trade_date": record.trade_date,
            "total_count": record.total_count,
            "status": record.status,
            "execution_time": record.execution_time,
            "notification_sent": record.notification_sent,
            "t0_model_disclaimer": T0_MODEL_DISCLAIMER,
            "stocks": stock_list
        }

        # 批量填充龙头战法评分
        if stock_list and record.trade_date:
            ts_codes = [s["ts_code"] for s in stock_list]
            dl_records = db.query(DragonLeaderScore).filter(
                DragonLeaderScore.ts_code.in_(ts_codes),
                DragonLeaderScore.trade_date == record.trade_date,
            ).all()
            dl_map = {r.ts_code: r for r in dl_records}
            for s in stock_list:
                dl = dl_map.get(s["ts_code"])
                if dl:
                    s["leader_strength_score"] = dl.leader_strength_score
                    s["retreat_risk_score"] = dl.retreat_risk_score
                    s["health_score"] = dl.health_score
                    s["leader_level"] = dl.leader_level
                    s["cycle_stage"] = dl.cycle_stage

        return ApiResponse(code=200, message="success", data=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询选股详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.delete("/stock/results/{record_id}", response_model=None, tags=["选股"])
async def delete_selection_record(
    record_id: int,
    db: Session = Depends(get_db)
):
    """删除单条选股记录"""
    try:
        record = db.query(SelectionRecord).filter(SelectionRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")

        db.delete(record)
        db.commit()

        logger.info(f"选股记录已删除: ID={record_id}")
        return ApiResponse(code=200, message="删除成功", data={"deleted_id": record_id})

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除选股记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/stock/results/batch-delete", response_model=None, tags=["选股"])
async def batch_delete_selection_records(
    ids: List[int],
    db: Session = Depends(get_db)
):
    """批量删除选股记录"""
    try:
        if not ids:
            raise HTTPException(status_code=422, detail="请提供要删除的记录ID列表")

        records = db.query(SelectionRecord).filter(SelectionRecord.id.in_(ids)).all()
        if not records:
            raise HTTPException(status_code=404, detail="未找到指定的记录")

        deleted_count = len(records)
        for record in records:
            db.delete(record)
        db.commit()

        logger.info(f"批量删除选股记录成功: IDs={ids}, 共{deleted_count}条")
        return ApiResponse(code=200, message="批量删除成功", data={
            "deleted_ids": ids,
            "deleted_count": deleted_count
        })

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"批量删除选股记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")
