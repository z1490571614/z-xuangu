"""
三阶段选股服务
"""
import logging
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
from backend.services.data_collector import TushareDataCollector
from backend.services.seal_rate_calculator import SealRateCalculator
from backend.models import SelectionRecord, SelectedStock
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
        phase1 = self._execute_phase1(tasks, tdx_mcp_func)
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
            phase1.data, phase2.data, phase3.data if phase3 else None, min_open_change_pct, min_seal_rate
        )

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
        self, tasks: List[SelectionTask], tdx_mcp_func: Optional[Callable]
    ) -> PhaseResult:
        """执行阶段1：通达信 MCP 选股"""
        result = PhaseResult(phase_name="选股", source="tdx_mcp")
        phase_start = time.time()

        if tdx_mcp_func is None:
            logger.warning("未提供通达信 MCP 函数，阶段1返回空结果")
            result.data = {"stocks": [], "total_count": 0}
            result.success = True
            result.execution_time = time.time() - phase_start
            return result

        try:
            logger.info("========== 阶段1：通达信 MCP 选股 ==========")
            for i, task in enumerate(tasks):
                self.tdx_selector.add_task(task)

            selection_result = self.tdx_selector.select(tdx_mcp_func=tdx_mcp_func)

            result.data = selection_result
            result.success = True
            result.execution_time = time.time() - phase_start

            logger.info(f"阶段1完成：选出 {len(selection_result.get('stocks', []))} 只股票")
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.execution_time = time.time() - phase_start
            logger.error(f"阶段1失败: {e}", exc_info=True)

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

    def _merge_results(
        self,
        phase1_data: Dict[str, Any],
        phase2_data: Optional[Dict[str, Any]],
        phase3_data: Optional[Dict[str, Any]],
        min_open_change_pct: Optional[float],
        min_seal_rate: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """合并三阶段结果"""
        phase1_stocks = phase1_data.get("stocks", [])
        if not phase1_stocks:
            return []

        analysis = phase2_data.get("analysis", {}) if phase2_data else {}
        seal_rates = phase3_data.get("seal_rates", {}) if phase3_data else {}

        merged = []
        for stock in phase1_stocks:
            ts_code = stock.ts_code

            stock_data = {
                "ts_code": ts_code,
                "name": stock.name,
                "close_price": stock.close,
                "change_pct": stock.change_pct,
                "auction_ratio": stock.auction_ratio,
                "auction_turnover_rate": stock.auction_turnover_rate,
                "limit_up_count": stock.limit_up_count,
                "rise_10d_pct": stock.rise_10d_pct,
                "industry": stock.industry,
                "concept": stock.concept,
            }

            # 添加阶段2数据（当阶段2有数据时补充/覆盖）
            if ts_code in analysis:
                phase2_pre_change = analysis[ts_code].get("pre_change_pct")
                if phase2_pre_change is not None:
                    stock_data["pre_change_pct"] = phase2_pre_change
                else:
                    stock_data.setdefault("pre_change_pct", stock.pre_change_pct)

                phase2_open_change = analysis[ts_code].get("open_change_pct")
                if phase2_open_change is not None:
                    stock_data["open_change_pct"] = phase2_open_change
                else:
                    stock_data.setdefault("open_change_pct", stock.open_change_pct)

                stock_data["circ_mv"] = analysis[ts_code].get("circ_mv", 0) / 10000 if analysis[ts_code].get("circ_mv") else None

                phase2_industry = analysis[ts_code].get("industry")
                if phase2_industry is not None:
                    stock_data["industry"] = phase2_industry
                else:
                    stock_data.setdefault("industry", stock.industry)

                phase2_concept = analysis[ts_code].get("concept")
                if phase2_concept is not None:
                    stock_data["concept"] = phase2_concept
                else:
                    stock_data.setdefault("concept", stock.concept)

            # 添加阶段3数据
            if ts_code in seal_rates:
                stock_data["touch_days"] = seal_rates[ts_code].get("touch_days")
                stock_data["limit_up_days"] = seal_rates[ts_code].get("limit_up_days")
                stock_data["seal_rate"] = seal_rates[ts_code].get("seal_rate")

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

            merged.append(stock_data)

        return merged

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
                selected_stock = SelectedStock(
                    record_id=record.id,
                    ts_code=stock["ts_code"],
                    name=stock.get("name"),
                    close_price=stock.get("close_price"),
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

    completeness = validate_data_completeness(result)
    result["completeness"] = completeness

    return result
