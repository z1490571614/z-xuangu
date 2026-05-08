"""
评分V2 API路由
"""
import asyncio
import json
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.scoring_v2 import StockScoreV2, StockScoreBreakdownV2, StockRiskBreakdownV2
from backend.schemas.common import ApiResponse

router = APIRouter(prefix="/api/v1/score-v2", tags=["评分V2"])


@router.get("/detail")
async def get_score_v2_detail(
    ts_code: str = Query(..., description="股票代码"),
    trade_date: str = Query(None, description="交易日期"),
    record_id: int = Query(None, description="选股记录ID"),
    db: Session = Depends(get_db),
):
    """获取评分V2详情（含评分拆解+风险拆解+决策建议）"""
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_score_detail, ts_code, trade_date, record_id, db),
            timeout=15.0
        )
        return ApiResponse(code=200, message="success", data=result)
    except asyncio.TimeoutError:
        return ApiResponse(code=408, message="查询超时", data=None)


def _fetch_score_detail(ts_code: str, trade_date: str, record_id: int, db: Session) -> dict:
    """同步执行评分V2数据查询"""
    from backend.models.scoring_v2 import StockScoreV2, StockScoreBreakdownV2, StockRiskBreakdownV2
    
    query = db.query(StockScoreV2).filter(StockScoreV2.stock_code == ts_code)
    if record_id:
        query = query.filter(StockScoreV2.selection_record_id == record_id)
    if trade_date:
        query = query.filter(StockScoreV2.trade_date == trade_date)
    score = query.order_by(StockScoreV2.created_at.desc()).first()

    if not score:
        return None

    breakdown = db.query(StockScoreBreakdownV2).filter(
        StockScoreBreakdownV2.score_id == score.id
    ).first()
    risk_breakdown = db.query(StockRiskBreakdownV2).filter(
        StockRiskBreakdownV2.score_id == score.id
    ).first()

    result = {
        "stock_code": score.stock_code,
        "stock_name": score.stock_name,
        "trade_date": score.trade_date,
        "score": {
            "alpha_score": score.alpha_score,
            "risk_score": score.risk_score,
            "model_score": score.model_score,
            "raw_score": score.raw_score,
            "final_score": score.final_score,
            "score_grade": score.score_grade,
        },
        "model_prediction": {
            "success_prob": score.model_success_prob,
            "expected_return": score.model_expected_return,
            "expected_drawdown": score.model_expected_drawdown,
            "reward_risk_ratio": score.reward_risk_ratio,
        },
        "decision": {
            "action_level": score.action_level,
            "position_suggestion": score.position_suggestion,
            "entry_suggestion": score.entry_suggestion,
            "stop_loss_suggestion": score.stop_loss_suggestion,
            "take_profit_suggestion": score.take_profit_suggestion,
        },
        "explanation": score.explanation,
        "risk_flags": json.loads(score.risk_flags) if score.risk_flags else [],
    }

    if breakdown:
        try:
            items = json.loads(breakdown.limitup_structure_detail) if breakdown.limitup_structure_detail else []
            if items and isinstance(items, list) and len(items) > 0 and isinstance(items[0], dict) and "name" in items[0]:
                result["alpha_breakdown"] = items
            else:
                result["alpha_breakdown"] = {
                    "limitup_structure_score": breakdown.limitup_structure_score,
                    "seal_quality_score": breakdown.seal_quality_score,
                    "auction_strength_score": breakdown.auction_strength_score,
                    "trend_momentum_score": breakdown.trend_momentum_score,
                    "volume_price_score": breakdown.volume_price_score,
                    "sector_strength_score": breakdown.sector_strength_score,
                }
        except Exception:
            result["alpha_breakdown"] = {
                "limitup_structure_score": breakdown.limitup_structure_score,
                "seal_quality_score": breakdown.seal_quality_score,
                "auction_strength_score": breakdown.auction_strength_score,
                "trend_momentum_score": breakdown.trend_momentum_score,
                "volume_price_score": breakdown.volume_price_score,
                "sector_strength_score": breakdown.sector_strength_score,
            }

    if risk_breakdown:
        try:
            items = json.loads(risk_breakdown.high_position_detail) if risk_breakdown.high_position_detail else []
            if items and isinstance(items, list) and len(items) > 0 and isinstance(items[0], dict) and "name" in items[0]:
                result["risk_breakdown"] = items
            else:
                result["risk_breakdown"] = {
                    "high_position_risk": risk_breakdown.high_position_risk,
                    "open_board_risk": risk_breakdown.open_board_risk,
                    "liquidity_risk": risk_breakdown.liquidity_risk,
                    "sentiment_risk": risk_breakdown.sentiment_risk,
                    "sector_laggard_risk": risk_breakdown.sector_laggard_risk,
                    "news_risk": risk_breakdown.news_risk,
                    "capital_structure_risk": risk_breakdown.capital_structure_risk,
                    "volatility_risk": risk_breakdown.volatility_risk,
                }
        except Exception:
            result["risk_breakdown"] = {
                "high_position_risk": risk_breakdown.high_position_risk,
                "open_board_risk": risk_breakdown.open_board_risk,
                "liquidity_risk": risk_breakdown.liquidity_risk,
                "sentiment_risk": risk_breakdown.sentiment_risk,
                "sector_laggard_risk": risk_breakdown.sector_laggard_risk,
                "news_risk": risk_breakdown.news_risk,
                "capital_structure_risk": risk_breakdown.capital_structure_risk,
                "volatility_risk": risk_breakdown.volatility_risk,
            }

    return result


@router.get("/list")
async def get_score_v2_list(
    trade_date: str = Query(None, description="交易日期"),
    record_id: int = Query(None, description="选股记录ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取评分V2列表"""
    query = db.query(StockScoreV2)
    if trade_date:
        query = query.filter(StockScoreV2.trade_date == trade_date)
    if record_id:
        query = query.filter(StockScoreV2.selection_record_id == record_id)

    total = query.count()
    records = query.order_by(StockScoreV2.final_score.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for s in records:
        items.append({
            "stock_code": s.stock_code,
            "stock_name": s.stock_name,
            "alpha_score": s.alpha_score,
            "risk_score": s.risk_score,
            "final_score": s.final_score,
            "score_grade": s.score_grade,
            "action_level": s.action_level,
            "position_suggestion": s.position_suggestion,
            "risk_flags": json.loads(s.risk_flags) if s.risk_flags else [],
            "explanation": s.explanation,
        })

    return ApiResponse(code=200, message="success", data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })
