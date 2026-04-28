"""
通达信MCP选股服务

阶段1: 通过通达信问小达MCP接口进行服务端选股筛选
仅用于选股阶段，严禁调用Tushare接口

模块化选股条件架构:
- SelectionCondition: 单个选股条件定义
- SelectionTask: 独立的选股任务 (包含条件和配置)
- TdxSelectorService: 选股服务 (执行多个独立任务)
"""
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TdxStockResult:
    """通达信选股结果"""
    ts_code: str
    name: str
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


class SelectionCondition(ABC):
    """选股条件基类 - 模块化条件定义"""

    name: str = "base_condition"
    description: str = ""

    @abstractmethod
    def build_query_part(self) -> str:
        """构建该条件的查询语句片段"""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """验证条件参数是否有效"""
        pass


class BasicFilterCondition(SelectionCondition):
    """基本筛选条件: 非ST、非停牌、非北交所"""

    name = "basic_filter"
    description = "非ST非停牌非北交所股票"

    def __init__(self, exclude_st: bool = True, exclude_suspended: bool = True, exclude_bse: bool = True):
        self.exclude_st = exclude_st
        self.exclude_suspended = exclude_suspended
        self.exclude_bse = exclude_bse

    def build_query_part(self) -> str:
        if self.exclude_st and self.exclude_suspended and self.exclude_bse:
            return "非ST非停牌非北交所股票"
        parts = []
        if self.exclude_st:
            parts.append("非ST")
        if self.exclude_suspended:
            parts.append("非停牌")
        if self.exclude_bse:
            parts.append("非北交所")
        return "，".join(parts) + "股票" if parts else ""

    def validate(self) -> bool:
        return self.exclude_st or self.exclude_suspended or self.exclude_bse


class MarketCapCondition(SelectionCondition):
    """市值条件"""

    name = "market_cap"
    description = "流通市值过滤"

    def __init__(self, max_market_cap: float = 2000):
        self.max_market_cap = max_market_cap

    def build_query_part(self) -> str:
        return f"流通市值小于{self.max_market_cap}亿"

    def validate(self) -> bool:
        return self.max_market_cap > 0


class PriceCondition(SelectionCondition):
    """价格条件"""

    name = "price"
    description = "收盘价过滤"

    def __init__(self, max_close_price: float = 500):
        self.max_close_price = max_close_price

    def build_query_part(self) -> str:
        return f"昨日收盘价小于{self.max_close_price}元"

    def validate(self) -> bool:
        return self.max_close_price > 0


class TrendCondition(SelectionCondition):
    """趋势条件"""

    name = "trend"
    description = "近N日股价上涨"

    def __init__(self, min_rise_days: int = 10):
        self.min_rise_days = min_rise_days

    def build_query_part(self) -> str:
        return f"近{self.min_rise_days}日股价上涨"

    def validate(self) -> bool:
        return self.min_rise_days > 0


class LimitUpCondition(SelectionCondition):
    """涨停条件"""

    name = "limit_up"
    description = "涨停次数"

    def __init__(self, min_limit_up_count: int = 3, limit_up_days: int = 100):
        self.min_limit_up_count = min_limit_up_count
        self.limit_up_days = limit_up_days

    def build_query_part(self) -> str:
        if self.min_limit_up_count > 0:
            return f"近{self.limit_up_days}个交易日内涨停次数不少于{self.min_limit_up_count}次"
        return ""

    def validate(self) -> bool:
        return self.min_limit_up_count >= 0


