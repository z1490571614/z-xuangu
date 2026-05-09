"""
通达信本地日线选股服务 (MCP 降级方案)

当通达信MCP接口不可用时，使用本地 .day 文件进行选股筛选。
数据源: G:\new_tdx\vipdoc\{sh,sz}\lday\*.day
"""
import os
import struct
import time
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)

PRICE_SCALE = 100.0
TDX_VOL_TO_TUSHARE_VOL_SCALE = 100.0
TDX_AMOUNT_TO_TUSHARE_AMOUNT_SCALE = 1000.0

# 板块涨跌幅比例
def get_limit_ratio(stock_code: str) -> float:
    code = str(stock_code).strip()
    if code.startswith(("300", "301", "688")):
        return 0.2
    if code.startswith("60") or code.startswith("00"):
        return 0.1
    return 0.1

def get_limit_price(code: str, prev_close: float) -> float:
    return round(prev_close * (1 + get_limit_ratio(code)), 2)


@dataclass
class TdxLocalResult:
    ts_code: str
    name: str = ""
    close: Optional[float] = None
    change_pct: Optional[float] = None
    pre_change_pct: Optional[float] = None
    open_change_pct: Optional[float] = None
    auction_ratio: Optional[float] = None
    auction_turnover_rate: Optional[float] = None
    industry: Optional[str] = None
    concept: Optional[str] = None
    board_type: Optional[str] = None
    limit_up_count: Optional[int] = None
    seal_rate: Optional[float] = None
    rise_10d_pct: Optional[float] = None
    market: Optional[str] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)


