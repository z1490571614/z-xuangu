"""
测试异动解读AI功能
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.anomaly_interpretation import get_anomaly_interpretation

def test_basic():
    """基本功能测试"""
    print("=" * 60)
    print("异动解读AI功能测试")
    print("=" * 60)

    # 测试数据
    ts_code = "002429.SZ"
    stock_name = "兆驰股份"
    trade_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n正在生成异动解读:")
    print(f"  股票代码: {ts_code}")
    print(f"  股票名称: {stock_name}")
    print(f"  交易日期: {trade_date}")
    print()

    # 调用服务
    result = get_anomaly_interpretation(ts_code, stock_name, trade_date, force_refresh=True)

    print("\n" + "=" * 60)
    print("生成结果:")
    print("=" * 60)

    print(f"\n数据状态: {result.get('data_status', 'N/A')}")

    # 打印新版同花顺格式
    if result.get("core_tags_line"):
        print(f"\n核心标签: {result['core_tags_line']}")

        if result.get("industry_reason"):
            print(f"\n行业原因:\n{result['industry_reason']}")

        company_reasons = result.get("company_reasons", [])
        if company_reasons:
            print(f"\n公司原因:")
            for reason in company_reasons:
                print(f"  {reason}")

        if result.get("market_background"):
            print(f"\n行情背景: {result['market_background']}")

        print(f"\n免责声明: {result.get('disclaimer', '')}")
    else:
        # 旧版兼容
        print(f"标题: {result.get('summary_title', 'N/A')}")
        print(f"内容: {result.get('summary_text', 'N/A')}")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    test_basic()
