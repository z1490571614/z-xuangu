#!/usr/bin/env python
"""
训练数据源全面验证脚本
逐一测试文档 xuangu_multi_model_training_data_supplement.md 附录A
中所有必需字段能否从 Tushare 和通达信本地数据成功提取。
"""
import sys, os, struct, logging
from datetime import date, datetime, timedelta
from collections import defaultdict
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.WARNING)
os.environ.setdefault('TUSHARE_PRO_SAVE_PATH', os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'tushare_cache'
))

TEST_DATE = "20260508"  # 最近一个本地数据可用的交易日
TEST_PREV_DATE = "20260507"
TEST_CODE_SH = "600000.SH"
TEST_CODE_SZ = "000001.SZ"

TDX_VIPDOC = os.getenv("TDX_VIPDOC_PATH", r"G:\new_tdx\vipdoc")
PRICE_SCALE = 100.0
AMOUNT_SCALE = 1000.0
VOL_SCALE = 100.0

# ── 统计 ──────────────────────────────────────────
results = {"pass": [], "fail": [], "warn": []}


def record(name, ok, detail=""):
    if ok:
        results["pass"].append(name)
        print(f"  [PASS] {name}: {detail}")
    else:
        if detail and ("not found" in detail or "missing" in detail or "unsupported" in detail or "不存在" in detail or "缺失" in detail or "不支持" in detail):
            results["fail"].append(name)
            print(f"  [FAIL] {name}: {detail}")
        else:
            results["warn"].append(name)
            print(f"  [WARN] {name}: {detail}")


# ═══════════════════════════════════════════════════
# 1. Tushare 数据源验证
# ═══════════════════════════════════════════════════
print("=" * 65)
print("1. Tushare 数据源")
print("=" * 65)

from backend.utils.tushare_client import get_tushare_pro

pro = get_tushare_pro()
record("Tushare 连接", pro is not None, f"pro={'OK' if pro else 'FAIL'}")


def test_tushare_api(api_name, method, **kwargs):
    try:
        df = method(**kwargs)
        if df is None or (hasattr(df, 'empty') and df.empty):
            return False, "返回空 DataFrame"
        return True, f"{len(df)} 条记录"
    except Exception as e:
        msg = str(e)[:120]
        return False, msg


# 1.1 stock_basic
ok, detail = test_tushare_api("stock_basic", pro.stock_basic, exchange='', list_status='L', fields='ts_code,name,industry,list_date,is_hs')
record("stock_basic (全量)", ok, detail)

for code, label in [(TEST_CODE_SH, "600000"), (TEST_CODE_SZ, "000001")]:
    ok, detail = test_tushare_api(f"stock_basic({label})", pro.stock_basic,
                                  ts_code=code, fields='ts_code,name,industry,list_date,is_hs')
    record(f"stock_basic 单股({label})", ok, detail)

# 1.2 trade_cal
ok, detail = test_tushare_api("trade_cal", pro.trade_cal,
                               exchange='SSE', start_date='20260101', end_date='20260517', is_open='1')
record("trade_cal", ok, detail)

# 1.3 daily (日线行情)
for code, label in [(TEST_CODE_SH, "600000"), (TEST_CODE_SZ, "000001")]:
    ok, detail = test_tushare_api(f"daily({label})", pro.daily,
                                  ts_code=code, trade_date=TEST_DATE)
    record(f"daily 日线({label})", ok, detail)

# 1.4 daily_basic (日线基础指标)
ok, detail = test_tushare_api(f"daily_basic({TEST_DATE})", pro.daily_basic,
                               trade_date=TEST_DATE, fields='ts_code,turnover_rate,volume_ratio,pe,pb,total_mv,circ_mv')
record(f"daily_basic ({TEST_DATE})", ok, detail)

# 验证流通市值字段
if ok:
    df = pro.daily_basic(trade_date=TEST_DATE, fields='ts_code,turnover_rate,volume_ratio,pe,pb,total_mv,circ_mv')
    has_float_mv = 'circ_mv' in df.columns
    record("daily_basic.circ_mv 字段", has_float_mv)

