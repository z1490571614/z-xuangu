"""
对比5月8日选股的11只股票:MCP数据 vs 纯Tushare+本地日线数据

用法: python scripts/compare_mcp_vs_tushare_0508.py
"""
import os, sys, struct
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv(override=True)

import pandas as pd
from backend.utils.tushare_client import get_tushare_pro

TDX_PATH = os.environ.get('TDX_VIPDOC_PATH', r'G:\new_tdx\vipdoc')
TRADE_DATE = '20260508'

# -- 从DB读取MCP选出的11只股 --
import sqlite3
conn = sqlite3.connect('data/xuangu.db')
rows = conn.execute("""
    SELECT ts_code, name, close_price, change_pct, pre_change_pct, open_change_pct,
           auction_ratio, auction_turnover_rate, limit_up_count, seal_rate,
           rule_score, final_score, circ_mv
    FROM selected_stock WHERE record_id = 45 ORDER BY final_score DESC
""").fetchall()
conn.close()

STOCKS = [(r[0], r[1]) for r in rows]
MCP = {r[0]: dict(zip(
    ['name','close_price','change_pct','pre_change_pct','open_change_pct',
     'auction_ratio','auction_turnover_rate','limit_up_count','seal_rate',
     'rule_score','final_score','circ_mv'], r[1:]
)) for r in rows}

print('=' * 90)
title = f'5月8日选股数据对比: MCP vs Tushare+本地日线 ({TRADE_DATE})'
print(f'  {title}')
print('=' * 90)
print()

# -- 读取本地.day文件 --
def read_day_file(ts_code):
    code = ts_code.split('.')[0]
    market = 'sh' if ts_code.endswith('.SH') else 'sz'
    path = os.path.join(TDX_PATH, market, 'lday', f'{market}{code}.day')
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        data = f.read()
    n = len(data) // 32
    records = []
    for i in range(n):
        offset = i * 32
        d, o, h, l, c, amt, vol = struct.unpack_from('<IIIIIfI', data, offset)
        records.append({
            'date': str(d),
            'open': o / 100.0,
            'high': h / 100.0,
            'low': l / 100.0,
            'close': c / 100.0,
            'amount': float(amt) / 1000.0,
            'vol': int(vol) / 100.0,  # 手
        })
    return records

# -- 涨停价判断 --
def get_limit_pct(ts_code):
    code = ts_code.split('.')[0]
    if code.startswith(('300','301','688','689')):
        return 0.20
    return 0.10

# -- 获取Tushare数据 --
print('[1/4] 获取Tushare数据...')
pro = get_tushare_pro()
print(f'  Tushare连接成功')

auc_df = pro.stk_auction(trade_date=TRADE_DATE)
cols_str = ", ".join(auc_df.columns)
print(f'  stk_auction({TRADE_DATE}): {len(auc_df)}条 (fields: {cols_str})')

prev_date = '20260507'
prev_daily_df = pro.daily(trade_date=prev_date)
print(f'  daily({prev_date}): {len(prev_daily_df)}条')

basic_df = pro.daily_basic(trade_date=TRADE_DATE)
print(f'  daily_basic({TRADE_DATE}): {len(basic_df)}条')

daily_df = pro.daily(trade_date=TRADE_DATE)
print(f'  daily({TRADE_DATE}): {len(daily_df)}条')
print()

# -- 逐股对比 --
print('[2/4] 逐股对比...')
print()

all_pass = 0
all_fail = 0
all_issues = []

