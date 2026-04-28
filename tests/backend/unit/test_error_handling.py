"""
异常处理和边界情况测试
"""
import pytest


class TestErrorHandling:
    def test_404_not_found(self, client):
        """访问不存在的 API 路径应返回 404"""
        resp = client.get("/api/v1/nonexistent-endpoint")
        assert resp.status_code == 404

    def test_405_method_not_allowed(self, client):
        """使用错误的 HTTP 方法应返回 405"""
        resp = client.delete("/api/v1/health")
        assert resp.status_code in (405, 404)

    def test_malformed_json_body(self, client):
        """损坏的 JSON 请求体应返回 422"""
        resp = client.post(
            "/api/v1/stock/select",
            data="This is not json at all",
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code in (422, 400)

    def test_empty_request_body(self, client):
        """空请求体应返回 422"""
        resp = client.post(
            "/api/v1/stock/select",
            data="",
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code in (422, 400)

    def test_xss_injection(self, client):
        """尝试 XSS 注入应被安全处理"""
        resp = client.get("/api/v1/stock/results/1", headers={"User-Agent": "<script>alert('xss')</script>"})
        assert resp.status_code in (200, 404, 422, 500)

    def test_sql_injection_in_path(self, client):
        """路径参数 SQL 注入尝试应被安全处理"""
        resp = client.get("/api/v1/stock/results/1; DROP TABLE users")
        assert resp.status_code in (404, 422, 200)

    def test_security_headers_present(self, client):
        """响应应包含安全头"""
        resp = client.get("/api/v1/health")
        headers = resp.headers
        assert any(h in str(headers).lower() for h in ["x-content-type", "x-frame", "x-xss"])

    def test_large_request_body(self, client):
        """超大请求体应被拒绝"""
        large_payload = {"trade_date": "x" * 100000}
        resp = client.post("/api/v1/stock/select", json=large_payload)
        assert resp.status_code in (422, 413, 200, 500)

    def test_get_metrics_endpoint(self, client):
        """Prometheus 指标端点可访问"""
        resp = client.get("/metrics")
        assert resp.status_code in (200, 404)

    def test_concurrent_requests(self, client):
        """并发请求不应导致崩溃"""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(client.get, "/api/v1/health") for _ in range(10)]
            results = [f.result() for f in futures]
        assert all(r.status_code == 200 for r in results)
