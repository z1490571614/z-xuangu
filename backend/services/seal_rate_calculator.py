"""
封板率计算服务

功能：
1. 获取并缓存股票前复权日线数据
2. 计算封板率指标
3. 支持按条件过滤
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.database import SessionLocal
from backend.models.seal_rate import StockDailyData, SealRateCache
from backend.services.data_collector import TushareDataCollector

logger = logging.getLogger(__name__)

_PARALLEL_WORKERS = 5


class SealRateCalculator:
    """封板率计算器"""

    def __init__(self, tushare_token: Optional[str] = None):
        self.collector = TushareDataCollector(tushare_token)
        self.db = SessionLocal()

    def close(self):
        """关闭数据库连接"""
        if hasattr(self, 'db') and self.db:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_trading_dates(
        self,
        end_date: str,
        period_days: int = 100
    ) -> List[str]:
        """
        获取周期内的交易日列表

        Args:
            end_date: 结束日期（YYYYMMDD格式）
            period_days: 周期天数（交易日）

        Returns:
            交易日列表（从旧到新）
        """
        try:
            # 获取交易日历
            end_dt = datetime.strptime(end_date, "%Y%m%d")
            # 向前多取一些天确保能覆盖period_days个交易日
            start_dt = end_dt - timedelta(days=period_days * 2)
            start_date = start_dt.strftime("%Y%m%d")

            df = self.collector.pro.trade_cal(
                exchange='SSE',
                start_date=start_date,
                end_date=end_date,
                is_open='1'
            )

            if df is None or len(df) == 0:
                logger.warning(f"未获取到 {start_date} 到 {end_date} 的交易日历")
                return []

            # 获取最近的period_days个交易日
            trading_dates = sorted(df['cal_date'].tolist(), reverse=True)[:period_days]
            return sorted(trading_dates)  # 返回从旧到新

        except Exception as e:
            logger.error(f"获取交易日历失败: {e}")
            return []

    def fetch_and_save_daily_data(
        self,
        ts_code: str,
        trading_dates: List[str]
    ) -> bool:
        """
        获取并保存股票日线数据（前复权）

        Args:
            ts_code: 股票代码
            trading_dates: 交易日列表

        Returns:
            是否成功
        """
        if not trading_dates:
            return False

        try:
            start_date = trading_dates[0]
            end_date = trading_dates[-1]

            # 获取日线数据（不复权）
            daily_df = self.collector.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
            )

            if daily_df is None or len(daily_df) == 0:
                logger.warning(f"未获取到 {ts_code} 的日线数据")
                return False

            # 获取复权因子
            adj_df = self.collector.pro.adj_factor(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            # 获取涨跌停价格
            limit_df = self.collector.pro.stk_limit(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            # 合并数据
            if adj_df is not None and len(adj_df) > 0:
                daily_df = pd.merge(daily_df, adj_df, on=['ts_code', 'trade_date'], how='left')
            else:
                daily_df['adj_factor'] = None

            if limit_df is not None and len(limit_df) > 0:
                daily_df = pd.merge(daily_df, limit_df, on=['ts_code', 'trade_date'], how='left')
            else:
                daily_df['up_limit'] = None
                daily_df['down_limit'] = None

            # 前复权计算
            if 'adj_factor' in daily_df.columns:
                # 获取最新复权因子
                latest_adj = daily_df['adj_factor'].max()
                if pd.notna(latest_adj) and latest_adj > 0:
                    price_cols = ['open', 'high', 'low', 'close', 'pre_close']
                    for col in price_cols:
                        if col in daily_df.columns:
                            daily_df[col] = daily_df[col] * daily_df['adj_factor'] / latest_adj
                    if 'up_limit' in daily_df.columns:
                        daily_df['up_limit'] = daily_df['up_limit'] * daily_df['adj_factor'] / latest_adj
                    if 'down_limit' in daily_df.columns:
                        daily_df['down_limit'] = daily_df['down_limit'] * daily_df['adj_factor'] / latest_adj

            # 保存到数据库
            for _, row in daily_df.iterrows():
                trade_date = row['trade_date']

                existing = self.db.query(StockDailyData).filter(
                    and_(
                        StockDailyData.ts_code == ts_code,
                        StockDailyData.trade_date == trade_date
                    )
                ).first()

                if existing:
                    # 更新
                    existing.open = float(row['open']) if pd.notna(row['open']) else None
                    existing.high = float(row['high']) if pd.notna(row['high']) else None
                    existing.low = float(row['low']) if pd.notna(row['low']) else None
                    existing.close = float(row['close']) if pd.notna(row['close']) else None
                    existing.pre_close = float(row['pre_close']) if pd.notna(row['pre_close']) else None
                    existing.change = float(row['change']) if pd.notna(row['change']) else None
                    existing.pct_chg = float(row['pct_chg']) if pd.notna(row['pct_chg']) else None
                    existing.up_limit = float(row['up_limit']) if pd.notna(row.get('up_limit')) else None
                    existing.down_limit = float(row['down_limit']) if pd.notna(row.get('down_limit')) else None
                    existing.vol = float(row['vol']) if pd.notna(row['vol']) else None
                    existing.amount = float(row['amount']) if pd.notna(row['amount']) else None
                    existing.adj_factor = float(row['adj_factor']) if pd.notna(row.get('adj_factor')) else None
                    existing.is_adj = 1
                else:
                    # 新增
                    record = StockDailyData(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        open=float(row['open']) if pd.notna(row['open']) else None,
                        high=float(row['high']) if pd.notna(row['high']) else None,
                        low=float(row['low']) if pd.notna(row['low']) else None,
                        close=float(row['close']) if pd.notna(row['close']) else None,
                        pre_close=float(row['pre_close']) if pd.notna(row['pre_close']) else None,
                        change=float(row['change']) if pd.notna(row['change']) else None,
                        pct_chg=float(row['pct_chg']) if pd.notna(row['pct_chg']) else None,
                        up_limit=float(row['up_limit']) if pd.notna(row.get('up_limit')) else None,
                        down_limit=float(row['down_limit']) if pd.notna(row.get('down_limit')) else None,
                        vol=float(row['vol']) if pd.notna(row['vol']) else None,
                        amount=float(row['amount']) if pd.notna(row['amount']) else None,
                        adj_factor=float(row['adj_factor']) if pd.notna(row.get('adj_factor')) else None,
                        is_adj=1,
                    )
                    self.db.add(record)

            self.db.commit()
            logger.info(f"已保存 {ts_code} 的 {len(daily_df)} 条日线数据")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"获取并保存 {ts_code} 日线数据失败: {e}", exc_info=True)
            return False

    def calculate_seal_rate_from_cache(
        self,
        ts_code: str,
        trading_dates: List[str]
    ) -> Dict[str, Any]:
        """
        从缓存数据计算封板率

        Args:
            ts_code: 股票代码
            trading_dates: 交易日列表

        Returns:
            计算结果
        """
        try:
            records = self.db.query(StockDailyData).filter(
                and_(
                    StockDailyData.ts_code == ts_code,
                    StockDailyData.trade_date.in_(trading_dates)
                )
            ).order_by(StockDailyData.trade_date).all()

            if not records:
                return {
                    'touch_days': 0,
                    'limit_up_days': 0,
                    'seal_rate': None,
                    'data_complete': 0,
                }

            touch_days = 0
            limit_up_days = 0
            data_complete = 1 if len(records) >= len(trading_dates) else 0

            for record in records:
                if record.high is not None and record.up_limit is not None:
                    # 触板判断：最高价 >= 涨停价
                    if record.high >= record.up_limit - 0.01:  # 允许0.01的精度误差
                        touch_days += 1

                        # 封板判断：收盘价 >= 涨停价
                        if record.close is not None and record.close >= record.up_limit - 0.01:
                            limit_up_days += 1

            seal_rate = None
            if touch_days > 0:
                seal_rate = round(limit_up_days / touch_days * 100, 2)  # 转为百分比

            return {
                'touch_days': touch_days,
                'limit_up_days': limit_up_days,
                'seal_rate': seal_rate,
                'data_complete': data_complete,
            }

        except Exception as e:
            logger.error(f"计算 {ts_code} 封板率失败: {e}", exc_info=True)
            return {
                'touch_days': 0,
                'limit_up_days': 0,
                'seal_rate': None,
                'data_complete': 0,
            }

    def get_cached_result(
        self,
        ts_code: str,
        trade_date: str,
        period_days: int = 100
    ) -> Optional[SealRateCache]:
        """
        从缓存获取计算结果

        Args:
            ts_code: 股票代码
            trade_date: 计算基准日
            period_days: 周期天数

        Returns:
            缓存结果或None
        """
        try:
            return self.db.query(SealRateCache).filter(
                and_(
                    SealRateCache.ts_code == ts_code,
                    SealRateCache.trade_date == trade_date,
                    SealRateCache.period_days == period_days
                )
            ).first()
        except Exception as e:
            logger.error(f"查询缓存失败: {e}")
            return None

    def save_cached_result(
        self,
        ts_code: str,
        trade_date: str,
        period_days: int,
        result: Dict[str, Any],
        trading_dates: List[str]
    ):
        """
        保存计算结果到缓存

        Args:
            ts_code: 股票代码
            trade_date: 计算基准日
            period_days: 周期天数
            result: 计算结果
            trading_dates: 交易日列表
        """
        try:
            existing = self.get_cached_result(ts_code, trade_date, period_days)

            start_date = trading_dates[0] if trading_dates else None
            end_date = trading_dates[-1] if trading_dates else None

            if existing:
                existing.touch_days = result['touch_days']
                existing.limit_up_days = result['limit_up_days']
                existing.seal_rate = result['seal_rate']
                existing.start_date = start_date
                existing.end_date = end_date
                existing.data_complete = result['data_complete']
            else:
                cache = SealRateCache(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    period_days=period_days,
                    touch_days=result['touch_days'],
                    limit_up_days=result['limit_up_days'],
                    seal_rate=result['seal_rate'],
                    start_date=start_date,
                    end_date=end_date,
                    data_complete=result['data_complete'],
                )
                self.db.add(cache)

            self.db.commit()

        except Exception as e:
            self.db.rollback()
            logger.error(f"保存缓存失败: {e}")

    def calculate_seal_rate(
        self,
        ts_code: str,
        trade_date: str,
        period_days: int = 100,
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        计算封板率

        Args:
            ts_code: 股票代码
            trade_date: 计算基准日
            period_days: 周期天数
            use_cache: 是否使用缓存
            force_refresh: 是否强制刷新

        Returns:
            计算结果
        """
        # 1. 检查缓存
        cached = None
        if use_cache and not force_refresh:
            cached = self.get_cached_result(ts_code, trade_date, period_days)
            if cached and cached.data_complete:
                logger.info(f"从缓存获取 {ts_code} 在 {trade_date} 的封板率: {cached.seal_rate}%")
                return {
                    'ts_code': ts_code,
                    'trade_date': trade_date,
                    'period_days': period_days,
                    'touch_days': cached.touch_days,
                    'limit_up_days': cached.limit_up_days,
                    'seal_rate': cached.seal_rate,
                    'start_date': cached.start_date,
                    'end_date': cached.end_date,
                    'data_complete': cached.data_complete,
                    'from_cache': True,
                }
            if cached:
                logger.info(f"{ts_code} 在 {trade_date} 的封板率缓存不完整，尝试从本地日线重算")

        # 2. 获取交易日列表
        trading_dates = self.get_trading_dates(trade_date, period_days)
        if not trading_dates:
            logger.warning(f"未获取到交易日列表")
            if cached:
                return {
                    'ts_code': ts_code,
                    'trade_date': trade_date,
                    'period_days': period_days,
                    'touch_days': cached.touch_days,
                    'limit_up_days': cached.limit_up_days,
                    'seal_rate': cached.seal_rate,
                    'start_date': cached.start_date,
                    'end_date': cached.end_date,
                    'data_complete': cached.data_complete,
                    'from_cache': True,
                }
            return {
                'ts_code': ts_code,
                'trade_date': trade_date,
                'period_days': period_days,
                'touch_days': 0,
                'limit_up_days': 0,
                'seal_rate': None,
                'data_complete': 0,
                'from_cache': False,
            }

        # 3. 优先用本地日线缓存重算，避免旧的不完整缓存遮蔽已同步好的本地数据
        result = self.calculate_seal_rate_from_cache(ts_code, trading_dates)
        if result.get('data_complete') == 1:
            result.update({
                'ts_code': ts_code,
                'trade_date': trade_date,
                'period_days': period_days,
                'start_date': trading_dates[0] if trading_dates else None,
                'end_date': trading_dates[-1] if trading_dates else None,
                'from_cache': False,
            })
            self.save_cached_result(ts_code, trade_date, period_days, result, trading_dates)
            logger.info(
                f"从本地日线重算 {ts_code} 封板率完成: 触板{result['touch_days']}天, "
                f"封板{result['limit_up_days']}天, 封板率{result['seal_rate']}%"
            )
            return result

        # 4. 本地日线不完整时再获取并保存日线数据
        success = self.fetch_and_save_daily_data(ts_code, trading_dates)
        if not success:
            logger.warning(f"获取日线数据失败")

        # 5. 计算封板率
        result = self.calculate_seal_rate_from_cache(ts_code, trading_dates)

        # 6. 保存缓存
        result.update({
            'ts_code': ts_code,
            'trade_date': trade_date,
            'period_days': period_days,
            'start_date': trading_dates[0] if trading_dates else None,
            'end_date': trading_dates[-1] if trading_dates else None,
            'from_cache': False,
        })

        self.save_cached_result(ts_code, trade_date, period_days, result, trading_dates)

        logger.info(
            f"计算 {ts_code} 封板率完成: 触板{result['touch_days']}天, "
            f"封板{result['limit_up_days']}天, 封板率{result['seal_rate']}%"
        )

        return result

    def batch_calculate_seal_rate(
        self,
        ts_codes: List[str],
        trade_date: str,
        period_days: int = 100,
        min_seal_rate: Optional[float] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        批量计算封板率（优先查缓存，未缓存的使用线程池并行计算）

        Args:
            ts_codes: 股票代码列表
            trade_date: 计算基准日
            period_days: 周期天数
            min_seal_rate: 最小封板率过滤阈值（百分比），None不过滤

        Returns:
            (通过过滤的列表, 全部结果列表)
        """
        all_results = []
        passed_results = []
        uncached_codes = []

        # 第一轮：检查缓存（顺序执行，快速）
        for ts_code in ts_codes:
            cached = self.get_cached_result(ts_code, trade_date, period_days)
            if cached:
                result = {
                    'ts_code': ts_code,
                    'trade_date': trade_date,
                    'period_days': period_days,
                    'touch_days': cached.touch_days,
                    'limit_up_days': cached.limit_up_days,
                    'seal_rate': cached.seal_rate,
                    'start_date': cached.start_date,
                    'end_date': cached.end_date,
                    'data_complete': cached.data_complete,
                    'from_cache': True,
                }
                all_results.append(result)
                if min_seal_rate is None or (result['seal_rate'] is not None and result['seal_rate'] >= min_seal_rate - 0.01):
                    passed_results.append(result)
            else:
                uncached_codes.append(ts_code)

        if not uncached_codes:
            return passed_results, all_results

        # 第二轮：未缓存的股票并行计算
        def _calc_one(code: str) -> Dict[str, Any]:
            calc = SealRateCalculator()
            try:
                return calc.calculate_seal_rate(code, trade_date, period_days)
            finally:
                calc.close()

        with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
            futures = {executor.submit(_calc_one, code): code for code in uncached_codes}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    result = future.result()
                    result['from_cache'] = False
                    all_results.append(result)
                    if min_seal_rate is None or (result['seal_rate'] is not None and result['seal_rate'] >= min_seal_rate - 0.01):
                        passed_results.append(result)
                except Exception as e:
                    logger.error(f"计算 {code} 封板率异常: {e}", exc_info=True)
                    error_result = {
                        'ts_code': code,
                        'trade_date': trade_date,
                        'period_days': period_days,
                        'touch_days': 0,
                        'limit_up_days': 0,
                        'seal_rate': None,
                        'data_complete': 0,
                        'error': str(e),
                        'from_cache': False,
                    }
                    all_results.append(error_result)

        logger.info(
            f"批量计算完成: 共{len(ts_codes)}只(缓存{len(ts_codes)-len(uncached_codes)}+计算{len(uncached_codes)}), "
            f"通过{len(passed_results)}只"
        )

        return passed_results, all_results