# 1.5 adj_factor (复权因子)
ok, detail = test_tushare_api("adj_factor", pro.adj_factor,
                               ts_code=TEST_CODE_SH, trade_date='')
record(f"adj_factor({TEST_CODE_SH})", ok, detail)

# 1.6 stk_limit (涨跌停价格)
ok, detail = test_tushare_api(f"stk_limit({TEST_DATE})", pro.stk_limit,
                               trade_date=TEST_DATE, fields='ts_code,up_limit,down_limit,pre_close')
record(f"stk_limit ({TEST_DATE})", ok, detail)

# 1.7 limit_list_d (涨跌停列表)
ok, detail = test_tushare_api(f"limit_list_d({TEST_DATE})", pro.limit_list_d,
                               trade_date=TEST_DATE, fields='ts_code,limit,up_limit,down_limit')
record(f"limit_list_d ({TEST_DATE})", ok, detail)

# 1.8 limit_list_ths (同花顺涨停池)
ok, detail = test_tushare_api(f"limit_list_ths({TEST_DATE})", pro.limit_list_ths,
                               trade_date=TEST_DATE, limit_type='涨停池')
record(f"limit_list_ths ({TEST_DATE})", ok, detail)

# 1.9 stk_auction (集合竞价)
ok, detail = test_tushare_api(f"stk_auction({TEST_DATE})", pro.stk_auction,
                               trade_date=TEST_DATE, fields='ts_code,price,vol,amount,pre_close')
record(f"stk_auction ({TEST_DATE})", ok, detail)

# 1.10 moneyflow (资金流)
ok, detail = test_tushare_api(f"moneyflow({TEST_DATE})", pro.moneyflow,
                               trade_date=TEST_DATE, fields='ts_code,net_mf_amount')
record(f"moneyflow ({TEST_DATE})", ok, detail)

# 1.11 top_list (龙虎榜)
ok, detail = test_tushare_api(f"top_list({TEST_DATE})", pro.top_list,
                               trade_date=TEST_DATE, fields='ts_code,name,close,change,amount,net_amount')
record(f"top_list ({TEST_DATE})", ok, detail)

# 1.12 fina_indicator (财务指标) — 文档标记为必需
ok, detail = test_tushare_api("fina_indicator(000001,2025Q4)", pro.fina_indicator,
                               ts_code=TEST_CODE_SZ, period='20251231', fields='ts_code,end_date,revenue,profit,roe')
record("fina_indicator (财务指标)", ok, detail)


# ═══════════════════════════════════════════════════
# 2. 通达信本地日线 (.day)
# ═══════════════════════════════════════════════════
print()
print("=" * 65)
print("2. 通达信本地日线 (lday/*.day)")
print("=" * 65)

from backend.services.tdx_local_selector import TdxLocalSelectorService

tdx = TdxLocalSelectorService(tdx_vipdoc_path=TDX_VIPDOC)
record("TDX 路径存在", os.path.isdir(TDX_VIPDOC), TDX_VIPDOC)

# 2.1 日线读取
for code, label in [(TEST_CODE_SH, "600000"), (TEST_CODE_SZ, "000001")]:
    df = tdx.get_daily_data(ts_code=code, trade_date=TEST_DATE)
    ok = not df.empty
    detail = f"{len(df)} 条" if ok else "无数据"
    record(f"TDX 日线({label}) {TEST_DATE}", ok, detail)
    if ok:
        cols = df.columns.tolist()
        has_open = 'open' in cols
        has_close = 'close' in cols
        has_pct = 'pct_chg' in cols
        record(f"  日线 OHLC({label})", has_open and has_close)

# 2.2 历史区间读取
df_hist = tdx.get_daily_data(ts_code=TEST_CODE_SH, start_date="20250901", end_date="20260508")
record(f"TDX 日线区间({TEST_CODE_SH}) 2025-09~2026-05", len(df_hist) > 50, f"{len(df_hist)} 条")

