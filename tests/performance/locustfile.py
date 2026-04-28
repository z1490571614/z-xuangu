"""
Locust 性能测试脚本
"""
from locust import HttpUser, task, between
import random


class StockSelectorUser(HttpUser):
    wait_time = between(1, 3)

    @task(5)
    def health_check(self):
        self.client.get("/api/v1/health", name="/health")

    @task(3)
    def view_stock_results(self):
        page = random.randint(1, 5)
        page_size = random.choice([10, 20, 50])
        self.client.get(
            f"/api/v1/stock/results?page={page}&page_size={page_size}",
            name="/stock/results"
        )

    @task(2)
    def view_tasks(self):
        self.client.get("/api/v1/tasks", name="/tasks")

    @task(2)
    def view_config(self):
        self.client.get("/api/v1/config", name="/config")

    @task(1)
    def trigger_selection(self):
        self.client.post(
            "/api/v1/stock/select",
            json={"trade_date": "20240115", "notify": False},
            name="/stock/select"
        )

    @task(1)
    def view_metrics(self):
        self.client.get("/metrics", name="/metrics")


class AdminUser(HttpUser):
    wait_time = between(5, 10)

    @task(3)
    def health_check(self):
        self.client.get("/api/v1/health", name="/health-admin")

    @task(2)
    def view_stock_results(self):
        self.client.get("/api/v1/stock/results", name="/stock/results-admin")

    @task(1)
    def view_tasks(self):
        self.client.get("/api/v1/tasks", name="/tasks-admin")
