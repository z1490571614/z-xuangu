"""调试API返回格式"""
import requests
import json

BASE_URL = "http://localhost:9999/api/v1"

payload = {
    "trade_date": None,
    "notify": False,
    "task_template": "default",
    "save_result": False
}

response = requests.post(
    f"{BASE_URL}/stock/select",
    json=payload,
    timeout=60
)

print(f"状态码: {response.status_code}")
print(f"\n完整响应:")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
