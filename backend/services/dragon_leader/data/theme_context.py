"""
题材/板块数据采集层（阶段2新增）
- ths_index: 全量概念/行业板块代码缓存
- ths_member: 个股所属板块
- limit_cpt_list: 每日最强板块排名
- kpl_list: 炸板回封、开盘啦榜单
"""
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import re
from threading import Lock

import tushare as ts
import pandas as pd

from backend.database import SessionLocal
from backend.models import SelectedStock, SelectionRecord
from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)

THEME_ALIAS_RULES = [
    (("半导体", "洁净室", "芯片"), ("芯片", "半导体", "集成电路")),
    (("算力", "数据中心", "服务器"), ("算力", "数据中心", "人工智能", "云计算")),
    (("海外EPC", "EPC", "海外工程"), ("一带一路", "海外", "工程")),
    (("城市更新", "旧改"), ("城市更新", "新型城镇化", "装配式建筑")),
    (("华为", "鸿蒙"), ("华为", "鸿蒙")),
    (("5G", "通信运维"), ("5G", "通信")),
]


class ThemeContext:
    """题材/板块上下文（缓存1天，最大缓存10个交易日）"""

    _shared_concept_cache: Optional[Dict[str, str]] = None
    _shared_industry_cache: Optional[Dict[str, str]] = None
    _shared_lock = Lock()
    _shared_hot_board_cache: Dict[str, Any] = {}
    _shared_kpl_cache: Dict[str, Dict] = {}

    def __init__(self):
        self._pro = None
        self._hot_board_cache = self.__class__._shared_hot_board_cache
        self._kpl_cache = self.__class__._shared_kpl_cache
        self._MAX_CACHE_DAYS = 10

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    # ========== 概念/行业板块缓存 ==========

    def _ensure_concept_cache(self):
        """全量加载同花顺概念板块（N型）"""
        cls = self.__class__
        if cls._shared_concept_cache is not None:
            return
        with cls._shared_lock:
            if cls._shared_concept_cache is not None:
                return
            cache: Dict[str, str] = {}
            try:
                df = self.pro.ths_index(type="N")
                if df is not None and not df.empty:
                    for _, r in df.iterrows():
                        cache[str(r["ts_code"])] = str(r["name"])
                if cache:
                    cls._shared_concept_cache = cache
                    logger.info(f"同花顺概念板块缓存完成: {len(cache)} 条")
                else:
                    logger.warning("同花顺概念板块返回空数据，暂不写入全局缓存")
            except Exception as e:
                logger.warning(f"加载概念板块失败: {e}")

    def _ensure_industry_cache(self):
        """全量加载同花顺行业板块（I型）"""
        cls = self.__class__
        if cls._shared_industry_cache is not None:
            return
        with cls._shared_lock:
            if cls._shared_industry_cache is not None:
                return
            cache: Dict[str, str] = {}
            try:
                df = self.pro.ths_index(type="I")
                if df is not None and not df.empty:
                    for _, r in df.iterrows():
                        cache[str(r["ts_code"])] = str(r["name"])
                if cache:
                    cls._shared_industry_cache = cache
                    logger.info(f"同花顺行业板块缓存完成: {len(cache)} 条")
                else:
                    logger.warning("同花顺行业板块返回空数据，暂不写入全局缓存")
            except Exception as e:
                logger.warning(f"加载行业板块失败: {e}")

    def get_stock_concepts(self, ts_code: str) -> List[Dict[str, str]]:
        """获取个股所属的同花顺概念板块列表

        Returns:
            [{"ts_code": "885xxx.TI", "name": "芯片概念"}, ...]
        """
        self._ensure_concept_cache()
        self._ensure_industry_cache()

        # 合并概念+行业索引
        full_cache = {}
        full_cache.update(self.__class__._shared_concept_cache or {})
        full_cache.update(self.__class__._shared_industry_cache or {})

        result = []
        try:
            df = self.pro.ths_member(con_code=ts_code)
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    idx_code = str(r["ts_code"])
                    # 只保留在缓存中有名称的代码（过滤掉700xxx.TI等分类代码）
                    if idx_code in full_cache:
                        result.append({
                            "ts_code": idx_code,
                            "name": full_cache[idx_code]
                        })
        except Exception as e:
            logger.warning(f"获取个股所属板块失败 {ts_code}: {e}")

        return result

    def _get_stock_theme_hints(self, ts_code: str, trade_date: str) -> Dict[str, str]:
        """从选股结果读取题材匹配提示，优先复用已入库的涨停原因"""
        db = SessionLocal()
        try:
            stock = db.query(SelectedStock).join(
                SelectionRecord, SelectedStock.record_id == SelectionRecord.id
            ).filter(
                SelectionRecord.trade_date == trade_date,
                SelectionRecord.status == "success",
                SelectedStock.ts_code == ts_code,
            ).order_by(
                (SelectedStock.lu_desc.isnot(None)).desc(),
                (SelectedStock.concept.isnot(None)).desc(),
                SelectionRecord.id.desc(),
            ).first()
            if not stock:
                return self._get_limit_hints_from_ths(ts_code, trade_date)
            hints = {
                "industry": stock.industry or "",
                "concept": stock.concept or "",
                "lu_desc": stock.lu_desc or "",
                "board_type": stock.board_type or "",
            }
            if not hints["lu_desc"] and not hints["concept"] and not hints["board_type"]:
                hints.update(self._get_limit_hints_from_ths(ts_code, trade_date))
            return hints
        finally:
            db.close()

    def _get_limit_hints_from_ths(self, ts_code: str, trade_date: str) -> Dict[str, str]:
        """当最新选股记录缺字段时，直接从同花顺涨停池兜底读取涨停原因"""
        try:
            df = self.pro.limit_list_ths(ts_code=ts_code, trade_date=trade_date, limit_type="涨停池")
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "industry": "",
                    "concept": "",
                    "lu_desc": str(row.get("lu_desc", "") or ""),
                    "board_type": "",
                }
        except Exception as e:
            logger.warning(f"获取涨停题材提示失败 {ts_code}: {e}")
        return {}

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"[\s,，/、;；|｜（）()【】\[\]：:]+", "", str(text or ""))

    @staticmethod
    def _split_terms(text: str) -> List[str]:
        terms = re.split(r"[+＋,，/、;；|｜\s]+", str(text or ""))
        return [t.strip() for t in terms if len(t.strip()) >= 2]

    def _theme_match_score(self, board: Dict[str, Any], hints: Dict[str, str]) -> tuple[int, List[str]]:
        """根据涨停原因/概念/行业给热点板块排序，避免泛概念抢占主线"""
        score = max(0, 30 - int(board.get("rank", 999) or 999))
        reasons: List[str] = []
        name = str(board.get("name", "") or "")
        clean_name = self._clean_text(name)

        for source_key, label in (("lu_desc", "涨停原因"), ("concept", "概念字段"), ("board_type", "板块字段")):
            text = hints.get(source_key, "")
            for idx, term in enumerate(self._split_terms(text)):
                clean_term = self._clean_text(term)
                if clean_name and clean_term and clean_name == clean_term:
                    score += 120 + max(0, 30 - idx * 5)
                    reasons.append(f"{label}优先命中{name}")
                    return score, reasons
            clean_text = self._clean_text(text)
            if clean_name and clean_name in clean_text:
                score += 80
                reasons.append(f"{label}命中{name}")

        lu_desc = hints.get("lu_desc", "")
        for triggers, aliases in THEME_ALIAS_RULES:
            if any(trigger in lu_desc for trigger in triggers) and any(alias in name for alias in aliases):
                score += 180
                reasons.append(f"涨停原因语义命中{name}")
                break

        industry = self._clean_text(hints.get("industry", ""))
        if clean_name and industry:
            if clean_name == industry:
                score += 55
                reasons.append(f"行业精确匹配{name}")
            elif clean_name in industry or industry in clean_name:
                score += 30
                reasons.append(f"行业模糊匹配{name}")

        return score, reasons

    # ========== 最强板块排行 ==========

    def _trim_cache(self):
        """限制缓存大小，防止内存泄漏"""
        for cache in (self._hot_board_cache, self._kpl_cache):
            if len(cache) > self._MAX_CACHE_DAYS:
                keys_to_del = sorted(cache.keys())[:len(cache) - self._MAX_CACHE_DAYS]
                for k in keys_to_del:
                    del cache[k]

    def get_hot_boards(self, trade_date: str) -> List[Dict[str, Any]]:
        """获取每日最强板块排行

        Returns:
            [{"rank":1, "name":"芯片概念", "up_nums":22, "cons_nums":7,
              "up_stat":"13天10板", "days":10, "pct_chg":2.86, "ts_code":"885xxx.TI"}, ...]
        """
        if trade_date in self._hot_board_cache:
            return self._hot_board_cache[trade_date]

        result = []
        try:
            df = self.pro.limit_cpt_list(trade_date=trade_date)
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    result.append({
                        "rank": int(r.get("rank", 0)),
                        "name": str(r.get("name", "")),
                        "ts_code": str(r.get("ts_code", "")),
                        "up_nums": int(r.get("up_nums", 0) or 0),
                        "cons_nums": int(r.get("cons_nums", 0) or 0),
                        "up_stat": str(r.get("up_stat", "")),
                        "days": int(r.get("days", 0) or 0),
                        "pct_chg": float(r.get("pct_chg", 0) or 0),
                    })
        except Exception as e:
            logger.warning(f"获取最强板块失败: {e}")

        self._hot_board_cache[trade_date] = result
        self._trim_cache()
        return result

    def get_stock_theme_rank(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取个股所属题材的最强排行信息

        Returns:
            {
                "best_rank": 1,          # 所属题材中的最高排名
                "best_name": "芯片概念",
                "hot_boards": [...],     # 所属题材的排行列表
                "board_count": 2,        # 所属热点题材数
                "all_concepts": [...]    # 个股所有概念
            }
        """
        concepts = self.get_stock_concepts(ts_code)
        hints = self._get_stock_theme_hints(ts_code, trade_date)
        concept_names = {c["name"] for c in concepts}
        concept_codes = {c["ts_code"] for c in concepts}

        hot_boards = self.get_hot_boards(trade_date)
        matched = []

        for board in hot_boards:
            name = board["name"]
            code = board.get("ts_code", "")
            if name in concept_names or code in concept_codes:
                matched.append(dict(board))
            else:
                # 也尝试子串匹配
                for cn in concept_names:
                    if cn in name or name in cn:
                        matched.append(dict(board))
                        break

        for board in matched:
            match_score, match_reasons = self._theme_match_score(board, hints)
            board["match_score"] = match_score
            board["match_reasons"] = match_reasons

        matched_sorted = sorted(
            matched,
            key=lambda b: (b.get("match_score", 0), -int(b.get("rank", 999) or 999)),
            reverse=True,
        )
        best_board = matched_sorted[0] if matched_sorted else {}
        best_rank = int(best_board.get("rank", 999) or 999)
        best_name = str(best_board.get("name", "") or "")

        return {
            "best_rank": best_rank,
            "best_name": best_name,
            "primary_board": best_board,
            "hot_boards": matched_sorted[:5],
            "board_count": len(matched),
            "all_concepts": concepts[:10],  # 最多返回10个
            "match_hints": hints,
        }

    # ========== KPL 榜单 ==========

    def get_kpl_data(self, trade_date: str) -> Dict[str, Any]:
        """获取开盘啦榜单数据

        Returns:
            {
                "limit_up_list": [...],   # 涨停榜
                "break_list": [...],      # 炸板榜
                "limit_up_count": 97,
                "break_count": 20,
            }
        """
        if trade_date in self._kpl_cache:
            return self._kpl_cache[trade_date]

        result = {
            "limit_up_list": [],
            "break_list": [],
            "limit_up_count": 0,
            "break_count": 0,
        }

        try:
            df = self.pro.kpl_list(trade_date=trade_date, tag="涨停")
            if df is not None and not df.empty:
                result["limit_up_list"] = df.to_dict("records")
                result["limit_up_count"] = len(df)
        except Exception as e:
            logger.warning(f"获取KPL涨停榜失败: {e}")

        try:
            df = self.pro.kpl_list(trade_date=trade_date, tag="炸板")
            if df is not None and not df.empty:
                result["break_list"] = df.to_dict("records")
                result["break_count"] = len(df)
        except Exception as e:
            logger.warning(f"获取KPL炸板榜失败: {e}")

        self._kpl_cache[trade_date] = result
        self._trim_cache()
        return result

    def get_stock_kpl_detail(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取个股的KPL详情（封板/炸板/竞价）

        Returns:
            {
                "is_limit_up": bool,
                "is_break": bool,
                "open_time": "09:31:00" or None,
                "last_time": "14:56:00" or None,
                "seal_amount": 12345678 or 0,
                "theme": "芯片概念",
                "status": "首板",
                "bid_pct_chg": 3.5 or None,
            }
        """
        result = {
            "is_limit_up": False,
            "is_break": False,
            "open_time": None,
            "last_time": None,
            "seal_amount": 0,
            "theme": "",
            "status": "",
            "bid_pct_chg": None,
        }

        kpl = self.get_kpl_data(trade_date)

        # 在涨停榜中查找
        for item in kpl.get("limit_up_list", []):
            if str(item.get("ts_code", "")) == ts_code:
                result["is_limit_up"] = True
                result["last_time"] = item.get("last_time")
                result["seal_amount"] = float(item.get("limit_order", 0) or 0)
                result["theme"] = str(item.get("theme", ""))
                result["status"] = str(item.get("status", ""))
                bid_pct = item.get("bid_pct_chg")
                result["bid_pct_chg"] = float(bid_pct) if bid_pct and not (isinstance(bid_pct, float) and str(bid_pct) == "nan") else None
                break

        # 在炸板榜中查找（冲突时炸板榜优先）
        for item in kpl.get("break_list", []):
            if str(item.get("ts_code", "")) == ts_code:
                result["is_break"] = True
                result["open_time"] = item.get("open_time")
                break

        return result

    def collect(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """采集全部题材上下文"""
        theme_rank = self.get_stock_theme_rank(ts_code, trade_date)
        kpl_detail = self.get_stock_kpl_detail(ts_code, trade_date)

        return {
            "theme_rank": theme_rank,
            "kpl_detail": kpl_detail,
            "hot_boards": self.get_hot_boards(trade_date),
        }