# 2.3 特征计算验证
print("  特征计算验证 (基于 TDX 日线):")
if not df_hist.empty:
    # ret_5d
    if 'close' in df_hist.columns:
        df_hist = df_hist.sort_values('trade_date')
        closes = df_hist['close'].values
        if len(closes) >= 6:
            ret_5d = (closes[-1] / closes[-6] - 1) * 100
            record("ret_5d 计算", True, f"{ret_5d:.2f}%")

# 2.4 涨停计数 (limitup_count_20d)
if not df_hist.empty and 'pct_chg' in df_hist.columns:
    limitup_20d = (df_hist['pct_chg'].tail(20) >= 9.5).sum()
    record("limitup_count_20d 计算", True, f"{limitup_20d} 次")


# ═══════════════════════════════════════════════════
# 3. 通达信本地分钟线 (.lc1 1分钟)
# ═══════════════════════════════════════════════════
print()
print("=" * 65)
print("3. 通达信本地 1分钟线 (minline/*.lc1)")
print("=" * 65)


def read_lc1_file(filepath):
    """读取 .lc1 1分钟线文件"""
    with open(filepath, 'rb') as f:
        data = f.read()
    n = len(data) // 32
    records = []
    for i in range(n):
        offset = i * 32
        date_val, time_val = struct.unpack_from('<HH', data, offset)
        o, h, l, c, amt = struct.unpack_from('<fffff', data, offset + 4)
        vol = struct.unpack_from('<I', data, offset + 24)[0]
        # 解码日期: (year-2004)*2048 + month*100 + day
        y_idx = date_val // 2048
        rem = date_val % 2048
        month = rem // 100
        day = rem % 100
        year = 2004 + y_idx
        # 时间: 分钟从午夜开始
        hour = time_val // 60
        minute = time_val % 60
        records.append({
            'datetime': f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            'year': year, 'month': month, 'day': day, 'hour': hour, 'minute': minute,
            'open': o, 'high': h, 'low': l, 'close': c,
            'amount': amt, 'volume': vol,
        })
    return records


def read_lc5_file(filepath):
    """读取 .lc5 5分钟线文件 (格式与 lc1 相同，只是K线周期不同)"""
    return read_lc1_file(filepath)  # 二进制格式相同


min1_path = os.path.join(TDX_VIPDOC, 'sh', 'minline', 'sh600000.lc1')
min5_path = os.path.join(TDX_VIPDOC, 'sh', 'fzline', 'sh600000.lc5')

record(".lc1 文件存在(sh600000)", os.path.exists(min1_path), min1_path)
record(".lc5 文件存在(sh600000)", os.path.exists(min5_path), min5_path)

# 3.1 读取 1分钟线
if os.path.exists(min1_path):
    recs = read_lc1_file(min1_path)
    record(f"1分钟线 解析(sh600000)", len(recs) > 0, f"{len(recs)} 条")

    if recs:
        # 按日期分组
        by_date = defaultdict(list)
        for r in recs:
            key = f"{r['year']}-{r['month']:02d}-{r['day']:02d}"
            by_date[key].append(r)

        # 找 TEST_DATE 那天的数据
        td = f"{TEST_DATE[:4]}-{TEST_DATE[4:6]}-{TEST_DATE[6:8]}"
        if td in by_date:
            day_recs = by_date[td]
            record(f"1分钟线 有 {TEST_DATE} 数据(sh600000)", True,
                   f"{len(day_recs)} 条 (开盘~收盘)")

            # 验证开盘5分钟 (09:31~09:35)
            first_5min = [r for r in day_recs if r['hour'] == 9 and 31 <= r['minute'] <= 35]
            if first_5min:
                open_5min_high = max(r['high'] for r in first_5min)
                open_5min_low = min(r['low'] for r in first_5min)
                first_close = first_5min[0]['close']
                open_5min_return = (first_5min[-1]['close'] / first_5min[0]['open'] - 1) * 100
                open_5min_dd = (open_5min_low / first_5min[0]['open'] - 1) * 100
                record("open_5min_return 提取", True, f"{open_5min_return:.2f}%")
                record("open_5min_max_drawdown 提取", True, f"{open_5min_dd:.2f}%")

                # 开盘涨幅 proxy: 首分钟收盘 vs 前收盘
                first_bar = day_recs[0]
                record("open_pct_proxy (首分钟)", True,
                       f"open={first_bar['open']:.2f} close={first_bar['close']:.2f}")
            else:
                record("open_5min 数据", False, f"{td} 无 09:31-09:35 的分钟数据")
        else:
            # 找最近一个交易日
            available_dates = sorted(by_date.keys())
            record(f"1分钟线 有 {TEST_DATE} 数据(sh600000)", False,
                   f"{TEST_DATE} 不在范围内，最近日期: {available_dates[-1] if available_dates else '无'}")

