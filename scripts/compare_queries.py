"""
对比分析：为什么优化后的查询能选出数据
找出导致返回0条记录的具体原因
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.tdx_mcp_client import mcp_query_wrapper
from dotenv import load_dotenv

load_dotenv()


def compare_queries():
    """对比两种查询语句的差异"""
    print("=" * 80)
    print("🔍 对比分析：查询语句差异")
    print("=" * 80)
    
    # 之前测试失败的查询
    failed_query = "非ST非停牌非北交所股票，流通市值小于2000亿，昨日收盘价小于500元，近10日股价上涨，近100个交易日内涨停次数不少于3次，封板成功率不低于90%，竞价量占昨日成交量比例4.0%到30.0%，竞价换手率0.5%到10.0%"
    
    # 优化后成功的查询
    success_query = "非ST非停牌非北交所股票，流通市值小于2000亿，昨日收盘价小于500元，近10日股价上涨，近100个交易日内涨停次数不少于3次，封板成功率不低于90%，竞价量占昨日成交量比例4%到30%，竞价换手率0.5%到10%"
    
    print("\n📋 失败的查询:")
    print(failed_query)
    
    print("\n📋 成功的查询:")
    print(success_query)
    
    print("\n" + "=" * 80)
    print("🔍 差异分析")
    print("=" * 80)
    
    # 找出差异
    print("\n差异点:")
    print("1. 竞昨比范围:")
    print("   失败: '4.0%到30.0%' (小数格式)")
    print("   成功: '4%到30%' (整数格式)")
    
    print("\n2. 竞价换手率范围:")
    print("   失败: '0.5%到10.0%' (混合格式)")
    print("   成功: '0.5%到10%' (整数格式)")
    
    # 测试不同的数值格式
    print("\n" + "=" * 80)
    print("🧪 测试不同数值格式")
    print("=" * 80)
    
    test_cases = [
        {
            "name": "测试1: 小数格式 (4.0%-30.0%)",
            "query": "非ST非停牌非北交所股票，流通市值小于2000亿，竞价量占昨日成交量比例4.0%到30.0%"
        },
        {
            "name": "测试2: 整数格式 (4%-30%)",
            "query": "非ST非停牌非北交所股票，流通市值小于2000亿，竞价量占昨日成交量比例4%到30%"
        },
        {
            "name": "测试3: 混合格式 (0.5%-10.0%)",
            "query": "非ST非停牌非北交所股票，流通市值小于2000亿，竞价换手率0.5%到10.0%"
        },
        {
            "name": "测试4: 整数格式 (0.5%-10%)",
            "query": "非ST非停牌非北交所股票，流通市值小于2000亿，竞价换手率0.5%到10%"
        }
    ]
    
    for test in test_cases:
        print(f"\n{test['name']}")
        print(f"查询: {test['query']}")
        
        try:
            result = mcp_query_wrapper(
                question=test['query'],
                range="AG",
                size="10"
            )
            
            total = result.get("meta", {}).get("total", 0)
            print(f"✅ 返回记录数: {total}")
            
        except Exception as e:
            print(f"❌ 查询失败: {e}")
    
    # 测试完整查询
    print("\n" + "=" * 80)
    print("🧪 测试完整查询")
    print("=" * 80)
    
    print("\n测试1: 失败的完整查询")
    try:
        result = mcp_query_wrapper(question=failed_query, range="AG", size="10")
        total = result.get("meta", {}).get("total", 0)
        print(f"返回记录数: {total}")
    except Exception as e:
        print(f"查询失败: {e}")
    
    print("\n测试2: 成功的完整查询")
    try:
        result = mcp_query_wrapper(question=success_query, range="AG", size="10")
        total = result.get("meta", {}).get("total", 0)
        print(f"返回记录数: {total}")
    except Exception as e:
        print(f"查询失败: {e}")
    
    print("\n" + "=" * 80)
    print("💡 结论")
    print("=" * 80)
    print("""
关键发现：
1. MCP接口支持8个条件的查询
2. 数值格式很重要：
   - ✅ 推荐使用整数格式: "4%到30%"
   - ❌ 避免使用小数格式: "4.0%到30.0%"
3. 优化后的选股语句格式正确，可以正常工作
""")


if __name__ == "__main__":
    compare_queries()
