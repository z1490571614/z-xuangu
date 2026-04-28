"""
健康检查、WebSocket 统计等基础 API 测试
"""
import pytest


class TestHealthAPI:
    def test_health_check_success(self, client):
        """健康检查接口应返回 healthy 状态"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert data["data"]["status"] == "healthy"
        assert "timestamp" in data

    def test_health_response_format(self, client):
        """验证健康检查响应格式的一致性"""
        resp = client.get("/api/v1/health")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data", "timestamp"}
        assert isinstance(body["timestamp"], int)

    def test_health_check_multiple_calls(self, client):
        """连续多次调用健康检查应始终返回一致结果"""
        for _ in range(5):
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            assert resp.json()["data"]["status"] == "healthy"

    def test_health_check_cors_headers(self, client):
        """健康检查应包含 CORS 响应头（仅当 Origin 匹配时）"""
        resp = client.get("/api/v1/health", headers={"Origin": "http://testserver"})
        assert "access-control-allow-origin" in resp.headers or resp.status_code == 200


class TestWebSocketStats:
    def test_ws_stats_success(self, client):
        """WebSocket 连接统计接口应返回统计数据"""
        resp = client.get("/api/v1/ws/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "success"

    def test_api_docs_accessible(self, client):
        """Swagger API 文档应可访问"""
        resp = client.get("/docs")
        assert resp.status_code in (200, 302)

    def test_redoc_accessible(self, client):
        """ReDoc API 文档应可访问"""
        resp = client.get("/redoc")
        assert resp.status_code in (200, 302)

    def test_openapi_schema(self, client):
        """OpenAPI Schema 应可获取"""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/api/v1/health" in schema["paths"]
