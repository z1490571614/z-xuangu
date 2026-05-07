"""
分时数据采集层（阶段3新增）
- stk_mins: 分钟K线，用于盘后复盘承接判断（无权限时默认关闭）
- 通达信实时行情/日线OHLC: 默认降级数据源
"""
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import tushare as ts
import pandas as pd

from backend.services.data_collector import TushareDataCollector
from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)


class IntradayContext:
    """分时数据上下文（缓存最大100条）"""

    def __init__(self):
        self._pro = None
        self._cache: Dict[str, List[Dict]] = {}
        self._MAX_CACHE = 100

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    def get_minute_kline(self, ts_code: str, trade_date: str, freq: str = "5min") -> List[Dict]:
        """获取分钟K线数据

        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            freq: 频率 (1min/5min/15min/30min/60min)

        Returns:
            [{"trade_time": "09:35", "open": 12.5, "high": 12.6, "low": 12.4, "close": 12.55, "vol": 12345}, ...]
        """
        cache_key = f"{ts_code}_{trade_date}_{freq}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = []
        if os.getenv("ENABLE_TUSHARE_STK_MINS", "false").lower() not in ("1", "true", "yes"):
            self._cache[cache_key] = result
            return result

        try:
            if self.pro is None:
                return result
            df = self.pro.stk_mins(ts_code=ts_code, trade_date=trade_date, freq=freq)
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    result.append({
                        "trade_time": str(r.get("trade_time", "")),
                        "open": float(r.get("open", 0) or 0),
                        "high": float(r.get("high", 0) or 0),
                        "low": float(r.get("low", 0) or 0),
                        "close": float(r.get("close", 0) or 0),
                        "vol": float(r.get("vol", 0) or 0),
                    })
        except Exception as e:
            logger.warning(f"获取分钟K线失败 {ts_code} {trade_date}: {e}")

        self._cache[cache_key] = result
        if len(self._cache) > self._MAX_CACHE * 2:
            keys_to_del = sorted(self._cache.keys())[:len(self._cache) - self._MAX_CACHE]
            for k in keys_to_del:
                del self._cache[k]
        return result

    def _get_realtime_intraday(self, ts_code: str, trade_date: str) -> Optional[Dict[str, Any]]:
        """Use the existing internal TDX quote API when the requested date is today."""
        if trade_date != datetime.now().strftime("%Y%m%d"):
            return None
        try:
            quotes = TushareDataCollector().get_realtime_quotes([ts_code])
            quote = quotes.get(ts_code) or {}
            open_p = float(quote.get("open") or 0)
            close_p = float(quote.get("close") or 0)
            high_p = float(quote.get("high") or 0)
            low_p = float(quote.get("low") or 0)
            if open_p <= 0 or close_p <= 0:
                return None
            return self._build_ohlc_intraday(
                open_p=open_p,
                close_p=close_p,
                high_p=high_p or max(open_p, close_p),
                low_p=low_p or min(open_p, close_p),
                data_status="fallback_realtime",
                data_source="tdx_realtime_quotes",
            )
        except Exception as e:
            logger.warning(f"实时行情分时降级失败 {ts_code} {trade_date}: {e}")
            return None

    def _get_daily_intraday(self, ts_code: str, trade_date: str) -> Optional[Dict[str, Any]]:
        """Fallback to daily OHLC when minute permission is unavailable."""
        try:
            if self.pro is None:
                return None
            df = self.pro.daily(
                ts_code=ts_code,
                trade_date=trade_date,
                fields="open,high,low,close",
            )
            if df is None or df.empty:
                return None
            row = df.iloc[0]
            open_p = float(row.get("open", 0) or 0)
            close_p = float(row.get("close", 0) or 0)
            high_p = float(row.get("high", 0) or 0)
            low_p = float(row.get("low", 0) or 0)
            if open_p <= 0 or close_p <= 0:
                return None
            return self._build_ohlc_intraday(
                open_p=open_p,
                close_p=close_p,
                high_p=high_p or max(open_p, close_p),
                low_p=low_p or min(open_p, close_p),
                data_status="fallback_daily",
                data_source="tushare_daily",
            )
        except Exception as e:
            logger.warning(f"日线分时降级失败 {ts_code} {trade_date}: {e}")
            return None

    @staticmethod
    def _build_ohlc_intraday(
        open_p: float,
        close_p: float,
        high_p: float,
        low_p: float,
        data_status: str,
        data_source: str,
    ) -> Dict[str, Any]:
        max_drop_pct = round((open_p - low_p) / open_p * 100, 2) if open_p > 0 else 0
        opening_pct = round((close_p - open_p) / open_p * 100, 2) if open_p > 0 else 0
        return {
            "open_price": open_p,
            "close_price": close_p,
            "intraday_high": high_p,
            "intraday_low": low_p,
            "intraday_direction": "上涨" if close_p > open_p else "下跌" if close_p < open_p else "平盘",
            "max_drop_pct": max_drop_pct,
            "tail_direction": "未知",
            "opening_30min_pct": opening_pct,
            "is_weak_open": close_p < open_p,
            "has_tail_recovery": False,
            "data_status": data_status,
            "data_source": data_source,
            "note": "分钟K线无权限，已使用实时/日线OHLC降级估算",
        }

    def analyze_intraday(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """分析日内分时走势，返回承接指标

        Returns:
            {
                "open_price": 15.25,
                "close_price": 12.48,
                "intraday_high": 15.25,
                "intraday_low": 12.13,
                "intraday_direction": "下跌",
                "max_drop_pct": 3.5,
                "tail_direction": "跌",       # 最后30分钟方向
                "opening_30min_pct": -1.2,    # 开盘30分钟涨跌幅
                "is_weak_open": True,          # 是否开盘走弱
                "has_tail_recovery": False,    # 是否有尾盘拉升
                "data_status": "available"/"missing"
            }
        """
        result = {
            "open_price": 0, "close_price": 0,
            "intraday_high": 0, "intraday_low": 0,
            "intraday_direction": "未知",
            "max_drop_pct": 0,
            "tail_direction": "未知",
            "opening_30min_pct": 0,
            "is_weak_open": False,
            "has_tail_recovery": False,
            "data_status": "missing"
        }

        klines = self.get_minute_kline(ts_code, trade_date, "5min")
        if not klines:
            fallback = self._get_realtime_intraday(ts_code, trade_date) or self._get_daily_intraday(ts_code, trade_date)
            return fallback or result

        # 开盘/收盘
        first = klines[0]
        last = klines[-1]
        open_p = first.get("open", 0)
        close_p = last.get("close", 0)
        high_p = max(k.get("high", 0) for k in klines)
        low_p = min(k.get("low", 0) for k in klines)

        result["open_price"] = open_p
        result["close_price"] = close_p
        result["intraday_high"] = high_p
        result["intraday_low"] = low_p
        result["intraday_direction"] = "上涨" if close_p > open_p else "下跌" if close_p < open_p else "平盘"

        # 最大回撤（相比开盘价）
        max_drop_pct = 0
        if open_p > 0:
            max_drop_pct = round((open_p - low_p) / open_p * 100, 2)
        result["max_drop_pct"] = max_drop_pct

        # 尾盘方向（最后30分钟≈6根5分钟K线）
        tail_bars = klines[-6:] if len(klines) >= 6 else klines
        tail_open = tail_bars[0].get("open", 0)
        tail_close = tail_bars[-1].get("close", 0)
        result["tail_direction"] = "涨" if tail_close > tail_open else "跌" if tail_close < tail_open else "平"
        result["has_tail_recovery"] = tail_close > close_p * 0.99 if close_p > 0 else False

        # 开盘30分钟走势（前6根5分钟K线）
        open_bars = klines[:6] if len(klines) >= 6 else klines
        if open_bars:
            open_30_open = open_bars[0].get("open", 0)
            open_30_close = open_bars[-1].get("close", 0)
            if open_30_open > 0:
                result["opening_30min_pct"] = round((open_30_close - open_30_open) / open_30_open * 100, 2)
                result["is_weak_open"] = open_30_close < open_30_open

        result["data_status"] = "available"
        return result

    def collect(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """采集分时上下文"""
        return {"intraday": self.analyze_intraday(ts_code, trade_date)}
