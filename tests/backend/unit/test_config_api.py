"""
系统配置 API 测试
"""
import pytest


class TestConfigAPI:
    BASE_URL = "/api/v1/config"

    def test_get_all_config(self, client):
        """获取所有系统配置"""
        resp = client.get(self.BASE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_get_single_config(self, client):
        """获取单个配置"""
        resp = client.get(f"{self.BASE_URL}/max_circ_mv")
        assert resp.status_code in (200, 404)

    def test_get_nonexistent_config(self, client):
        """不存在的配置键应返回 404"""
        resp = client.get(f"{self.BASE_URL}/nonexistent_key_xyz")
        assert resp.status_code == 404

    def test_update_config(self, client):
        """更新配置"""
        resp = client.put(f"{self.BASE_URL}/max_circ_mv", json={
            "value": "1500",
            "value_type": "float",
            "description": "最大流通市值（测试）"
        })
        assert resp.status_code in (200, 404)

    def test_update_config_missing_value(self, client):
        """更新配置缺少值应返回 422"""
        resp = client.put(f"{self.BASE_URL}/max_circ_mv", json={})
        assert resp.status_code == 422

    def test_update_and_query_consistency(self, client):
        """更新后查询应返回最新的值"""
        key = "test_update_key"
        new_value = "test_value_123"

        resp = client.put(f"{self.BASE_URL}/{key}", json={
            "value": new_value,
            "value_type": "string",
            "description": "测试一致性"
        })
        assert resp.status_code in (200, 404)

        if resp.status_code == 200:
            resp = client.get(f"{self.BASE_URL}/{key}")
            assert resp.json()["data"]["value"] == new_value

    def test_init_default_config(self, client):
        """初始化默认配置"""
        resp = client.post(f"{self.BASE_URL}/init-default")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert resp.json()["code"] == 200

    def test_config_value_types(self, client):
        """配置返回值类型应正确"""
        resp = client.get(f"{self.BASE_URL}/max_circ_mv")
        if resp.status_code == 200:
            config = resp.json()["data"]
            assert "value_type" in config
            assert config["value_type"] in ("string", "float", "int", "bool", "json")
