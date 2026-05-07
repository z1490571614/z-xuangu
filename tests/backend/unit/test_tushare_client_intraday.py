from backend.services.dragon_leader.data.intraday_context import IntradayContext
from backend.utils.tushare_client import get_tushare_token


def test_get_tushare_token_prefers_explicit_token():
    assert get_tushare_token(" explicit-token ") == "explicit-token"


def test_intraday_skips_stk_mins_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_TUSHARE_STK_MINS", raising=False)
    ctx = IntradayContext()

    class _Pro:
        def stk_mins(self, *args, **kwargs):
            raise AssertionError("stk_mins should be disabled by default")

    ctx._pro = _Pro()

    assert ctx.get_minute_kline("000889.SZ", "20260507") == []


def test_intraday_uses_daily_fallback_when_minutes_missing(monkeypatch):
    monkeypatch.delenv("ENABLE_TUSHARE_STK_MINS", raising=False)
    ctx = IntradayContext()
    fallback = {
        "open_price": 5.0,
        "close_price": 5.2,
        "intraday_high": 5.3,
        "intraday_low": 4.9,
        "intraday_direction": "上涨",
        "max_drop_pct": 2.0,
        "tail_direction": "未知",
        "opening_30min_pct": 4.0,
        "is_weak_open": False,
        "has_tail_recovery": False,
        "data_status": "fallback_daily",
        "data_source": "tushare_daily",
    }
    monkeypatch.setattr(ctx, "_get_realtime_intraday", lambda *_: None)
    monkeypatch.setattr(ctx, "_get_daily_intraday", lambda *_: fallback)

    result = ctx.analyze_intraday("000889.SZ", "20260507")

    assert result["data_status"] == "fallback_daily"
    assert result["data_source"] == "tushare_daily"
