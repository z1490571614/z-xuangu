"""
默认竞价策略历史回放入口。

首版只定义模型中心需要的可测试接口。真实回放优先复用已落库的默认策略结果和历史竞价数据，
不得引入新闻、公告、舆情或 AI 文本特征。
"""
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.models import SelectionRecord, SelectedStock


class DefaultAuctionReplayService:
    def __init__(self, db: Session):
        self.db = db

    def get_recent_real_selection_days(self, limit: int = 5) -> List[Dict[str, Any]]:
        records = (
            self.db.query(SelectionRecord)
            .filter(SelectionRecord.total_count > 0)
            .order_by(SelectionRecord.trade_date.desc(), SelectionRecord.id.desc())
            .all()
        )
        result = []
        seen_trade_dates = set()
        for record in records:
            if record.trade_date in seen_trade_dates:
                continue
            seen_trade_dates.add(record.trade_date)
            result.append(
                {
                    "trade_date": record.trade_date,
                    "record_id": record.id,
                    "real_codes": [
                        stock.ts_code
                        for stock in self.db.query(SelectedStock)
                        .filter(SelectedStock.record_id == record.id)
                        .order_by(SelectedStock.id.asc())
                        .all()
                    ],
                }
            )
            if len(result) >= limit:
                break
        return result

    def replay_trade_date(self, trade_date: str) -> Dict[str, Any]:
        record = (
            self.db.query(SelectionRecord)
            .filter(SelectionRecord.trade_date == trade_date, SelectionRecord.total_count > 0)
            .order_by(SelectionRecord.id.desc())
            .first()
        )
        if not record:
            return {"trade_date": trade_date, "replay_codes": [], "diagnostics": ["no_real_or_replay_source"]}
        stocks = (
            self.db.query(SelectedStock)
            .filter(SelectedStock.record_id == record.id)
            .order_by(SelectedStock.id.asc())
            .all()
        )
        return {
            "trade_date": trade_date,
            "replay_codes": [stock.ts_code for stock in stocks],
            "diagnostics": [],
            "replay_source": "historical_backfill",
        }
