"""
评分V2主服务 - 编排分层评分流程
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from backend.database import SessionLocal
from backend.models.scoring_v2 import StockScoreV2, StockScoreBreakdownV2, StockRiskBreakdownV2
from backend.services.scoring_v2.alpha_score_service import AlphaScoreService
from backend.services.scoring_v2.risk_score_service import RiskScoreService
from backend.services.scoring_v2.final_score_service import FinalScoreService
from backend.services.scoring_v2.decision_engine import DecisionEngine

logger = logging.getLogger(__name__)

SCORE_VERSION = "score_v2.0"

# 全局开关（兼容阶段控制）
_score_v2_enabled = True


def set_score_v2_enabled(enabled: bool):
    global _score_v2_enabled
    _score_v2_enabled = enabled


def is_score_v2_enabled() -> bool:
    return _score_v2_enabled


class StockScoringV2Service:
    """评分V2主服务"""

    def __init__(self):
        self.alpha_service = AlphaScoreService()
        self.risk_service = RiskScoreService()
        self.final_service = FinalScoreService()
        self.decision_engine = DecisionEngine()

    def score_stock(
        self,
        stock_data: Dict[str, Any],
        selection_record_id: int,
        trade_date: str,
        has_news_positive: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """对单只股票执行完整评分V2流程"""
        if not _score_v2_enabled:
            return None

        try:
            event_driven = stock_data.get("has_news_positive") if has_news_positive is None else has_news_positive

            # 1. Alpha评分
            alpha_result = AlphaScoreService.calculate(
                limit_up_count_100d=stock_data.get("limit_up_count"),
                limit_up_days=stock_data.get("limit_up_days"),
                touch_days=stock_data.get("touch_days"),
                seal_rate=stock_data.get("seal_rate"),
                auction_ratio=stock_data.get("auction_ratio"),
                auction_turnover_rate=stock_data.get("auction_turnover_rate"),
                open_change_pct=stock_data.get("open_change_pct"),
                pre_change_pct=stock_data.get("pre_change_pct"),
                rise_10d_pct=stock_data.get("rise_10d_pct"),
                circ_mv=stock_data.get("circ_mv"),
                industry=stock_data.get("industry"),
                has_news_positive=bool(event_driven) if event_driven is not None else False,
            )

            # 2. 风险评分
            risk_result = RiskScoreService.calculate(
                rise_10d_pct=stock_data.get("rise_10d_pct"),
                pre_change_pct=stock_data.get("pre_change_pct"),
                open_change_pct=stock_data.get("open_change_pct"),
                seal_rate=stock_data.get("seal_rate"),
                limit_up_count=stock_data.get("limit_up_count"),
                touch_days=stock_data.get("touch_days"),
                limit_up_days=stock_data.get("limit_up_days"),
                auction_ratio=stock_data.get("auction_ratio"),
                auction_turnover_rate=stock_data.get("auction_turnover_rate"),
                circ_mv=stock_data.get("circ_mv"),
            )

            # 3. 最终评分（模型不可用，纯规则）
            final_result = FinalScoreService.calculate(
                alpha_score=alpha_result["total_score"],
                risk_score=risk_result["total_score"],
                model_score=None,
            )

            # 4. 决策
            decision = DecisionEngine.decide(
                final_score=final_result["final_score"],
                alpha_score=alpha_result["total_score"],
                risk_score=risk_result["total_score"],
                risk_flags=risk_result.get("risk_flags", []),
            )

            # 5. 生成解释
            explanation = self._build_explanation(
                alpha_result, risk_result, final_result, decision
            )

            # 6. 保存到数据库
            db = SessionLocal()
            try:
                score_record = StockScoreV2(
                    selection_record_id=selection_record_id,
                    stock_code=stock_data["ts_code"],
                    stock_name=stock_data.get("name"),
                    trade_date=trade_date,
                    alpha_score=round(alpha_result["total_score"], 2),
                    risk_score=round(risk_result["total_score"], 2),
                    raw_score=round(final_result["raw_score"], 2),
                    final_score=round(final_result["final_score"], 2),
                    score_grade=final_result["grade"],
                    action_level=decision["action_level"],
                    position_suggestion=decision["position_suggestion"],
                    entry_suggestion=decision["entry_suggestion"],
                    stop_loss_suggestion=decision.get("stop_loss_suggestion", ""),
                    take_profit_suggestion=decision.get("take_profit_suggestion", ""),
                    explanation=explanation,
                    risk_flags=json.dumps(risk_result.get("risk_flags", []), ensure_ascii=False),
                    score_version=SCORE_VERSION,
                )
                db.add(score_record)
                db.flush()

                # 保存Alpha评分拆解 — 使用新的items格式
                alpha_items = alpha_result.get("items", [])
                bd_record = StockScoreBreakdownV2(
                    score_id=score_record.id,
                    limitup_structure_score=alpha_items[0].get("score") if len(alpha_items) > 0 else 0,
                    seal_quality_score=alpha_items[1].get("score") if len(alpha_items) > 1 else 0,
                    auction_strength_score=alpha_items[2].get("score") if len(alpha_items) > 2 else 0,
                    trend_momentum_score=alpha_items[3].get("score") if len(alpha_items) > 3 else 0,
                    volume_price_score=alpha_items[4].get("score") if len(alpha_items) > 4 else 0,
                    sector_strength_score=alpha_items[5].get("score") if len(alpha_items) > 5 else 0,
                    limitup_structure_detail=json.dumps(alpha_items, ensure_ascii=False),
                )
                db.add(bd_record)

                # 保存风险评分拆解
                risk_items = risk_result.get("items", [])
                rd_record = StockRiskBreakdownV2(
                    score_id=score_record.id,
                    high_position_risk=risk_items[0].get("score") if len(risk_items) > 0 else 0,
                    open_board_risk=risk_items[2].get("score") if len(risk_items) > 2 else 0,
                    liquidity_risk=risk_items[3].get("score") if len(risk_items) > 3 else 0,
                    sentiment_risk=risk_items[4].get("score") if len(risk_items) > 4 else 0,
                    sector_laggard_risk=risk_items[5].get("score") if len(risk_items) > 5 else 0,
                    news_risk=risk_items[6].get("score") if len(risk_items) > 6 else 0,
                    capital_structure_risk=0,
                    volatility_risk=risk_items[7].get("score") if len(risk_items) > 7 else 0,
                    high_position_detail=json.dumps(risk_items, ensure_ascii=False),
                )
                db.add(rd_record)
                db.commit()

                logger.info(f"评分V2已保存: {stock_data.get('name')} alpha={alpha_result['total_score']:.1f} risk={risk_result['total_score']:.1f} final={final_result['final_score']:.1f}")
            except Exception as e:
                db.rollback()
                logger.warning(f"保存评分V2失败: {e}")
            finally:
                db.close()

            return {
                "alpha_score": round(alpha_result["total_score"], 2),
                "risk_score": round(risk_result["total_score"], 2),
                "raw_score": round(final_result["raw_score"], 2),
                "final_score": round(final_result["final_score"], 2),
                "score_grade": final_result["grade"],
                "action_level": decision["action_level"],
                "position_suggestion": decision["position_suggestion"],
                "entry_suggestion": decision["entry_suggestion"],
                "risk_flags": risk_result.get("risk_flags", []),
                "explanation": explanation,
            }

        except Exception as e:
            logger.error(f"评分V2计算失败: {e}")
            return None

    def score_batch(
        self,
        stocks_data: list,
        selection_record_id: int,
        trade_date: str,
    ) -> list:
        """批量评分"""
        results = []
        for stock in stocks_data:
            result = self.score_stock(stock, selection_record_id, trade_date)
            if result:
                stock["score_v2"] = result
                results.append(result)
            else:
                stock["score_v2"] = None
        return results

    def _build_explanation(self, alpha, risk, final, decision) -> str:
        if isinstance(alpha.get("summary"), str) and alpha["summary"]:
            return alpha["summary"]
        level = alpha.get("level", "")
        risk_level = risk.get("risk_level", "")
        action = decision.get("action_level", "观察")
        return f"Alpha潜力{level}，风险{risk_level}，建议{action}"