class CallAuctionCondition(SelectionCondition):
    """竞价条件"""

    name = "call_auction"
    description = "竞价活跃度过滤"

    def __init__(
        self,
        call_auction_ratio_min: float = 0.04,
        call_auction_ratio_max: float = 0.30,
        turnover_rate_min: float = 0.005,
        turnover_rate_max: float = 0.10,
    ):
        self.call_auction_ratio_min = call_auction_ratio_min
        self.call_auction_ratio_max = call_auction_ratio_max
        self.turnover_rate_min = turnover_rate_min
        self.turnover_rate_max = turnover_rate_max

    def build_query_part(self) -> str:
        parts = []
        if self.call_auction_ratio_min > 0 and self.call_auction_ratio_max > 0:
            parts.append(
                f"竞价量占昨日成交量比例{int(self.call_auction_ratio_min * 100)}%到{int(self.call_auction_ratio_max * 100)}%"
            )
        if self.turnover_rate_min > 0 and self.turnover_rate_max > 0:
            # 修复：确保竞价换手率也使用整数格式
            # 处理 0.5% -> "0.5%" 而不是 "0.5000000000000001%"
            min_val = round(self.turnover_rate_min * 100, 2)
            max_val = round(self.turnover_rate_max * 100, 2)
            min_str = f"{int(min_val)}%" if min_val.is_integer() else f"{min_val}%"
            max_str = f"{int(max_val)}%" if max_val.is_integer() else f"{max_val}%"
            parts.append(
                f"竞价换手率{min_str}到{max_str}"
            )
        return "，".join(parts)

    def validate(self) -> bool:
        return (
            0 < self.call_auction_ratio_min < self.call_auction_ratio_max
            and 0 < self.turnover_rate_min < self.turnover_rate_max
        )


CONDITION_REGISTRY: Dict[str, type] = {
    "basic_filter": BasicFilterCondition,
    "market_cap": MarketCapCondition,
    "price": PriceCondition,
    "trend": TrendCondition,
    "limit_up": LimitUpCondition,
    "call_auction": CallAuctionCondition,
}


@dataclass
class SelectionTask:
    """
    独立的选股任务

    每个任务包含一组选股条件，任务间保持逻辑隔离
    """
    task_id: str
    task_name: str
    conditions: List[SelectionCondition] = field(default_factory=list)
    page_size: int = 50
    market: str = "AG"

    def build_query(self) -> str:
        """构建完整的查询语句"""
        parts = []
        for cond in self.conditions:
            if cond.validate():
                part = cond.build_query_part()
                if part:
                    parts.append(part)
            else:
                logger.warning(f"任务[{self.task_id}] 条件[{cond.name}] 验证失败，已跳过")
        query = "，".join(parts)
        logger.debug(f"任务[{self.task_id}] 查询语句: {query}")
        return query

    def add_condition(self, condition: SelectionCondition) -> "SelectionTask":
        """添加条件 (链式调用)"""
        self.conditions.append(condition)
        return self

    def validate(self) -> bool:
        """验证任务是否有效"""
        if not self.task_id:
            return False
        if not self.conditions:
            return False
        return all(c.validate() for c in self.conditions)


def create_default_task() -> SelectionTask:
    """创建默认选股任务 (竞价活跃度策略)"""
    return SelectionTask(
        task_id="default_call_auction",
        task_name="竞价活跃度选股",
        conditions=[
            BasicFilterCondition(),
            MarketCapCondition(),
            PriceCondition(),
            TrendCondition(),
            LimitUpCondition(),
            CallAuctionCondition(),
        ],
    )


def create_conservative_task() -> SelectionTask:
    """创建保守型选股任务"""
    return SelectionTask(
        task_id="conservative",
        task_name="保守型选股",
        conditions=[
            BasicFilterCondition(),
            MarketCapCondition(max_market_cap=1000),
            PriceCondition(max_close_price=100),
            TrendCondition(min_rise_days=15),
            LimitUpCondition(min_limit_up_count=5),
            CallAuctionCondition(
                call_auction_ratio_min=0.05,
                call_auction_ratio_max=0.20,
                turnover_rate_min=0.01,
                turnover_rate_max=0.05,
            ),
        ],
    )


def create_aggressive_task() -> SelectionTask:
    """创建激进型选股任务"""
    return SelectionTask(
        task_id="aggressive",
        task_name="激进型选股",
        conditions=[
            BasicFilterCondition(),
            MarketCapCondition(max_market_cap=500),
            PriceCondition(max_close_price=200),
            TrendCondition(min_rise_days=5),
            LimitUpCondition(min_limit_up_count=3),
            CallAuctionCondition(
                call_auction_ratio_min=0.10,
                call_auction_ratio_max=0.30,
                turnover_rate_min=0.02,
                turnover_rate_max=0.10,
            ),
        ],
    )


TASK_TEMPLATES: Dict[str, type] = {
    "default": create_default_task,
    "conservative": create_conservative_task,
    "aggressive": create_aggressive_task,
}


