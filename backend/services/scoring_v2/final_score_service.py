"""
最终评分服务 - 风险调制后的最终评分
MVP公式:
  raw_score = alpha_score (模型不可用时)
  risk_adjustment = 1 - min(risk_score, 80) / 120
  final_score = raw_score * risk_adjustment
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class FinalScoreService:
    """最终评分服务：计算风险调整后的最终得分"""

    ALPHA_WEIGHT = 0.4
    MODEL_WEIGHT = 0.4
    EXPECTED_RETURN_WEIGHT = 0.2
    MAX_RISK_FOR_ADJUSTMENT = 80
    RISK_ADJUSTMENT_DIVISOR = 120

    @classmethod
    def calculate(
        cls,
        alpha_score: float,
        risk_score: float,
        model_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        if model_score is not None:
            raw_score = (
                alpha_score * cls.ALPHA_WEIGHT
                + model_score * cls.MODEL_WEIGHT
                + alpha_score * cls.EXPECTED_RETURN_WEIGHT
            )
        else:
            raw_score = alpha_score

        risk_adjustment = 1 - min(risk_score, cls.MAX_RISK_FOR_ADJUSTMENT) / cls.RISK_ADJUSTMENT_DIVISOR
        final_score = raw_score * risk_adjustment

        return {
            "raw_score": round(raw_score, 2),
            "final_score": round(final_score, 2),
            "risk_adjustment": round(risk_adjustment, 4),
            "grade": cls._to_grade(final_score),
        }

    @staticmethod
    def _to_grade(final_score: float) -> str:
        if final_score >= 85:
            return "S"
        elif final_score >= 75:
            return "A"
        elif final_score >= 65:
            return "B"
        elif final_score >= 50:
            return "C"
        return "D"
