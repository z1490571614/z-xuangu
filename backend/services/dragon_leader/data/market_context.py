import logging
from typing import Dict, Any
from collections import defaultdict

import tushare as ts

from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)


class MarketContext:
    """市场情绪数据采集 - 复用现有 risk_breakdown_service 的缓存逻辑"""

    def __init__(self):
        self._pro = None
        self._cache: Dict[str, Dict] = {}
        self._MAX_CACHE_DAYS = 10

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    def get_market_sentiment(self, trade_date: str) -> Dict[str, Any]:
        """获取全局市场情绪（缓存1天）"""
        if trade_date in self._cache:
            return self._cache[trade_date]

        result: Dict[str, Any] = {
            "index_pct": 0,
            "market_volume": 0,
            "market_tr": 0,
            "limit_up_count": 0,
            "limit_down_count": 0,
            "max_connected": 0,
            "up_down_ratio": 0,
            "zhaban_rate": 0,
            "north_money": 0,
        }

        try:
            df = self.pro.index_daily(ts_code="000001.SH", trade_date=trade_date, fields="pct_chg,amount")
            if df is not None and not df.empty:
                row = df.iloc[0]
                result["index_pct"] = float(row.get("pct_chg", 0) or 0)
                amount = float(row.get("amount", 0) or 0)
                result["market_volume"] = round(amount / 100000, 1)
        except Exception as e:
            logger.warning(f"获取大盘指数失败: {e}")

        try:
            df = self.pro.index_dailybasic(ts_code="000001.SH", trade_date=trade_date, fields="turnover_rate")
            if df is not None and not df.empty:
                result["market_tr"] = float(df.iloc[0].get("turnover_rate", 0) or 0)
        except Exception as e:
            logger.warning(f"获取市场换手率失败: {e}")

        try:
            df = self.pro.limit_step(trade_date=trade_date)
            if df is not None and not df.empty and "nums" in df.columns:
                result["max_connected"] = int(df["nums"].max())
        except Exception as e:
            logger.warning(f"获取连板数据失败: {e}")

        try:
            df = self.pro.limit_list_ths(trade_date=trade_date)
            if df is not None and not df.empty:
                type_col = None
                for col in ("limit_type", "type", "status"):
                    if col in df.columns:
                        type_col = col
                        break
                if type_col:
                    type_vals = df[type_col].astype(str).str.upper()
                    result["limit_up_count"] = int(len(type_vals[type_vals.str.contains("U", na=False)]))
                    result["limit_down_count"] = int(len(type_vals[type_vals.str.contains("D", na=False)]))
        except Exception as e:
            logger.warning(f"获取涨跌停数据失败: {e}")

        try:
            df = self.pro.limit_list_d(trade_date=trade_date)
            if df is not None and not df.empty:
                total = len(df)
                zhaban = len(df[df.get("limit", "") == "Z"])
                if total > 0:
                    result["zhaban_rate"] = round(zhaban / total * 100, 1)
        except Exception as e:
            logger.warning(f"获取炸板数据失败: {e}")

        try:
            df = self.pro.moneyflow_hsgt(trade_date=trade_date)
            if df is not None and not df.empty:
                result["north_money"] = float(df.iloc[0].get("north_money", 0) or 0)
        except Exception as e:
            logger.warning(f"获取北向资金数据失败: {e}")

        self._cache[trade_date] = result
        if len(self._cache) > self._MAX_CACHE_DAYS * 2:
            keys_to_del = sorted(self._cache.keys())[:len(self._cache) - self._MAX_CACHE_DAYS]
            for k in keys_to_del:
                del self._cache[k]
        return result

    def collect(self, trade_date: str) -> Dict[str, Any]:
        """采集市场上下文"""
        sentiment = self.get_market_sentiment(trade_date)
        return {"sentiment": sentiment}
