import pandas as pd

from backend.services.risk_breakdown_service import (
    RiskBreakdownService,
)


class FakeTusharePro:
    def __init__(self):
        self.ths_called = False

    def ths_daily(self, **kwargs):
        self.ths_called = True
        raise AssertionError("sector risk must use DcBoardService, not ths_daily")

    def moneyflow_cnt_ths(self, **kwargs):
        self.ths_called = True
        raise AssertionError("sector risk must use Eastmoney board moneyflow")

    def moneyflow_ind_ths(self, **kwargs):
        self.ths_called = True
        raise AssertionError("sector risk must use Eastmoney board moneyflow")


class FakeDcBoardService:
    def __init__(self):
        self.stock_board_called = False
        self.daily_called = False
        self.moneyflow_called = False
        self.strength_called = False

    def get_stock_boards(self, ts_code, trade_date=None, refresh_if_missing=False):
        self.stock_board_called = True
        assert ts_code == "000889.SZ"
        assert trade_date == "20260507"
        assert refresh_if_missing is True
        return [
            {"ts_code": "BK0448.DC", "name": "通信设备", "type": "行业板块", "source": "eastmoney"},
            {"ts_code": "BK1160.DC", "name": "算力租赁", "type": "概念板块", "source": "eastmoney"},
        ]

    def normalize_board_terms(self, text, source, top_n=5):
        if "算力" in text or "智算" in text:
            return [{
                "ts_code": "BK1160.DC",
                "name": "算力租赁",
                "type": "概念板块",
                "source": "eastmoney",
                "match_score": 120,
                "matched_from": source,
            }]
        if "通信" in text:
            return [{
                "ts_code": "BK0448.DC",
                "name": "通信设备",
                "type": "行业板块",
                "source": "eastmoney",
                "match_score": 100,
                "matched_from": source,
            }]
        return []

    def get_board_daily(self, board_code, trade_date):
        self.daily_called = True
        assert board_code == "BK1160.DC"
        return {
            "board_code": board_code,
            "trade_date": trade_date,
            "pct_chg": -2.1,
            "amount": 8000000000,
            "turnover_rate": 5.2,
        }

    def get_board_moneyflow(self, board_code, trade_date):
        self.moneyflow_called = True
        assert board_code == "BK1160.DC"
        return {
            "board_code": board_code,
            "trade_date": trade_date,
            "net_amount": -320000000,
            "net_amount_yi": -3.2,
        }

    def get_board_strength(self, board_code, trade_date):
        self.strength_called = True
        assert board_code == "BK1160.DC"
        return {
            "board_code": board_code,
            "trade_date": trade_date,
            "limit_up_count": 2,
            "member_count": 80,
            "strength_score": 42,
            "board_pct_chg": -2.1,
            "money_net_amount": -320000000,
        }


def make_service(fake_pro):
    svc = RiskBreakdownService()
    svc._pro = fake_pro
    svc._board_service = FakeDcBoardService()
    return svc


def test_resolve_sector_board_prefers_lu_desc_over_static_industry():
    svc = make_service(FakeTusharePro())

    board = svc._resolve_sector_board("000889.SZ", {
        "industry": "通信设备",
        "concept": "",
        "lu_desc": "算力租赁+通信运维+5G消息+亏损收窄",
    }, "20260507")

    assert board["ts_code"] == "BK1160.DC"
    assert board["name"] == "算力租赁"
    assert board["type"] == "概念板块"
    assert board["source"] == "eastmoney"


def test_resolve_sector_board_uses_industry_when_no_theme_text():
    svc = make_service(FakeTusharePro())

    board = svc._resolve_sector_board("000889.SZ", {
        "industry": "通信设备",
        "concept": "",
        "lu_desc": "",
    }, "20260507")

    assert board["ts_code"] == "BK0448.DC"
    assert board["name"] == "通信设备"


def test_calc_sector_risk_uses_eastmoney_board_snapshots():
    fake_pro = FakeTusharePro()
    svc = make_service(fake_pro)

    score, tips = svc._calc_sector_risk("000889.SZ", {
        "industry": "通信设备",
        "concept": "",
        "lu_desc": "算力租赁+通信运维+5G消息+亏损收窄",
    }, "20260507")

    assert score == 7
    assert "算力租赁板块下跌2.1%，题材承接转弱" in tips
    assert "板块资金净流出3.2亿" in tips
    assert "板块内涨停扩散不足，仅2家涨停" in tips
    assert not any("匹配" in tip or "归一" in tip for tip in tips)
    assert fake_pro.ths_called is False
    assert svc._board_service.daily_called is True
    assert svc._board_service.moneyflow_called is True
    assert svc._board_service.strength_called is True


def test_calc_sector_risk_appends_cached_theme_attribution_tips():
    fake_pro = FakeTusharePro()
    svc = make_service(fake_pro)
    svc._get_cached_theme_attribution_for_risk = lambda ts_code, trade_date: {
        "primary_theme": "算力租赁",
        "explanation_lines": [
            "主跟随题材：算力租赁",
            "板块归因证据，不构成个股利好/利空判断",
        ],
    }

    score, tips = svc._calc_sector_risk("000889.SZ", {
        "industry": "通信设备",
        "concept": "",
        "lu_desc": "算力租赁+通信运维+5G消息+亏损收窄",
    }, "20260507")

    assert score == 7
    assert "主跟随题材：算力租赁" in tips
    assert "板块归因证据，不构成个股利好/利空判断" in tips


def test_append_theme_attribution_tips_distinguishes_sector_news_from_good_news():
    svc = make_service(FakeTusharePro())
    tips = ["PCB概念板块下跌1.5%，题材承接转弱"]
    attribution = {
        "primary_theme": "PCB概念",
        "explanation_lines": [
            "主跟随题材：PCB概念",
            "新闻《PCB概念股盘初拉升》点名合力泰跟涨",
            "板块归因证据，不构成个股利好/利空判断",
        ],
    }

    result = svc._append_theme_attribution_tips(tips, attribution)

    assert "主跟随题材：PCB概念" in result
    assert "板块归因证据，不构成个股利好/利空判断" in result
