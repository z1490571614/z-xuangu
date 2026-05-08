from backend.services.risk_breakdown_service import RiskBreakdownService


def test_lhb_tags_distinguish_institution_northbound_and_premium_trader():
    from backend.services.lhb_service import _build_seat_tags_list, _generate_tags

    buy_details = _build_seat_tags_list([
        {"exalter": "机构专用", "side": 0, "buy": 30000000, "sell": 0, "net_buy": 30000000},
        {"exalter": "沪股通专用", "side": 0, "buy": 25000000, "sell": 0, "net_buy": 25000000},
        {
            "exalter": "中信证券股份有限公司大连黄河路证券营业部",
            "side": 0,
            "buy": 20000000,
            "sell": 0,
            "net_buy": 20000000,
        },
    ], service=None)

    tags = _generate_tags(buy_details, [], "一致抢筹", 75000000)

    assert "机构净买入" in tags
    assert "北向加仓" in tags
    assert "顶级游资买入" in tags


def test_lhb_risk_allows_institutional_premium_to_offset_weak_seat(monkeypatch):
    from backend.services import lhb_service

    def fake_analyze_lhb(ts_code, trade_date, force_refresh=False):
        return {
            "data_status": "available",
            "action_tag": "主力分歧",
            "net_amount": 0,
            "buy_top5": [{"exalter": "机构专用"}],
            "sell_top5": [{"exalter": "东方财富证券拉萨团结路"}],
            "risk_tips": [],
        }

    monkeypatch.setattr(lhb_service, "analyze_lhb", fake_analyze_lhb)

    score, tips = RiskBreakdownService()._calc_lhb_risk("000001.SZ", "20260508")

    assert score == 1
    assert tips == []


def test_lhb_risk_exposes_strength_and_risk_seat_names(monkeypatch):
    from backend.services import lhb_service

    def fake_analyze_lhb(ts_code, trade_date, force_refresh=False):
        return {
            "data_status": "available",
            "action_tag": "主力分歧",
            "net_amount": 0,
            "buy_top5": [
                {"exalter": "中信证券股份有限公司大连黄河路证券营业部"},
                {"exalter": "机构专用"},
            ],
            "sell_top5": [
                {"exalter": "华泰证券股份有限公司成都南一环路证券营业部"},
                {"exalter": "东方财富证券拉萨团结路"},
            ],
            "risk_tips": ["核按钮席位卖出"],
        }

    monkeypatch.setattr(lhb_service, "analyze_lhb", fake_analyze_lhb)

    svc = RiskBreakdownService()
    score, tips = svc._calc_lhb_risk("000001.SZ", "20260508")

    assert score >= 0
    assert "核按钮席位" in tips
    assert svc._last_lhb_strength_evidence == [
        {
            "type": "premium_buy",
            "label": "高溢价席位买入",
            "seats": ["中信证券股份有限公司大连黄河路证券营业部", "机构专用"],
            "score_effect": "抵扣龙虎风险，进入强势依据",
        }
    ]
    assert svc._last_lhb_risk_evidence == [
        {
            "type": "dump_sell",
            "label": "砸盘席位卖出",
            "seats": [
                "华泰证券股份有限公司成都南一环路证券营业部",
                "东方财富证券拉萨团结路",
            ],
            "score_effect": "增加龙虎风险",
        }
    ]