for ts_code, name in STOCKS:
    m = MCP[ts_code]

    # -- 本地日线 --
    day_records = read_day_file(ts_code)
    if not day_records:
        print(f'  {ts_code} {name}: .day缺失')
        continue

    # 找TRADE_DATE在记录中的位置
    idx_t = None
    for i, rec in enumerate(day_records):
        if rec['date'] == TRADE_DATE:
            idx_t = i
            break

    if idx_t is None:
        print(f'  {ts_code} {name}: .day中没有{TRADE_DATE}记录')
        continue

    rec_t = day_records[idx_t]
    local_close = rec_t['close']
    local_vol = rec_t['vol']  # 手

    # 10日趋势
    uptrend_pct = None
    if idx_t >= 10:
        close_10_ago = day_records[idx_t - 10]['close']
        if close_10_ago > 0:
            uptrend_pct = round((local_close / close_10_ago - 1) * 100, 2)

    # 100日涨停次数+封板率
    limit_pct = get_limit_pct(ts_code)
    touch_count = 0
    limit_up_count_local = 0
    start_idx = max(0, idx_t - 100)
    for i in range(start_idx, idx_t):
        if i == 0:
            continue
        prev_close = day_records[i-1]['close']
        if prev_close <= 0:
            continue
        limit_price = round(prev_close * (1 + limit_pct), 2)
        rec = day_records[i]
        if rec['high'] >= limit_price * 0.997:
            touch_count += 1
            if rec['close'] >= limit_price * 0.997:
                limit_up_count_local += 1
    seal_rate_local = round(limit_up_count_local / touch_count * 100, 2) if touch_count > 0 else 0

    # -- Tushare auction --
    auc_row = auc_df[auc_df['ts_code'] == ts_code]
    auc_vol = auc_price = auc_pre_close = auc_turnover = auc_float_share = None
    if len(auc_row) > 0:
        r = auc_row.iloc[0]
        auc_vol = float(r['vol']) if pd.notna(r.get('vol')) else None
        auc_price = float(r['price']) if pd.notna(r.get('price')) else None
        auc_pre_close = float(r['pre_close']) if pd.notna(r.get('pre_close')) else None
        auc_turnover = float(r['turnover_rate']) if pd.notna(r.get('turnover_rate')) else None
        auc_float_share = float(r['float_share']) if pd.notna(r.get('float_share')) else None

    # -- Tushare prev daily vol --
    prev_row = prev_daily_df[prev_daily_df['ts_code'] == ts_code]
    prev_daily_vol = None  # 手
    if len(prev_row) > 0:
        prev_daily_vol = float(prev_row.iloc[0]['vol']) if pd.notna(prev_row.iloc[0].get('vol')) else None

    # -- Tushare daily_basic circ_mv --
    basic_row = basic_df[basic_df['ts_code'] == ts_code]
    circ_mv_ts = None
    if len(basic_row) > 0:
        r = basic_row.iloc[0]
        v = float(r['circ_mv']) if pd.notna(r.get('circ_mv')) else None
        if v and v > 100000:
            circ_mv_ts = round(v / 10000, 2)  # 万元->亿

    # -- Tushare daily (for open_change_pct) --
    daily_row = daily_df[daily_df['ts_code'] == ts_code]
    open_change_from_daily = None
    daily_pre_close = None
    if len(daily_row) > 0:
        r = daily_row.iloc[0]
        d_open = float(r['open']) if pd.notna(r.get('open')) else None
        daily_pre_close = float(r['pre_close']) if pd.notna(r.get('pre_close')) else None
        if d_open and daily_pre_close and daily_pre_close > 0:
            open_change_from_daily = round((d_open / daily_pre_close - 1) * 100, 2)

    # -- 计算指标 --
    # auction_ratio: stk_auction.vol(股) / daily.vol(手) → 直接得到百分比
    # 因为: (股)/(手) = (股)/(100股) → 值就是百分比
    auction_ratio_ts = None
    if auc_vol and prev_daily_vol and prev_daily_vol > 0:
        auction_ratio_ts = round(auc_vol / prev_daily_vol, 2)

    # auction_turnover_rate: stk_auction自带
    auction_turnover_ts = auc_turnover

    # open_change_pct: stk_auction.price vs stk_auction.pre_close
    open_change_ts = None
    if auc_price and auc_pre_close and auc_pre_close > 0:
        open_change_ts = round((auc_price / auc_pre_close - 1) * 100, 2)

    # -- 对比 --
    def cmp(label, mcp_val, ts_val, tol=0.5):
        if mcp_val is None or ts_val is None:
            return f'{label}: MCP={mcp_val}, TS=None [WARN]', abs(mcp_val or 0)
        if isinstance(mcp_val, (int,float)) and isinstance(ts_val, (int,float)):
            diff = abs(mcp_val - ts_val)
            pct = (diff / abs(mcp_val)) * 100 if mcp_val != 0 else 0
            if diff > tol:
                return f'{label}: MCP={mcp_val}, TS={ts_val}, diff={diff:.2f} ({pct:.1f}%) [DIFF]', diff
            return f'{label}: MCP={mcp_val}, TS={ts_val}, diff={diff:.2f} [OK]', diff
        return f'{label}: MCP={mcp_val}, TS={ts_val}', 0

    c1, d1 = cmp('竞昨比(%)', m['auction_ratio'], auction_ratio_ts, tol=1.0)
    c2, d2 = cmp('竞价换手(%)', m['auction_turnover_rate'], auction_turnover_ts, tol=0.10)
    c3, d3 = cmp('开涨幅-auc(%)', m['open_change_pct'], open_change_ts, tol=1.0)
    c4, d4 = cmp('开涨幅-daily(%)', m['open_change_pct'], open_change_from_daily, tol=1.0)
    c5, d5 = cmp('涨停次数', m['limit_up_count'], limit_up_count_local, tol=1)
    c6, d6 = cmp('封板率(%)', m['seal_rate'], seal_rate_local, tol=3.0)
    c7, d7 = cmp('流通市值(亿)', m['circ_mv'], circ_mv_ts, tol=5.0)

    comparisons = [c1, c2, c3, c4, c5, c6, c7]
    diffs = [d1, d2, d3, d4, d5, d6, d7]

    sep_line = '-' * 50
    print(f'  {sep_line}')
    print(f'  {ts_code} {name}  |  .day收盘={local_close} | .day收量={local_vol:.0f}手')
    print(f'  竞价量={auc_vol:.0f}股 | 昨量={prev_daily_vol:.0f}手 | '
          f'竞价均价={auc_price} | 昨收(竞价)={auc_pre_close} | 昨收(daily)={daily_pre_close}')
    print(f'  近10日涨幅={uptrend_pct}% | 涨停{limit_up_count_local}/{touch_count}触板=封板率{seal_rate_local}%')
    for c in comparisons:
        if '[DIFF]' in c:
            flag = '  [DIFF]'
        elif '[WARN]' in c:
            flag = '  [WARN]'
        else:
            flag = '  [OK] '
        print(flag + c)
    print()

    # 过滤条件检查
    reasons = []
    if auction_ratio_ts is None or auction_ratio_ts < 4 or auction_ratio_ts > 30:
        reasons.append(f'竞昨比={auction_ratio_ts}(需4-30%)')
    if auction_turnover_ts is None or auction_turnover_ts < 0.5 or auction_turnover_ts > 10:
        reasons.append(f'竞价换手={auction_turnover_ts}(需0.5-10%)')
    if limit_up_count_local < 3:
        reasons.append(f'涨停次数={limit_up_count_local}(需>=3)')
    if seal_rate_local < 80:
        reasons.append(f'封板率={seal_rate_local}%(需>=80%)')
    if circ_mv_ts is not None and circ_mv_ts > 2000:
        reasons.append(f'流通市值={circ_mv_ts}亿(需<2000)')
    if uptrend_pct is not None and uptrend_pct <= 0:
        reasons.append(f'10日涨幅={uptrend_pct}%(需>0)')

    if reasons:
        all_fail += 1
        reason_str = ' | '.join(reasons)
        print(f'  [FAIL] 过滤不通过: {reason_str}')
    else:
        all_pass += 1
        print(f'  [PASS] 过滤通过')

    # 收集显著差异
    for i, (d, label) in enumerate(zip(diffs, ['竞昨比','竞价换手','开涨幅(auc)','开涨幅(daily)','涨停次数','封板率','市值'])):
        if d > (1.0 if i < 4 else 1 if i == 4 else 3 if i == 5 else 5):
            all_issues.append(f'{ts_code} {name}: {label}差异={d:.2f}')

    print()