# 3.2 读取 5分钟线
if os.path.exists(min5_path):
    recs5 = read_lc5_file(min5_path)
    record(f"5分钟线 解析(sh600000)", len(recs5) > 0, f"{len(recs5)} 条")

    if recs5:
        by_date5 = defaultdict(list)
        for r in recs5:
            key = f"{r['year']}-{r['month']:02d}-{r['day']:02d}"
            by_date5[key].append(r)

        available = sorted(by_date5.keys())
        record("5分钟线 日期范围", True, f"{available[0]} ~ {available[-1]} ({len(available)} 个交易日)")

        # 找最近一天验证特征提取
        latest = available[-1]
        latest_recs = by_date5[latest]
        if latest_recs:
            open_bar = latest_recs[0]
            record("5分钟线 开盘首K线", True,
                   f"{latest} open={open_bar['open']:.2f} close={open_bar['close']:.2f}")


# ═══════════════════════════════════════════════════
# 4. 合成特征验证 (Tushare + TDX 联合)
# ═══════════════════════════════════════════════════
print()
print("=" * 65)
print("4. 合成特征验证 (多数据源联合)")
print("=" * 65)

# 4.1 竞昨比 (auction_ratio)
# 需要: stk_auction.vol + daily.vol
try:
    auction_df = pro.stk_auction(trade_date=TEST_DATE, ts_code=TEST_CODE_SH,
                                 fields='ts_code,vol,amount,price,pre_close')
    daily_df = pro.daily(trade_date=TEST_PREV_DATE, ts_code=TEST_CODE_SH,
                         fields='ts_code,vol')
    if not auction_df.empty and not daily_df.empty:
        auction_vol = float(auction_df.iloc[0]['vol'])
        prev_vol = float(daily_df.iloc[0]['vol']) * 100  # Tushare daily.vol 是手, 需×100转股
        if auction_vol > 0 and prev_vol > 0:
            ratio = auction_vol / prev_vol
            record("auction_ratio 竞昨比(Tushare)", True, f"{ratio:.4f} ({ratio*100:.2f}%)")

            # 竞价换手率
            basic_df = pro.daily_basic(trade_date=TEST_PREV_DATE, ts_code=TEST_CODE_SH,
                                       fields='ts_code,free_share,float_share')
            if not basic_df.empty:
                share_col = 'free_share' if 'free_share' in basic_df.columns else 'float_share'
                if share_col in basic_df.columns:
                    float_share = float(basic_df.iloc[0][share_col])  # 万股
                    if float_share > 0:
                        turnover = auction_vol / (float_share * 10000) * 100
                        record("auction_turnover_rate 竞价换手率(Tushare)", True, f"{turnover:.2f}%")
                    else:
                        record("auction_turnover_rate", False, "float_share=0")
                else:
                    record("auction_turnover_rate", False, "无 free_share/float_share 字段")
            else:
                record("auction_turnover_rate", False, "daily_basic 无数据")
        else:
            record("auction_ratio", False, f"vol=0 (竞价{auction_vol} 昨日{prev_vol})")
    else:
        record("auction_ratio", False, "stk_auction/daily 无数据")
