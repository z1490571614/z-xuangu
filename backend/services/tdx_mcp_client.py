"""
通达信MCP HTTP客户端（带会话管理）

通过HTTP协议调用通达信MCP服务器，支持会话管理和环境变量配置
"""

import os
import time
import json
import logging
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class McpSession:
    """MCP会话信息"""
    session_id: str
    created_at: float
    last_activity: float
    expires_at: Optional[float] = None


class TdxMcpSessionManager:
    """MCP会话管理器（每次选股使用新会话，无需心跳）"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        session_timeout: int = 3600,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.session_timeout = session_timeout

        self._session: Optional[McpSession] = None
        self._lock = threading.Lock()

        logger.info(f"✅ MCP会话管理器初始化成功")

    def create_session(self) -> McpSession:
        """
        创建新的MCP会话

        Returns:
            会话信息

        Raises:
            RuntimeError: 会话创建失败
        """
        logger.info("🔄 创建新的MCP会话...")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "tdx-api-key": self.api_key,
        }

        payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "xuangu-stock-selector",
                    "version": "2.0.0"
                }
            },
            "id": 1
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                )

                response.raise_for_status()

                session_id = response.headers.get("mcp-session-id")

                if not session_id:
                    response_text = response.text

                    if response_text.startswith("event:"):
                        lines = response_text.strip().split('\n')
                        for line in lines:
                            if line.startswith("data:"):
                                data_str = line[5:].strip()
                                result = json.loads(data_str)
                                session_id = result.get("result", {}).get("sessionId")
                                break

                if not session_id:
                    session_id = f"session-{int(time.time())}"

                current_time = time.time()
                session = McpSession(
                    session_id=session_id,
                    created_at=current_time,
                    last_activity=current_time,
                    expires_at=current_time + self.session_timeout,
                )

                logger.info(f"✅ MCP会话创建成功: session_id={session_id}")
                return session

        except Exception as e:
            logger.error(f"❌ MCP会话创建失败: {e}")
            raise RuntimeError(f"无法创建MCP会话: {e}")

    def get_session(self) -> McpSession:
        """获取有效会话（过期自动重建）"""
        with self._lock:
            current_time = time.time()
            if self._session is None or self._session.expires_at < current_time:
                logger.info("会话不存在或已过期，创建新会话")
                self._session = self.create_session()
            self._session.last_activity = current_time
            return self._session

    def invalidate_session(self):
        """使当前会话失效（下次查询时重建）"""
        with self._lock:
            self._session = None
            logger.debug("MCP会话已失效")

    def close(self):
        """关闭会话管理器"""
        self._session = None
        logger.info("MCP会话管理器已关闭")


class TdxMcpHttpClient:
    """通达信MCP HTTP客户端（带会话管理）"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        enable_session: bool = True,
    ):
        """
        初始化MCP客户端

        Args:
            base_url: MCP服务器地址，默认从环境变量读取
            api_key: API密钥，默认从环境变量读取
            timeout: 请求超时时间（秒）
            enable_session: 是否启用会话管理
        """
        self.base_url = base_url or os.getenv("TDX_MCP_URL", "")
        self.api_key = api_key or os.getenv("TDX_MCP_API_KEY", "")
        self.timeout = timeout
        self.enable_session = enable_session

        if not self.base_url:
            raise ValueError(
                "MCP服务器地址未配置。请设置环境变量 TDX_MCP_URL 或在初始化时传入 base_url 参数。"
            )

        if not self.api_key:
            logger.warning("⚠️  MCP API密钥未配置，可能导致认证失败")

        self._session_manager: Optional[TdxMcpSessionManager] = None

        if self.enable_session:
            self._session_manager = TdxMcpSessionManager(
                base_url=self.base_url,
                api_key=self.api_key,
            )

        logger.info(f"✅ MCP客户端初始化成功: {self.base_url} (会话管理={'启用' if enable_session else '禁用'})")

    def query(
        self,
        question: str,
        range: str = "AG",
        size: str = "20",
        page: str = "1",
    ) -> Dict[str, Any]:
        """
        执行通达信查询

        Args:
            question: 自然语言查询语句
            range: 市场范围 (AG=A股, HK-GP=港股, JJ=基金, ZS=指数)
            size: 每页数量
            page: 页码

        Returns:
            查询结果字典

        Raises:
            httpx.HTTPError: HTTP请求失败
            ValueError: 参数错误
        """
        if not question:
            raise ValueError("查询语句不能为空")

        logger.info(f"🔍 MCP查询: {question[:60]}... (range={range}, size={size})")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        if self.api_key:
            headers["tdx-api-key"] = self.api_key

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "tdx_wenda_quotes",
                "arguments": {
                    "question": question,
                    "range": range,
                    "size": size,
                    "page": page,
                }
            },
            "id": int(time.time())
        }

        if self._session_manager:
            session = self._session_manager.get_session()
            headers["mcp-session-id"] = session.session_id
            logger.debug(f"使用会话: session_id={session.session_id}")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                )

                response.raise_for_status()

                response_text = response.text

                if response_text.startswith("event:"):
                    lines = response_text.strip().split('\n')
                    for line in lines:
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            rpc_result = json.loads(data_str)
                            break
                    else:
                        rpc_result = {"result": {"content": [{"text": "{}"}]}}
                else:
                    rpc_result = response.json()

                if "error" in rpc_result:
                    error_msg = rpc_result.get("error", {}).get("message", "未知错误")
                    logger.error(f"❌ MCP查询失败: {error_msg}")

                    if "session" in error_msg.lower():
                        logger.info("会话可能已失效，尝试重新创建...")
                        if self._session_manager:
                            self._session_manager._session = None
                            return self.query(question, range, size, page)

                    raise RuntimeError(f"MCP查询失败: {error_msg}")

                content = rpc_result.get("result", {}).get("content", [])
                if content and len(content) > 0:
                    text_content = content[0].get("text", "{}")
                    if text_content and text_content.strip():
                        try:
                            result = json.loads(text_content)
                        except json.JSONDecodeError:
                            logger.warning(f"MCP返回数据格式错误，返回空结果")
                            result = {"meta": {"code": 0, "total": 0}, "data": []}
                    else:
                        logger.warning("MCP返回空内容")
                        result = {"meta": {"code": 0, "total": 0}, "data": []}
                else:
                    result = {"meta": {"code": 0, "total": 0}, "data": []}

                total = result.get("meta", {}).get("total", 0)
                logger.info(f"✅ MCP查询成功: 返回 {total} 条记录")

                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ MCP查询失败: HTTP {e.response.status_code}")
            logger.error(f"   响应内容: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ MCP请求失败: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ MCP查询未知错误: {e}", exc_info=True)
            raise

    def close(self):
        """关闭客户端"""
        if self._session_manager:
            self._session_manager.close()
        logger.info("MCP客户端已关闭")


_global_client: Optional[TdxMcpHttpClient] = None


def create_mcp_client() -> Optional[TdxMcpHttpClient]:
    """
    创建MCP客户端实例（单例模式）

    Returns:
        MCP客户端实例，如果未配置则返回None
    """
    global _global_client

    mcp_enabled = os.getenv("TDX_MCP_ENABLED", "false").lower() == "true"

    if not mcp_enabled:
        logger.info("ℹ️  MCP服务未启用 (TDX_MCP_ENABLED=false)")
        return None

    if _global_client is not None:
        return _global_client

    try:
        _global_client = TdxMcpHttpClient()
        return _global_client
    except ValueError as e:
        logger.warning(f"⚠️  MCP客户端创建失败: {e}")
        return None


def mcp_query_wrapper(question: str, range: str = "AG", size: str = "20") -> dict:
    """
    MCP查询包装函数（兼容原有接口）

    Args:
        question: 查询语句
        range: 市场范围
        size: 返回数量

    Returns:
        查询结果字典
    """
    client = create_mcp_client()

    if client is None:
        raise RuntimeError("MCP服务不可用，请检查配置")

    return client.query(question=question, range=range, size=size)