# -- 汇总 --
print('=' * 90)
print('[3/4] 汇总')
print(f'  通过过滤: {all_pass}/{len(STOCKS)}')
print(f'  不通过:   {all_fail}/{len(STOCKS)}')
if all_issues:
    print(f'  显著差异项: {len(all_issues)}')
    for i in all_issues:
        print(f'    - {i}')
print()

print('[4/4] 关键发现')
print('-' * 90)
print("""
1. 竞价数据: stk_auction 提供 vol(股)/price(均价)/pre_close/turnover_rate
   - 竞昨比 = stk_auction.vol(股) / prev_daily.vol(手) → 因为(股)/(100股)的单位直接就是百分比
   - 竞价换手率 = stk_auction.turnover_rate (Tushare预计算值)

2. 本地日线: .day 文件提供前复权OHLCV (date/4+2*int/100, 2*float/1000+int/100)
   - 涨停次数/封板率基于前复权数据计算,口径与MCP一致

3. 开盘涨幅: 两个来源可交叉验证
   - stk_auction.price vs stk_auction.pre_close (竞价均价vs昨收)
   - daily.open vs daily.pre_close (开盘价vs昨收)
   - MCP的open_change_pct基于竞价数据,与daily.open接近但不完全相同

4. 流通市值: daily_basic.circ_mv 单位是万元,需/10000转为亿
""")
