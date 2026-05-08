"""
三阶段选股服务
"""
import logging
import os
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import time

from backend.services.tdx_selector import (
    TdxSelectorService,
    TdxStockResult,
    SelectionTask,
    create_default_task,
    create_conservative_task,
    create_aggressive_task,
    TASK_TEMPLATES,
)
try:
    from backend.services.tdx_mcp_client import McpTemporaryUnavailable
except Exception:
    class McpTemporaryUnavailable(RuntimeError):
        pass
from backend.services.data_collector import TushareDataCollector
from backend.services.seal_rate_calculator import SealRateCalculator
from backend.services.scoring.rule_score_service import RuleScoreService
from backend.services.scoring.next_day_plan import NextDayPlanService
from backend.services.model_engine.lightgbm_service import (
    batch_predict_before_selection,
    batch_predict_leader_main_t0,
)
from backend.services.scoring_v2 import StockScoringV2Service, is_score_v2_enabled
from backend.models import SelectionRecord, SelectedStock, StockFeatureSnapshot
from backend.database import SessionLocal
from backend.core.logging_config import get_selection_logger

logger = logging.getLogger(__name__)
sel_logger = get_selection_logger()


class PhaseResult:
    """阶段结果"""
    def __init__(self, phase_name: str, source: str):
        self.phase_name = phase_name
        self.source = source
        self.success = False
        self.data = None
        self.execution_time = 0.0
        self.error = None


