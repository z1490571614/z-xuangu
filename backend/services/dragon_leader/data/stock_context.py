import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

import tushare as ts
import pandas as pd

from backend.database import SessionLocal
from backend.models import SelectedStock, SelectionRecord
from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)


class StockContext:
    """个股数据采集 - 复用现有数据源"""

    def __init__(self):
        self._pro = None

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    def collect(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """采集个股相关全部数据"""
        
        stock = self._get_selected_stock(ts_code, trade_date)
        
        ctx = {
            "stock": stock,
            "daily": self._get_daily(ts_code, trade_date),
            "daily_basic": self._get_daily_basic(ts_code, trade_date),
            "chip": self._get_chip(ts_code, trade_date),
            "capital": self._get_capital(ts_code, trade_date),
            "technical": self._get_technical(ts_code, trade_date),
        }
        return ctx

    def _get_selected_stock(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """从选股结果获取个股数据（含MCP竞价数据）"""
        db = SessionLocal()
        try:
            rec = db.query(SelectionRecord).filter(
                SelectionRecord.trade_date == trade_date,
                SelectionRecord.status == "success"
            ).order_by(SelectionRecord.id.desc()).first()
            if not rec:
                return {}
            stock = db.query(SelectedStock).filter(
                SelectedStock.record_id == rec.id,
                SelectedStock.ts_code == ts_code
            ).first()
            if not stock:
                return {}
            data = {
                "ts_code": stock.ts_code,
                "name": stock.name or "",
                "close": stock.close or 0,
                "change_pct": stock.change_pct or 0,
                "pre_change_pct": stock.pre_change_pct or 0,
                "open_change_pct": stock.open_change_pct or 0,
                "auction_ratio": stock.auction_ratio or 0,
                "auction_turnover_rate": stock.auction_turnover_rate or 0,
                "limit_up_count": stock.limit_up_count or 0,
                "seal_rate": stock.seal_rate or 0,
                "rise_10d_pct": stock.rise_10d_pct or 0,
                "circ_mv": stock.circ_mv or 0,
                "industry": stock.industry or "",
                "lu_desc": stock.lu_desc or "",
                "lu_tag": stock.lu_tag or "",
                "lu_status": stock.lu_status or "",
                "lu_open_num": stock.lu_open_num or 0,
                "limit_up_suc_rate": stock.limit_up_suc_rate or 0,
            }

            if not data.get("lu_desc") or not data.get("lu_tag"):
                fallback = self._get_limit_fields_from_db(db, ts_code, trade_date) or self._get_limit_fields_from_ths(ts_code, trade_date)
                for key, value in fallback.items():
                    if value not in (None, "") and not data.get(key):
                        data[key] = value

            return data
        finally:
            db.close()

    def _get_limit_fields_from_db(self, db, ts_code: str, trade_date: str) -> Dict[str, Any]:
        stock = db.query(SelectedStock).join(
            SelectionRecord, SelectedStock.record_id == SelectionRecord.id
        ).filter(
            SelectionRecord.trade_date == trade_date,
            SelectionRecord.status == "success",
            SelectedStock.ts_code == ts_code,
            SelectedStock.lu_desc.isnot(None),
        ).order_by(SelectionRecord.id.desc()).first()
        if not stock:
            return {}
        return {
            "lu_desc": stock.lu_desc or "",
            "lu_tag": stock.lu_tag or "",
            "lu_status": stock.lu_status or "",
            "lu_open_num": stock.lu_open_num or 0,
            "limit_up_suc_rate": stock.limit_up_suc_rate or 0,
        }

    def _get_limit_fields_from_ths(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        try:
            df = self.pro.limit_list_ths(ts_code=ts_code, trade_date=trade_date, limit_type="涨停池")
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "lu_desc": str(row.get("lu_desc", "") or ""),
                    "lu_tag": str(row.get("tag", "") or ""),
                    "lu_status": str(row.get("status", "") or ""),
                    "lu_open_num": int(row.get("open_num", 0) or 0),
                    "limit_up_suc_rate": float(row.get("limit_up_suc_rate", 0) or 0),
                }
        except Exception as e:
            logger.warning(f"涨停字段兜底失败 {ts_code}: {e}")
        return {}

    def _get_daily(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取日线数据"""
        try:
            df = self.pro.daily(ts_code=ts_code, trade_date=trade_date,
                                fields="ts_code,open,high,low,close,pre_close,pct_chg,vol,amount")
            if df is not None and not df.empty:
                row = df.iloc[0]
                high = float(row.get("high", 0) or 0)
                low = float(row.get("low", 0) or 0)
                pre_close = float(row.get("pre_close", 0) or 0)
                amplitude = (high - low) / pre_close * 100 if pre_close > 0 else 0
                return {
                    "open": float(row.get("open", 0) or 0),
                    "high": high,
                    "low": low,
                    "close": float(row.get("close", 0) or 0),
                    "pct_chg": float(row.get("pct_chg", 0) or 0),
                    "vol": float(row.get("vol", 0) or 0),
                    "amount": float(row.get("amount", 0) or 0),
                    "amplitude": amplitude,
                }
        except Exception as e:
            logger.warning(f"获取日线失败 {ts_code}: {e}")
        return {}

    def _get_daily_basic(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取每日基本面"""
        try:
            prev_date = self._get_prev_trade_date(trade_date)
            df = self.pro.daily_basic(ts_code=ts_code, trade_date=prev_date,
                                      fields="ts_code,turnover_rate,volume_ratio")
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "turnover_rate": float(row.get("turnover_rate", 0) or 0),
                    "volume_ratio": float(row.get("volume_ratio", 0) or 0),
                }
        except Exception as e:
            logger.warning(f"获取每日基本面失败 {ts_code}: {e}")
        return {}

    def _get_chip(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取筹码数据"""
        try:
            df = self.pro.cyq_perf(ts_code=ts_code, trade_date=trade_date,
                                   fields="ts_code,winner_rate,weight_avg,cost_5pct,cost_95pct")
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "winner_rate": float(row.get("winner_rate", 0) or 0),
                    "weight_avg": float(row.get("weight_avg", 0) or 0),
                    "cost_5pct": float(row.get("cost_5pct", 0) or 0),
                    "cost_95pct": float(row.get("cost_95pct", 0) or 0),
                }
        except Exception as e:
            logger.warning(f"获取筹码数据失败 {ts_code}: {e}")
        return {}

    def _get_capital(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取资金流向"""
        try:
            df = self.pro.moneyflow(ts_code=ts_code, trade_date=trade_date,
                                    fields="ts_code,net_mf_amount,buy_elg_amount,sell_elg_amount,buy_lg_amount,sell_lg_amount")
            if df is not None and not df.empty:
                row = df.iloc[0]
                net_mf = float(row.get("net_mf_amount", 0) or 0)
                buy_elg = float(row.get("buy_elg_amount", 0) or 0)
                sell_elg = float(row.get("sell_elg_amount", 0) or 0)
                buy_lg = float(row.get("buy_lg_amount", 0) or 0)
                sell_lg = float(row.get("sell_lg_amount", 0) or 0)
                return {
                    "net_mf_amount": net_mf,
                    "elg_net": buy_elg - sell_elg,
                    "lg_net": buy_lg - sell_lg,
                    "buy_elg_amount": buy_elg,
                    "sell_elg_amount": sell_elg,
                    "buy_lg_amount": buy_lg,
                    "sell_lg_amount": sell_lg,
                }
        except Exception as e:
            logger.warning(f"获取资金流向失败 {ts_code}: {e}")
        return {}

    def _get_technical(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取技术面指标"""
        try:
            df = self.pro.stk_factor_pro(
                ts_code=ts_code, trade_date=trade_date,
                fields="macd_bfq,macd_dea_bfq,macd_dif_bfq,rsi_bfq_6,kdj_k_bfq,kdj_bfq,"
                       "cci_bfq,volume_ratio,updays,downdays"
            )
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "macd": float(row.get("macd_bfq", 0) or 0),
                    "macd_dea": float(row.get("macd_dea_bfq", 0) or 0),
                    "macd_dif": float(row.get("macd_dif_bfq", 0) or 0),
                    "rsi": float(row.get("rsi_bfq_6", 50) or 50),
                    "kdj_k": float(row.get("kdj_k_bfq", 50) or 50),
                    "kdj": float(row.get("kdj_bfq", 50) or 50),
                    "cci": float(row.get("cci_bfq", 0) or 0),
                    "volume_ratio": float(row.get("volume_ratio", 1) or 1),
                    "updays": int(row.get("updays", 0) or 0),
                    "downdays": int(row.get("downdays", 0) or 0),
                }
        except Exception as e:
            logger.warning(f"获取技术面失败 {ts_code}: {e}")
        return {}

    def _get_prev_trade_date(self, trade_date: str) -> Optional[str]:
        try:
            from backend.utils.trading_date import get_previous_trading_day
            return get_previous_trading_day(trade_date)
        except Exception:
            dt = datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=1)
            return dt.strftime("%Y%m%d")