HEADER_FIELD_MAP: Dict[str, str] = {
    "代码": "code",
    "股票代码": "code",
    "sec_code": "code",
    "名称": "name",
    "股票名称": "name",
    "sec_name": "name",
    "现价": "close",
    "最新价": "close",
    "收盘价": "close",
    "price": "close",
    "now_price": "close",
    "涨幅": "change_pct",
    "涨跌幅": "change_pct",
    "change_pct": "change_pct",
    "chg": "change_pct",
    "chg0#": "change_pct",
    "昨涨幅": "pre_change_pct",
    "昨涨跌幅": "pre_change_pct",
    "开涨幅": "open_change_pct",
    "开涨跌幅": "open_change_pct",
    "开盘(%)": "open_change_pct",
    "行业": "industry",
    "所属行业": "industry",
    "industry": "industry",
    "概念": "concept",
    "行业概念": "concept",
    "板块": "board_type",
    "板型": "board_type",
    "排名": "rank",
    "序号": "rank",
    "POS": "rank",
    "市场": "market",
    "market": "market",
    "封成比": "seal_rate",
    "涨停区间次数": "limit_up_count",
    "涨停次数": "limit_up_count",
    "封板成功率": "seal_rate",
    "封板率": "seal_rate",
    "涨幅(%)": "rise_10d_pct",
    "10日涨幅": "rise_10d_pct",
    "近10日涨幅": "rise_10d_pct",
    "竞价量占比": "auction_ratio",
    "竞昨比": "auction_ratio",
    "[1]/[2]": "auction_ratio",
    "竞价换手率": "auction_turnover_rate",
    "换手率": "auction_turnover_rate",
    "开盘自由换手率": "auction_turnover_rate",
    "开盘自由换手率(%)": "auction_turnover_rate",
}


def _build_header_index(headers: list) -> Dict[str, int]:
    """构建 header -> 列索引 的映射"""
    index_map: Dict[str, int] = {}
    for i, h in enumerate(headers):
        h_clean = str(h).strip()
        # 去除日期后缀，比如 "<br>2026.04.24" 或 ".前复权<br>2026.04.23"
        if '<br>' in h_clean:
            h_clean = h_clean.split('<br>')[0].strip()
        # 先检查带 .前复权 的原始key（优先级高）
        field = HEADER_FIELD_MAP.get(h_clean)
        if not field and '.前复权' in h_clean:
            h_clean = h_clean.split('.前复权')[0].strip()
            # 再检查去掉 .前复权 后的key
            field = HEADER_FIELD_MAP.get(h_clean)
        if field and field not in index_map:
            index_map[field] = i
    logger.debug(f"处理后的列映射: {index_map} (原始headers: {headers})")
    return index_map


def parse_tdx_response(data: Dict) -> List[TdxStockResult]:
    """
    解析通达信MCP接口返回的数据

    使用 headers 进行动态列映射，兼容不同查询返回的不同列顺序

    Args:
        data: MCP服务返回的原始数据

    Returns:
        解析后的股票结果列表
    """
    if not data:
        logger.warning("通达信MCP返回空数据")
        return []

    meta = data.get("meta", {})
    if meta.get("code") != 0:
        logger.warning(f"通达信MCP返回错误: code={meta.get('code')}, message={meta.get('message', '')}")
        return []

    headers = data.get("headers", [])
    rows = data.get("data", [])
    total = meta.get("total", 0)

    logger.info(f"通达信MCP返回 {total} 条记录，当前页 {len(rows)} 条，headers: {headers}")

    col_map = _build_header_index(headers)
    logger.debug(f"列映射: {col_map}")

    stocks = []
    for row in rows:
        try:
            stock = _parse_stock_row(row, col_map, headers)
            if stock:
                stocks.append(stock)
        except (IndexError, ValueError, TypeError) as e:
            logger.warning(f"解析股票数据失败: {row}, 错误: {e}")
            continue

    logger.info(f"通达信MCP选股解析完成: 共 {len(stocks)} 只股票")
    return stocks


