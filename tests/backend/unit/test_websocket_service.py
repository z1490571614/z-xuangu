import json

import pytest
from fastapi import WebSocketDisconnect

from backend.services.websocket_service import manager, websocket_endpoint


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.accept_calls = 0
        self.sent_json = []

    async def accept(self):
        self.accept_calls += 1
        if self.accept_calls > 1:
            raise RuntimeError("websocket.accept called twice")

    async def receive_text(self):
        if not self.messages:
            raise WebSocketDisconnect()
        return self.messages.pop(0)

    async def send_json(self, message):
        self.sent_json.append(message)


@pytest.mark.asyncio
async def test_subscribe_switches_channel_without_accepting_websocket_twice():
    manager.active_connections.clear()
    websocket = FakeWebSocket(
        [
            json.dumps({"type": "subscribe", "channel": "tasks"}),
        ]
    )

    await websocket_endpoint(websocket)

    assert websocket.accept_calls == 1
    assert websocket.sent_json[-1]["type"] == "subscribed"
    assert websocket.sent_json[-1]["channel"] == "tasks"
    assert websocket not in manager.get_connections("default")
    assert websocket not in manager.get_connections("tasks")
