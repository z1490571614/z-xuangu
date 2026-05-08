import pandas as pd

from backend.services.risk_breakdown_service import RiskBreakdownService


class FakeMarketSentimentPro:
    def __init__(self):
        self.calls = []

    def index_daily(self, **kwargs):
        self.calls.append(("index_daily", kwargs))
        if kwargs.get("fields") == "pct_change":
            return pd.DataFrame([{"pct_change": -0.5}])
        if kwargs.get("fields") == "amount":
            return pd.DataFrame([{"amount": 900000000}])
        return pd.DataFrame()

    def index_dailybasic(self, **kwargs):
        self.calls.append(("index_dailybasic", kwargs))
        return pd.DataFrame([{"turnover_rate": 0.8}])

    def limit_step(self, **kwargs):
        self.calls.append(("limit_step", kwargs))
        return pd.DataFrame([{"nums": 5}, {"nums": 3}])

    def limit_list_d(self, **kwargs):
        self.calls.append(("limit_list_d", kwargs))
        return pd.DataFrame([
            {"ts_code": "000001.SZ", "limit": "U"},
            {"ts_code": "000002.SZ", "limit": "U"},
            {"ts_code": "000003.SZ", "limit": "D"},
            {"ts_code": "000004.SZ", "limit": "Z"},
        ])

    def limit_list_ths(self, **kwargs):
        self.calls.append(("limit_list_ths", kwargs))
        raise AssertionError("market sentiment must use limit_list_d for up/down/break counts")

    def moneyflow_hsgt(self, **kwargs):
        self.calls.append(("moneyflow_hsgt", kwargs))
        return pd.DataFrame([{"north_money": 1200}])


def test_market_sentiment_uses_limit_list_d_for_up_down_and_break_counts():
    fake = FakeMarketSentimentPro()
    svc = RiskBreakdownService()
    svc._pro = fake

    sentiment = svc._get_market_sentiment("20260508")

    assert sentiment["limit_up_count"] == 2
    assert sentiment["limit_down_count"] == 1
    assert sentiment["up_down_ratio"] == 2
    assert sentiment["zhaban_rate"] == 25
    assert not any(name == "limit_list_ths" for name, _ in fake.calls)