class StockSelectorService:
    """三阶段选股服务"""

    def __init__(self, tushare_token: Optional[str] = None):
        self.tdx_selector = TdxSelectorService()
        self.collector = TushareDataCollector(tushare_token)
        self.seal_calculator = SealRateCalculator(tushare_token)

    def select_stocks(
        self,
        trade_date: Optional[str] = None,
        task_template: str = "default",
        custom_tasks: Optional[List[SelectionTask]] = None,
        tdx_mcp_func: Optional[Callable] = None,
        min_seal_rate: Optional[float] = None,
        period_days: int = 100,
        min_open_change_pct: Optional[float] = -3.0,
    ) -> Dict[str, Any]:
        """
        执行三阶段选股
        """
        overall_start = time.time()

        if trade_date is None:
            trade_date = self._get_trade_date()
            logger.info(f"自动获取最新交易日: {trade_date}")

        sel_logger.task_start(trade_date)

        # 获取任务
        if custom_tasks and len(custom_tasks) > 0:
            tasks = custom_tasks
        else:
            tasks = [TASK_TEMPLATES.get(task_template, create_default_task)()]

        # ========== 阶段1：通达信 MCP 选股 ==========
        phase1 = self._execute_phase1(tasks, tdx_mcp_func, trade_date)
        sel_logger.mcp_call_end(
            phase1.data.get("total_count", 0) if phase1.data else 0,
            phase1.execution_time * 1000
        )

        if not phase1.success or not phase1.data.get("stocks"):
            logger.warning("阶段1未选出股票，跳过后续阶段")
            sel_logger.task_complete(0, time.time() - overall_start)
            return self._build_final_result(
                trade_date=trade_date,
                phase1=phase1,
                phase2=None,
                phase3=None,
                final_stocks=[],
                overall_start=overall_start,
            )

        # ========== 阶段2：Tushare 补充分析 ==========
        phase2 = self._execute_phase2(phase1.data, trade_date)

        # ========== 阶段3：封板率计算与过滤 ==========
        phase3 = self._execute_phase3(
            phase1.data, trade_date, min_seal_rate, period_days
        )

        # 合并结果
        final_stocks = self._merge_results(
            phase1.data, phase2.data, phase3.data if phase3 else None, min_open_change_pct, min_seal_rate, trade_date
        )

        # 丰富数据：获取同花顺涨停榜单 + 上一日换手率
        if final_stocks:
            try:
                self._enrich_with_limit_list_ths(final_stocks, trade_date)
            except Exception as e:
                logger.warning(f"丰富涨停榜单数据失败（不影响主流程）: {e}")

        logger.info(
            f"========== 三阶段选股完成：阶段1选出 {phase1.data.get('total_count', 0)} 只，"
            f"最终通过 {len(final_stocks)} 只，总耗时 {time.time() - overall_start:.2f}秒 =========="
        )
        sel_logger.task_complete(len(final_stocks), time.time() - overall_start)

        return self._build_final_result(
            trade_date=trade_date,
            phase1=phase1,
            phase2=phase2,
            phase3=phase3,
            final_stocks=final_stocks,
            overall_start=overall_start,
        )

    def _execute_phase1(
        self, tasks: List[SelectionTask], tdx_mcp_func: Optional[Callable],
        trade_date: Optional[str] = None,
    ) -> PhaseResult:
        """执行阶段1：通达信 MCP 选股（支持降级到本地数据）"""
        phase_start = time.time()
        enable_fallback = os.getenv("ENABLE_LOCAL_FALLBACK", "true").lower() == "true"
        force_fallback = False

        # ─── 优先尝试 MCP ───
        if tdx_mcp_func is not None:
            result = PhaseResult(phase_name="选股", source="tdx_mcp")
            try:
                logger.info("========== 阶段1：通达信 MCP 选股 ==========")
                self.tdx_selector.tasks = list(tasks)
                selection_result = self.tdx_selector.select(tdx_mcp_func=tdx_mcp_func)
                total_count = selection_result.get("total_count", 0)

                if total_count > 0:
                    result.data = selection_result
                    result.success = True
                    result.execution_time = time.time() - phase_start
                    logger.info(f"阶段1完成(MCP)：选出 {total_count} 只股票")
                    return result

                task_results = selection_result.get("task_results", []) or []
                has_mcp_error = any((task.get("error") for task in task_results))
                has_temporary_unavailable = any(
                    task.get("error_type") == "mcp_temporary_unavailable"
                    for task in task_results
                )
                force_fallback = has_temporary_unavailable
                if (enable_fallback or force_fallback) and (total_count == 0 or has_mcp_error):
                    error_types = ",".join(sorted({
                        str(task.get("error_type") or "mcp_error")
                        for task in task_results
                        if task.get("error")
                    }))
                    logger.warning(
                        f"MCP返回 {total_count} 条"
                        f"{f'，错误类型={error_types}' if error_types else ''}，降级到本地数据选股"
                    )
                else:
                    result.data = selection_result
                    result.success = True
                    result.execution_time = time.time() - phase_start
                    return result
            except McpTemporaryUnavailable as e:
                force_fallback = True
                logger.warning(f"MCP临时不可用，强制降级到本地数据: {e}")
            except Exception as e:
                if enable_fallback:
                    logger.warning(f"MCP选股异常，降级到本地数据: {e}")
                else:
                    result.success = False
                    result.error = str(e)
                    result.execution_time = time.time() - phase_start
                    logger.error(f"MCP选股失败: {e}", exc_info=True)
                    return result

        # ─── 降级：本地 .day 文件选股（仅当启用降级时）───
        if not (enable_fallback or force_fallback):
            result = PhaseResult(phase_name="选股", source="tdx_mcp")
            result.success = False
            result.error = "MCP函数未配置且降级未启用"
            result.execution_time = time.time() - phase_start
            logger.error("MCP函数未配置且降级未启用，选股失败")
            return result

        logger.info("========== 阶段1：本地日线选股(降级模式) ==========")
        result = PhaseResult(phase_name="选股", source="tdx_local")
        try:
            from backend.services.tdx_local_selector import TdxLocalSelectorService
            local_selector = TdxLocalSelectorService()
            use_date = trade_date or self._get_trade_date()
            selection_result = local_selector.select(
                trade_date=use_date,
                max_circ_mv=2000,
                max_close_price=500,
                min_limit_up_count=3,
                period_days=100,
                data_collector=self.collector,
            )
            result.data = selection_result
            result.success = True
            result.execution_time = time.time() - phase_start

            total = selection_result.get("total_count", 0)
            logger.info(f"阶段1完成(本地)：选出 {total} 只股票")
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.execution_time = time.time() - phase_start
            logger.error(f"本地选股也失败: {e}", exc_info=True)

        return result

    def _execute_phase2(
        self, phase1_data: Dict[str, Any], trade_date: str
    ) -> PhaseResult:
        """执行阶段2：Tushare 补充分析"""
        result = PhaseResult(phase_name="分析", source="tushare")
        phase_start = time.time()

        try:
            logger.info("========== 阶段2：Tushare 补充分析 ==========")

            phase1_stocks = phase1_data.get("stocks", [])
            if not phase1_stocks:
                result.data = {"analysis": {}}
                result.success = True
                result.execution_time = time.time() - phase_start
                return result

            ts_codes = [s.ts_code for s in phase1_stocks]
            analysis_data = {}

            # 获取每日指标
            try:
                daily_basic = self.collector.get_daily_basic(
                    trade_date=trade_date
                )
                # 过滤出需要的股票
                if not daily_basic.empty:
                    daily_basic = daily_basic[daily_basic['ts_code'].isin(ts_codes)]
                for row in daily_basic.itertuples():
                    ts_code = row.ts_code
                    analysis_data[ts_code] = {
                        "pe": row.pe,
                        "pe_ttm": row.pe_ttm,
                        "pb": row.pb,
                        "turnover_rate": row.turnover_rate,
                        "volume_ratio": row.volume_ratio,
                        "total_mv": row.total_mv,
                        "circ_mv": row.circ_mv,
                    }
            except Exception as e:
                logger.warning(f"获取每日指标失败: {e}")

            # 获取行业数据
            try:
                stock_basic = self.collector.get_stock_basic()
                if not stock_basic.empty:
                    stock_basic = stock_basic[stock_basic['ts_code'].isin(ts_codes)]
                    for row in stock_basic.itertuples():
                        ts_code = row.ts_code
                        if ts_code not in analysis_data:
                            analysis_data[ts_code] = {}
                        analysis_data[ts_code]["industry"] = row.industry
            except Exception as e:
                logger.warning(f"获取行业数据失败: {e}")

            # 计算昨涨幅（前一交易日pct_chg）& 开涨幅（内网通达信行情: (open-pre_close)/pre_close）
            try:
                from backend.utils.trading_date import get_previous_trading_day
                calendar_set = self.collector.get_trading_calendar()
                prev_date = get_previous_trading_day(trade_date, calendar_set) if calendar_set else None

                if prev_date is None:
                    logger.warning("无法获取前一交易日，跳过昨涨幅/开涨幅计算")
                else:
                    # 1. 用内网通达信行情API获取今日实时数据（open + pre_close），单个查询
                    realtime = self.collector.get_realtime_quotes(ts_codes)

                    # 2. 用daily批量获取前一交易日数据（pct_chg = 昨涨幅，open = 降级用）
                    fresh = self.collector._get_pro()
                    prev_df = fresh.daily(start_date=prev_date, end_date=prev_date, fields='ts_code,trade_date,open,close,pct_chg')
                    prev_has = prev_df is not None and not prev_df.empty
                    if prev_has:
                        prev_df = prev_df[prev_df['ts_code'].isin(ts_codes)]

                    logger.info(f"实时行情={len(realtime)}只, daily={prev_date}({len(prev_df) if prev_has else 0}行)")

                    for ts_code in ts_codes:
                        rt = realtime.get(ts_code)
                        prev = prev_df[prev_df['ts_code'] == ts_code] if prev_has else None
                        prev_ok = prev is not None and not prev.empty

                        if rt is None and not prev_ok:
                            continue
                        if ts_code not in analysis_data:
                            analysis_data[ts_code] = {}

                        # 昨涨幅 = 前一交易日涨跌幅
                        if prev_ok:
                            pr = prev.iloc[0]
                            analysis_data[ts_code]["pre_change_pct"] = pr.get('pct_chg')
                            analysis_data[ts_code]["close"] = pr.get('close')

                        # 开涨幅 = (今日开盘价 - 昨收价) / 昨收价 × 100
                        if rt:
                            rt_open = rt.get('open')
                            rt_pre_close = rt.get('pre_close')
                            cur_close = rt.get('close')
                            if rt_open is not None and rt_pre_close is not None and rt_pre_close > 0:
                                analysis_data[ts_code]["open_change_pct"] = (rt_open - rt_pre_close) / rt_pre_close * 100
                            if cur_close is not None:
                                analysis_data[ts_code]["close"] = cur_close
                            if analysis_data[ts_code].get("change_pct") is None and rt_open is not None and rt_pre_close is not None and rt_pre_close > 0:
                                analysis_data[ts_code]["change_pct"] = (cur_close - rt_pre_close) / rt_pre_close * 100 if cur_close is not None else None
                        elif prev_ok:
                            # 实时数据不可用时降级：用前日开盘/收盘近似
                            pr = prev.iloc[0]
                            p_open = pr.get('open')
                            p_close = pr.get('close')
                            if p_open is not None and p_close is not None and p_close > 0:
                                analysis_data[ts_code]["open_change_pct"] = (p_open - p_close) / p_close * 100

                    logger.info(f"开涨/昨涨幅计算完成: {len(analysis_data)} 只股票")
            except Exception as e:
                logger.warning(f"计算开涨/昨涨幅失败: {e}")

            result.data = {"analysis": analysis_data}
            result.success = True
            result.execution_time = time.time() - phase_start

            logger.info(f"阶段2完成：分析了 {len(analysis_data)} 只股票")
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.execution_time = time.time() - phase_start
            logger.error(f"阶段2失败: {e}", exc_info=True)

        return result

    def _execute_phase3(
        self, phase1_data: Dict[str, Any], trade_date: str, min_seal_rate: Optional[float], period_days: int
    ) -> PhaseResult:
        """执行阶段3：封板率计算与过滤"""
        result = PhaseResult(phase_name="封板率", source="tushare")
        phase_start = time.time()

        try:
            logger.info("========== 阶段3：封板率计算 ==========")

            phase1_stocks = phase1_data.get("stocks", [])
            if not phase1_stocks:
                result.data = {"seal_rates": {}, "min_seal_rate": min_seal_rate}
                result.success = True
                result.execution_time = time.time() - phase_start
                return result

            ts_codes = [s.ts_code for s in phase1_stocks]
            seal_rates = {}

            # 批量计算封板率
            for ts_code in ts_codes:
                try:
                    seal_rate_data = self.seal_calculator.calculate_seal_rate(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        period_days=period_days
                    )
                    if seal_rate_data:
                        seal_rates[ts_code] = {
                            "touch_days": seal_rate_data.get("touch_days", 0),
                            "limit_up_days": seal_rate_data.get("limit_up_days", 0),
                            "seal_rate": seal_rate_data.get("seal_rate", 0),
                        }
                except Exception as e:
                    logger.warning(f"计算 {ts_code} 封板率失败: {e}")

            result.data = {"seal_rates": seal_rates, "min_seal_rate": min_seal_rate}
            result.success = True
            result.execution_time = time.time() - phase_start

            logger.info(f"阶段3完成：计算了 {len(seal_rates)} 只股票的封板率，阈值: {min_seal_rate}%")
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.execution_time = time.time() - phase_start
            logger.error(f"阶段3失败: {e}", exc_info=True)

        return result

    def _enrich_with_limit_list_ths(self, final_stocks: List[Dict[str, Any]], trade_date: str):
        """获取同花顺涨停榜单数据 + 上一日换手率，丰富到每只股票的数据中"""
        if not final_stocks:
            return

        ts_codes = [s["ts_code"] for s in final_stocks]
        logger.info(f"开始丰富涨停榜单数据：{len(ts_codes)} 只股票")

        # 获取前一交易日（用于判断涨停是否近期）
        prev_date = None
        calendar_set = None
        try:
            from backend.utils.trading_date import get_previous_trading_day
            calendar_set = self.collector.get_trading_calendar()
            if calendar_set:
                prev_date = get_previous_trading_day(trade_date, calendar_set)
        except Exception as e:
            logger.warning(f"获取前一交易日失败: {e}")

        # 1. 获取上一日换手率
        try:
            if calendar_set and prev_date:
                prev_basic = self.collector.get_daily_basic(trade_date=prev_date)
                if prev_basic is not None and not prev_basic.empty:
                    prev_basic_filtered = prev_basic[prev_basic['ts_code'].isin(ts_codes)]
                    prev_turnover_map = {}
                    for row in prev_basic_filtered.itertuples():
                        prev_turnover_map[row.ts_code] = row.turnover_rate

                    for stock in final_stocks:
                        ts_code = stock["ts_code"]
                        if ts_code in prev_turnover_map:
                            stock["prev_turnover_rate"] = prev_turnover_map[ts_code]

                    logger.info(f"上一日换手率获取成功：{len(prev_turnover_map)} 只")
        except Exception as e:
            logger.warning(f"获取上一日换手率失败: {e}")

        # 2. 逐只获取同花顺涨停榜单数据
        success_count = 0
        for stock in final_stocks:
            ts_code = stock["ts_code"]
            try:
                df = self.collector.get_limit_list_ths(ts_code=ts_code, limit_type='涨停池')
                if df is not None and not df.empty:
                    latest = df.iloc[0]
                    stock["lu_desc"] = latest.get("lu_desc")
                    stock["lu_tag"] = latest.get("tag")
                    stock["lu_status"] = latest.get("status")
                    open_num = latest.get("open_num")
                    stock["lu_open_num"] = int(open_num) if (open_num is not None and not (isinstance(open_num, float) and open_num != open_num)) else None
                    suc_rate = latest.get("limit_up_suc_rate")
                    stock["limit_up_suc_rate"] = float(suc_rate) if (suc_rate is not None and not (isinstance(suc_rate, float) and suc_rate != suc_rate)) else None
                    lu_date = latest.get("trade_date")
                    stock["latest_lu_date"] = str(lu_date) if lu_date else None
                    # 判断涨停是否在近两日（选股日或上一交易日）
                    stock["is_recent_limit_up"] = (
                        (lu_date and trade_date and lu_date == trade_date) or
                        (lu_date and prev_date and lu_date == prev_date)
                    )
                    success_count += 1
                else:
                    logger.warning(f"  无涨停数据: {ts_code}")
            except Exception as e:
                logger.warning(f"  获取涨停数据失败 {ts_code}: {e}")

        logger.info(f"涨停榜单数据丰富完成：成功 {success_count}/{len(final_stocks)}")

    def _merge_results(
        self,
        phase1_data: Dict[str, Any],
        phase2_data: Optional[Dict[str, Any]],
        phase3_data: Optional[Dict[str, Any]],
        min_open_change_pct: Optional[float],
        min_seal_rate: Optional[float] = None,
        trade_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """合并三阶段结果并计算规则评分"""
        phase1_stocks = phase1_data.get("stocks", [])
        if not phase1_stocks:
            return []

        analysis = phase2_data.get("analysis", {}) if phase2_data else {}
        seal_rates = phase3_data.get("seal_rates", {}) if phase3_data else {}
        local_fallback_metrics = self._build_phase1_metric_fallbacks(
            phase1_stocks,
            trade_date=trade_date,
            seal_rates=seal_rates,
        )

        merged = []
        for stock in phase1_stocks:
            ts_code = stock.ts_code

            stock_data = {
                "ts_code": ts_code,
                "name": stock.name,
                "close_price": stock.close,
                "close": stock.close,
                "change_pct": stock.change_pct,
                "pre_change_pct": stock.pre_change_pct,
                "open_change_pct": stock.open_change_pct,
                "auction_ratio": stock.auction_ratio,
                "auction_turnover_rate": stock.auction_turnover_rate,
                "limit_up_count": stock.limit_up_count,
                "rise_10d_pct": stock.rise_10d_pct,
                "industry": stock.industry,
                "concept": stock.concept,
            }

            local_fallback = local_fallback_metrics.get(ts_code, {})
            if stock_data.get("limit_up_count") is None and local_fallback.get("limit_up_count") is not None:
                stock_data["limit_up_count"] = local_fallback["limit_up_count"]
            if stock_data.get("rise_10d_pct") is None and local_fallback.get("rise_10d_pct") is not None:
                stock_data["rise_10d_pct"] = local_fallback["rise_10d_pct"]

            # 添加阶段2数据
            if ts_code in analysis:
                p2 = analysis[ts_code]
                for key in ("pre_change_pct", "open_change_pct", "industry", "concept"):
                    if p2.get(key) is not None:
                        stock_data[key] = p2[key]

                stock_data["circ_mv"] = p2.get("circ_mv", 0) / 10000 if p2.get("circ_mv") else stock_data.get("circ_mv")

            # 添加阶段3数据
            if ts_code in seal_rates:
                stock_data["touch_days"] = seal_rates[ts_code].get("touch_days")
                stock_data["limit_up_days"] = seal_rates[ts_code].get("limit_up_days")
                stock_data["seal_rate"] = seal_rates[ts_code].get("seal_rate")
                if stock_data.get("limit_up_count") is None:
                    stock_data["limit_up_count"] = stock_data.get("limit_up_days")

            # 过滤封板率低于阈值的股票
            if min_seal_rate is not None:
                seal_rate = stock_data.get("seal_rate")
                if seal_rate is not None and seal_rate < min_seal_rate:
                    continue

            # 过滤开盘跌幅过大的股票
            if min_open_change_pct is not None:
                open_change_pct = stock_data.get("open_change_pct")
                if open_change_pct is not None and open_change_pct < min_open_change_pct:
                    continue

            # ========== 规则评分 ==========
            score_result = RuleScoreService.calculate(
                limit_up_count=stock_data.get("limit_up_count"),
                touch_days=stock_data.get("touch_days"),
                limit_up_days=stock_data.get("limit_up_days"),
                seal_rate=stock_data.get("seal_rate"),
                rise_10d_pct=stock_data.get("rise_10d_pct"),
                pre_change_pct=stock_data.get("pre_change_pct"),
                open_change_pct=stock_data.get("open_change_pct"),
                auction_ratio=stock_data.get("auction_ratio"),
                auction_turnover_rate=stock_data.get("auction_turnover_rate"),
                circ_mv=stock_data.get("circ_mv"),
            )
            stock_data["rule_score"] = score_result["rule_score"]
            stock_data["score_level"] = score_result["score_level"]
            stock_data["score_breakdown"] = score_result["score_breakdown"]
            stock_data["reasons"] = score_result["reasons"]
            stock_data["risk_tags"] = score_result["risk_tags"]

            # 次日预案
            plan = NextDayPlanService.generate(
                open_change_pct=stock_data.get("open_change_pct"),
                auction_ratio=stock_data.get("auction_ratio"),
                auction_turnover_rate=stock_data.get("auction_turnover_rate"),
                pre_change_pct=stock_data.get("pre_change_pct"),
                seal_rate=stock_data.get("seal_rate"),
                limit_up_count=stock_data.get("limit_up_count"),
            )
            stock_data["next_day_plan"] = plan

            merged.append(stock_data)

        # 按规则评分降序排序
        merged.sort(key=lambda x: x.get("rule_score", 0) or 0, reverse=True)

        # LightGBM模型预测（批量添加model_score）
        try:
            merged = batch_predict_before_selection(merged)
            for s in merged:
                model_score = s.get("model_score")
                if model_score is not None:
                    s["final_score"] = round(s.get("rule_score", 0) * 0.6 + model_score * 0.4, 2)
                else:
                    s["final_score"] = round(s.get("rule_score", 0), 2)
        except Exception as e:
            logger.warning(f"LightGBM预测失败: {e}")
            for s in merged:
                s["final_score"] = round(s.get("rule_score", 0), 2)

        # 龙头主升 T+0 成功率模型只做展示/排序参考，不覆盖 final_score。
        try:
            merged = batch_predict_leader_main_t0(merged)
        except Exception as e:
            logger.warning(f"龙头主升T+0模型预测失败: {e}")
            for s in merged:
                s["t0_limit_success_prob"] = None

        return merged

    def _build_phase1_metric_fallbacks(
        self,
        phase1_stocks: List[TdxStockResult],
        trade_date: Optional[str],
        seal_rates: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """用本地日线兜底 MCP 未返回的涨停次数和10日涨幅。"""
        needs = [
            s for s in phase1_stocks
            if s.limit_up_count is None or s.rise_10d_pct is None
        ]
        if not needs:
            return {}

        fallbacks: Dict[str, Dict[str, Any]] = {}
        for s in needs:
            if s.limit_up_count is None and s.ts_code in seal_rates:
                limit_up_days = seal_rates[s.ts_code].get("limit_up_days")
                if limit_up_days is not None:
                    fallbacks.setdefault(s.ts_code, {})["limit_up_count"] = limit_up_days

        try:
            from backend.services.tdx_local_selector import (
                TdxLocalSelectorService,
                get_limit_price,
            )

            local_selector = TdxLocalSelectorService()
            for stock in needs:
                path = local_selector._ts_code_to_day_path(stock.ts_code)
                if not path or not os.path.exists(path):
                    continue

                records = local_selector._read_day_file(path)
                if trade_date:
                    cutoff = int(trade_date)
                    records = [r for r in records if r[0] <= cutoff]
                records.sort(key=lambda x: x[0])
                if len(records) < 2:
                    continue

                metrics = fallbacks.setdefault(stock.ts_code, {})
                close_price = records[-1][4]
                if stock.rise_10d_pct is None and len(records) >= 11:
                    base_close = records[-11][4]
                    if base_close > 0:
                        metrics["rise_10d_pct"] = round((close_price - base_close) / base_close * 100, 2)

                if stock.limit_up_count is None and "limit_up_count" not in metrics:
                    last_100 = records[-101:] if len(records) >= 101 else records[:]
                    code_num = stock.ts_code.split(".")[0]
                    limit_count = 0
                    for i in range(1, len(last_100)):
                        limit_price = get_limit_price(code_num, last_100[i - 1][4])
                        if abs(last_100[i][4] - limit_price) < 0.01:
                            limit_count += 1
                    metrics["limit_up_count"] = limit_count
        except Exception as e:
            logger.warning(f"本地日线兜底阶段1指标失败: {e}")

        return fallbacks

    def _build_final_result(
        self,
        trade_date: str,
        phase1: PhaseResult,
        phase2: Optional[PhaseResult],
        phase3: Optional[PhaseResult],
        final_stocks: List[Dict[str, Any]],
        overall_start: float,
    ) -> Dict[str, Any]:
        """构建最终结果"""
        total_count = len(phase1.data.get("stocks", [])) if phase1.data else 0

        result = {
            "trade_date": trade_date,
            "total_count": total_count,
            "passed_count": len(final_stocks),
            "pass_rate": (len(final_stocks) / total_count * 100) if total_count > 0 else 0,
            "stocks": final_stocks,
            "execution_time": time.time() - overall_start,
            "phase1": {
                "phase": phase1.phase_name,
                "source": phase1.source,
                "success": phase1.success,
                "execution_time": phase1.execution_time,
                "error": phase1.error,
            },
            "phase2": {
                "phase": phase2.phase_name,
                "source": phase2.source,
                "success": phase2.success,
                "execution_time": phase2.execution_time,
                "error": phase2.error,
            } if phase2 else None,
            "phase3": {
                "phase": phase3.phase_name,
                "source": phase3.source,
                "success": phase3.success,
                "execution_time": phase3.execution_time,
                "error": phase3.error,
                "data": phase3.data if phase3 else None,
            } if phase3 else None,
        }
        return result

    def _get_trade_date(self) -> str:
        """获取最新交易日"""
        try:
            return self.collector.get_latest_trade_date()
        except Exception as e:
            logger.warning(f"获取交易日失败: {e}，使用当前日期")
            return datetime.now().strftime("%Y%m%d")

    def save_selection_result(self, result: Dict[str, Any], notification_sent: bool = False) -> int:
        """保存选股结果到数据库"""
        db = SessionLocal()
        try:
            record = SelectionRecord(
                execute_time=datetime.now(),
                trade_date=result["trade_date"],
                total_count=result["passed_count"],
                status="success",
                execution_time=result.get("execution_time"),
                notification_sent=notification_sent
            )
            db.add(record)
            db.flush()

            for stock in result.get("stocks", []):
                import json as _json
                selected_stock = SelectedStock(
                    record_id=record.id,
                    ts_code=stock["ts_code"],
                    name=stock.get("name"),
                    close_price=stock.get("close_price"),
                    close=stock.get("close"),
                    change_pct=stock.get("change_pct"),
                    pre_change_pct=stock.get("pre_change_pct"),
                    open_change_pct=stock.get("open_change_pct"),
                    auction_ratio=stock.get("auction_ratio"),
                    auction_turnover_rate=stock.get("auction_turnover_rate"),
                    industry=stock.get("industry"),
                    concept=stock.get("concept"),
                    board_type=stock.get("board_type"),
                    limit_up_count=stock.get("limit_up_count"),
                    touch_days=stock.get("touch_days"),
                    limit_up_days=stock.get("limit_up_days"),
                    seal_rate=stock.get("seal_rate"),
                    rise_10d_pct=stock.get("rise_10d_pct"),
                    circ_mv=stock.get("circ_mv"),
                    # 同花顺涨停榜单数据
                    lu_desc=stock.get("lu_desc"),
                    lu_tag=stock.get("lu_tag"),
                    lu_status=stock.get("lu_status"),
                    lu_open_num=stock.get("lu_open_num"),
                    limit_up_suc_rate=stock.get("limit_up_suc_rate"),
                    latest_lu_date=stock.get("latest_lu_date"),
                    # 上一日换手率
                    prev_turnover_rate=stock.get("prev_turnover_rate"),
                    # 评分字段
                    rule_score=stock.get("rule_score"),
                    model_score=stock.get("model_score"),
                    t0_limit_success_prob=stock.get("t0_limit_success_prob"),
                    final_score=stock.get("final_score"),
                    score_level=stock.get("score_level"),
                    score_breakdown=_json.dumps(stock.get("score_breakdown", {}), ensure_ascii=False) if stock.get("score_breakdown") else None,
                    reasons="; ".join(stock.get("reasons", [])) if stock.get("reasons") else None,
                    risk_tags=_json.dumps(stock.get("risk_tags", []), ensure_ascii=False) if stock.get("risk_tags") else None,
                    next_day_plan=_json.dumps(stock.get("next_day_plan", {}), ensure_ascii=False) if stock.get("next_day_plan") else None,
                    t0_limit_success_model_version=stock.get("t0_limit_success_prob_model_version"),
                )
                db.add(selected_stock)

            db.commit()
            logger.info(f"选股结果已保存，记录ID: {record.id}")
            return record.id
        except Exception as e:
            db.rollback()
            logger.error(f"保存选股结果失败: {e}")
            raise
        finally:
            db.close()

    def save_feature_snapshot(self, result: Dict[str, Any], trade_date: str) -> int:
        """保存候选股特征快照（upsert模式）"""
        db = SessionLocal()
        saved = 0
        try:
            for stock in result.get("stocks", []):
                ts_code = stock["ts_code"]
                existing = db.query(StockFeatureSnapshot).filter(
                    StockFeatureSnapshot.trade_date == trade_date,
                    StockFeatureSnapshot.ts_code == ts_code,
                ).first()
                if existing:
                    existing.name = stock.get("name")
                    existing.limit_up_count_100d = stock.get("limit_up_count")
                    existing.seal_rate_100d = stock.get("seal_rate")
                    existing.rise_10d_pct = stock.get("rise_10d_pct")
                    existing.pre_change_pct = stock.get("pre_change_pct")
                    existing.open_change_pct = stock.get("open_change_pct")
                    existing.auction_turnover_rate = stock.get("auction_turnover_rate")
                    existing.auction_ratio = stock.get("auction_ratio")
                    existing.circ_mv = stock.get("circ_mv")
                else:
                    snapshot = StockFeatureSnapshot(
                        trade_date=trade_date,
                        ts_code=ts_code,
                        name=stock.get("name"),
                        limit_up_count_100d=stock.get("limit_up_count"),
                        seal_rate_100d=stock.get("seal_rate"),
                        rise_10d_pct=stock.get("rise_10d_pct"),
                        pre_change_pct=stock.get("pre_change_pct"),
                        open_change_pct=stock.get("open_change_pct"),
                        auction_turnover_rate=stock.get("auction_turnover_rate"),
                        auction_ratio=stock.get("auction_ratio"),
                        circ_mv=stock.get("circ_mv"),
                    )
                    db.add(snapshot)
                saved += 1
            db.commit()
            logger.info(f"特征快照已保存: {saved} 只股票, 交易日={trade_date}")
            return saved
        except Exception as e:
            db.rollback()
            logger.warning(f"保存特征快照失败: {e}")
            return 0
        finally:
            db.close()


CRITICAL_FIELDS = ["pre_change_pct", "open_change_pct", "industry", "concept"]


def validate_data_completeness(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证选股结果中关键字段的数据完整性
    
    检查 pre_change_pct、open_change_pct、industry、concept
    四个字段的数据填充率，低于阈值时发出告警。

    Args:
        result: 选股结果字典

    Returns:
        包含完整性统计的字典
    """
    stocks = result.get("stocks", [])
    if not stocks:
        return {"total": 0, "missing": {}, "alert": False}

    missing_counts = {field: 0 for field in CRITICAL_FIELDS}
    missing_stocks = {field: [] for field in CRITICAL_FIELDS}

    for stock in stocks:
        ts_name = f"{stock.get('ts_code', '?')} {stock.get('name', '?')}"
        for field in CRITICAL_FIELDS:
            val = stock.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing_counts[field] += 1
                if len(missing_stocks[field]) < 5:
                    missing_stocks[field].append(ts_name)

    total = len(stocks)
    alert = False
    completeness = {}

    for field in CRITICAL_FIELDS:
        filled = total - missing_counts[field]
        rate = round(filled / total * 100, 1) if total > 0 else 0
        completeness[field] = {
            "filled": filled,
            "total": total,
            "rate": rate,
            "missing_examples": missing_stocks[field],
        }
        if rate < 50:
            alert = True
            logger.warning(
                f"⚠️ 数据完整性告警: {field} 填充率仅 {rate}% "
                f"({filled}/{total})，缺失示例: {missing_stocks[field]}"
            )

    info_msg = (
        f"数据完整性: "
        f"pre_change_pct={completeness['pre_change_pct']['rate']}%, "
        f"open_change_pct={completeness['open_change_pct']['rate']}%, "
        f"industry={completeness['industry']['rate']}%, "
        f"concept={completeness['concept']['rate']}%"
    )
    logger.info(info_msg)

    if alert:
        import json as _json
        logger.error(
            f"🚨 数据完整性严重不足！请检查数据源连接。"
            f"详情: {_json.dumps(completeness, ensure_ascii=False)}"
        )

    return {
        "total": total,
        "completeness": completeness,
        "alert": alert,
    }


def select_stocks(
    trade_date: Optional[str] = None,
    task_template: str = "default",
    custom_tasks: Optional[List[SelectionTask]] = None,
    save_result: bool = True,
    tdx_mcp_func: Optional[Callable] = None,
    min_seal_rate: Optional[float] = None,
    period_days: int = 100,
    min_open_change_pct: Optional[float] = -3.0,
) -> Dict[str, Any]:
    """
    主选股函数（三阶段）
    """
    selector = StockSelectorService()
    result = selector.select_stocks(
        trade_date=trade_date,
        task_template=task_template,
        custom_tasks=custom_tasks,
        tdx_mcp_func=tdx_mcp_func,
        min_seal_rate=min_seal_rate,
        period_days=period_days,
        min_open_change_pct=min_open_change_pct
    )

    if save_result:
        result["record_id"] = selector.save_selection_result(result)
        selector.save_feature_snapshot(result, result.get("trade_date", ""))
        # 评分V2并行计算
        if is_score_v2_enabled() and result.get("record_id"):
            try:
                v2_service = StockScoringV2Service()
                v2_service.score_batch(
                    result.get("stocks", []),
                    result["record_id"],
                    result.get("trade_date", ""),
                )
            except Exception as e:
                logger.warning(f"评分V2计算失败（不影响主流程）: {e}")

        # 龙头战法评分并行计算
        if result.get("record_id") and result.get("stocks"):
            try:
                _trigger_dragon_leader_scoring(result["stocks"], result.get("trade_date", ""))
            except Exception as e:
                logger.warning(f"龙头战法评分失败（不影响主流程）: {e}")

    completeness = validate_data_completeness(result)
    result["completeness"] = completeness

    # AI后台预热：选股完成后自动生成综合概览+异动解读
    if save_result and result.get("stocks"):
        try:
            _trigger_ai_preheat(result["stocks"], result.get("trade_date", ""), result.get("record_id"))
        except Exception as e:
            logger.warning(f"AI预热触发失败（不影响主流程）: {e}")

    # 龙虎榜后台预热：选股完成后批量拉取龙虎榜数据
    if save_result and result.get("stocks"):
        try:
            _trigger_lhb_preheat(result["stocks"])
        except Exception as e:
            logger.warning(f"龙虎榜预热触发失败（不影响主流程）: {e}")

    # 东财板块关系后台预热：只补齐入选股票，不阻塞选股接口返回
    if save_result and result.get("stocks"):
        try:
            _trigger_dc_board_preheat(result["stocks"], result.get("trade_date", ""))
        except Exception as e:
            logger.warning(f"东财板块关系预热触发失败（不影响主流程）: {e}")

    # 风险拆解后台预热：选股完成后批量计算
    if save_result and result.get("stocks"):
        try:
            _trigger_risk_preheat(result["stocks"], result.get("trade_date", ""))
        except Exception as e:
            logger.warning(f"风险拆解预热触发失败（不影响主流程）: {e}")

    return result


def _trigger_dc_board_preheat(stocks: List[Dict], trade_date: str):
    """后台线程批量刷新入选股票的东财板块关系"""
    from concurrent.futures import ThreadPoolExecutor
    from backend.services.dc_board_service import refresh_stock_dc_boards

    if not trade_date:
        logger.warning("[预热] 东财板块关系缺少交易日，跳过")
        return

    def _warm_all():
        try:
            stats = refresh_stock_dc_boards(stocks, trade_date)
            logger.info(
                f"[预热] 东财板块关系刷新完成：股票{stats.get('stocks', 0)}只，"
                f"板块关系{stats.get('boards', 0)}条，失败{stats.get('failed', 0)}只"
            )
        except Exception as e:
            logger.warning(f"[预热] 东财板块关系批量刷新失败: {e}")

    logger.info(f"[预热] 后台启动 {len(stocks)} 只股票的东财板块关系刷新")
    pool = ThreadPoolExecutor(max_workers=1)
    pool.submit(_warm_all)
    pool.shutdown(wait=False)


def _trigger_risk_preheat(stocks: List[Dict], trade_date: str):
    """后台线程批量预热风险拆解数据"""
    from concurrent.futures import ThreadPoolExecutor
    from backend.services.risk_breakdown_service import calculate_risk

    def _warm_one(stock: Dict):
        ts_code = stock.get("ts_code", "")
        stock_name = stock.get("name", "")
        if not ts_code:
            return
        try:
            result = calculate_risk(ts_code, trade_date, force_refresh=False)
            if result.get("data_status") == "available":
                logger.info(f"[预热] 风险拆解完成: {ts_code} {stock_name}")
        except Exception as e:
            logger.warning(f"[预热] 风险拆解 {ts_code} 失败: {e}")

    logger.info(f"[预热] 后台启动 {len(stocks)} 只股票的风险拆解")
    pool = ThreadPoolExecutor(max_workers=5)
    for stock in stocks:
        pool.submit(_warm_one, stock)
    pool.shutdown(wait=False)


def _trigger_dragon_leader_scoring(stocks: List[Dict], trade_date: str):
    """后台线程批量计算龙头战法评分"""
    from concurrent.futures import ThreadPoolExecutor
    from backend.services.dragon_leader import calculate_dragon_leader_score

    def _score_one(stock: Dict):
        ts_code = stock.get("ts_code", "")
        stock_name = stock.get("name", "")
        if not ts_code or not stock_name:
            return
        try:
            calculate_dragon_leader_score(ts_code, trade_date, stock_name, force_refresh=True)
        except Exception as e:
            logger.warning(f"[龙头战法评分] {ts_code} 失败: {e}")

    logger.info(f"[龙头战法评分] 后台启动 {len(stocks)} 只股票的评分计算")
    pool = ThreadPoolExecutor(max_workers=3)
    for stock in stocks:
        pool.submit(_score_one, stock)
    pool.shutdown(wait=False)


def _trigger_lhb_preheat(stocks: List[Dict]):
    """后台线程批量预热龙虎榜数据"""
    from concurrent.futures import ThreadPoolExecutor
    from backend.services.lhb_service import analyze_lhb

    def _warm_one(stock: Dict):
        ts_code = stock.get("ts_code", "")
        stock_name = stock.get("name", "")
        if not ts_code or not stock_name:
            return
        try:
            result = analyze_lhb(ts_code, force_refresh=False)
            if result.get("data_status") == "available":
                logger.info(f"[预热] 龙虎榜数据完成: {ts_code} {stock_name}")
            elif result.get("data_status") == "not_on_list":
                logger.info(f"[预热] 龙虎榜未上榜: {ts_code} {stock_name}")
            else:
                logger.warning(f"[预热] 龙虎榜 {ts_code} 返回异常: {result.get('data_status')}")
        except Exception as e:
            logger.warning(f"[预热] 龙虎榜 {ts_code} 失败: {e}")

    logger.info(f"[预热] 后台启动 {len(stocks)} 只股票的龙虎榜数据")
    pool = ThreadPoolExecutor(max_workers=5)
    for stock in stocks:
        pool.submit(_warm_one, stock)
    pool.shutdown(wait=False)


def _trigger_ai_preheat(stocks: List[Dict], trade_date: str, record_id: Optional[int]):
    """后台线程批量预热AI数据（概览+异动）"""
    from concurrent.futures import ThreadPoolExecutor

    def _warm_one(stock: Dict):
        ts_code = stock.get("ts_code", "")
        stock_name = stock.get("name", "")
        if not ts_code or not stock_name:
            return
        try:
            from backend.services.ai_brief.overview_brief_service import OverviewBriefService
            from backend.services.anomaly_interpretation.interpreter_service import get_anomaly_interpretation
            pool = ThreadPoolExecutor(max_workers=2)
            pool.submit(OverviewBriefService.get_or_build, ts_code, stock_name, trade_date, record_id)
            pool.submit(get_anomaly_interpretation, ts_code, stock_name, trade_date, False)
            pool.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"[AI预热] {ts_code} 失败: {e}")

    logger.info(f"[AI预热] 后台启动 {len(stocks)} 只股票的AI生成")
    pool = ThreadPoolExecutor(max_workers=5)
    for stock in stocks:
        pool.submit(_warm_one, stock)
    pool.shutdown(wait=False)
