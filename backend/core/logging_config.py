"""
结构化日志模块

提供 JSON 格式日志输出、日志轮转、请求追踪功能
"""
import logging
import json
import os
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


class JSONFormatter(logging.Formatter):
    """JSON 格式化器 - 适合日志聚合工具"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        return json.dumps(log_data, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """人类可读格式化器 - 适合开发调试"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{ts} - {record.levelname} - {record.name} - {record.getMessage()}"
        if hasattr(record, "request_id"):
            msg = f"[{record.request_id}] {msg}"
        if record.exc_info and record.exc_info[0] is not None:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


class RequestLoggerMiddleware:
    """
    HTTP 请求日志中间件
    
    记录每个 API 请求的详细信息，包括：
    - 请求方法、路径、状态码、响应时间
    - 请求参数、客户端IP
    - 自动生成 request_id 用于全链路追踪
    """

    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("api.requests")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import time
        start_time = time.time()
        request_id = str(uuid.uuid4())[:8]

        method = scope.get("method", "")
        path = scope.get("path", "")
        query_string = scope.get("query_string", b"").decode()
        
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message["status"]
                elapsed_ms = (time.time() - start_time) * 1000
                
                extra = {
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "query_string": query_string or None,
                    "status_code": status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "client_ip": client_ip,
                }

                if status_code >= 400:
                    self.logger.warning(
                        f"{method} {path} → {status_code} ({elapsed_ms:.0f}ms)",
                        extra=extra
                    )
                elif status_code >= 300:
                    self.logger.info(
                        f"{method} {path} → {status_code} ({elapsed_ms:.0f}ms)",
                        extra=extra
                    )
                else:
                    self.logger.info(
                        f"{method} {path} → {status_code} ({elapsed_ms:.0f}ms)",
                        extra=extra
                    )

            await send(message)

        await self.app(scope, receive, send_wrapper)


class SelectionLogger:
    """
    选股流程专用日志记录器
    
    记录选股任务的关键节点：
    - 任务开始/结束
    - MCP接口调用
    - 数据解析结果
    - 数据库保存
    - 通知发送
    """

    def __init__(self):
        self.logger = logging.getLogger("selection.flow")

    def task_start(self, trade_date: str, strategy_config: dict = None):
        self.logger.info(
            f"选股任务开始 | 交易日={trade_date}",
            extra={"extra_data": {
                "event": "task_start",
                "trade_date": trade_date,
                "strategy_config": strategy_config
            }}
        )

    def mcp_call_start(self, query: str):
        self.logger.debug(
            f"MCP接口调用开始",
            extra={"extra_data": {"event": "mcp_call_start", "query": query[:100]}}
        )

    def mcp_call_end(self, stock_count: int, elapsed_ms: float):
        self.logger.info(
            f"MCP接口返回 | 股票数={stock_count}, 耗时={elapsed_ms:.0f}ms",
            extra={"extra_data": {
                "event": "mcp_call_end",
                "stock_count": stock_count,
                "elapsed_ms": round(elapsed_ms, 2)
            }}
        )

    def data_parse_result(self, parsed_count: int, total_raw: int):
        self.logger.info(
            f"数据解析完成 | 解析={parsed_count}, 原始={total_raw}",
            extra={"extra_data": {
                "event": "data_parse",
                "parsed_count": parsed_count,
                "total_raw": total_raw
            }}
        )

    def db_save_result(self, record_id: int, stock_count: int):
        self.logger.info(
            f"数据库保存成功 | 记录ID={record_id}, 股票数={stock_count}",
            extra={"extra_data": {
                "event": "db_save",
                "record_id": record_id,
                "stock_count": stock_count
            }}
        )

    def notification_sent(self, success: bool, channel: str = "feishu"):
        status = "成功" if success else "失败"
        self.logger.info(
            f"通知发送{status} | 渠道={channel}",
            extra={"extra_data": {
                "event": "notification",
                "success": success,
                "channel": channel
            }}
        )

    def task_complete(self, total_stocks: int, elapsed_sec: float):
        self.logger.info(
            f"选股任务完成 | 总股票={total_stocks}, 总耗时={elapsed_sec:.2f}s",
            extra={"extra_data": {
                "event": "task_complete",
                "total_stocks": total_stocks,
                "elapsed_sec": round(elapsed_sec, 2)
            }}
        )

    def error(self, stage: str, error: Exception):
        self.logger.error(
            f"选股异常 [{stage}] | {str(error)}",
            exc_info=True,
            extra={"extra_data": {
                "event": "error",
                "stage": stage,
                "error_type": type(error).__name__,
                "error_msg": str(error)[:500]
            }}
        )


def setup_logging(
    log_dir: str = "logs",
    log_level: str = "INFO",
    enable_json: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """
    初始化日志系统
    
    Args:
        log_dir: 日志目录
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        enable_json: 是否启用JSON格式日志
        max_bytes: 单个日志文件最大大小(字节)
        backup_count: 保留的备份文件数量
        
    Returns:
        根日志记录器
    """
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    
    existing_level = root_logger.level
    new_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(new_level)

    if not root_logger.handlers:
        if enable_json:
            json_handler = RotatingFileHandler(
                os.path.join(log_dir, "xuangu.json"),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            json_handler.setFormatter(JSONFormatter())
            root_logger.addHandler(json_handler)

        human_handler = RotatingFileHandler(
            os.path.join(log_dir, "xuangu.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        human_handler.setFormatter(HumanFormatter())
        root_logger.addHandler(human_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(HumanFormatter())
        console_handler.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)

    root_logger.info(f"日志系统初始化完成 | 级别={log_level}, 目录={log_dir}")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志记录器"""
    return logging.getLogger(name)


def get_selection_logger() -> SelectionLogger:
    """获取选股流程专用日志记录器"""
    return SelectionLogger()
