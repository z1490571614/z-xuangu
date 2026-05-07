"""
基本面/减持/ST/回购数据采集层（阶段3新增）
- forecast: 业绩预告
- fina_indicator: 财务指标
- stk_holdertrade: 股东增减持
- share_float: 限售股解禁
- repurchase: 回购
- stock_st: ST状态
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import tushare as ts

from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)


class FundamentalContext:
    """基本面上下文（缓存）"""

    def __init__(self):
        self._pro = None
        self._st_cache: Dict[str, Dict[str, bool]] = {}  # trade_date → {ts_code: True}

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    def get_forecast(self, ts_code: str) -> Dict[str, Any]:
        """获取业绩预告

        Returns:
            {
                "end_date": "20251231",
                "type": "预增"/"续亏"/"扭亏",
                "profit_range": "净利润xxx-xxx",
                "change_reason": "...",
                "data_status": "available"/"missing"
            }
        """
        result = {"data_status": "missing"}
        try:
            df = self.pro.forecast(ts_code=ts_code, start_date="20250101")
            if df is not None and not df.empty:
                row = df.iloc[0]
                result["end_date"] = str(row.get("end_date", ""))
                result["type"] = str(row.get("type", ""))
                result["profit_range"] = str(row.get("profit_range", "") or "")
                result["change_reason"] = str(row.get("change_reason", "") or "")[:100]
                result["data_status"] = "available"

                # 解析预告类型
                ftype = result["type"]
                if ftype in ("预增", "扭亏", "大幅上升"):
                    result["sentiment"] = "positive"
                elif ftype in ("预亏", "续亏", "大幅下降", "预减"):
                    result["sentiment"] = "negative"
                else:
                    result["sentiment"] = "neutral"
        except Exception as e:
            logger.warning(f"获取业绩预告失败 {ts_code}: {e}")

        return result

    def get_fina_indicators(self, ts_code: str) -> Dict[str, Any]:
        """获取最新财务指标

        Returns:
            {
                "roe": 1.66, "eps": 0.12, "profit_dedt": 22832560.69,
                "debt_to_assets": 40.07, "data_status": "available"
            }
        """
        result = {"data_status": "missing"}
        try:
            df = self.pro.fina_indicator(
                ts_code=ts_code, start_date="20250101",
                fields="end_date,roe,eps,profit_dedt,debt_to_assets,current_ratio,quick_ratio"
            )
            if df is not None and not df.empty:
                row = df.iloc[0]
                result["roe"] = float(row.get("roe", 0) or 0)
                result["eps"] = float(row.get("eps", 0) or 0)
                result["profit_dedt"] = float(row.get("profit_dedt", 0) or 0)
                result["debt_to_assets"] = float(row.get("debt_to_assets", 0) or 0)
                result["current_ratio"] = float(row.get("current_ratio", 0) or 0)
                result["end_date"] = str(row.get("end_date", ""))
                result["data_status"] = "available"
        except Exception as e:
            logger.warning(f"获取财务指标失败 {ts_code}: {e}")

        return result

    def get_shareholder_trades(self, ts_code: str) -> Dict[str, Any]:
        """获取股东增减持

        Returns:
            {
                "has_holdertrade": True/False,
                "trades": [...],
                "sentiment": "positive"(增持)/"negative"(减持)/"neutral",
                "total_change": 累计变动比例,
                "data_status": "available"/"missing"
            }
        """
        result = {"has_holdertrade": False, "trades": [], "sentiment": "neutral", "total_change": 0, "data_status": "missing"}
        try:
            df = self.pro.stk_holdertrade(ts_code=ts_code, start_date="20260101")
            if df is not None and not df.empty:
                trades = []
                total_change = 0
                has_reduce = False
                has_increase = False
                for _, r in df.iterrows():
                    trade_type = str(r.get("type", ""))
                    vol_change = float(r.get("vol_change", 0) or 0)
                    total_change += vol_change
                    if "减" in trade_type:
                        has_reduce = True
                    elif "增" in trade_type:
                        has_increase = True
                    trades.append({
                        "ann_date": str(r.get("ann_date", "")),
                        "holder_name": str(r.get("holder_name", "")),
                        "type": trade_type,
                        "vol_change": vol_change,
                    })

                result["has_holdertrade"] = True
                result["trades"] = trades[:5]
                result["total_change"] = total_change
                result["data_status"] = "available"

                if has_reduce and not has_increase:
                    result["sentiment"] = "negative"
                elif has_increase and not has_reduce:
                    result["sentiment"] = "positive"
        except Exception as e:
            logger.warning(f"获取股东增减持失败 {ts_code}: {e}")

        return result

    def get_share_float(self, ts_code: str) -> Dict[str, Any]:
        """获取限售股解禁

        Returns:
            {
                "has_float": True/False,
                "float_items": [...],
                "total_vol": 解禁总量,
                "data_status": "available"/"missing"
            }
        """
        result = {"has_float": False, "float_items": [], "total_vol": 0, "data_status": "missing"}
        try:
            df = self.pro.share_float(ts_code=ts_code, start_date="20260101")
            if df is not None and not df.empty:
                items = []
                total_vol = 0
                for _, r in df.iterrows():
                    vol = float(r.get("float_vol", 0) or 0)
                    total_vol += vol
                    items.append({
                        "float_date": str(r.get("float_date", "")),
                        "float_vol": vol,
                        "float_reason": str(r.get("float_reason", "")),
                    })
                result["has_float"] = True
                result["float_items"] = items[:3]
                result["total_vol"] = total_vol
                result["data_status"] = "available"
        except Exception as e:
            logger.warning(f"获取限售股解禁失败 {ts_code}: {e}")

        return result

    def get_repurchase(self, ts_code: str) -> Dict[str, Any]:
        """获取回购

        Returns:
            {
                "has_repurchase": True/False,
                "total_amount": 累计回购金额,
                "data_status": "available"/"missing"
            }
        """
        result = {"has_repurchase": False, "total_amount": 0, "data_status": "missing"}
        try:
            df = self.pro.repurchase(ts_code=ts_code, start_date="20260101")
            if df is not None and not df.empty:
                total_amount = sum(float(r.get("amount", 0) or 0) for _, r in df.iterrows())
                result["has_repurchase"] = True
                result["total_amount"] = total_amount
                result["data_status"] = "available"
        except Exception as e:
            logger.warning(f"获取回购失败 {ts_code}: {e}")

        return result

    def _ensure_st_cache(self, trade_date: str):
        """缓存当日ST股票列表"""
        if trade_date in self._st_cache:
            return
        cache = {}
        try:
            df = self.pro.stock_st(trade_date=trade_date)
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    st_type = str(r.get("type", ""))
                    if st_type != "N":
                        cache[str(r.get("ts_code", ""))] = True
            logger.info(f"✅ ST股票缓存 {trade_date}: {len(cache)} 条")
        except Exception as e:
            logger.warning(f"获取ST列表失败: {e}")
        self._st_cache[trade_date] = cache

    def is_st_stock(self, ts_code: str, trade_date: str) -> bool:
        """判断是否为ST/*ST股票"""
        self._ensure_st_cache(trade_date)
        return self._st_cache.get(trade_date, {}).get(ts_code, False)

    def collect(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """采集全部基本面上下文"""
        forecast = self.get_forecast(ts_code)
        fina = self.get_fina_indicators(ts_code)
        holdertrade = self.get_shareholder_trades(ts_code)
        share_float = self.get_share_float(ts_code)
        repurchase = self.get_repurchase(ts_code)
        is_st = self.is_st_stock(ts_code, trade_date)

        return {
            "forecast": forecast,
            "fina": fina,
            "holdertrade": holdertrade,
            "share_float": share_float,
            "repurchase": repurchase,
            "is_st": is_st,
        }
