"""
风险拆解服务 - 7大维度量化风险计算（全面优化版）
新增技术面维度(stk_factor_pro)，修复行情/筹码/行业匹配问题
"""
import json
import math
import logging
import re
from typing import Dict, Any, Optional, List, Tuple, Set
from datetime import datetime, timedelta

from backend.database import SessionLocal
from backend.models.stock_risk import StockRiskBreakdown
from backend.models import SelectedStock, SelectionRecord
from backend.services.dc_board_service import DcBoardService
from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)

# 风险维度权重（总分100）- 新增技术面维度
RISK_WEIGHTS = {
    "market": 10,       # 市场环境 10分
    "chip": 14,         # 筹码压力 14分
    "news": 18,         # 舆情与公告 18分
    "capital": 14,      # 个股资金 14分
    "lhb": 10,          # 龙虎 10分
    "sector": 18,       # 板块与题材风险 18分
    "technical": 16,    # 技术结构 16分
}

# 公告风险关键词（合并到舆情&公告综合维度）
NEWS_RISK_KEYWORDS = {
    "减持": 10, "减持计划": 10, "大股东减持": 10,
    "减持股份": 8, "减持公告": 8,
    "解禁": 6, "限售股解禁": 6, "解禁公告": 5,
    "立案": 8, "立案调查": 10, "被立案": 8,
    "亏损": 5, "业绩亏损": 7, "净利润亏损": 8,
    "问询": 5, "监管问询": 6, "问询函": 6,
    "处罚": 7, "罚款": 7, "行政处罚": 8,
    "退市": 10, "退市风险": 10, "ST": 8,
    "违约": 7, "债务违约": 8, "逾期": 5,
}

# 东财个股-板块候选缓存
_DC_BOARD_CACHE: Dict[str, List[Dict[str, Any]]] = {}

BOARD_TYPE_PRIORITY = {
    "N": 8,     # 概念指数
    "TH": 7,    # 主题指数
    "S": 6,     # 特色指数
    "I": 4,     # 行业指数
    "R": 2,
}


# 否定词（用于关键词否定检测）
NEGATION_WORDS = {"不", "没有", "无", "未", "避免", "消除", "不存在", "无需"}


def _clean_board_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[\s,，/、;；|｜（）()【】\[\]：:]+", "", str(text))


def _split_board_terms(text: Optional[str]) -> List[str]:
    if not text:
        return []
    terms = re.split(r"[+＋,，/、;；|｜\s]+", str(text))
    return [term.strip() for term in terms if len(term.strip()) >= 2]


def get_risk_level(score: int) -> str:
    if score <= 20:
        return "低"
    elif score <= 40:
        return "中"
    elif score <= 70:
        return "高"
    else:
        return "极高"


def _get_risk_summary(total_score: int, level: str, tags: List[str]) -> str:
    if level == "极高":
        return "风险极高，接力价值极低"
    elif level == "高":
        return "风险较高，谨慎参与"
    elif level == "中":
        return "风险中等，需观察确认"
    return "风险可控，可正常观察"


def _build_warning_tip(tags: List[str], total_score: int) -> str:
    tips = []
    if "减持" in str(tags) or "减持计划" in str(tags):
        tips.append("股东减持")
    if "核按钮" in str(tags) and "无核按钮" not in str(tags):
        tips.append("核按钮砸盘")
    if total_score >= 70:
        if tips:
            tips.append("禁止接力")
        else:
            tips.append("全面风险较高")
    if tips:
        return "高危预警：" + "+".join(tips)
    return ""


