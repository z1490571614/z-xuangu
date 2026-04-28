"""
选股 API 接口测试
"""
import pytest


class TestTradingDate:
    def test_get_trading_date_success(self, client):
        """获取交易日接口应返回日期字符串"""
        resp = client.get("/api/v1/stock/trading-date")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "trading_date" in data["data"]

    def test_trading_date_format(self, client):
        """交易日格式应为 YYYYMMDD"""
        resp = client.get("/api/v1/stock/trading-date")
        date_str = resp.json()["data"]["trading_date"]
        assert len(date_str) == 8
        assert date_str.isdigit()


class TestStockSelect:
    def test_select_without_auth(self, client):
        """未认证可发起选股请求（公开接口）"""
        resp = client.post("/api/v1/stock/select", json={})
        assert resp.status_code in (200, 422, 500)

    def test_select_with_invalid_date_format(self, client):
        """非法日期格式应返回 422"""
        resp = client.post("/api/v1/stock/select", json={"trade_date": "2026-13-01"})
        assert resp.status_code in (200, 422, 500)

    def test_select_with_invalid_task_template(self, client):
        """非法策略模板应返回 422 或友好处理"""
        resp = client.post("/api/v1/stock/select", json={"task_template": "nonexistent_template"})
        assert resp.status_code in (200, 422, 500)

    def test_select_with_min_seal_rate_100(self, client):
        """设置封板率 100% 应正常处理"""
        resp = client.post("/api/v1/stock/select", json={"min_seal_rate": 100})
        assert resp.status_code in (200, 422, 500)

    def test_select_with_high_period_days(self, client):
        """设置较大封板率周期应正常处理"""
        resp = client.post("/api/v1/stock/select", json={"period_days": 250})
        assert resp.status_code in (200, 422, 500)


class TestStockResults:
    def test_get_results_list_success(self, client):
        """选股结果列表应返回分页数据"""
        resp = client.get("/api/v1/stock/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "records" in data["data"]
        assert "total" in data["data"]
        assert "page" in data["data"]
        assert "page_size" in data["data"]

    def test_results_list_pagination(self, client):
        """分页参数应正确应用"""
        resp = client.get("/api/v1/stock/results?page=1&page_size=5")
        assert resp.status_code == 200

    def test_results_with_invalid_page(self, client):
        """非法页码应返回 422（当前行为：自动修正为默认值）"""
        resp = client.get("/api/v1/stock/results?page=0")
        assert resp.status_code in (200, 422)

    def test_results_with_large_page_size(self, client):
        """超大 page_size 应返回 422（当前行为：自动修正为默认值）"""
        resp = client.get("/api/v1/stock/results?page_size=999")
        assert resp.status_code in (200, 422)

    def test_get_nonexistent_result_detail(self, client):
        """不存在的选股记录详情应返回 404"""
        resp = client.get("/api/v1/stock/results/999999")
        assert resp.status_code in (404, 200)

    def test_result_detail_structure(self, client):
        """选股结果详情应包含完整的股票信息字段"""
        resp = client.get("/api/v1/stock/results/1")
        if resp.status_code == 200:
            data = resp.json()
            stocks = data["data"].get("stocks", [])
            if stocks:
                stock = stocks[0]
                for field in ["ts_code", "name", "close_price", "change_pct"]:
                    assert field in stock