def _parse_stock_row(row: list, col_map: Dict[str, int], headers: list) -> Optional[TdxStockResult]:
    """解析单行股票数据 (基于列映射)"""
    if not row or len(row) < 2:
        return None

    code_val = _get_col_value(row, col_map, "code")
    name_val = _get_col_value(row, col_map, "name")

    if not code_val and not name_val:
        if len(row) >= 2:
            code_val = str(row[0]).strip() if row[0] else ""
            name_val = str(row[1]).strip() if row[1] else ""

    if not code_val and not name_val:
        return None

    ts_code = _convert_to_ts_code(str(code_val).strip()) if code_val else ""

    close = _safe_float(_get_col_value(row, col_map, "close"))
    change_pct = _safe_float(_get_col_value(row, col_map, "change_pct"))
    pre_change_pct = _safe_float(_get_col_value(row, col_map, "pre_change_pct"))
    open_change_pct = _safe_float(_get_col_value(row, col_map, "open_change_pct"))
    auction_ratio = _safe_float(_get_col_value(row, col_map, "auction_ratio"))
    # 竞昨比从小数(0.0735)转成百分比(7.35)
    if auction_ratio is not None and auction_ratio < 1:
        auction_ratio = round(auction_ratio * 100, 2)
    auction_turnover_rate = _safe_float(_get_col_value(row, col_map, "auction_turnover_rate"))
    industry = _get_col_value(row, col_map, "industry")
    if industry:
        industry = str(industry).strip()
    concept = _get_col_value(row, col_map, "concept")
    if concept:
        concept = str(concept).strip()
    board_type = _get_col_value(row, col_map, "board_type")
    if board_type:
        board_type = str(board_type).strip()
    limit_up_count_val = _get_col_value(row, col_map, "limit_up_count")
    limit_up_count = int(limit_up_count_val) if limit_up_count_val is not None else None
    seal_rate = _safe_float(_get_col_value(row, col_map, "seal_rate"))
    # 封成比从小数(0.9117)转成百分比(91.17)
    if seal_rate is not None and seal_rate < 1:
        seal_rate = round(seal_rate * 100, 2)
    rise_10d_pct = _safe_float(_get_col_value(row, col_map, "rise_10d_pct"))

    extra = {}
    mapped_indices = set(col_map.values())
    for i, h in enumerate(headers):
        if i < len(row) and i not in mapped_indices:
            extra[str(h)] = row[i]

    return TdxStockResult(
        ts_code=ts_code,
        name=str(name_val).strip() if name_val else "",
        close=close,
        change_pct=change_pct,
        pre_change_pct=pre_change_pct,
        open_change_pct=open_change_pct,
        auction_ratio=auction_ratio,
        auction_turnover_rate=auction_turnover_rate,
        industry=industry,
        concept=concept,
        board_type=board_type,
        limit_up_count=limit_up_count,
        seal_rate=seal_rate,
        rise_10d_pct=rise_10d_pct,
        extra_data=extra,
    )


def _get_col_value(row: list, col_map: Dict[str, int], field: str):
    """根据列映射获取值"""
    idx = col_map.get(field)
    if idx is not None and idx < len(row):
        return row[idx]
    return None


