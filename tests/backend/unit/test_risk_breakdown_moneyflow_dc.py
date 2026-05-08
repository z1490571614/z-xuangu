import pandas as pd

from backend.services.risk_breakdown_service import RiskBreakdownService


class FakeMoneyflowDcPro:
    def __init__(self):
        self.calls = []

    def moneyflow_dc(self, **kwargs):
        self.calls.append(("moneyflow_dc", kwargs))
        return pd.DataFrame([{
            "ts_code": kwargs["ts_code"],
            "trade_date": kwargs["trade_date"],
            "buy_elg_amount": 1000,
            "sell_elg_amount": 7000,
            "net_mf_amount": -1000,
        }])

    def moneyflow(self, **kwargs):
        self.calls.append(("moneyflow", kwargs))
        return pd.DataFrame([{
            "ts_code": kwargs["ts_code"],
            "trade_date": kwargs["trade_date"],
            "net_mf_amount": 8000,
        }])


class FakeFallbackMoneyflowPro:
    def __init__(self):
        self.calls = []

    def moneyflow_dc(self, **kwargs):
        self.calls.append(("moneyflow_dc", kwargs))
        return pd.DataFrame()

    def moneyflow(self, **kwargs):
        self.calls.append(("moneyflow", kwargs))
        return pd.DataFrame([{
            "ts_code": kwargs["ts_code"],
            "trade_date": kwargs["trade_date"],
            "net_mf_amount": -2500,
        }])


def test_capital_risk_prefers_eastmoney_super_large_order_net_amount():
    fake = FakeMoneyflowDcPro()
    svc = RiskBreakdownService()
    svc._pro = fake

    score, tips = svc._calc_capital_risk("000001.SZ", "20260508")

    assert score == 10
    assert tips == ["超大单净流出6000万元，资金出逃明显"]
    assert fake.calls == [("moneyflow_dc", {"ts_code": "000001.SZ", "trade_date": "20260508"})]


def test_capital_risk_falls_back_to_legacy_moneyflow_when_dc_missing():
    fake = FakeFallbackMoneyflowPro()
    svc = RiskBreakdownService()
    svc._pro = fake

    score, tips = svc._calc_capital_risk("000001.SZ", "20260508")

    assert score == 6
    assert tips == ["主力净流出2500万元"]
    assert fake.calls == [
        ("moneyflow_dc", {"ts_code": "000001.SZ", "trade_date": "20260508"}),
        ("moneyflow", {"ts_code": "000001.SZ", "trade_date": "20260508"}),
    ]
