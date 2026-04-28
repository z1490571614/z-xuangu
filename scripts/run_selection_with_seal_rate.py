"""
执行默认选股策略，并计算每只股票的封板率
"""
import os
import sys
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

# 添加项目路径
sys.path.insert(0, '/vol1/1000/docker/xuangu')

# 加载环境变量
load_dotenv('/vol1/1000/docker/xuangu/.env')

from backend.services.data_collector import TushareDataCollector

BASE_URL = "http://localhost:9999/api/v1"

def run_selection():
    """执行选股"""
    print('='*80)
    print('📊 阶段1: 通达信MCP选股')
    print('='*80)
    
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
        print(f'✅ 选股成功')
        print(f'📅 交易日期: {result["trade_date"]}')
        print(f'📈 选出股票数: {result["passed_count"]}')
        print(f'⏱️  总耗时: {result["execution_time"]:.2f}秒')
        return result["stocks"], result["trade_date"]
    else:
        print(f'❌ 选股失败: {response.text}')
        return None, None

def calculate_seal_rate_for_stock(collector, ts_code, trade_date):
    """计算单只股票的封板率"""
    # 计算日期范围（约100个交易日）
    end_date = trade_date
    start_date_dt = datetime.strptime(end_date, '%Y%m%d') - timedelta(days=150)
    start_date = start_date_dt.strftime('%Y%m%d')
    
    # 获取日线数据
    daily_df = collector.get_daily_data(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date
    )
    
    if daily_df.empty:
        return None
    
    # 获取涨跌停价格
    limit_df = collector.get_stk_limit(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date
    )
    
    if limit_df.empty:
        return None
    
    # 合并数据
    merged_df = pd.merge(daily_df, limit_df, on=['ts_code', 'trade_date'], how='left')
    
    # 按日期降序排序，取最近100个交易日
    merged_df = merged_df.sort_values('trade_date', ascending=False)
    merged_df = merged_df.head(100).sort_values('trade_date', ascending=True)
    
    # 计算指标
    touch_days = 0
    limit_up_days = 0
    
    for idx, row in merged_df.iterrows():
        high = row['high']
        close = row['close']
        up_limit = row['up_limit']
        
        if pd.notna(up_limit):
            # 检查触板
            touched = high >= up_limit - 0.01
            if touched:
                touch_days += 1
            
            # 检查涨停
            limit_up = close >= up_limit - 0.01
            if limit_up:
                limit_up_days += 1
    
    seal_rate = (limit_up_days / touch_days * 100) if touch_days > 0 else 0
    
    return {
        "touch_days": touch_days,
        "limit_up_days": limit_up_days,
        "seal_rate": seal_rate,
        "trading_days": len(merged_df)
    }

def main():
    print('='*80)
    print('🚀 选股 + 封板率计算 完整流程')
    print('='*80)
    
    # 1. 执行选股
    stocks, trade_date = run_selection()
    
    if not stocks:
        print('\n❌ 没有选出股票，退出')
        return
    
    # 2. 初始化Tushare
    print('\n' + '='*80)
    print('📊 阶段2: Tushare计算封板率')
    print('='*80)
    
    try:
        collector = TushareDataCollector()
        print('✅ Tushare初始化成功')
    except Exception as e:
        print(f'❌ Tushare初始化失败: {e}')
        return
    
    print(f'\n📅 统计基准日: {trade_date}')
    print(f'📋 待处理股票数: {len(stocks)}')
    
    # 3. 计算每只股票的封板率
    results = []
    
    print('\n⏳ 开始计算...')
    print('-'*80)
    
    for i, stock in enumerate(stocks):
        ts_code = stock.get('ts_code')
        name = stock.get('name')
        
        print(f'  [{i+1}/{len(stocks)}] 处理 {ts_code} {name}...', end='', flush=True)
        
        try:
            seal_data = calculate_seal_rate_for_stock(collector, ts_code, trade_date)
            
            if seal_data:
                results.append({
                    **stock,
                    **seal_data
                })
                print(f' ✅ 触板{seal_data["touch_days"]}天, 涨停{seal_data["limit_up_days"]}次, 封板率{seal_data["seal_rate"]:.1f}%')
            else:
                results.append({
                    **stock,
                    "touch_days": 0,
                    "limit_up_days": 0,
                    "seal_rate": 0,
                    "trading_days": 0
                })
                print(' ⚠️  数据不足')
        except Exception as e:
            print(f' ❌ 错误: {e}')
    
    # 4. 输出最终结果
    print('\n' + '='*80)
    print('📊 最终结果汇总')
    print('='*80)
    
    # 按封板率排序
    results_sorted = sorted(results, key=lambda x: x.get('seal_rate', 0), reverse=True)
    
    print(f'\n{"排名":<6} {"股票代码":<12} {"名称":<10} {"现价":<8} {"涨幅":<8} {"触板":<6} {"涨停":<6} {"封板率":<10}')
    print('-'*80)
    
    for i, stock in enumerate(results_sorted):
        print(f'{i+1:<6} {stock["ts_code"]:<12} {stock["name"]:<10} {stock.get("close_price", 0):<8.2f} {stock.get("change_pct", 0):<8.2f} {stock["touch_days"]:<6} {stock["limit_up_days"]:<6} {stock["seal_rate"]:<10.1f}%')
    
    print('-'*80)
    
    # 5. 统计信息
    print('\n📈 统计摘要:')
    avg_seal_rate = sum(s['seal_rate'] for s in results_sorted) / len(results_sorted) if results_sorted else 0
    print(f'  平均封板率: {avg_seal_rate:.1f}%')
    
    high_seal = [s for s in results_sorted if s['seal_rate'] >= 80]
    print(f'  封板率≥80%: {len(high_seal)}只')
    
    medium_seal = [s for s in results_sorted if 50 <= s['seal_rate'] < 80]
    print(f'  50%≤封板率<80%: {len(medium_seal)}只')
    
    low_seal = [s for s in results_sorted if s['seal_rate'] < 50]
    print(f'  封板率<50%: {len(low_seal)}只')
    
    print('\n' + '='*80)
    print('✅ 流程完成')
    print('='*80)
    
    return results_sorted

if __name__ == '__main__':
    main()
