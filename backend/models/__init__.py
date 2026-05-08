"""
数据库模型模块
"""
from backend.models.selection_record import SelectionRecord
from backend.models.selected_stock import SelectedStock
from backend.models.task_log import TaskLog
from backend.models.system_config import SystemConfig
from backend.models.scheduled_task import ScheduledTask
from backend.models.strategy_template import StrategyTemplate
from backend.models.stock_feature_snapshot import StockFeatureSnapshot, StockDetailSnapshot, ModelVersion
from backend.models.scoring_v2 import StockScoreV2, StockScoreBreakdownV2, StockRiskBreakdownV2
from backend.models.anomaly_interpretation import StockAnomalyInterpretation
from backend.models.overview_brief import StockOverviewBrief
from backend.models.stock_news import StockNews
from backend.models.stock_lhb import StockLhb
from backend.models.stock_risk import StockRiskBreakdown
from backend.models.stock_ths_board import ThsBoardIndex, StockThsBoardMember
from backend.models.board import BoardIndex, StockBoardMember, BoardDailySnapshot, BoardStrengthSnapshot
from backend.auth.models import User

__all__ = [
    "SelectionRecord",
    "SelectedStock",
    "TaskLog",
    "SystemConfig",
    "ScheduledTask",
    "StrategyTemplate",
    "StockFeatureSnapshot",
    "StockDetailSnapshot",
    "ModelVersion",
    "StockScoreV2",
    "StockScoreBreakdownV2",
    "StockRiskBreakdownV2",
    "StockAnomalyInterpretation",
    "StockOverviewBrief",
    "StockNews",
    "StockLhb",
    "StockRiskBreakdown",
    "ThsBoardIndex",
    "StockThsBoardMember",
    "BoardIndex",
    "StockBoardMember",
    "BoardDailySnapshot",
    "BoardStrengthSnapshot",
    "User",
]
