"""
WebSocket 实时推送服务
用于替代轮询，实现真正的实时更新
"""
import asyncio
import json
import logging
from typing import Dict, Set, Any, Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str = "default"):
        """
        接受WebSocket连接

        Args:
            websocket: WebSocket实例
            channel: 频道名称（如：tasks、stocks等）
        """
        await websocket.accept()

        async with self._lock:
            if channel not in self.active_connections:
                self.active_connections[channel] = set()
            self.active_connections[channel].add(websocket)

        logger.info(f"WebSocket连接已建立 | 频道: {channel} | 当前连接数: {len(self.get_connections(channel))}")

    def disconnect(self, websocket: WebSocket, channel: str = "default"):
        """
        断开WebSocket连接

        Args:
            websocket: WebSocket实例
            channel: 频道名称
        """
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)
            if not self.active_connections[channel]:
                del self.active_connections[channel]

        logger.info(f"WebSocket连接已断开 | 频道: {channel}")

    def get_connections(self, channel: str) -> Set[WebSocket]:
        """获取指定频道的所有连接"""
        return self.active_connections.get(channel, set())

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """发送个人消息给指定连接"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"发送个人消息失败: {e}", exc_info=True)

    async def broadcast_to_channel(self, message: dict, channel: str):
        """
        广播消息到指定频道

        Args:
            message: 消息内容（字典格式，会自动转为JSON）
            channel: 目标频道
        """
        connections = self.get_connections(channel)
        if not connections:
            return

        message_json = json.dumps(message, ensure_ascii=False, default=str)
        disconnected = []

        for connection in connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"广播消息失败，移除连接: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn, channel)

        logger.debug(f"广播消息到 {channel}: {len(connections)} 个连接")

    async def broadcast_to_all(self, message: dict):
        """广播消息到所有频道"""
        for channel in list(self.active_connections.keys()):
            await self.broadcast_to_channel(message, channel)


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket端点 - 通用消息通道

    支持的消息类型：
    - subscribe: 订阅频道
    - unsubscribe: 取消订阅
    - ping: 心跳检测
    """
    current_channel = "default"

    try:
        await manager.connect(websocket, current_channel)

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "subscribe":
                    new_channel = message.get("channel", "default")
                    if new_channel != current_channel:
                        manager.disconnect(websocket, current_channel)
                        await manager.connect(websocket, new_channel)
                        current_channel = new_channel
                        await manager.send_personal_message({
                            "type": "subscribed",
                            "channel": current_channel,
                            "timestamp": datetime.now().isoformat(),
                            "message": f"已订阅频道: {current_channel}"
                        }, websocket)

                elif msg_type == "unsubscribe":
                    await manager.send_personal_message({
                        "type": "unsubscribed",
                        "channel": current_channel,
                        "timestamp": datetime.now().isoformat(),
                        "message": f"已取消订阅频道: {current_channel}"
                    }, websocket)
                    manager.disconnect(websocket, current_channel)
                    current_channel = None

                elif msg_type == "ping":
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }, websocket)

                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "message": f"未知消息类型: {msg_type}",
                        "timestamp": datetime.now().isoformat()
                    }, websocket)

            except json.JSONDecodeError:
                await manager.send_personal_message({
                    "type": "error",
                    "message": "无效的JSON格式",
                    "timestamp": datetime.now().isoformat()
                }, websocket)

    except WebSocketDisconnect:
        if current_channel:
            manager.disconnect(websocket, current_channel)
        logger.info("WebSocket客户端断开连接")


def get_connection_stats() -> dict:
    """获取连接统计信息"""
    return {
        "total_channels": len(manager.active_connections),
        "channels": {
            channel: len(connections)
            for channel, connections in manager.active_connections.items()
        },
        "total_connections": sum(
            len(conns) for conns in manager.active_connections.values()
        )
    }


__all__ = [
    'manager',
    'websocket_endpoint',
    'get_connection_stats'
]
