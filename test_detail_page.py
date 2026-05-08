"""
个股详情页完整功能测试
测试所有前端调用的API接口
用法: conda activate xuangu && python test_detail_page.py
"""
import os, sys, json, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env', override=True)

import requests

BASE = "http://127.0.0.1:9999/api/v1"
STOCK_CODE = "605006.SH"  # 山东玻纤
STOCK_NAME = "山东玻纤"
TRADE_DATE = "20260430"
RECORD_ID = 2

results = {"pass": 0, "fail": 0, "tests": []}

def test(name, url, expected_code=200, max_ms=None):
    full_url = url if url.startswith("http") else f"{BASE}{url}"
    start = time.time()
    try:
        r = requests.get(full_url, timeout=30)
        elapsed = (time.time() - start) * 1000
        ok = r.status_code == expected_code
        msg = f"HTTP {r.status_code}"
        if max_ms and elapsed > max_ms:
            ok = False
            msg += f" ({elapsed:.0f}ms, 超过{max_ms}ms限制)"
        else:
            msg += f" ({elapsed:.0f}ms)"
        
        # 检查返回格式
        data = r.json()
        if data.get("code") is not None:
            msg += f" | api_code={data['code']} msg={str(data.get('message',''))[:40]}"
        
        if ok:
            results["pass"] += 1
            results["tests"].append(f"  [OK] {name:30s} {msg}")
        else:
            results["fail"] += 1
            results["tests"].append(f"  [FAIL] {name:30s} {msg}")
    except Exception as e:
        results["fail"] += 1
        results["tests"].append(f"  [FAIL] {name:30s} ERROR: {e}")

def test_post(name, url, body, expected_code=200, max_ms=None):
    full_url = url if url.startswith("http") else f"{BASE}{url}"
    start = time.time()
    try:
        r = requests.post(full_url, json=body, timeout=30)
        elapsed = (time.time() - start) * 1000
        ok = r.status_code == expected_code
        msg = f"HTTP {r.status_code} ({elapsed:.0f}ms)"
        if ok:
            results["pass"] += 1
            results["tests"].append(f"  [OK] {name:30s} {msg}")
        else:
            results["fail"] += 1
            results["tests"].append(f"  [FAIL] {name:30s} {msg}")
    except Exception as e:
        results["fail"] += 1
        results["tests"].append(f"  [FAIL] {name:30s} ERROR: {e}")

# ========== 1. 基础服务 ==========
print("\n=== 基础服务 ===")
test("健康检查", "/health")
test("交易日查询", f"/stock/trading-date")
test("调度器状态", "/scheduler/status")
test("新闻数据库统计", "/stock/news-v2/db-stats")

# ========== 2. 个股详情 ==========
print("\n=== 个股详情 ===")
test("综合详情", f"/stock/detail?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}", max_ms=30000)
test("综合详情(缓存)", f"/stock/detail?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}", max_ms=500)

# ========== 3. 批量预加载 ==========
print("\n=== 批量预加载 ===")
test_post("批量详情", f"/stock/detail/batch", [{"ts_code": STOCK_CODE, "stock_name": STOCK_NAME, "record_id": RECORD_ID}], max_ms=30000)
test("缓存统计", "/stock/detail/cache/stats")

# ========== 4. AI预加载 ==========
print("\n=== AI预加载 ===")
test_post("批量AI预热", "/stock/detail/preload-ai", [{"ts_code": STOCK_CODE, "stock_name": STOCK_NAME, "trade_date": TRADE_DATE, "record_id": RECORD_ID}])

# ========== 4. 新闻舆情 ==========
print("\n=== 新闻舆情 ===")
test("新闻V2", f"/stock/news-v2?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}&ensure_recent=False", max_ms=15000)

# ========== 5. 评分V2 ==========
print("\n=== 评分V2 ===")
test("评分V2详情", f"/score-v2/detail?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}", max_ms=15000)

# ========== 6. 综合概览 ==========
print("\n=== 综合概览 ===")
test("综合概览", f"/stock/overview-brief?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}", max_ms=60000)

# ========== 7. 异动解读 ==========
print("\n=== 异动解读 ===")
test("异动解读", f"/stock/anomaly-interpretation?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}", max_ms=60000)
test("异动解读(强制刷新)", f"/stock/anomaly-interpretation?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}&force_refresh=true", max_ms=60000)

# ========== 8. 龙虎榜 ==========
print("\n=== 龙虎榜 ===")
test("龙虎榜详情", f"/stock/detail/lhb?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}", max_ms=30000)

# ========== 9. 风险拆解 ==========
print("\n=== 风险拆解 ===")
test("风险拆解详情", f"/stock/detail/risk?ts_code={STOCK_CODE}&stock_name={STOCK_NAME}&trade_date={TRADE_DATE}&record_id={RECORD_ID}", max_ms=30000)

# ========== 10. 选股结果列表 ==========
print("\n=== 选股结果 ===")
test("选股结果列表", f"/stock/results?page=1&page_size=10")
test("选股结果详情", f"/stock/results/{RECORD_ID}")
test("选股结果详情(第3条)", f"/stock/results/3")

# ========== 汇总 ==========
print(f"\n{'='*50}")
print(f"测试完成: 通过 {results['pass']} / 总数 {results['pass'] + results['fail']}")
print(f"{'='*50}")

# 写入文件
with open("test_report.txt", "w", encoding="utf-8") as f:
    for t in results["tests"]:
        f.write(t + "\n")
    f.write(f"\n总计: 通过 {results['pass']} / 失败 {results['fail']}\n")

for t in results["tests"]:
    print(t)
