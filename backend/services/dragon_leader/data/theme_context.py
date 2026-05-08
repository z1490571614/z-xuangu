"""
题材/板块数据采集层（阶段2新增）
- stock_board_member: 选股后落库的东财个股所属板块
- board_strength_snapshot: 每日最强板块排名主来源
- limit_cpt_list: 同花顺热榜降级参考
- kpl_list: 炸板回封、开盘啦榜单
"""
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import re

import tushare as ts
import pandas as pd

from backend.database import SessionLocal
from backend.models import SelectedStock, SelectionRecord
from backend.services.theme_alias_resolver import ThemeAliasResolver
from backend.services.dc_board_service import DcBoardService
from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)

class ThemeContext:
    """题材/板块上下文（缓存1天，最大缓存10个交易日）"""

    _shared_hot_board_cache: Dict[str, Any] = {}
    _shared_kpl_cache: Dict[str, Dict] = {}

    def __init__(self):
        self._pro = None
        self._board_service = DcBoardService()
        self._theme_resolver = ThemeAliasResolver()
        self._hot_board_cache = self.__class__._shared_hot_board_cache
        self._kpl_cache = self.__class__._shared_kpl_cache
        self._MAX_CACHE_DAYS = 10

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    # ========== 个股板块关系 ==========

    def get_stock_concepts(self, ts_code: str, trade_date: Optional[str] = None) -> List[Dict[str, str]]:
        """获取个股所属的东财板块列表

        Returns:
            [{"ts_code": "BKxxxx.DC", "name": "芯片概念"}, ...]
        """
        boards = self._board_service.get_stock_boards(
            ts_code,
            trade_date=trade_date,
            refresh_if_missing=bool(trade_date),
        )
        return [{"ts_code": b["ts_code"], "name": b["name"], "type": b.get("type", "")} for b in boards]

    def _get_stock_theme_hints(self, ts_code: str, trade_date: str) -> Dict[str, str]:
        """从选股结果读取题材匹配提示，优先复用已入库的涨停原因"""
        news_theme = self._get_cached_news_theme_hint(ts_code, trade_date)
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
                hints = self._get_limit_hints_from_ths(ts_code, trade_date)
                hints["news_theme"] = news_theme
                return hints
            hints = {
                "news_theme": news_theme,
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

    def _get_cached_news_theme_hint(self, ts_code: str, trade_date: str) -> str:
        """读取已抽取的新闻主题关系，不触发新闻采集。"""
        try:
            from backend.services.integrated_news_service import get_integrated_news_service
            svc = get_integrated_news_service()
            try:
                relations = svc.get_cached_theme_relations(ts_code, trade_date)
            finally:
                try:
                    svc.close()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"读取新闻主题缓存失败 {ts_code}: {e}")
            return ""

        themes = []
        seen = set()
        for relation in relations:
            theme = str(relation.get("normalized_theme_name") or relation.get("theme_name") or "").strip()
            if not theme or theme in seen:
                continue
            seen.add(theme)
            themes.append(theme)
            if len(themes) >= 5:
                break
        return "+".join(themes)

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

        for source_key, label in (
            ("news_theme", "新闻主题"),
            ("lu_desc", "涨停原因"),
            ("concept", "概念字段"),
            ("board_type", "板块字段"),
        ):
            if source_key == "news_theme":
                exact_base = 180
                fuzzy_base = 120
            elif source_key == "lu_desc":
                exact_base = 120
                fuzzy_base = 80
            else:
                exact_base = 35
                fuzzy_base = 20
            text = hints.get(source_key, "")
            for idx, term in enumerate(self._split_terms(text)):
                clean_term = self._clean_text(term)
                if clean_name and clean_term and clean_name == clean_term:
                    score += exact_base + max(0, 30 - idx * 5)
                    reasons.append(f"{label}优先命中{name}")
                    return score, reasons
            clean_text = self._clean_text(text)
            if clean_name and len(clean_name) >= 4 and clean_name in clean_text:
                score += fuzzy_base
                reasons.append(f"{label}命中{name}")

        lu_desc = hints.get("lu_desc", "")
        board_theme = self._theme_resolver.resolve_one(name).get("normalized_theme_name", name)
        lu_themes = self._theme_resolver.resolve_text(lu_desc)
        for item in lu_themes:
            if item.get("normalized_theme_name") == board_theme:
                if item.get("is_generic"):
                    score += 15
                    reasons.append(f"涨停原因弱语义命中{name}")
                else:
                    score += int(80 * item.get("weight", 1.0)) + item.get("penalty", 0)
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

    def _exact_hint_boards_from_concepts(
        self,
        concepts: List[Dict[str, str]],
        hints: Dict[str, str],
        hot_boards: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """用精确题材文本补齐热板块缺失的同花顺板块代码。

        只接受涨停原因/概念字段中的完整词命中，避免回到宽泛的成分股匹配。
        """
        hot_codes = {str(b.get("ts_code", "") or "") for b in hot_boards}
        hot_names = {self._clean_text(str(b.get("name", "") or "")) for b in hot_boards}
        lu_terms = {self._clean_text(t) for t in self._split_terms(hints.get("lu_desc", ""))}
        other_terms = {
            self._clean_text(t)
            for source_key in ("concept", "board_type")
            for t in self._split_terms(hints.get(source_key, ""))
        }
        exact_terms = lu_terms | other_terms
        if not exact_terms:
            return []

        result: List[Dict[str, Any]] = []
        seen_codes: Set[str] = set(hot_codes)
        seen_names: Set[str] = set(hot_names)
        for concept in concepts:
            name = str(concept.get("name", "") or "")
            code = str(concept.get("ts_code", "") or "")
            clean_name = self._clean_text(name)
            if not clean_name or clean_name not in exact_terms:
                continue
            if code in seen_codes or clean_name in seen_names:
                continue

            matched_from = "exact_lu_desc_board" if clean_name in lu_terms else "exact_hint_board"
            result.append({
                "rank": 999,
                "name": name,
                "ts_code": code,
                "up_nums": 0,
                "cons_nums": 0,
                "up_stat": "",
                "days": 0,
                "pct_chg": 0.0,
                "matched_from": matched_from,
            })
            if code:
                seen_codes.add(code)
            seen_names.add(clean_name)

        return result

    def _normalized_hint_boards(
        self,
        hints: Dict[str, str],
        hot_boards: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """将新闻主题/涨停标签/行业字段通过东财词典归一为候选板块。"""
        hot_by_code = {str(b.get("ts_code", "") or ""): b for b in hot_boards}
        hot_by_name = {self._clean_text(str(b.get("name", "") or "")): b for b in hot_boards}
        source_groups = [
            [("news_theme", "news_theme", "news_theme_board", 500, 3)],
            [("lu_desc", "limit_tag", "limit_tag_board", 400, 3)],
            [
                ("concept", "selected_concept", "selected_concept_board", 260, 2),
                ("board_type", "selected_board_type", "selected_board_type_board", 240, 2),
                ("industry", "selected_industry", "selected_industry_board", 220, 1),
            ],
        ]

        for group in source_groups:
            result: List[Dict[str, Any]] = []
            seen: Set[str] = set()
            for source_key, normalize_source, matched_from, priority, top_n in group:
                text = hints.get(source_key, "")
                for match in self._board_service.normalize_board_terms(text, source=normalize_source, top_n=top_n):
                    code = str(match.get("ts_code", "") or "")
                    clean_name = self._clean_text(str(match.get("name", "") or ""))
                    identity = code or clean_name
                    if not identity or identity in seen:
                        continue
                    seen.add(identity)

                    hot = hot_by_code.get(code) or hot_by_name.get(clean_name) or {}
                    item = dict(hot) if hot else {
                        "rank": 999,
                        "name": match.get("name", ""),
                        "ts_code": code,
                        "up_nums": 0,
                        "cons_nums": 0,
                        "up_stat": "",
                        "days": 0,
                        "pct_chg": 0.0,
                    }
                    item["name"] = item.get("name") or match.get("name", "")
                    item["ts_code"] = item.get("ts_code") or code
                    item["matched_from"] = matched_from
                    item["_source_score_bonus"] = priority + int(match.get("match_score", 0) or 0)
                    item["_dict_match_reasons"] = match.get("match_reasons", [])
                    result.append(item)
            if result:
                return result

        return []

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
              "up_stat":"13天10板", "days":10, "pct_chg":2.86, "ts_code":"BKxxxx.DC"}, ...]
        """
        if trade_date in self._hot_board_cache:
            return self._hot_board_cache[trade_date]

        result = self._board_service.get_hot_boards(trade_date)
        if result:
            self._hot_board_cache[trade_date] = result
            self._trim_cache()
            return result

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
                        "matched_from": "limit_cpt_list_reference",
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
        concepts = self.get_stock_concepts(ts_code, trade_date)
        hints = self._get_stock_theme_hints(ts_code, trade_date)
        concept_names = {c["name"] for c in concepts}
        concept_codes = {c["ts_code"] for c in concepts}

        hot_boards = self.get_hot_boards(trade_date)
        normalized_hint_boards = self._normalized_hint_boards(hints, hot_boards)
        hint_matched = []
        membership_matched = []

        for board in hot_boards:
            name = board["name"]
            code = board.get("ts_code", "")
            match_score, match_reasons = self._theme_match_score(board, hints)
            if match_reasons:
                item = dict(board)
                item["matched_from"] = "hot_board_hint"
                hint_matched.append(item)
            elif name in concept_names or code in concept_codes:
                item = dict(board)
                item["matched_from"] = "stock_membership"
                membership_matched.append(item)
            else:
                # 也尝试子串匹配
                for cn in concept_names:
                    if cn in name or name in cn:
                        item = dict(board)
                        item["matched_from"] = "stock_membership"
                        membership_matched.append(item)
                        break

        exact_hint_boards = self._exact_hint_boards_from_concepts(concepts, hints, hot_boards)
        if normalized_hint_boards:
            matched = []
            seen_matched: Set[str] = set()
            for item in normalized_hint_boards + hint_matched + exact_hint_boards:
                identity = str(item.get("ts_code", "") or "") or self._clean_text(str(item.get("name", "") or ""))
                if not identity or identity in seen_matched:
                    continue
                seen_matched.add(identity)
                matched.append(item)
        else:
            matched = (hint_matched + exact_hint_boards) if (hint_matched or exact_hint_boards) else membership_matched

        for board in matched:
            match_score, match_reasons = self._theme_match_score(board, hints)
            board["match_score"] = match_score + int(board.get("_source_score_bonus", 0) or 0)
            board["match_reasons"] = list(board.get("_dict_match_reasons", [])) + match_reasons

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
