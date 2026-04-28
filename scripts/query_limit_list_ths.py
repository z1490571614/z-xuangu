"""
使用 tushare limit_list_ths 查询股票近一年涨停封板率
"""
import os
import sys
import requests
import pandas as pd
from dotenv import load_dotenv

# 添加项目路径
sys.path.insert(0, '/vol1/1000/docker/xuangu')

# 加载环境变量
load_dotenv('/vol1/1000/docker/xuangu/.env')

import tushare as ts

BASE_URL = "http://localhost:9999/api/v1"

def get_stocks_from_selection():
    """从选股API获取股票列表"""
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
    
    if response.status_code == 200:
        result = response.json()
        return result["stocks"]
    return None

def query_limit_list_ths(ts_codes):
    """
    使用 limit_list_ths 查询股票近一年涨停封板率
    
    Args:
        ts_codes: 股票代码列表
    
    Returns:
        包含封板率数据的列表
    """
    token = os.getenv("TUSHARE_TOKEN")
    ts.set_token(token)
    pro = ts.pro_api()
    
    all_results = []
    
    for ts_code in ts_codes:
        print(f"查询 {ts_code}...", end='', flush=True)
        
        try:
            df = pro.limit_list_ths(ts_code=ts_code)
            
            if df is not None and len(df) > 0:
                # 获取最新记录中的封板率
                latest = df.iloc[0]
                seal_rate = latest.get('limit_up_suc_rate')
                
                # 获取涨停次数
                limit_count = len(df)
                
                # 统计打开次数
                open_count = df['open_num'].sum() if 'open_num' in df.columns else 0
                
                result = {
                    'ts_code': ts_code,
                    'name': latest.get('name', ''),
                    'limit_up_suc_rate': seal_rate,
                    'limit_count': limit_count,
                    'open_count': open_count
                }
                all_results.append(result)
                
                rate_display = f"{seal_rate*100:.1f}%" if seal_rate is not None else "N/A"
                print(f" ✅ 封板率: {rate_display}, 涨停 {limit_count} 次")
            else:
                all_results.append({
                    'ts_code': ts_code,
                    'name': '',
                    'limit_up_suc_rate': None,
                    'limit_count': 0,
                    'open_count': 0
                })
                print(" ⚠️ 无数据")
                
        except Exception as e:
            print(f" ❌ 错误: {e}")
            all_results.append({
                'ts_code': ts_code,
                'name': '',
                'limit_up_suc_rate': None,
                'limit_count': 0,
                'open_count': 0
            })
    
    return all_results

def main():
    print('='*80)
    print('📊 使用 tushare limit_list_ths 查询近一年涨停封板率')
    print('='*80)
    
    # 1. 获取股票列表
    print("\n📋 从选股API获取股票列表...")
    stocks = get_stocks_from_selection()
    
    if not stocks:
        print("❌ 无法获取股票列表")
        return
    
    ts_codes = [s['ts_code'] for s in stocks]
    print(f"✅ 共 {len(ts_codes)} 只股票")
    
    # 2. 查询封板率
    print("\n🔍 开始查询 limit_list_ths...")
    print('-'*80)
    
    results = query_limit_list_ths(ts_codes)
    
    # 3. 合并数据并输出
    print("\n" + '='*80)
    print("📈 最终结果（按近一年封板率排序）")
    print('='*80)
    
    # 创建股票信息字典
    stock_info = {s['ts_code']: s for s in stocks}
    
    # 合并结果
    merged_data = []
    for data in results:
        ts_code = data['ts_code']
        info = stock_info.get(ts_code, {})
        
        merged_data.append({
            'ts_code': ts_code,
            'name': data['name'] or info.get('name', ''),
            'close_price': info.get('close_price', 0),
            'change_pct': info.get('change_pct', 0),
            'limit_up_suc_rate': data['limit_up_suc_rate'],
            'limit_count': data['limit_count'],
            'open_count': data['open_count']
        })
    
    # 按封板率排序
    merged_data.sort(key=lambda x: (x['limit_up_suc_rate'] or 0), reverse=True)
    
    # 输出表格
    print(f"\n{'排名':<6} {'股票代码':<12} {'名称':<10} {'现价':<8} {'涨幅':<8} {'近一年封板率':<12} {'涨停次数':<8} {'打开次数':<8}")
    print('-'*80)
    
    for i, data in enumerate(merged_data):
        rate = data['limit_up_suc_rate']
        rate_display = f"{rate*100:.1f}%" if rate is not None else 'N/A'
        print(f"{i+1:<6} {data['ts_code']:<12} {data['name']:<10} {data['close_price']:<8.2f} {data['change_pct']:<8.2f} {rate_display:<12} {data['limit_count']:<8} {data['open_count']:<8}")
    
    print('-'*80)
    
    # 统计
    print("\n📊 统计摘要:")
    valid_rates = [d['limit_up_suc_rate'] for d in merged_data if d['limit_up_suc_rate'] is not None]
    if valid_rates:
        avg_rate = sum(valid_rates) / len(valid_rates)
        print(f"  平均封板率: {avg_rate*100:.1f}%")
        
        high_rate = [d for d in merged_data if d['limit_up_suc_rate'] and d['limit_up_suc_rate'] >= 0.8]
        print(f"  封板率≥80%: {len(high_rate)}只")
        
        medium_rate = [d for d in merged_data if d['limit_up_suc_rate'] and 0.5 <= d['limit_up_suc_rate'] < 0.8]
        print(f"  50%≤封板率<80%: {len(medium_rate)}只")
        
        # 总涨停次数
        total_limit = sum(d['limit_count'] for d in merged_data)
        print(f"  总涨停次数: {total_limit}次")
    
    print("\n✅ 查询完成")

if __name__ == '__main__':
    main()
