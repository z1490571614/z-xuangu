"""
评分V2模块初始化
"""
from backend.models.scoring_v2.stock_score_v2 import StockScoreV2
from backend.models.scoring_v2.stock_score_breakdown_v2 import StockScoreBreakdownV2
from backend.models.scoring_v2.stock_risk_breakdown_v2 import StockRiskBreakdownV2

__all__ = [
    "StockScoreV2",
    "StockScoreBreakdownV2",
    "StockRiskBreakdownV2",
]