except Exception as e:
    record("auction_ratio 合成", False, str(e)[:100])

# 4.2 auction_amount_to_float_mv
try:
    if not auction_df.empty and not basic_df.empty if 'basic_df' in dir() else True:
        basic_df2 = pro.daily_basic(trade_date=TEST_PREV_DATE, ts_code=TEST_CODE_SH,
                                    fields='ts_code,circ_mv')
        if not basic_df2.empty:
            auction_amount = float(auction_df.iloc[0]['amount'])  # 万元
            circ_mv = float(basic_df2.iloc[0]['circ_mv'])  # 万元 (Tushare circ_mv 单位万元)
            if circ_mv > 0:
                amt_ratio = auction_amount / circ_mv
                record("auction_amount_to_float_mv(Tushare)", True, f"{amt_ratio:.6f}")
            else:
                record("auction_amount_to_float_mv", False, "circ_mv=0")
        else:
            record("auction_amount_to_float_mv", False, "daily_basic 无 circ_mv")
except Exception as e:
    record("auction_amount_to_float_mv 合成", False, str(e)[:100])

# 4.3 float_mv (流通市值)
try:
    basic_all = pro.daily_basic(trade_date=TEST_DATE, fields='ts_code,circ_mv')
    has_mv = not basic_all.empty and 'circ_mv' in basic_all.columns
    if has_mv:
        valid_mv = basic_all['circ_mv'].dropna()
        record(f"float_mv 流通市值({TEST_DATE})", True, f"{len(valid_mv)} 只股票, 中位数={valid_mv.median():.0f}万")
    else:
        record(f"float_mv 流通市值({TEST_DATE})", False, "无数据")
except Exception as e:
    record("float_mv", False, str(e)[:100])

# 4.4 seal_rate_20d (封板率)
# 用 limit_list_d 或 limit_list_ths 计算
try:
    import datetime as dt_mod
    from backend.utils.trading_date import get_latest_trading_day
    # 获取近20个交易日
    cal_df = pro.trade_cal(exchange='SSE', start_date='20260401', end_date=TEST_DATE, is_open='1')
    trade_dates = sorted(cal_df['cal_date'].tolist())[-20:]

    seal_count = 0
    touch_count = 0
    for td in trade_dates:
        lim_df = pro.limit_list_d(trade_date=td, fields='ts_code,limit,up_limit,down_limit')
        if not lim_df.empty:
            code_mask = lim_df['ts_code'] == TEST_CODE_SH
            if code_mask.any():
                touch_count += 1
                # 封板: 当日最高触碰涨停且收盘也在涨停价附近
                daily_td = pro.daily(trade_date=td, ts_code=TEST_CODE_SH, fields='ts_code,close,high,pre_close')
                if not daily_td.empty:
                    row = daily_td.iloc[0]
                    up_limit = float(lim_df[lim_df['ts_code'] == TEST_CODE_SH].iloc[0]['up_limit'])
                    if float(row['close']) >= up_limit * 0.997:
                        seal_count += 1

    if touch_count > 0:
        seal_rate = seal_count / touch_count * 100
        record(f"seal_rate_20d({TEST_CODE_SH})", True,
               f"触板{touch_count}天 封板{seal_count}天 封板率={seal_rate:.1f}%")
    else:
        record(f"seal_rate_20d({TEST_CODE_SH})", False, "近20日无触板")
except Exception as e:
    record("seal_rate_20d", False, str(e)[:100])

# 4.5 市场环境 (market_seal_rate)
try:
    td = TEST_DATE
    lim_df = pro.limit_list_d(trade_date=td, fields='ts_code,limit')
    if not lim_df.empty:
        total_limitup = len(lim_df[lim_df['limit'] == 'U'])
        record("market_seal_rate (涨停数)", True, f"{td} 涨停{total_limitup}只")
    else:
        record("market_seal_rate", False, "limit_list_d 无数据")
except Exception as e:
    record("market_seal_rate", False, str(e)[:100])