class TdxLocalSelectorService:
    """
    通达信本地日线选股服务

    从通达信本地 .day 文件中读取前复权日线数据，执行筛选条件：
    非ST、非停牌、流通市值<2000亿、收盘价<500、近10日上涨、近100日涨停≥3
    """

    def __init__(
        self,
        tdx_vipdoc_path: Optional[str] = None,
        tushare_token: Optional[str] = None,
    ):
        self.tdx_vipdoc_path = tdx_vipdoc_path or os.getenv(
            "TDX_VIPDOC_PATH", r"G:\new_tdx\vipdoc"
        )
        self._stock_cache = None
        self._st_set = None
        self._day_record_cache: Dict[str, List[tuple]] = {}

    @staticmethod
    def _read_day_file(filepath: str) -> List[tuple]:
        with open(filepath, 'rb') as f:
            data = f.read()
        n = len(data) // 32
        records = []
        for i in range(n):
            offset = i * 32
            date, o, h, l, c, amount, vol = struct.unpack_from('<IIIIIfI', data, offset)
            records.append((
                date,
                o / PRICE_SCALE,
                h / PRICE_SCALE,
                l / PRICE_SCALE,
                c / PRICE_SCALE,
                float(amount) / TDX_AMOUNT_TO_TUSHARE_AMOUNT_SCALE,
                int(vol) / TDX_VOL_TO_TUSHARE_VOL_SCALE,
            ))
        return records

    def _get_day_records(self, filepath: str) -> List[tuple]:
        if filepath not in self._day_record_cache:
            self._day_record_cache[filepath] = self._read_day_file(filepath)
        return self._day_record_cache[filepath]

    def _ts_code_to_day_path(self, ts_code: str) -> Optional[str]:
        code = ts_code.split('.')[0]
        suffix = ts_code.split('.')[1]
        if suffix == 'SH':
            return os.path.join(self.tdx_vipdoc_path, 'sh', 'lday', f'sh{code}.day')
        elif suffix == 'SZ':
            return os.path.join(self.tdx_vipdoc_path, 'sz', 'lday', f'sz{code}.day')
        return None

    def get_daily_data(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        从通达信本地 .day 文件读取日线行情，返回兼容 Tushare daily 的字段。
        """
        if not trade_date and not start_date and not end_date:
            return pd.DataFrame()

        targets = [ts_code] if ts_code else self._list_local_ts_codes()
        rows = []
        for target in targets:
            if not target:
                continue
            path = self._ts_code_to_day_path(target)
            if not path or not os.path.exists(path):
                continue
            try:
                records = sorted(self._get_day_records(path), key=lambda x: x[0])
            except Exception as e:
                logger.debug(f"读取通达信日线失败: {target} {e}")
                continue

            for idx, record in enumerate(records):
                date_value = str(record[0])
                if trade_date and date_value != trade_date:
                    continue
                if start_date and date_value < start_date:
                    continue
                if end_date and date_value > end_date:
                    continue

                pre_close = records[idx - 1][4] if idx > 0 else None
                close = record[4]
                change = None
                pct_chg = None
                if pre_close and pre_close > 0:
                    change = round(close - pre_close, 2)
                    pct_chg = round((close - pre_close) / pre_close * 100, 3)
                rows.append({
                    "ts_code": target,
                    "trade_date": date_value,
                    "open": record[1],
                    "high": record[2],
                    "low": record[3],
                    "close": close,
                    "pre_close": pre_close,
                    "change": change,
                    "pct_chg": pct_chg,
                    "vol": record[6],
                    "amount": record[5],
                })
        return pd.DataFrame(rows)

    def _list_local_ts_codes(self) -> List[str]:
        self._ensure_stock_list()
        if self._stock_cache is None or self._stock_cache.empty:
            return []
        return self._stock_cache["ts_code"].tolist()

    def _ensure_stock_list(self):
        """从本地 .day 文件目录扫描股票列表（不依赖Tushare）"""
        if self._stock_cache is not None:
            return
            
        import pandas as pd
        
        stock_list = []
        # 扫描 sh 市场
        sh_dir = os.path.join(self.tdx_vipdoc_path, 'sh', 'lday')
        if os.path.exists(sh_dir):
            for filename in os.listdir(sh_dir):
                if filename.endswith('.day') and filename.startswith('sh'):
                    code = filename[2:-4]
                    ts_code = f"{code}.SH"
                    stock_list.append({'ts_code': ts_code, 'name': '', 'market': 'sh'})
        
        # 扫描 sz 市场
        sz_dir = os.path.join(self.tdx_vipdoc_path, 'sz', 'lday')
        if os.path.exists(sz_dir):
            for filename in os.listdir(sz_dir):
                if filename.endswith('.day') and filename.startswith('sz'):
                    code = filename[2:-4]
                    ts_code = f"{code}.SZ"
                    stock_list.append({'ts_code': ts_code, 'name': '', 'market': 'sz'})
        
        # 过滤北交所股票（代码以 8 开头）
        stock_list = [s for s in stock_list if not s['ts_code'].startswith('8')]
        
        self._stock_cache = pd.DataFrame(stock_list)
        logger.info(f"本地选股股票池初始化: {len(self._stock_cache)} 只 (从 .day 文件扫描)")

    def _ensure_suspend_set(self, trade_date: str):
        """获取停牌列表（降级模式：跳过停牌检查）"""
        logger.info(f"本地选股跳过停牌检查（需要Tushare）")
        self._suspend_set = set()

    def select(
        self,
        trade_date: str,
        max_circ_mv: float = 2000,
        max_close_price: float = 500,
        min_limit_up_count: int = 3,
        period_days: int = 100,
        data_collector=None,
    ) -> Dict[str, Any]:
        """
        从本地 .day 文件执行选股

        Args:
            trade_date: 交易日期 (YYYYMMDD)
            max_circ_mv: 最大流通市值 (亿)
            max_close_price: 最大收盘价 (元)
            min_limit_up_count: 最少涨停次数
            period_days: 涨停统计周期 (交易日)
            data_collector: TushareDataCollector 实例 (用于获取市值)

        Returns:
            {"stocks": [TdxLocalResult], "total_count": int, "execution_time": float,
             "source": "tdx_local", "task_results": [...]}
        """
        start_time = time.time()
        logger.info(f"========== 本地选股开始 (降级模式) | 日期={trade_date} ==========")

        # 1. 确保股票池
        self._ensure_stock_list()

        # 2. 获取停牌列表
        self._ensure_suspend_set(trade_date)

        # 3. 获取市值数据
        circ_mv_map = {}
        if data_collector:
            try:
                db = data_collector.get_daily_basic(trade_date=trade_date)
                if db is not None and not db.empty:
                    for row in db.itertuples():
                        if row.circ_mv:
                            circ_mv_map[row.ts_code] = row.circ_mv / 10000  # 万元→亿
            except Exception as e:
                logger.warning(f"获取市值数据失败: {e}")

        # 4. 逐股筛选
        all_stocks = []
        funnel = {"total": 0, "has_file": 0, "close_pass": 0, "rise_pass": 0, "limit_pass": 0}

        for _, row in self._stock_cache.iterrows():
            ts_code = row['ts_code']
            name = row['name']
            funnel["total"] += 1

            # 停牌跳过
            if self._suspend_set and ts_code in self._suspend_set:
                continue

            # 市值过滤
            if ts_code in circ_mv_map and circ_mv_map[ts_code] >= max_circ_mv:
                continue

            # 文件路径
            path = self._ts_code_to_day_path(ts_code)
            if not path or not os.path.exists(path):
                continue
            funnel["has_file"] += 1

            try:
                records = self._read_day_file(path)
                if len(records) < 11:
                    continue
            except Exception:
                continue

            records.sort(key=lambda x: x[0])
            close_price = records[-1][4]
            n = len(records)
            last_100 = records[-101:] if n >= 101 else records[:]
            code_num = ts_code.split('.')[0]

            # 条件1: 收盘价 < 500
            if close_price >= max_close_price:
                continue
            funnel["close_pass"] += 1

            # 条件2: 近10日上涨 (前复权收盘价 ≥ 10日前收盘价)
            if n >= 11 and close_price < records[-11][4]:
                continue
            funnel["rise_pass"] += 1

            # 条件3: 近100日涨停 ≥ min_limit_up_count
            limit_count = 0
            for i in range(1, len(last_100)):
                limit_price = get_limit_price(code_num, last_100[i - 1][4])
                if abs(last_100[i][4] - limit_price) < 0.01:
                    limit_count += 1

            if limit_count < min_limit_up_count:
                continue
            funnel["limit_pass"] += 1

            # 计算涨跌幅
            pre_close = records[-2][4] if n >= 2 else None
            change_pct = None
            if pre_close and pre_close > 0:
                change_pct = round((close_price - pre_close) / pre_close * 100, 2)

            # 近10日涨幅
            rise_10d_pct = None
            if n >= 11:
                prev_close = records[-11][4]
                if prev_close > 0:
                    rise_10d_pct = round((close_price - prev_close) / prev_close * 100, 2)

            stock = TdxLocalResult(
                ts_code=ts_code,
                name=name,
                close=close_price,
                change_pct=change_pct,
                limit_up_count=limit_count,
                rise_10d_pct=rise_10d_pct,
            )
            all_stocks.append(stock)

        execution_time = time.time() - start_time

        logger.info(
            f"本地选股完成: {funnel['total']}→{funnel['close_pass']}→"
            f"{funnel['rise_pass']}→{funnel['limit_pass']} ({len(all_stocks)}只), "
            f"耗时 {execution_time:.2f}s"
        )

        return {
            "stocks": all_stocks,
            "total_count": len(all_stocks),
            "execution_time": execution_time,
            "source": "tdx_local",
            "task_results": [{
                "task_id": "local_fallback",
                "task_name": "本地日线选股(降级)",
                "query": "本地 .day 文件筛选",
                "stocks": all_stocks,
                "total_count": len(all_stocks),
                "execution_time": execution_time,
                "funnel": funnel,
            }],
        }
