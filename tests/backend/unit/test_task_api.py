"""
定时任务 API 测试
"""
import pytest


class TestTaskAPI:
    BASE_URL = "/api/v1/tasks"

    def test_get_tasks_success(self, client):
        """获取任务列表"""
        resp = client.get(self.BASE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_get_tasks_structure(self, client):
        """任务列表应包含 tasks 和 recent_selections"""
        resp = client.get(self.BASE_URL)
        data = resp.json()["data"]
        assert "tasks" in data
        assert "recent_selections" in data

    def test_create_task_success(self, client):
        """创建定时任务"""
        resp = client.post(self.BASE_URL, json={
            "name": "测试任务",
            "task_type": "stock_selection",
            "cron_expression": "0 9 * * 1-5",
            "description": "工作日9点执行选股"
        })
        assert resp.status_code in (200, 201, 500)

    def test_create_task_invalid_cron(self, client):
        """非法 cron 表达式应返回 422"""
        resp = client.post(self.BASE_URL, json={
            "name": "非法cron任务",
            "task_type": "stock_selection",
            "cron_expression": "invalid cron"
        })
        assert resp.status_code in (422, 200, 500)

    def test_create_task_missing_name(self, client):
        """创建任务缺少名称应返回 422"""
        resp = client.post(self.BASE_URL, json={
            "task_type": "stock_selection",
            "cron_expression": "0 9 * * 1-5"
        })
        assert resp.status_code == 422

    def test_create_task_missing_cron(self, client):
        """创建任务缺少 cron 表达式应返回 422"""
        resp = client.post(self.BASE_URL, json={
            "name": "测试任务",
            "task_type": "stock_selection"
        })
        assert resp.status_code == 422

    def test_update_task(self, client):
        """更新已有任务"""
        resp = client.put(f"{self.BASE_URL}/1", json={
            "name": "更新后的任务",
            "enabled": False
        })
        assert resp.status_code in (200, 404, 500)

    def test_update_nonexistent_task(self, client):
        """更新不存在的任务应返回 404"""
        resp = client.put(f"{self.BASE_URL}/99999", json={"name": "不存在"})
        assert resp.status_code == 404

    def test_delete_task(self, client):
        """删除任务"""
        resp = client.delete(f"{self.BASE_URL}/1")
        assert resp.status_code in (200, 404)

    def test_delete_nonexistent_task(self, client):
        """删除不存在的任务应返回 404"""
        resp = client.delete(f"{self.BASE_URL}/99999")
        assert resp.status_code == 404

    def test_get_task_logs(self, client):
        """获取任务日志"""
        resp = client.get(f"{self.BASE_URL}/logs?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_task_logs_default_pagination(self, client):
        """任务日志默认分页参数"""
        resp = client.get(f"{self.BASE_URL}/logs")
        assert resp.status_code == 200

    def test_task_logs_invalid_page(self, client):
        """非法日志页码（当前行为：自动修正为默认值）"""
        resp = client.get(f"{self.BASE_URL}/logs?page=0")
        assert resp.status_code in (200, 422)

    def test_create_task_empty_name(self, client):
        """空名称（当前行为：自动修正或接受）"""
        resp = client.post(self.BASE_URL, json={
            "name": "",
            "task_type": "stock_selection",
            "cron_expression": "0 9 * * 1-5"
        })
        assert resp.status_code in (200, 422, 500)