class RiskBreakdownService:
    """风险拆解服务（6维度优化版）"""

    def __init__(self):
        self._pro = None
        self._market_sentiment_cache: Dict[str, Dict] = {}
        self._board_service = DcBoardService()
        self._last_sector_context: Dict[str, Any] = {}
        self._last_lhb_strength_evidence: List[Dict[str, Any]] = []
        self._last_lhb_risk_evidence: List[Dict[str, Any]] = []

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    def calculate_risk(self, ts_code: str, trade_date: Optional[str] = None,
                       force_refresh: bool = False) -> Dict[str, Any]:
        """7大维度风险计算"""
        if not force_refresh:
            cached = self._get_from_db(ts_code, trade_date)
            if cached:
                return cached

        if not trade_date:
            from backend.utils.trading_date import get_latest_trading_day
            trade_date = get_latest_trading_day()

        if not self.pro:
            return self._fallback_empty(trade_date)

        stock_data = self._get_stock_data(ts_code, trade_date)

        # 1. 行情风险（个股波动 + 市场情绪）
        market_score, market_tips = self._calc_market_risk(ts_code, trade_date, stock_data)

        # 2. 筹码风险
        chip_score, chip_tips = self._calc_chip_risk(ts_code, trade_date, stock_data)

        # 3. 舆情&公告综合风险
        news_score, news_tips = self._calc_news_risk(
            ts_code, stock_data.get("stock_name", ""), trade_date
        )

        # 4. 资金风险
        capital_score, capital_tips = self._calc_capital_risk(ts_code, trade_date)

        # 5. 龙虎风险
        lhb_score, lhb_tips = self._calc_lhb_risk(ts_code, trade_date)

        # 6. 行业风险（动态映射）
        sector_score, sector_tips = self._calc_sector_risk(
            ts_code, stock_data, trade_date
        )

        # 7. 技术面风险（新增，stk_factor_pro）
        technical_score, technical_tips = self._calc_technical_risk(ts_code, trade_date)

        # 总分
        total_score = market_score + chip_score + news_score + capital_score + lhb_score + sector_score + technical_score
        risk_level = get_risk_level(total_score)

        all_tips = market_tips + chip_tips + news_tips + capital_tips + lhb_tips + sector_tips + technical_tips
        risk_summary = _get_risk_summary(total_score, risk_level, all_tips)
        warning_tip = _build_warning_tip(all_tips, total_score)

        result = {
            "data_status": "available",
            "ts_code": ts_code,
            "trade_date": trade_date,
            "total_score": total_score,
            "risk_level": risk_level,
            "risk_summary": risk_summary,
            "warning_tip": warning_tip,
            "market_score": market_score,
            "chip_score": chip_score,
            "news_score": news_score,
            "capital_score": capital_score,
            "lhb_score": lhb_score,
            "sector_score": sector_score,
            "technical_score": technical_score,
            "market_tips": market_tips,
            "chip_tips": chip_tips,
            "news_tips": news_tips,
            "capital_tips": capital_tips,
            "lhb_tips": lhb_tips,
            "sector_tips": sector_tips,
            "technical_tips": technical_tips,
            "sector_context": self._last_sector_context,
            "lhb_strength_evidence": self._last_lhb_strength_evidence,
            "lhb_risk_evidence": self._last_lhb_risk_evidence,
            "strength_evidence": self._build_strength_evidence(),
            "risk_evidence": self._build_risk_evidence(),
        }

        self._save_to_db(ts_code, trade_date, result)

        history = self._get_history(ts_code, trade_date)
        if history:
            result["history"] = history

        return result

    # ==================== 数据采集 ====================

    def _get_stock_data(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """获取选股数据"""
        db = SessionLocal()
        try:
            rec = db.query(SelectionRecord).filter(
                SelectionRecord.trade_date == trade_date,
                SelectionRecord.status == "success",
            ).order_by(SelectionRecord.id.desc()).first()
            if rec:
                stock = db.query(SelectedStock).filter(
                    SelectedStock.record_id == rec.id,
                    SelectedStock.ts_code == ts_code,
                ).first()
                if stock:
                    return {
                        "trade_date": trade_date,
                        "change_pct": stock.change_pct or 0,
                        "pre_change_pct": stock.pre_change_pct or 0,
                        "rise_10d_pct": stock.rise_10d_pct or 0,
                        "limit_up_days": stock.limit_up_days or 0,
                        "circ_mv": stock.circ_mv or 0,
                        "industry": stock.industry or "",
                        "concept": stock.concept or "",
                        "stock_name": stock.name or "",
                        "lu_desc": stock.lu_desc or "",
                        "lu_tag": stock.lu_tag or "",
                        "board_type": stock.board_type or "",
                    }
        finally:
            db.close()
        return {}

    def _get_yesterday_daily_data(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        """从Tushare获取昨日行情（换手率+振幅）"""
        try:
            prev_date = self._get_prev_trade_date(trade_date)
            if not prev_date:
                return {}
            df_basic = self.pro.daily_basic(ts_code=ts_code, trade_date=prev_date,
                                            fields="ts_code,turnover_rate")
            turnover_rate = 0
            if df_basic is not None and not df_basic.empty:
                turnover_rate = float(df_basic.iloc[0].get("turnover_rate", 0) or 0)
            df_daily = self.pro.daily(ts_code=ts_code, trade_date=prev_date,
                                      fields="ts_code,high,low,pre_close")
            amplitude = 0
            if df_daily is not None and not df_daily.empty:
                row = df_daily.iloc[0]
                high = float(row.get("high", 0) or 0)
                low = float(row.get("low", 0) or 0)
                pre_close = float(row.get("pre_close", 0) or 0)
                if pre_close > 0:
                    amplitude = (high - low) / pre_close * 100
            return {"turnover_rate": turnover_rate, "amplitude": amplitude}
        except Exception as e:
            logger.warning(f"获取昨日行情失败 {ts_code}: {e}")
        return {}

    def _get_prev_trade_date(self, trade_date: str) -> Optional[str]:
        """获取前一个交易日"""
        try:
            from backend.utils.trading_date import get_previous_trading_day
            return get_previous_trading_day(trade_date)
        except Exception:
            dt = datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=1)
            return dt.strftime("%Y%m%d")

    def _get_market_sentiment(self, trade_date: str) -> Dict[str, Any]:
        """获取全局市场情绪数据（缓存1天）"""
        if trade_date in self._market_sentiment_cache:
            return self._market_sentiment_cache[trade_date]

        result: Dict[str, Any] = {
            "index_pct": 0,          # 大盘涨跌幅
            "market_volume": 0,      # 沪深总成交额(亿元)
            "market_tr": 0,          # 上证换手率(%)
            "limit_up_count": 0,     # 涨停家数
            "limit_down_count": 0,   # 跌停家数
            "max_connected": 0,      # 最高连板高度
            "up_down_ratio": 0,      # 涨跌比
            "zhaban_rate": 0,        # 炸板率(%)
            "north_money": 0,        # 北向资金净流入(百万元)
        }

        try:
            df_idx = self.pro.index_daily(ts_code="000001.SH", trade_date=trade_date,
                                          fields="pct_change")
            if df_idx is not None and not df_idx.empty:
                result["index_pct"] = float(df_idx.iloc[0].get("pct_change", 0) or 0)
        except Exception as e:
            logger.warning(f"获取大盘指数失败: {e}")

        try:
            # 市场成交额从 index_daily 获取（上证综合指数）
            df_vol = self.pro.index_daily(ts_code="000001.SH", trade_date=trade_date,
                                          fields="amount")
            if df_vol is not None and not df_vol.empty:
                sh_amount = float(df_vol.iloc[0].get("amount", 0) or 0)
                # amount 单位千元，转为亿元
                result["market_volume"] = round(sh_amount / 100000, 1)
        except Exception as e:
            logger.warning(f"获取市场成交额失败: {e}")

        try:
            # 上证换手率（index_dailybasic）
            df_tr = self.pro.index_dailybasic(ts_code="000001.SH", trade_date=trade_date,
                                              fields="turnover_rate")
            if df_tr is not None and not df_tr.empty:
                result["market_tr"] = float(df_tr.iloc[0].get("turnover_rate", 0) or 0)
        except Exception as e:
            logger.warning(f"获取市场换手率失败: {e}")

        try:
            df_step = self.pro.limit_step(trade_date=trade_date)
            if df_step is not None and not df_step.empty:
                result["max_connected"] = int(df_step["nums"].max()) if "nums" in df_step.columns else 0
        except Exception as e:
            logger.warning(f"获取连板数据失败: {e}")

        try:
            # 涨跌停/炸板统计统一使用 limit_list_d，避免和同花顺涨停池混口径。
            df_limit = self.pro.limit_list_d(trade_date=trade_date)
            if df_limit is not None and not df_limit.empty:
                limit_col = "limit" if "limit" in df_limit.columns else "limit_type"
                limits = df_limit[limit_col].astype(str).str.upper() if limit_col in df_limit.columns else []
                up_count = sum(1 for item in limits if item == "U" or "涨停" in item)
                down_count = sum(1 for item in limits if item == "D" or "跌停" in item)
                zhaban_count = sum(1 for item in limits if item == "Z" or "炸" in item)
                result["limit_up_count"] = int(up_count)
                result["limit_down_count"] = int(down_count)
                if up_count + down_count > 0:
                    result["up_down_ratio"] = round(up_count / max(down_count, 1), 2)
                if len(df_limit) > 0:
                    result["zhaban_rate"] = round(zhaban_count / len(df_limit) * 100, 1)
        except Exception as e:
            logger.warning(f"获取涨跌停/炸板数据失败: {e}")

        try:
            # 北向资金净流入（moneyflow_hsgt）
            df_north = self.pro.moneyflow_hsgt(trade_date=trade_date)
            if df_north is not None and not df_north.empty:
                row = df_north.iloc[0]
                result["north_money"] = float(row.get("north_money", 0) or 0)
        except Exception as e:
            logger.warning(f"获取北向资金数据失败: {e}")

        self._market_sentiment_cache[trade_date] = result
        return result

    # ==================== 行业动态映射 ====================

    def _get_dc_board_candidates(self, ts_code: str, trade_date: str) -> List[Dict[str, Any]]:
        """从已落库的东财个股-板块关系读取候选板块，缺失时按需刷新单股"""
        cache_key = f"{ts_code}_{trade_date}"
        if cache_key in _DC_BOARD_CACHE:
            return _DC_BOARD_CACHE[cache_key]

        candidates = self._board_service.get_stock_boards(
            ts_code,
            trade_date=trade_date,
            refresh_if_missing=True,
        )
        _DC_BOARD_CACHE[cache_key] = candidates
        return candidates

    def _score_board_candidate(self, board: Dict[str, Any], stock_data: Dict[str, Any]) -> Tuple[int, List[str]]:
        """根据新闻主题、涨停原因、概念和行业字段给候选板块打分"""
        score = 0
        reasons: List[str] = []

        board_name = str(board.get("name", "") or "")
        board_type = str(board.get("type", "") or "")
        clean_name = _clean_board_text(board_name)
        industry = str(stock_data.get("industry", "") or "")
        concept = str(stock_data.get("concept", "") or "")
        lu_desc = str(stock_data.get("lu_desc", "") or "")
        board_type_text = str(stock_data.get("board_type", "") or "")
        news_theme = str(stock_data.get("news_theme", "") or "")

        if board.get("source") == "eastmoney":
            score += 8

        if "概念" in board_type:
            score += 8
        elif "行业" in board_type:
            score += 4
        elif "地域" in board_type:
            score -= 12

        for source_text, label, exact_weight, fuzzy_weight in (
            (news_theme, "新闻主题", 160, 110),
            (lu_desc, "涨停原因", 120, 85),
            (concept, "概念字段", 55, 35),
            (board_type_text, "板块字段", 45, 30),
        ):
            clean_text = _clean_board_text(source_text)
            matched = False
            for idx, term in enumerate(_split_board_terms(source_text)):
                clean_term = _clean_board_text(term)
                if clean_name and clean_term and clean_name == clean_term:
                    score += exact_weight + max(0, 30 - idx * 5)
                    reasons.append(f"{label}优先命中{board_name}")
                    matched = True
                    break
            if matched:
                continue
            if clean_name and clean_name in clean_text:
                score += fuzzy_weight
                reasons.append(f"{label}命中{board_name}")
                continue
            for term in _split_board_terms(source_text):
                clean_term = _clean_board_text(term)
                if clean_name and clean_term and (clean_term in clean_name or clean_name in clean_term):
                    score += max(20, fuzzy_weight - 15)
                    reasons.append(f"{label}匹配{term}")
                    break

        clean_industry = _clean_board_text(industry)
        if clean_name and clean_industry:
            if clean_name == clean_industry:
                score += 50
                reasons.append(f"行业精确匹配{industry}")
            elif clean_industry in clean_name or clean_name in clean_industry:
                score += 30
                reasons.append(f"行业模糊匹配{industry}")

        return score, reasons

    def _resolve_sector_board(self, ts_code: str, stock_data: Dict[str, Any], trade_date: str) -> Optional[Dict[str, Any]]:
        """优先按新闻主题/涨停标签归一到东财板块，再用成分关系确认和兜底。"""
        enriched_stock_data = dict(stock_data)
        attribution = self._get_cached_theme_attribution_for_risk(ts_code, trade_date)
        if attribution:
            enriched_stock_data["news_theme"] = attribution.get("primary_theme") or ""

        candidates = self._get_dc_board_candidates(ts_code, trade_date)
        by_code = {str(board.get("ts_code", "") or ""): board for board in candidates}
        by_name = {_clean_board_text(str(board.get("name", "") or "")): board for board in candidates}

        priority_sources = [
            ("news_theme", "news_theme"),
            ("lu_desc", "limit_tag"),
            ("concept", "selected_concept"),
            ("board_type", "selected_board_type"),
            ("industry", "selected_industry"),
        ]

        for key, source in priority_sources:
            text = str(enriched_stock_data.get(key, "") or "")
            for match in self._board_service.normalize_board_terms(text, source=source, top_n=3):
                code = str(match.get("ts_code", "") or "")
                clean_name = _clean_board_text(str(match.get("name", "") or ""))
                member = by_code.get(code) or by_name.get(clean_name)
                if member:
                    result = dict(member)
                    result.update({
                        "ts_code": code or member.get("ts_code"),
                        "name": match.get("name") or member.get("name"),
                        "type": match.get("type") or member.get("type", ""),
                        "source": "eastmoney",
                        "match_score": match.get("match_score", 0),
                        "matched_from": match.get("matched_from", source),
                    })
                    return result

        best: Optional[Dict[str, Any]] = None
        for board in candidates:
            score, reasons = self._score_board_candidate(board, enriched_stock_data)
            if score <= 0:
                continue
            enriched = dict(board)
            enriched["match_score"] = score
            enriched["match_reasons"] = reasons
            if best is None or score > best.get("match_score", 0):
                best = enriched

        if best:
            return best

        return None

    # ==================== 维度计算 ====================

    def _calc_market_risk(self, ts_code: str, trade_date: str,
                          stock_data: Dict) -> Tuple[int, List[str]]:
        """行情风险计算（个股波动 + 市场情绪 + 行业板块）"""
        score = 0
        tips = []

        # -- 个股维度 --
        daily = self._get_yesterday_daily_data(ts_code, trade_date)
        turnover_rate = daily.get("turnover_rate", 0) or 0
        if turnover_rate > 20:
            score += 2
            tips.append(f"昨日换手率{turnover_rate:.1f}%，交投活跃")
        elif turnover_rate > 10:
            score += 1
            tips.append(f"昨日换手率{turnover_rate:.1f}%，筹码换手偏高")
        amplitude = daily.get("amplitude", 0) or 0
        if amplitude > 10:
            score += 2
            tips.append(f"昨日振幅{amplitude:.1f}%，股价波动大")
        elif amplitude > 5:
            score += 1
            tips.append(f"昨日振幅{amplitude:.1f}%，波动适中")

        # -- 市场情绪（全局） --
        sentiment = self._get_market_sentiment(trade_date)

        index_pct = sentiment.get("index_pct", 0) or 0
        if index_pct < -2:
            score += 2
            tips.append(f"大盘下跌{index_pct:.2f}%，系统性风险")
        elif index_pct < -1:
            score += 1
            tips.append(f"大盘下跌{index_pct:.2f}%")

        # 沪深总成交额（亿元）
        market_volume = sentiment.get("market_volume", 0) or 0
        if 0 < market_volume < 5000:
            score += 1
            tips.append(f"沪市成交额{market_volume:.0f}亿，缩量市场")
        elif market_volume > 15000:
            score += 1
            tips.append(f"沪市成交额{market_volume:.0f}亿，放量过热")

        # 上证换手率
        market_tr = sentiment.get("market_tr", 0) or 0
        if 0 < market_tr < 0.5:
            score += 1
            tips.append(f"上证换手率{market_tr:.2f}%，交投冷清")

        max_connected = sentiment.get("max_connected", 0) or 0
        if max_connected <= 2:
            score += 2
            tips.append(f"最高连板仅{max_connected}板，短线情绪冰点")
        elif max_connected <= 4:
            score += 1
            tips.append(f"最高连板{max_connected}板，情绪一般")

        limit_down = sentiment.get("limit_down_count", 0) or 0
        if limit_down > 20:
            score += 2
            tips.append(f"跌停{limit_down}家，市场恐慌")
        elif limit_down > 10:
            score += 1
            tips.append(f"跌停{limit_down}家，局部恐慌")

        # 炸板率
        zhaban_rate = sentiment.get("zhaban_rate", 0) or 0
        if zhaban_rate > 40:
            score += 2
            tips.append(f"炸板率{zhaban_rate:.1f}%，封板意愿弱")
        elif zhaban_rate > 25:
            score += 1
            tips.append(f"炸板率{zhaban_rate:.1f}%，封板一般")

        # 北向资金
        north_money = sentiment.get("north_money", 0) or 0
        if north_money < -5000:
            score += 2
            tips.append(f"北向净流出{abs(north_money):.0f}百万，外资出逃")
        elif north_money < -2000:
            score += 1
            tips.append(f"北向净流出{abs(north_money):.0f}百万")

        # -- 行业板块表现纳入行情风险 --
        board = self._resolve_sector_board(ts_code, stock_data, trade_date)
        if board:
            try:
                daily = self._board_service.get_board_daily(board["ts_code"], trade_date)
                ind_pct = float(daily.get("pct_chg", 0) or 0)
                board_name = board.get("name") or board.get("ts_code")
                if ind_pct < -3:
                    score += 2
                    tips.append(f"{board_name}下跌{ind_pct:.2f}%，板块走弱")
                elif ind_pct < -1:
                    score += 1
                    tips.append(f"{board_name}下跌{ind_pct:.2f}%")
            except Exception:
                pass

        return min(score, RISK_WEIGHTS["market"]), tips[:5]

    def _calc_chip_risk(self, ts_code: str, trade_date: str,
                        stock_data: Dict) -> Tuple[int, List[str]]:
        """筹码风险计算"""
        score = 0
        tips = []

        try:
            df = self.pro.cyq_perf(ts_code=ts_code, trade_date=trade_date)
            if df is not None and not df.empty:
                winner_rate = float(df.iloc[0].get("winner_rate", 0) or 0)
                if winner_rate > 80:
                    score += 10
                    tips.append(f"获利盘{winner_rate:.1f}%，抛压极大")
                elif winner_rate > 60:
                    score += 5
                    tips.append(f"获利盘{winner_rate:.1f}%，存在兑现压力")
        except Exception as e:
            logger.warning(f"获取筹码数据失败 {ts_code}: {e}")

        rise_10d = stock_data.get("rise_10d_pct", 0) or 0
        if rise_10d > 30:
            score += 5
            tips.append(f"近10日涨幅{rise_10d:.1f}%，阶段高位")
        elif rise_10d > 20:
            score += 3
            tips.append(f"近10日涨幅{rise_10d:.1f}%，短期涨幅较大")

        return min(score, 18), tips[:3]

    def _calc_news_risk(self, ts_code: str, stock_name: str,
                        trade_date: str) -> Tuple[int, List[str]]:
        """舆情&公告综合风险计算（合并项）"""
        score = 0
        tips = []
        if not stock_name:
            return 0, []

        from backend.services.integrated_news_service import get_integrated_news_service
        svc = get_integrated_news_service()
        try:
            news_result = svc.get_stock_news(stock_name=stock_name, limit=20, ensure_recent=False)
            if news_result.get("code") == 200:
                news_list = news_result.get("data", {}).get("news_list", [])

                # 公告关键词扫描（含否定检测）
                matched = set()
                for news in news_list:
                    text = f"{news.get('title', '')} {news.get('content', '')}"
                    for kw, weight in sorted(NEWS_RISK_KEYWORDS.items(), key=lambda x: -len(x[0])):
                        if kw in text and kw not in matched:
                            # 否定检测：关键词前5个字符内有否定词则不计数
                            idx = text.find(kw)
                            before = text[max(0, idx - 6):idx]
                            if any(neg in before for neg in NEGATION_WORDS):
                                continue
                            matched.add(kw)
                            score += weight
                            if kw not in tips:
                                tips.append(kw)
                            break

                # 负面情感计数（与公告互补，不重复计分）
                negative_count = sum(1 for n in news_list if n.get("sentiment_type") == "negative")
                if negative_count >= 3:
                    score += 8
                    tips.append(f"{negative_count}条利空新闻")
                elif negative_count >= 2:
                    score += 5
                    tips.append(f"{negative_count}条利空新闻")
                elif negative_count >= 1 and not matched:
                    score += 3
                    tips.append("存在利空新闻")
        except Exception as e:
            logger.warning(f"计算舆情&公告风险失败: {e}")
        finally:
            try:
                svc.close()
            except Exception:
                pass

        return min(score, 25), tips[:4]

    def _calc_capital_risk(self, ts_code: str, trade_date: str) -> Tuple[int, List[str]]:
        """资金风险计算"""
        score = 0
        tips = []
        net_mf = None
        net_label = "主力"
        try:
            df = self.pro.moneyflow_dc(ts_code=ts_code, trade_date=trade_date)
            if df is not None and not df.empty:
                row = df.iloc[0]
                buy_elg = row.get("buy_elg_amount")
                sell_elg = row.get("sell_elg_amount")
                if buy_elg is not None and sell_elg is not None:
                    net_mf = float(buy_elg or 0) - float(sell_elg or 0)
                    net_label = "超大单"
                else:
                    net_mf = float(row.get("net_mf_amount", 0) or 0)
        except Exception as e:
            logger.warning(f"获取东财资金流向失败 {ts_code}: {e}")

        if net_mf is None:
            try:
                df = self.pro.moneyflow(ts_code=ts_code, trade_date=trade_date)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    net_mf = float(row.get("net_mf_amount", 0) or 0)
                    net_label = "主力"
            except Exception as e:
                logger.warning(f"获取资金流向失败 {ts_code}: {e}")

        if net_mf is not None:
            if net_mf < -5000:
                score += 10
                tips.append(f"{net_label}净流出{abs(net_mf):.0f}万元，资金出逃明显")
            elif net_mf < -2000:
                score += 6
                tips.append(f"{net_label}净流出{abs(net_mf):.0f}万元")
            elif net_mf < -500:
                score += 3
                tips.append(f"{net_label}净流出{abs(net_mf):.0f}万元")
            elif net_mf > 5000:
                score -= 2

        return min(max(score, 0), RISK_WEIGHTS["capital"]), tips[:2]

    def _calc_lhb_risk(self, ts_code: str, trade_date: str) -> Tuple[int, List[str]]:
        """龙虎风险计算（席位升级）"""
        score = 0
        tips = []
        self._last_lhb_strength_evidence = []
        self._last_lhb_risk_evidence = []

        from backend.services.lhb_service import analyze_lhb
        from backend.services.seat_library import get_seat_risk_score, match_seat_tag
        try:
            lhb_data = analyze_lhb(ts_code, trade_date, force_refresh=False)
            if lhb_data.get("data_status") == "available":
                action_tag = lhb_data.get("action_tag", "")
                net_amount = lhb_data.get("net_amount", 0) or 0
                buy_top5 = lhb_data.get("buy_top5", [])
                sell_top5 = lhb_data.get("sell_top5", [])

                premium_buy_seats = [
                    seat.get("exalter", "")
                    for seat in buy_top5
                    if match_seat_tag(seat.get("exalter", ""))[0] == "高溢价"
                ]
                dump_sell_seats = [
                    seat.get("exalter", "")
                    for seat in sell_top5
                    if match_seat_tag(seat.get("exalter", ""))[0] in ("核按钮", "量化", "散户")
                ]
                if premium_buy_seats:
                    self._last_lhb_strength_evidence.append({
                        "type": "premium_buy",
                        "label": "高溢价席位买入",
                        "seats": premium_buy_seats[:5],
                        "score_effect": "抵扣龙虎风险，进入强势依据",
                    })
                if dump_sell_seats:
                    self._last_lhb_risk_evidence.append({
                        "type": "dump_sell",
                        "label": "砸盘席位卖出",
                        "seats": dump_sell_seats[:5],
                        "score_effect": "增加龙虎风险",
                    })

                # 席位标签风险评分（独立计算，用于评分）
                for seat_list, label in [(buy_top5, "买入"), (sell_top5, "卖出")]:
                    for seat in seat_list:
                        exalter = seat.get("exalter", "")
                        seat_risk = get_seat_risk_score(exalter)
                        if seat_risk > 0:
                            score += seat_risk
                        elif seat_risk < 0:
                            score += seat_risk

                # 核按钮提示使用 lhb_service.risk_tips（与龙虎榜面板共享数据源）
                lhb_risk_tips = lhb_data.get("risk_tips", [])
                has_knife = any(
                    "核按钮" in t and "无核按钮" not in t
                    for t in lhb_risk_tips if isinstance(t, str)
                )
                if has_knife:
                    tips.append("核按钮席位")

                # 净卖出风险
                if net_amount < -50000000:
                    score += 3
                    tips.append("机构/游资净卖出金额较大")

                if action_tag in ("一致砸盘", "温和出货"):
                    score += 2
                    tips.append("游资出货明显")

            elif lhb_data.get("data_status") == "not_on_list":
                pass
        except Exception as e:
            logger.warning(f"获取龙虎风险失败 {ts_code}: {e}")

        return min(max(score, 0), 12), tips[:3]

    def _build_strength_evidence(self) -> List[str]:
        evidence: List[str] = []
        for item in self._last_lhb_strength_evidence:
            seats = "、".join(item.get("seats", [])[:5])
            if seats:
                evidence.append(f"{item.get('label', '强势席位')}：{seats}")
        return evidence

    def _build_risk_evidence(self) -> List[str]:
        evidence: List[str] = []
        for item in self._last_lhb_risk_evidence:
            seats = "、".join(item.get("seats", [])[:5])
            if seats:
                evidence.append(f"{item.get('label', '风险席位')}：{seats}")
        return evidence

    def _calc_technical_risk(self, ts_code: str, trade_date: str) -> Tuple[int, List[str]]:
        """技术面风险计算（stk_factor_pro）18分

        评估维度：
        - MACD死叉/金叉
        - RSI超买/超卖
        - KDJ高位死叉
        - CCI 超买/超卖
        - WR 威廉指标触顶
        - 量比异常（放量/缩量）
        - 连涨/连跌天数
        """
        score = 0
        tips = []
        try:
            df = self.pro.stk_factor_pro(
                ts_code=ts_code, trade_date=trade_date,
                fields="macd_bfq,macd_dea_bfq,macd_dif_bfq,rsi_bfq_6,kdj_k_bfq,kdj_bfq,"
                       "cci_bfq,wr_bfq,volume_ratio,downdays,updays"
            )
            if df is None or df.empty:
                return 0, []

            row = df.iloc[0]

            # MACD 死叉(DIF < DEA) → 趋势转弱 +3
            dif = float(row.get("macd_dif_bfq", 0) or 0)
            dea = float(row.get("macd_dea_bfq", 0) or 0)
            if dif < dea and dea < 0:
                score += 3
                tips.append("MACD死叉，趋势转弱")
            elif dif < dea:
                score += 2
                tips.append("MACD死叉")

            # MACD 高位死叉(MACD > 0 且 DIF < DEA) → +1
            macd = float(row.get("macd_bfq", 0) or 0)
            if dif < dea and macd > 0:
                score += 1
                if not any("MACD" in t for t in tips):
                    tips.append("MACD高位死叉")

            # RSI 超买(>80) / 超卖(<20)
            rsi = float(row.get("rsi_bfq_6", 50) or 50)
            if rsi > 80:
                score += 3
                tips.append(f"RSI{rsi:.0f}，超买")
            elif rsi > 70:
                score += 1
                tips.append(f"RSI{rsi:.0f}，偏高")
            elif rsi < 20:
                score += 2
                tips.append(f"RSI{rsi:.0f}，超卖")
            elif rsi < 30:
                score += 1
                tips.append(f"RSI{rsi:.0f}，偏低")

            # KDJ 高位(>80)
            kdj_k = float(row.get("kdj_k_bfq", 50) or 50)
            if kdj_k > 80:
                score += 2
                tips.append(f"KDJ-K{kdj_k:.0f}，高位")

            # CCI 超买(>200) / 超卖(<-200)
            cci = float(row.get("cci_bfq", 0) or 0)
            if cci > 200:
                score += 2
                tips.append(f"CCI{cci:.0f}，超买")
            elif cci < -200:
                score += 2
                tips.append(f"CCI{cci:.0f}，超卖")

            # WR 触顶(=0表示最高价出现在近期高位)
            wr = float(row.get("wr_bfq", 50) or 50)
            if wr <= 5:
                score += 1
                tips.append("WR触顶")

            # 量比异常
            vol_ratio = float(row.get("volume_ratio", 1) or 1)
            if vol_ratio > 3:
                score += 2
                tips.append(f"量比{vol_ratio:.1f}，放量异常")
            elif vol_ratio < 0.3:
                score += 1
                tips.append(f"量比{vol_ratio:.1f}，缩量明显")

            # 连涨天数过多(>5) → 回调风险
            updays = int(row.get("updays", 0) or 0)
            if updays >= 5:
                score += 2
                tips.append(f"连涨{updays}天，回调风险")

            # 连跌天数过多(>3) → 弱势
            downdays = int(row.get("downdays", 0) or 0)
            if downdays >= 5:
                score += 2
                tips.append(f"连跌{downdays}天，弱势")
            elif downdays >= 3:
                score += 1
                tips.append(f"连跌{downdays}天")

        except Exception as e:
            logger.warning(f"获取技术面数据失败 {ts_code}: {e}")

        return min(score, 18), tips[:4]

    def _calc_sector_risk(self, ts_code: str, stock_data: Dict[str, Any], trade_date: str) -> Tuple[int, List[str]]:
        """板块与题材风险计算（东财板块体系）"""
        score = 0
        tips = []
        self._last_sector_context = {}
        industry = str(stock_data.get("industry", "") or "")
        if not industry and not stock_data.get("lu_desc") and not stock_data.get("concept"):
            return 0, []

        board = self._resolve_sector_board(ts_code, stock_data, trade_date)
        if not board:
            tips.append("暂无板块行情数据")
            return 0, tips

        board_code = board["ts_code"]
        board_name = board.get("name") or industry or board_code

        daily = self._board_service.get_board_daily(board_code, trade_date)
        moneyflow = self._board_service.get_board_moneyflow(board_code, trade_date)
        strength = self._board_service.get_board_strength(board_code, trade_date)

        pct = float(daily.get("pct_chg", 0) or 0)
        if pct <= -3:
            score += 5
            tips.append(f"{board_name}板块下跌{abs(pct):.1f}%，题材明显走弱")
        elif pct <= -1.5:
            score += 3
            tips.append(f"{board_name}板块下跌{abs(pct):.1f}%，题材承接转弱")
        elif pct <= -0.5:
            score += 1
            tips.append(f"{board_name}板块小幅走弱")
        elif pct >= 3:
            score -= 2

        net_yi = float(moneyflow.get("net_amount_yi", 0) or 0)
        if net_yi <= -5:
            score += 4
            tips.append(f"板块资金净流出{abs(net_yi):.1f}亿")
        elif net_yi <= -2:
            score += 2
            tips.append(f"板块资金净流出{abs(net_yi):.1f}亿")
        elif net_yi >= 5:
            score -= 2

        limit_up_count = int(strength.get("limit_up_count", 0) or 0)
        member_count = int(strength.get("member_count", 0) or 0)
        limit_up_ratio = limit_up_count / member_count if member_count else 0
        if limit_up_count == 0 and member_count:
            score += 4
            tips.append("板块内暂无涨停，题材扩散不足")
        elif limit_up_count <= 2 and member_count >= 30:
            score += 2
            tips.append(f"板块内涨停扩散不足，仅{limit_up_count}家涨停")
        elif limit_up_ratio >= 0.05:
            score -= 2

        stock_change_pct = float(stock_data.get("change_pct", 0) or 0)
        board_pct = float(strength.get("board_pct_chg", pct) or pct)
        if board_pct > 1 and stock_change_pct < board_pct:
            score += 1
            tips.append("个股表现弱于主线板块")

        strength_score = float(strength.get("strength_score", 0) or 0)
        if strength_score and strength_score < 35:
            score += 2
            tips.append("板块热度回落，题材承接偏弱")

        self._last_sector_context = {
            "primary_board": {
                "code": board_code,
                "name": board_name,
                "source": "eastmoney",
            },
            "board_pct_chg": pct,
            "money_net_amount": moneyflow.get("net_amount", 0) or 0,
            "money_net_amount_yi": net_yi,
            "limit_up_count": limit_up_count,
            "member_count": member_count,
            "strength_score": strength_score,
        }

        attribution = self._get_cached_theme_attribution_for_risk(ts_code, trade_date)
        if attribution:
            tips = self._append_theme_attribution_tips(tips, attribution)

        return min(max(score, 0), RISK_WEIGHTS["sector"]), tips[:6]

    @staticmethod
    def _get_cached_theme_attribution_for_risk(ts_code: str, trade_date: str) -> Dict[str, Any]:
        try:
            from backend.services.integrated_news_service import get_integrated_news_service
            svc = get_integrated_news_service()
            try:
                return svc.get_cached_stock_theme_attribution(ts_code, trade_date) or {}
            finally:
                svc.close()
        except Exception as e:
            logger.debug(f"读取主题归因缓存失败，风险拆解降级忽略: {e}")
            return {}

    @staticmethod
    def _append_theme_attribution_tips(tips: List[str], attribution: Dict[str, Any]) -> List[str]:
        result = list(tips or [])
        for line in attribution.get("explanation_lines", [])[:3]:
            if line and line not in result:
                result.append(line)
        return result[:6]

    # ==================== 数据库读写 ====================

    def _save_to_db(self, ts_code: str, trade_date: str, data: Dict[str, Any]):
        """保存到永久数据库"""
        db = SessionLocal()
        try:
            existing = db.query(StockRiskBreakdown).filter(
                StockRiskBreakdown.ts_code == ts_code,
                StockRiskBreakdown.trade_date == trade_date,
            ).first()
            fields = {
                "total_score": data["total_score"],
                "risk_level": data["risk_level"],
                "market_score": data["market_score"],
                "chip_score": data["chip_score"],
                "capital_score": data["capital_score"],
                "lhb_score": data["lhb_score"],
                "sector_score": data["sector_score"],
                "sentiment_score": data.get("technical_score", 0),
                "market_tips": json.dumps(data["market_tips"], ensure_ascii=False),
                "chip_tips": json.dumps(data["chip_tips"], ensure_ascii=False),
                "capital_tips": json.dumps(data["capital_tips"], ensure_ascii=False),
                "lhb_tips": json.dumps(data["lhb_tips"], ensure_ascii=False),
                "sector_tips": json.dumps(data["sector_tips"], ensure_ascii=False),
                "sentiment_tips": json.dumps(data.get("technical_tips", []), ensure_ascii=False),
                "news_tips": json.dumps(data["news_tips"], ensure_ascii=False),
                "risk_summary": data.get("risk_summary", ""),
                "warning_tip": data.get("warning_tip", ""),
            }
            # announcement/sentiment 字段不再写入（旧字段保留兼容）
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                existing.announcement_score = data["news_score"]
            else:
                record = StockRiskBreakdown(
                    ts_code=ts_code, trade_date=trade_date,
                    announcement_score=data["news_score"],
                    **fields,
                )
                db.add(record)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"保存风险数据失败 {ts_code}: {e}")
        finally:
            db.close()

    def _get_from_db(self, ts_code: str, trade_date: Optional[str] = None) -> Optional[Dict]:
        """从数据库读取缓存"""
        db = SessionLocal()
        try:
            query = db.query(StockRiskBreakdown).filter(StockRiskBreakdown.ts_code == ts_code)
            if trade_date:
                query = query.filter(StockRiskBreakdown.trade_date == trade_date)
            record = query.order_by(StockRiskBreakdown.trade_date.desc()).first()
            if not record:
                return None
            return self._record_to_dict(record)
        finally:
            db.close()

    def _get_history(self, ts_code: str, current_date: str) -> List[Dict]:
        """获取历史风险记录（近3条）"""
        db = SessionLocal()
        try:
            records = db.query(StockRiskBreakdown).filter(
                StockRiskBreakdown.ts_code == ts_code,
                StockRiskBreakdown.trade_date < current_date,
            ).order_by(StockRiskBreakdown.trade_date.desc()).limit(3).all()
            return [self._record_to_dict(r) for r in records]
        finally:
            db.close()

    def _record_to_dict(self, record: StockRiskBreakdown) -> Dict:
        """数据库记录转字典（兼容新旧字段）"""
        def load_json(val):
            if not val:
                return []
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []

        # news_score 优先从 announcement_score 读取（旧数据兼容）
        news_score = record.announcement_score or 0
        news_tips = load_json(record.news_tips) or load_json(record.announcement_tips) or []

        # technical_score 存储在 sentiment_score（复用旧字段）
        technical_score = record.sentiment_score or 0
        technical_tips = load_json(record.sentiment_tips) or []

        return {
            "data_status": "available",
            "ts_code": record.ts_code,
            "trade_date": record.trade_date,
            "total_score": record.total_score,
            "risk_level": record.risk_level,
            "risk_summary": record.risk_summary or "",
            "warning_tip": record.warning_tip or "",
            "market_score": record.market_score or 0,
            "chip_score": record.chip_score or 0,
            "news_score": news_score,
            "capital_score": record.capital_score or 0,
            "lhb_score": record.lhb_score or 0,
            "sector_score": record.sector_score or 0,
            "technical_score": technical_score,
            "market_tips": load_json(record.market_tips),
            "chip_tips": load_json(record.chip_tips),
            "news_tips": news_tips,
            "capital_tips": load_json(record.capital_tips),
            "lhb_tips": load_json(record.lhb_tips),
            "sector_tips": load_json(record.sector_tips),
            "technical_tips": technical_tips,
            "sector_context": {},
            "lhb_strength_evidence": [],
            "lhb_risk_evidence": [],
            "strength_evidence": [],
            "risk_evidence": [],
        }

    def _fallback_empty(self, trade_date: str) -> Dict:
        return {
            "data_status": "source_not_configured",
            "total_score": 0, "risk_level": "低",
            "market_score": 0, "chip_score": 0,
            "news_score": 0, "capital_score": 0,
            "lhb_score": 0, "sector_score": 0, "technical_score": 0,
            "market_tips": [], "chip_tips": [],
            "news_tips": [], "capital_tips": [],
            "lhb_tips": [], "sector_tips": [], "technical_tips": [],
            "sector_context": {},
            "lhb_strength_evidence": [],
            "lhb_risk_evidence": [],
            "strength_evidence": [],
            "risk_evidence": [],
            "risk_summary": "数据源未配置", "warning_tip": "",
            "trade_date": trade_date,
        }


_risk_service: Optional[RiskBreakdownService] = None


def get_risk_breakdown_service() -> RiskBreakdownService:
    global _risk_service
    if _risk_service is None:
        _risk_service = RiskBreakdownService()
    return _risk_service


def calculate_risk(ts_code: str, trade_date: Optional[str] = None,
                   force_refresh: bool = False) -> Dict[str, Any]:
    svc = get_risk_breakdown_service()
    return svc.calculate_risk(ts_code, trade_date, force_refresh)
