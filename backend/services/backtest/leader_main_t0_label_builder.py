"""
龙头主升 T+0 非一字涨停标签生成。
"""
import logging
from typing import Any, Dict, Optional

from backend.database import SessionLocal
from backend.models.auction_backtest import LeaderMainT0TrainingSample
from backend.services.data_collector import TushareDataCollector

logger = logging.getLogger(__name__)


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_limit_up_price(ts_code: str, pre_close: float) -> float:
    code = (ts_code or "").split(".")[0]
    rate = 0.2 if code.startswith(("300", "301", "688", "689")) else 0.1
    return round(pre_close * (1 + rate), 2)


def is_one_line_limit_up(row: Dict[str, Any], limit_up_price: float) -> bool:
    threshold = limit_up_price * 0.997
    prices = [_num(row.get(k)) for k in ("open", "high", "low", "close")]
    return all(price is not None and price >= threshold for price in prices)


def build_label_from_daily_row(row: Dict[str, Any], ts_code: str) -> Dict[str, Any]:
    pre_close = _num(row.get("pre_close"))
    high = _num(row.get("high"))
    low = _num(row.get("low"))
    close = _num(row.get("close"))

    if not pre_close or pre_close <= 0 or high is None or low is None or close is None:
        return {
            "label_t0_limit_success": None,
            "t0_touched_limit": None,
            "t0_closed_limit": None,
            "is_one_line_limit_up": None,
            "t0_high_return": None,
            "t0_close_return": None,
            "t0_low_return": None,
        }

    limit_up_price = calculate_limit_up_price(ts_code, pre_close)
    threshold = limit_up_price * 0.997
    one_line = is_one_line_limit_up(row, limit_up_price)
    touched = high >= threshold
    closed = close >= threshold

    return {
        "label_t0_limit_success": None if one_line else int(touched and closed),
        "t0_touched_limit": int(touched),
        "t0_closed_limit": int(closed),
        "is_one_line_limit_up": int(one_line),
        "t0_high_return": round((high - pre_close) / pre_close * 100, 2),
        "t0_close_return": round((close - pre_close) / pre_close * 100, 2),
        "t0_low_return": round((low - pre_close) / pre_close * 100, 2),
    }


class LeaderMainT0LabelBuilder:
    """给候选样本生成 T+0 标签，避免标签反哺特征。"""

    def __init__(self, collector: Optional[Any] = None, session_factory=SessionLocal):
        self.collector = collector or TushareDataCollector()
        self.session_factory = session_factory
        self._owns_session = session_factory is SessionLocal

    def build_leader_main_t0_labels(self, start_date: str, end_date: str) -> int:
        db = self.session_factory()
        updated = 0
        try:
            samples = db.query(LeaderMainT0TrainingSample).filter(
                LeaderMainT0TrainingSample.trade_date.between(start_date, end_date)
            ).all()
            by_date: Dict[str, list[LeaderMainT0TrainingSample]] = {}
            for sample in samples:
                by_date.setdefault(sample.trade_date, []).append(sample)

            for trade_date, date_samples in by_date.items():
                daily_df = self.collector.get_daily_data(trade_date=trade_date)
                if daily_df is None or daily_df.empty:
                    logger.warning(f"{trade_date} 无完整T日日线，跳过标签生成")
                    continue
                daily_map = {
                    row["ts_code"]: row
                    for row in daily_df.to_dict("records")
                    if row.get("ts_code")
                }
                for sample in date_samples:
                    row = daily_map.get(sample.ts_code)
                    if not row:
                        continue
                    label = build_label_from_daily_row(row, sample.ts_code)
                    sample.label_t0_limit_success = label["label_t0_limit_success"]
                    sample.t0_touched_limit = label["t0_touched_limit"]
                    sample.t0_closed_limit = label["t0_closed_limit"]
                    sample.is_one_line_limit_up = label["is_one_line_limit_up"]
                    sample.t0_high_return = label["t0_high_return"]
                    sample.t0_close_return = label["t0_close_return"]
                    sample.t0_low_return = label["t0_low_return"]
                    updated += 1
            db.commit()
            return updated
        except Exception:
            db.rollback()
            logger.exception(f"生成龙头主升T+0标签失败: {start_date}~{end_date}")
            return 0
        finally:
            if self._owns_session:
                db.close()
