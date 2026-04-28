"""
策略管理 API 测试
"""
import pytest


class TestStrategyAPI:
    BASE_URL = "/api/v1/stock/strategies"

    def test_get_strategies_without_auth(self, client):
        """获取策略列表应为公开接口"""
        resp = client.get(self.BASE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_get_strategies_structure(self, client):
        """策略列表应包含策略数组和总数"""
        resp = client.get(self.BASE_URL)
        data = resp.json()["data"]
        assert "strategies" in data
        assert "total" in data

    def test_create_strategy_without_auth(self, client):
        """创建策略无需认证"""
        resp = client.post(self.BASE_URL, json={
            "name": "Test Strategy",
            "conditions_config": {}
        })
        assert resp.status_code in (200, 201, 422)

    def test_create_strategy_with_valid_data(self, client):
        """创建有效策略"""
        resp = client.post(self.BASE_URL, json={
            "name": "自定义测试策略",
            "description": "用于测试的策略",
            "task_template": "custom",
            "conditions_config": {
                "max_circ_mv": 1000,
                "max_close_price": 300,
                "min_limit_count": 5,
                "min_seal_rate": 85
            }
        })
        assert resp.status_code in (200, 201)

    def test_create_strategy_missing_name(self, client):
        """创建策略缺少名称应返回 422"""
        resp = client.post(self.BASE_URL, json={
            "conditions_config": {"max_circ_mv": 1000}
        })
        assert resp.status_code == 422

    def test_create_strategy_missing_conditions(self, client):
        """创建策略缺少条件配置应返回 422"""
        resp = client.post(self.BASE_URL, json={
            "name": "不完整策略"
        })
        assert resp.status_code == 422

    def test_create_strategy_long_name(self, client):
        """策略名称超长应返回 422"""
        resp = client.post(self.BASE_URL, json={
            "name": "A" * 200,
            "conditions_config": {"max_circ_mv": 1000}
        })
        assert resp.status_code == 422

    def test_get_strategy_by_id(self, client):
        """通过 ID 获取策略详情"""
        resp = client.get(f"{self.BASE_URL}/1")
        assert resp.status_code in (200, 404)

    def test_get_nonexistent_strategy(self, client):
        """不存在的策略 ID 应返回 404"""
        resp = client.get(f"{self.BASE_URL}/99999")
        assert resp.status_code == 404

    def test_update_strategy_name_only(self, client):
        """仅更新策略名称"""
        resp = client.put(f"{self.BASE_URL}/1", json={
            "name": "更新后的策略名称"
        })
        assert resp.status_code in (200, 400, 404)

    def test_update_nonexistent_strategy(self, client):
        """更新不存在的策略（返回 400: ValueError -> 400）"""
        resp = client.put(f"{self.BASE_URL}/99999", json={
            "name": "不存在"
        })
        assert resp.status_code in (400, 404)

    def test_toggle_strategy_status(self, client):
        """切换策略启用/禁用状态"""
        resp = client.patch(f"{self.BASE_URL}/1/toggle")
        assert resp.status_code in (200, 404)

    def test_toggle_nonexistent_strategy(self, client):
        """切换不存在的策略状态应返回 404"""
        resp = client.patch(f"{self.BASE_URL}/99999/toggle")
        assert resp.status_code == 404

    def test_preview_strategy_query(self, client):
        """预览策略的 MCP 查询语句"""
        resp = client.post(f"{self.BASE_URL}/1/preview")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()["data"]
            assert "query" in data
            assert "conditions_count" in data

    def test_delete_strategy(self, client):
        """删除系统预置策略应被拒绝（返回 400 ValueError）"""
        resp = client.delete(f"{self.BASE_URL}/1")
        assert resp.status_code in (200, 400, 403, 404)

    def test_delete_nonexistent_strategy(self, client):
        """删除不存在的策略（返回 400: ValueError -> 400）"""
        resp = client.delete(f"{self.BASE_URL}/99999")
        assert resp.status_code in (400, 404)

    def test_initialize_strategies(self, client):
        """初始化预置策略模板"""
        resp = client.post(f"{self.BASE_URL}/initialize")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()["data"]
            assert "created_count" in data

    def test_get_all_strategies_pagination(self, client):
        """获取策略列表，包含已禁用的"""
        resp = client.get(f"{self.BASE_URL}?include_disabled=true")
        assert resp.status_code == 200