def _safe_float(val) -> Optional[float]:
    """安全转换为浮点数"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _convert_to_ts_code(code: str) -> str:
    """
    将股票代码转换为Tushare格式

    例: 000001 -> 000001.SZ, 600001 -> 600001.SH
    """
    code = code.strip()
    if not code:
        return ""

    if "." in code:
        return code

    if code.startswith(("6",)):
        return f"{code}.SH"
    elif code.startswith(("0", "3")):
        return f"{code}.SZ"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


class TdxSelectorService:
    """
    通达信MCP选股服务

    阶段1: 仅负责选股筛选，严禁调用Tushare
    支持执行多个独立的选股任务
    """

    def __init__(self, tasks: Optional[List[SelectionTask]] = None):
        self.tasks = tasks or [create_default_task()]

    def add_task(self, task: SelectionTask) -> None:
        """添加选股任务"""
        self.tasks.append(task)
        logger.info(f"添加选股任务: [{task.task_id}] {task.task_name}")

    def clear_tasks(self) -> None:
        """清空所有任务"""
        self.tasks.clear()

    def select(self, tdx_mcp_func=None) -> Dict[str, Any]:
        """
        执行所有选股任务 (阶段1)

        严禁在此方法中调用Tushare接口

        Args:
            tdx_mcp_func: 通达信MCP接口函数 (由调用方注入)

        Returns:
            合并后的选股结果
        """
        start_time = time.time()
        all_stocks: List[TdxStockResult] = []
        task_results = []
        seen_codes = set()

        for task in self.tasks:
            logger.info(f"阶段1: 执行选股任务 [{task.task_id}] {task.task_name}")
            task_result = self._execute_task(task, tdx_mcp_func)
            task_results.append(task_result)

            for stock in task_result.get("stocks", []):
                if stock.ts_code not in seen_codes:
                    seen_codes.add(stock.ts_code)
                    all_stocks.append(stock)

        execution_time = time.time() - start_time

        logger.info(
            f"阶段1完成: 共执行 {len(self.tasks)} 个任务，"
            f"合并后 {len(all_stocks)} 只股票，"
            f"耗时 {execution_time:.2f}秒"
        )

        return {
            "stocks": all_stocks,
            "total_count": len(all_stocks),
            "execution_time": execution_time,
            "source": "tdx_mcp",
            "task_results": task_results,
        }

    def _execute_task(self, task: SelectionTask, tdx_mcp_func) -> Dict[str, Any]:
        """执行单个选股任务"""
        task_start = time.time()
        query = task.build_query()

        if not query:
            logger.warning(f"任务 [{task.task_id}] 查询语句为空，跳过")
            return {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "query": "",
                "stocks": [],
                "total_count": 0,
                "execution_time": 0,
                "error": "查询语句为空",
            }

        logger.info(f"任务 [{task.task_id}] 查询语句: {query}")

        if tdx_mcp_func is None:
            logger.warning("未提供通达信MCP接口函数，返回空结果")
            return {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "query": query,
                "stocks": [],
                "total_count": 0,
                "execution_time": time.time() - task_start,
                "error": "MCP接口函数未提供",
            }

        try:
            raw_data = tdx_mcp_func(
                question=query,
                range=task.market,
                size=str(task.page_size),
            )
            raw_stocks = parse_tdx_response(raw_data)
            
            # 二次筛选，确保符合所有条件
            stocks = []
            for stock in raw_stocks:
                valid = True
                
                # 检查所有条件
                for cond in task.conditions:
                    # 检查涨停次数
                    if isinstance(cond, LimitUpCondition):
                        if cond.min_limit_up_count > 0:
                            if (stock.limit_up_count is None or 
                                stock.limit_up_count < cond.min_limit_up_count):
                                valid = False
                                break
                    # 检查竞价条件
                    elif isinstance(cond, CallAuctionCondition):
                        if (stock.auction_ratio is None or 
                            stock.auction_ratio < cond.call_auction_ratio_min * 100 or 
                            stock.auction_ratio > cond.call_auction_ratio_max * 100):
                            valid = False
                            break
                        if (stock.auction_turnover_rate is None or 
                            stock.auction_turnover_rate < cond.turnover_rate_min * 100 or 
                            stock.auction_turnover_rate > cond.turnover_rate_max * 100):
                            valid = False
                            break
                
                if valid:
                    stocks.append(stock)
            
            # 记录筛选前后的数量
            if len(raw_stocks) != len(stocks):
                logger.info(
                    f"二次筛选: {len(raw_stocks)} -> {len(stocks)} 只股票"
                )
            
            task_time = time.time() - task_start

            logger.info(
                f"任务 [{task.task_id}] 完成: {len(stocks)} 只股票, "
                f"耗时 {task_time:.2f}秒"
            )

            return {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "query": query,
                "stocks": stocks,
                "total_count": len(stocks),
                "execution_time": task_time,
            }

        except ConnectionError as e:
            logger.error(f"任务 [{task.task_id}] 网络连接失败: {e}")
            return {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "query": query,
                "stocks": [],
                "total_count": 0,
                "execution_time": time.time() - task_start,
                "error": f"网络连接失败: {e}",
            }
        except TimeoutError as e:
            logger.error(f"任务 [{task.task_id}] 请求超时: {e}")
            return {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "query": query,
                "stocks": [],
                "total_count": 0,
                "execution_time": time.time() - task_start,
                "error": f"请求超时: {e}",
            }
        except ValueError as e:
            logger.error(f"任务 [{task.task_id}] 数据格式异常: {e}")
            return {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "query": query,
                "stocks": [],
                "total_count": 0,
                "execution_time": time.time() - task_start,
                "error": f"数据格式异常: {e}",
            }
        except Exception as e:
            logger.error(f"任务 [{task.task_id}] 未知错误: {e}", exc_info=True)
            return {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "query": query,
                "stocks": [],
                "total_count": 0,
                "execution_time": time.time() - task_start,
                "error": f"未知错误: {e}",
            }
