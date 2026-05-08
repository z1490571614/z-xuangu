"""
数据采集服务
"""
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
import pandas as pd
import httpx
import tushare as ts

os.environ.setdefault('TUSHARE_PRO_SAVE_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'tushare_cache'))
os.makedirs(os.environ['TUSHARE_PRO_SAVE_PATH'], exist_ok=True)

from backend.utils.trading_date import is_trading_day, get_latest_trading_day
from backend.utils.tushare_client import get_tushare_pro, get_tushare_token

logger = logging.getLogger(__name__)


class TushareDataCollector:
    """Tushare 数据采集器"""

    def __init__(self, token: Optional[str] = None):
        """
        初始化数据采集器

        Args:
            token: Tushare API Token，如果为None则从环境变量获取
        """
        self.token = get_tushare_token(token)
        if not self.token:
            raise ValueError("Tushare Token 未配置，请设置 TUSHARE_TOKEN 环境变量")

        self._trading_calendar_cache: Dict[int, set] = {}
        self._last_pro: Optional[Any] = None

    @property
    def pro(self):
        """获取 Pro API 实例（惰性创建，带自动重连）"""
        if self._last_pro is None:
            self._last_pro = self._create_pro()
        return self._last_pro

    def _get_pro(self):
        """创建新的 Pro API 实例（供外部降级使用）"""
        return self._create_pro()

    def _create_pro(self):
        """创建新的 Pro API 实例（内部使用）"""
        try:
            return get_tushare_pro(self.token)
        except OSError:
            return get_tushare_pro(self.token)

    def get_trading_calendar(self, year: Optional[int] = None) -> set:
        """
        获取交易日历

        Args:
            year: 年份，None表示当前年份

        Returns:
            交易日集合（YYYYMMDD格式）
        """
        if year is None:
            year = date.today().year

        if not isinstance(self._trading_calendar_cache, dict):
            self._trading_calendar_cache = {}

        if year in self._trading_calendar_cache:
            return self._trading_calendar_cache[year]

        try:
            start_date = f"{year}0101"
            end_date = f"{year}1231"
            df = self.pro.trade_cal(
                exchange='SSE',
                start_date=start_date,
                end_date=end_date,
                is_open='1'
            )

            if df is not None and len(df) > 0:
                self._trading_calendar_cache[year] = set(df['cal_date'].tolist())
                return self._trading_calendar_cache[year]
        except Exception as e:
            logger.error(f"获取交易日历失败: {e}")

        return set()

    def is_trading_day(self, check_date: date) -> bool:
        """
        判断是否为交易日

        Args:
            check_date: 待检查的日期

        Returns:
            是否为交易日
        """
        calendar = self.get_trading_calendar(check_date.year)
        return is_trading_day(check_date, calendar)

    def get_stock_basic(self, list_status: str = 'L') -> pd.DataFrame:
        """
        获取股票基础信息

        Args:
            list_status: 上市状态，L表示上市，D表示退市，P表示暂停上市

        Returns:
            股票基础信息DataFrame
        """
        try:
            df = self.pro.stock_basic(
                exchange='',
                list_status=list_status,
                fields='ts_code,symbol,name,area,industry,market,list_date'
            )
            logger.info(f"获取股票基础信息成功，共 {len(df)} 只股票")
            return df
        except Exception as e:
            logger.error(f"获取股票基础信息失败: {e}")
            return pd.DataFrame()

    def get_concept(self, ts_code: str) -> Optional[str]:
        """
        获取股票概念板块信息

        Args:
            ts_code: 股票代码

        Returns:
            概念板块字符串，多个概念用逗号分隔
        """
        try:
            df = self.pro.concept(
                ts_code=ts_code,
                fields='ts_code,concept_name'
            )
            if not df.empty:
                concepts = df['concept_name'].tolist()
                return ','.join(concepts)
            return None
        except Exception as e:
            logger.warning(f"获取概念板块失败: {e}")
            return None

    def get_rt_k(self, ts_code: Optional[str] = None) -> pd.DataFrame:
        """
        获取实时日K线数据（rt_k接口，盘中可用，限1次/小时）

        Args:
            ts_code: 股票代码通配符，如 '000001.SZ' 或 '3*.SZ,6*.SH'

        Returns:
            实时日线DataFrame，包含 ts_code,name,pre_close,high,open,low,close,vol,amount
        """
        try:
            if ts_code is None:
                ts_code = "3*.SZ,6*.SH,0*.SZ,9*.BJ"
            pro = self._get_pro()
            df = pro.rt_k(ts_code=ts_code)
            if df is not None and len(df) > 0:
                logger.info(f"获取实时日线成功，共 {len(df)} 条记录")
                return df
            logger.warning(f"获取实时日线返回空数据")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"获取实时日线失败: {e}")
            return pd.DataFrame()

    def get_realtime_quotes(self, ts_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        从内部通达信行情API批量获取实时行情

        接口: http://192.168.10.109:8080/api/quote?code=000001,002429,600330
        价格单位: 厘（÷1000 = 元）

        Args:
            ts_codes: 股票代码列表（如 ['000062.SZ', '002429.SZ']）

        Returns:
            {ts_code: {open, pre_close, close}} 字典
        """
        if not ts_codes:
            return {}
        codes = [c.split('.')[0] for c in ts_codes]
        result = {}
        base_url = "http://192.168.10.109:8080/api/quote"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(base_url, params={"code": ",".join(codes)})
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 0 and data.get("data"):
                    for item in data["data"]:
                        raw_code = item.get("Code", "")
                        ts_code = None
                        for c in ts_codes:
                            if c.startswith(raw_code):
                                ts_code = c
                                break
                        if ts_code is None:
                            continue
                        k = item.get("K", {})
                        result[ts_code] = {
                            "open": k.get("Open", 0) / 1000 if k.get("Open") else None,
                            "pre_close": k.get("Last", 0) / 1000 if k.get("Last") else None,
                            "close": k.get("Close", 0) / 1000 if k.get("Close") else None,
                            "high": k.get("High", 0) / 1000 if k.get("High") else None,
                            "low": k.get("Low", 0) / 1000 if k.get("Low") else None,
                        }
            logger.info(f"批量获取实时行情成功: {len(result)}/{len(ts_codes)} 只")
            return result
        except Exception as e:
            logger.warning(f"批量获取实时行情失败: {e}")
            return result

    def get_daily_data(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取日线行情数据

        Args:
            ts_code: 股票代码（如 000001.SZ），None表示全市场
            trade_date: 交易日期（YYYYMMDD格式）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            日线行情DataFrame
        """
        try:
            kwargs = {
                'fields': 'ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
            }
            if ts_code:
                kwargs['ts_code'] = ts_code
            if trade_date:
                kwargs['trade_date'] = trade_date
            if start_date:
                kwargs['start_date'] = start_date
            if end_date:
                kwargs['end_date'] = end_date
            if not trade_date and not start_date and not end_date:
                logger.warning("get_daily_data 缺少日期参数")
                return pd.DataFrame()
            df = self.pro.daily(**kwargs)
            logger.info(f"获取日线行情成功，共 {len(df)} 条记录")
            return df
        except Exception as e:
            logger.error(f"获取日线行情失败: {e}")
            return pd.DataFrame()

    def get_daily_basic(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取每日指标数据（市值、PE等）

        Args:
            trade_date: 交易日期（YYYYMMDD格式）

        Returns:
            每日指标DataFrame
        """
        try:
            df = self.pro.daily_basic(
                trade_date=trade_date,
                fields='ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,total_mv,circ_mv,float_share'
            )
            logger.info(f"获取每日指标成功，共 {len(df)} 条记录")
            return df
        except Exception as e:
            logger.error(f"获取每日指标失败: {e}")
            return pd.DataFrame()

    def get_limit_list(
        self,
        trade_date: Optional[str] = None,
        ts_code: Optional[str] = None,
        limit_type: str = 'U'
    ) -> pd.DataFrame:
        """
        获取涨跌停数据

        Args:
            trade_date: 交易日期（YYYYMMDD格式）
            ts_code: 股票代码
            limit_type: 涨跌停类型，U表示涨停，D表示跌停

        Returns:
            涨跌停数据DataFrame
        """
        try:
            df = self.pro.limit_list(
                trade_date=trade_date,
                ts_code=ts_code,
                limit_type=limit_type,
                fields='ts_code,trade_date,name,close,pct_chg,limit_times,limit_times_hf,up_stat,fd_amount,first_time,last_time,open_times,up_stat'
            )
            logger.info(f"获取涨跌停数据成功，共 {len(df)} 条记录")
            return df
        except Exception as e:
            logger.error(f"获取涨跌停数据失败: {e}")
            return pd.DataFrame()

    def get_limit_list_ths(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        limit_type: str = '涨停池',
    ) -> pd.DataFrame:
        """
        获取同花顺涨跌停榜单数据

        Args:
            ts_code: 股票代码
            trade_date: 交易日期（YYYYMMDD格式）
            limit_type: 板单类别，如涨停池、连扳池、炸板池等

        Returns:
            同花顺涨跌停榜单DataFrame
        """
        try:
            kwargs = {'limit_type': limit_type}
            if ts_code:
                kwargs['ts_code'] = ts_code
            if trade_date:
                kwargs['trade_date'] = trade_date
            df = self.pro.limit_list_ths(**kwargs)
            if df is not None and len(df) > 0:
                logger.info(f"获取同花顺涨跌停榜单成功，共 {len(df)} 条记录")
                return df
            logger.warning(f"获取同花顺涨跌停榜单返回空数据")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"获取同花顺涨跌停榜单失败: {e}")
            return pd.DataFrame()

    def get_stk_limit(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取股票涨跌停价格

        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            涨跌停价格DataFrame
        """
        try:
            df = self.pro.stk_limit(
                ts_code=ts_code,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
                fields='ts_code,trade_date,up_limit,down_limit'
            )
            return df
        except Exception as e:
            logger.error(f"获取涨跌停价格失败: {e}")
            return pd.DataFrame()

    def get_auction_data(self, trade_date: str) -> pd.DataFrame:
        """
        获取集合竞价数据

        注意：此接口需要较高积分权限

        Args:
            trade_date: 交易日期（YYYYMMDD格式）

        Returns:
            集合竞价数据DataFrame
        """
        try:
            df = self.pro.auction_detail(trade_date=trade_date)
            if df is not None and len(df) > 0:
                logger.info(f"获取集合竞价数据成功，共 {len(df)} 条记录")
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"获取集合竞价数据失败（可能需要更高积分）: {e}")
            return pd.DataFrame()

    def get_stk_auction_open(self, trade_date: str) -> pd.DataFrame:
        """
        获取开盘集合竞价数据（Tushare stk_auction_o）。

        该接口用于历史回测和训练，实盘选股仍以 MCP 当日竞价字段为准。
        """
        try:
            df = self.pro.stk_auction_o(
                trade_date=trade_date,
                fields="ts_code,trade_date,open,high,low,close,vol,amount,vwap",
            )
            if df is not None and len(df) > 0:
                logger.info(f"获取开盘集合竞价数据成功，共 {len(df)} 条记录")
                return df
            logger.warning("获取开盘集合竞价数据返回空数据")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"获取开盘集合竞价数据失败: {e}")
            return pd.DataFrame()

    def get_latest_trade_date(self) -> str:
        """
        获取最新的交易日期

        Returns:
            最新交易日期（YYYYMMDD格式）
        """
        calendar = self.get_trading_calendar()
        return get_latest_trading_day(trading_calendar=calendar)

    def get_stock_pool(
        self,
        trade_date: Optional[str] = None,
        min_circ_mv: Optional[float] = None,
        max_circ_mv: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        获取股票池数据

        Args:
            trade_date: 交易日期，None表示最新交易日
            min_circ_mv: 最小流通市值（亿）
            max_circ_mv: 最大流通市值（亿）

        Returns:
            股票池数据列表
        """
        if trade_date is None:
            trade_date = self.get_latest_trade_date()

        daily_df = self.get_daily_data(trade_date=trade_date)
        if daily_df.empty:
            logger.warning(f"未获取到 {trade_date} 的日线数据")
            return []

        basic_df = self.get_daily_basic(trade_date=trade_date)
        if basic_df.empty:
            logger.warning(f"未获取到 {trade_date} 的每日指标数据")
            return []

        merged_df = pd.merge(daily_df, basic_df, on='ts_code', how='left')

        if min_circ_mv is not None:
            merged_df = merged_df[merged_df['circ_mv'] >= min_circ_mv * 10000]

        if max_circ_mv is not None:
            merged_df = merged_df[merged_df['circ_mv'] <= max_circ_mv * 10000]

        result = merged_df.to_dict('records')
        logger.info(f"股票池构建完成，共 {len(result)} 只股票")
        return result

    def get_pre_and_open_change(self, ts_code: str, trade_date: str) -> tuple[Optional[float], Optional[float]]:
        """
        计算昨涨幅和开涨幅

        Args:
            ts_code: 股票代码
            trade_date: 交易日期

        Returns:
            (昨涨幅, 开涨幅) 元组
        """
        try:
            # 获取当日和前一日的日线数据
            daily_data = self.get_daily_data(
                ts_code=ts_code,
                start_date=trade_date,
                end_date=trade_date
            )
            
            if daily_data.empty:
                return None, None
            
            # 获取前一日的日期
            calendar = self.get_trading_calendar()
            from backend.utils.trading_date import get_previous_trading_day
            prev_date = get_previous_trading_day(trade_date, calendar)
            
            # 获取前一日的日线数据
            prev_data = self.get_daily_data(
                ts_code=ts_code,
                start_date=prev_date,
                end_date=prev_date
            )
            
            if prev_data.empty:
                return None, None
            
            # 计算昨涨幅（前一日的涨跌幅）
            prev_row = prev_data.iloc[0]
            pre_change_pct = prev_row.get('pct_chg')
            
            # 计算开涨幅（当日开盘价相对昨日收盘价的涨跌幅）
            current_row = daily_data.iloc[0]
            open_price = current_row.get('open')
            prev_close = prev_row.get('close')
            
            if open_price is not None and prev_close is not None and prev_close > 0:
                open_change_pct = (open_price - prev_close) / prev_close * 100
            else:
                open_change_pct = None
            
            return pre_change_pct, open_change_pct
        except Exception as e:
            logger.warning(f"计算昨涨幅和开涨幅失败: {e}")
            return None, None