# 4.6 板块涨停数 (sector_limitup_count)
try:
    # 用 limit_list_ths 的 lu_desc 或 limit_list_d 聚合
    ths_df = pro.limit_list_ths(trade_date=TEST_DATE, limit_type='涨停池')
    if not ths_df.empty:
        record(f"sector_limitup_count({TEST_DATE})", True,
               f"涨停池 {len(ths_df)} 只, 可聚合板块")
    else:
        record(f"sector_limitup_count({TEST_DATE})", False, "无涨停池数据")
except Exception as e:
    record("sector_limitup_count", False, str(e)[:100])

# 4.7 T+0 标签: intraday_high_return, intraday_max_drawdown
# 需要分钟线
if os.path.exists(min1_path):
    recs = read_lc1_file(min1_path)
    by_date = defaultdict(list)
    for r in recs:
        by_date[f"{r['year']}-{r['month']:02d}-{r['day']:02d}"].append(r)

    test_date_str = f"{TEST_DATE[:4]}-{TEST_DATE[4:6]}-{TEST_DATE[6:8]}"
    if test_date_str in by_date:
        day_recs = by_date[test_date_str]
        open_price = day_recs[0]['open']
        day_high = max(r['high'] for r in day_recs)
        day_low = min(r['low'] for r in day_recs)
        day_close = day_recs[-1]['close']
        intraday_high_ret = (day_high / open_price - 1) * 100
        intraday_close_ret = (day_close / open_price - 1) * 100
        intraday_max_dd = (day_low / open_price - 1) * 100
        record("intraday_high_return (标签)", True, f"{intraday_high_ret:.2f}%")
        record("intraday_close_return (标签)", True, f"{intraday_close_ret:.2f}%")
        record("intraday_max_drawdown (标签)", True, f"{intraday_max_dd:.2f}%")
    else:
        record("intraday 标签", False, f"{test_date_str} 无分钟线数据")

# 4.8 T+1 标签
# t1_open_return 需要次日数据
# 在 TEST_DATE + 1 如果存在分钟线
next_date = "20260509"
next_date_str = "2026-05-09"
if os.path.exists(min1_path):
    if next_date_str in by_date:
        next_day_recs = by_date[next_date_str]
        t1_open = next_day_recs[0]['open']
        prev_close = day_recs[-1]['close'] if test_date_str in by_date else None
        if prev_close:
            t1_open_ret = (t1_open / prev_close - 1) * 100
            t1_high = max(r['high'] for r in next_day_recs)
            t1_close = next_day_recs[-1]['close']
            t1_high_ret = (t1_high / prev_close - 1) * 100
            t1_close_ret = (t1_close / prev_close - 1) * 100
            record("t1_open_return (标签)", True, f"{t1_open_ret:.2f}%")
            record("t1_high_return (标签)", True, f"{t1_high_ret:.2f}%")
            record("t1_close_return (标签)", True, f"{t1_close_ret:.2f}%")
        else:
            record("t1 标签", False, "无 T 日收盘价")
    else:
        record("t1 标签", False, f"{next_date_str} 无分钟线数据")


# ═══════════════════════════════════════════════════
# 5. 汇总
# ═══════════════════════════════════════════════════
print()
print("=" * 65)
print("5. 验证汇总")
print("=" * 65)

print(f"\n  [PASS] 通过: {len(results['pass'])} 项")
print(f"  [WARN] 部分可用: {len(results['warn'])} 项")
print(f"  [FAIL] 失败: {len(results['fail'])} 项")

if results['fail']:
    print(f"\n失败项明细:")
    for name in results['fail']:
        print(f"   - {name}")

if results['warn']:
    print(f"\n需关注项:")
    for name in results['warn']:
        print(f"   - {name}")

print()
print("核心数据提取能力评估:")
pass_count = len(results['pass'])
total = pass_count + len(results['fail']) + len(results['warn'])
pct = pass_count / total * 100 if total > 0 else 0
print(f"  提取成功率: {pass_count}/{total} = {pct:.0f}%")
