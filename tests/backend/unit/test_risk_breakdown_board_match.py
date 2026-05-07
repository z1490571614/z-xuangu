import pandas as pd

from backend.services.risk_breakdown_service import (
    RiskBreakdownService,
    _THS_BOARD_CACHE,
    _THS_INDUSTRY_CACHE,
)


class FakeTusharePro:
    def __init__(self):
        self.ind_moneyflow_called = False
        self.cnt_moneyflow_called = False

    def ths_member(self, con_code=None, ts_code=None, fields=None):
        if con_code == "000889.SZ":
            return pd.DataFrame([
                {"ts_code": "881162.TI", "con_code": "000889.SZ", "con_name": "中嘉博创", "is_new": "Y"},
                {"ts_code": "884314.TI", "con_code": "000889.SZ", "con_name": "中嘉博创", "is_new": "Y"},
                {"ts_code": "886050.TI", "con_code": "000889.SZ", "con_name": "中嘉博创", "is_new": "Y"},
            ])
        return pd.DataFrame()

    def ths_index(self, fields=None):
        return pd.DataFrame([
            {"ts_code": "881162.TI", "name": "通信服务", "type": "I", "count": 45},
            {"ts_code": "884314.TI", "name": "通信工程及服务", "type": "I", "count": 12},
            {"ts_code": "886050.TI", "name": "算力租赁", "type": "N", "count": 156},
            {"ts_code": "881134.TI", "name": "食品加工制造", "type": "I", "count": 82},
        ])

    def ths_daily(self, ts_code=None, trade_date=None):
        assert ts_code == "886050.TI"
        return pd.DataFrame([{"ts_code": ts_code, "trade_date": trade_date, "pct_change": 2.74}])

    def moneyflow_cnt_ths(self, ts_code=None, trade_date=None):
        self.cnt_moneyflow_called = True
        assert ts_code == "886050.TI"
        return pd.DataFrame([{"ts_code": ts_code, "trade_date": trade_date, "net_amount": 3.0}])

    def moneyflow_ind_ths(self, ts_code=None, trade_date=None):
        self.ind_moneyflow_called = True
        return pd.DataFrame([{"ts_code": ts_code, "trade_date": trade_date, "net_amount": -8.0}])


def make_service(fake_pro):
    svc = RiskBreakdownService()
    svc._pro = fake_pro
    return svc


def setup_function():
    _THS_BOARD_CACHE.clear()
    _THS_INDUSTRY_CACHE.clear()


def test_resolve_sector_board_prefers_lu_desc_concept_over_static_industry():
    svc = make_service(FakeTusharePro())

    board = svc._resolve_sector_board("000889.SZ", {
        "industry": "通信设备",
        "concept": "",
        "lu_desc": "算力租赁+通信运维+5G消息+亏损收窄",
    })

    assert board["ts_code"] == "886050.TI"
    assert board["name"] == "算力租赁"
    assert board["type"] == "N"


def test_static_industry_mapping_no_longer_maps_communication_to_food():
    svc = make_service(FakeTusharePro())

    assert svc._get_ths_industry_code("000889.SZ", "通信设备") == "881129.TI"
    assert svc._get_ths_industry_code("000889.SZ", "通信") == "881162.TI"


def test_calc_sector_risk_uses_concept_moneyflow_for_concept_board():
    fake_pro = FakeTusharePro()
    svc = make_service(fake_pro)

    score, tips = svc._calc_sector_risk("000889.SZ", {
        "industry": "通信设备",
        "concept": "",
        "lu_desc": "算力租赁+通信运维+5G消息+亏损收窄",
    }, "20260507")

    assert score == 0
    assert "匹配板块：算力租赁(886050.TI)" in tips
    assert fake_pro.cnt_moneyflow_called is True
    assert fake_pro.ind_moneyflow_called is False
