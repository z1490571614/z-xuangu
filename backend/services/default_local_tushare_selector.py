"""
默认竞价接力的本地日线 + Tushare 选股通道。

阶段边界：
1. 本地通达信 .day 日线负责 A 股股票池、价格、趋势、涨停次数筛选。
2. Tushare stk_auction 同步后的 stock_auction_open 负责竞昨比和竞价换手率筛选。

该服务只替换阶段1的数据接口，不负责入库、评分、预热和模型预测刷新。
"""
from __future__ import annotations

import logging
import time
from copy import copy
from typing import Any, Dict, Optional

import pandas as pd

from backend.services.auction_data_service import AuctionDataService
from backend.services.tdx_local_selector import TdxLocalSelectorService

logger = logging.getLogger(__name__)


def _clean_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class DefaultLocalTushareSelectorService:
    """用本地日线候选池叠加 Tushare 竞价字段，复刻默认 MCP 选股条件。"""

    def __init__(
        self,
        local_selector: Optional[Any] = None,
        auction_service: Optional[Any] = None,
    ):
        self.local_selector = local_selector or TdxLocalSelectorService()
        self.auction_service = auction_service or AuctionDataService()

    def select(
        self,
        trade_date: str,
        max_circ_mv: float = 2000,
        max_close_price: float = 500,
        min_limit_up_count: int = 3,
        period_days: int = 100,
        data_collector: Optional[Any] = None,
        auction_ratio_min: float = 4.0,
        auction_ratio_max: float = 30.0,
        auction_turnover_rate_min: float = 0.5,
        auction_turnover_rate_max: float = 10.0,
    ) -> Dict[str, Any]:
        start = time.time()
        logger.info(
            "========== 阶段1：本地日线 + Tushare竞价选股 | 日期=%s ==========",
            trade_date,
        )

        local_result = self.local_selector.select(
            trade_date=trade_date,
            max_circ_mv=max_circ_mv,
            max_close_price=max_close_price,
            min_limit_up_count=min_limit_up_count,
            period_days=period_days,
            data_collector=data_collector,
        )
        local_stocks = local_result.get("stocks", []) or []
        ts_codes = [stock.ts_code for stock in local_stocks if getattr(stock, "ts_code", None)]

        synced_count = self.auction_service.sync_auction_open(trade_date)
        auction_features = self.auction_service.batch_get_auction_features(trade_date, ts_codes)

        passed = []
        funnel = {
            "local_candidates": len(local_stocks),
            "auction_synced": synced_count,
            "has_auction": 0,
            "auction_ratio_pass": 0,
            "auction_turnover_pass": 0,
        }
        missing_auction = []

        for stock in local_stocks:
            ts_code = getattr(stock, "ts_code", None)
            if not ts_code:
                continue

            features = auction_features.get(ts_code)
            if not features:
                if len(missing_auction) < 10:
                    missing_auction.append(ts_code)
                continue
            funnel["has_auction"] += 1

            auction_ratio = _clean_float(features.get("auction_ratio"))
            if auction_ratio is None or not (auction_ratio_min <= auction_ratio <= auction_ratio_max):
                continue
            funnel["auction_ratio_pass"] += 1

            auction_turnover_rate = _clean_float(features.get("auction_turnover_rate"))
            if auction_turnover_rate is None or not (
                auction_turnover_rate_min <= auction_turnover_rate <= auction_turnover_rate_max
            ):
                continue
            funnel["auction_turnover_pass"] += 1

            enriched = copy(stock)
            enriched.auction_ratio = auction_ratio
            enriched.auction_turnover_rate = auction_turnover_rate
            if not hasattr(enriched, "extra_data") or enriched.extra_data is None:
                enriched.extra_data = {}
            enriched.extra_data.update(
                {
                    "auction_amount": features.get("auction_amount"),
                    "auction_volume": features.get("auction_volume"),
                    "auction_pre_close": features.get("auction_pre_close"),
                    "auction_source": features.get("auction_source"),
                }
            )
            passed.append(enriched)

        execution_time = time.time() - start
        if missing_auction:
            logger.warning(
                "本地+Tushare选股存在竞价数据缺失，已按真实缺失剔除，示例: %s",
                ",".join(missing_auction),
            )

        logger.info(
            "本地+Tushare选股完成: 本地候选=%s, 有竞价=%s, 竞昨比通过=%s, 最终=%s, 耗时=%.2fs",
            funnel["local_candidates"],
            funnel["has_auction"],
            funnel["auction_ratio_pass"],
            len(passed),
            execution_time,
        )

        return {
            "stocks": passed,
            "total_count": len(passed),
            "execution_time": execution_time,
            "source": "tdx_local_tushare",
            "task_results": [
                {
                    "task_id": "local_tushare_default",
                    "task_name": "本地日线+Tushare竞价选股",
                    "query": (
                        "通达信本地日线筛选 + Tushare stk_auction "
                        f"竞昨比{auction_ratio_min:g}%-{auction_ratio_max:g}%、"
                        f"竞价换手率{auction_turnover_rate_min:g}%-{auction_turnover_rate_max:g}%"
                    ),
                    "stocks": passed,
                    "total_count": len(passed),
                    "execution_time": execution_time,
                    "funnel": funnel,
                }
            ],
        }
