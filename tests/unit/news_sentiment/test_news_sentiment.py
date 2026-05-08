"""测试用例——覆盖情感判定.md第16节全部场景"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
os.environ.setdefault("TUSHARE_TOKEN", "test")

from backend.services.news_sentiment.analyzer import analyze_news_event


def test_carrier_words_not_affect():
    """16.1 载体词不影响判断"""
    r = analyze_news_event({"title": "公司公告称，2024年净利润同比增长1309.44%", "content": "", "source": "公告"})
    assert r["event_type"] == "performance"
    assert r["sentiment"] == "positive"
    assert r["score"] >= 2.5


def test_slight_performance_drop():
    """16.2 小幅业绩下降"""
    r = analyze_news_event({"title": "公司2024年净利润同比下降9.73%", "content": ""})
    assert r["event_type"] == "performance"
    assert r["score"] > -1.5
    assert r["sentiment"] in ("negative", "neutral")


def test_large_performance_drop():
    """16.3 大幅业绩下降"""
    r = analyze_news_event({"title": "公司2024年净利润同比下降85%", "content": ""})
    assert r["event_type"] == "performance"
    assert r["sentiment"] == "negative"
    assert r["score"] <= -2.0


def test_turnaround():
    """16.4 扭亏为盈"""
    r = analyze_news_event({"title": "公司预计2024年实现扭亏为盈", "content": ""})
    assert r["event_type"] == "performance"
    assert r["sentiment"] == "positive"
    assert r["score"] > 1.0
    assert r["certainty"] == "forecast"


def test_loss_expanding():
    """16.5 亏损扩大"""
    r = analyze_news_event({"title": "公司预计2024年亏损扩大", "content": ""})
    assert r["event_type"] == "performance"
    assert r["sentiment"] == "negative"
    assert r["score"] <= -2.0


def test_terminate_restructure():
    """16.6 终止重组"""
    r = analyze_news_event({"title": "公司决定终止重大资产重组事项", "content": ""})
    assert r["event_type"] == "restructure"
    assert r["sentiment"] == "negative"
    assert r["score"] <= -3.0


def test_planning_restructure_uncertain():
    """16.7 筹划重组存在不确定性"""
    r = analyze_news_event({"title": "公司正在筹划重大资产重组事项，尚存在不确定性", "content": ""})
    assert r["event_type"] == "restructure"
    assert r["score"] > 0
    assert r["certainty"] == "uncertain"


def test_passive_reduce():
    """16.8 被动减持"""
    r = analyze_news_event({"title": "控股股东因股票质押违约存在被动减持风险", "content": ""})
    assert r["event_type"] == "reduce_holding"
    assert r["sentiment"] == "negative"
    assert r["score"] < 0


def test_clearance_reduce():
    """16.9 清仓式减持"""
    r = analyze_news_event({"title": "持股5%以上股东拟清仓式减持公司股份", "content": ""})
    assert r["event_type"] == "reduce_holding"
    assert r["sentiment"] == "negative"
    assert r["score"] <= -3.0


def test_small_buyback():
    """16.10 小额回购"""
    r = analyze_news_event({"title": "公司拟以1000万元至2000万元回购股份", "content": ""})
    assert r["event_type"] == "buyback"
    assert r["sentiment"] in ("positive", "neutral")


def test_large_contract():
    """16.11 大额合同"""
    context = {"last_year_revenue": 1_000_000_000}
    r = analyze_news_event({"title": "公司签订5亿元重大销售合同", "content": ""}, context=context)
    assert r["event_type"] == "order_contract"
    assert r["sentiment"] == "positive"
    assert r["score"] >= 2.0


def test_market_overview_should_not_be_assigned_to_single_stock_without_target():
    """14.1 多股盘面综述不应直接判单股利好"""
    title = "竞价看龙头"
    content = "市场焦点股沃格光电高开3.00%，华升股份高开5.82%，宏英智能高开6.02%。今日市场情绪整体回暖。"
    r = analyze_news_event({"title": title, "content": content, "stock_name": ""})
    assert r["event_type"] == "market_overview"
    assert r["event_subtype"] == "multi_stock_overview"
    assert r["score"] == 0.0


def test_multi_stock_news_should_be_unrelated_if_target_not_found():
    """14.2 多股新闻中目标股票未出现"""
    title = "竞价看龙头"
    content = "沃格光电高开3.00%，宏英智能高开6.02%，市场情绪整体回暖。"
    r = analyze_news_event({"title": title, "content": content, "stock_name": "狮头股份"})
    assert r["event_type"] == "unrelated"
    assert r["score"] == 0.0


def test_multi_stock_news_target_price_action_neutral():
    """14.3 多股新闻中目标股票仅有涨停/连板等盘面描述，应判中性"""
    title = "竞价看龙头"
    content = "业绩超预期的飞马国际高开1.51%、宏英智能高开6.02%，宏英智能拿下2连板。"
    r = analyze_news_event({"title": title, "content": content, "stock_name": "宏英智能"})
    assert r["event_type"] == "market_overview"
    assert r["sentiment"] == "neutral"
    assert r["score"] == 0.0


def test_sector_intraday_rally_news_should_be_neutral_for_target_stock():
    """概念盘初拉升类新闻，只提到目标股票涨停/跟涨，应判中性"""
    title = "算力租赁板块盘初拉升，东阳光涨停"
    content = "算力租赁板块盘初拉升，东阳光涨停，平治信息、东方国信涨超10%，合力泰、朗科科技、行云科技、安诺其、大位科技跟涨。"
    r = analyze_news_event({"title": title, "content": content, "stock_name": "合力泰"})
    assert r["event_type"] == "market_overview"
    assert r["sentiment"] == "neutral"
    assert r["score"] == 0.0


def test_roundup_news_selected_should_not_be_assigned_to_target_stock_risk():
    """新闻精选/汇总类文本即使提到个股和监管词，也不归因为该股利空"""
    title = "财联社4月30日早间新闻精选"
    content = (
        "1、证监会表示将加强上市公司监管。"
        "2、国晟科技发布股票交易异常波动公告。"
        "3、多家公司披露一季报，部分公司净利润同比下降。"
        "4、机器人板块、算力租赁板块盘面活跃，多股涨停。"
    )
    r = analyze_news_event({"title": title, "content": content, "stock_name": "国晟科技", "source": "cls"})
    assert r["event_type"] == "market_overview"
    assert r["event_subtype"] == "target_stock_mention"
    assert r["sentiment"] == "neutral"
    assert r["score"] == 0.0


def test_single_stock_trading_risk_warning_should_be_weak_negative():
    """个股交易风险提示/高估值/业绩风险提示应判为轻度利空"""
    title = "国晟科技：股票自年初至5月8日期间累计涨幅达53.35% 市净率远高于行业平均水平"
    content = (
        "国晟科技发布股票交易风险提示公告称，公司股票价格短期波动较大。"
        "截至5月8日，公司市净率为60.58，远高于行业平均水平。"
        "敬请广大投资者注意二级市场交易风险，注意公司业绩风险，审慎投资。"
    )
    r = analyze_news_event({"title": title, "content": content, "stock_name": "国晟科技", "source": "公告"})
    assert r["event_type"] == "risk_warning"
    assert r["event_subtype"] == "trading_risk_warning"
    assert r["sentiment"] == "negative"
    assert r["impact_level"] == "weak"
    assert -1.5 < r["score"] <= -0.3


def test_yoy_drop_with_qoq_turnaround_should_not_be_positive():
    """14.4 同比下降+环比扭亏不能判利好"""
    r = analyze_news_event({"title": "狮头股份：第一季度净利润同比下降9.73%",
                            "content": "营业收入1.14亿元，同比下降2.32%；净利润52.63万元，同比下降9.73%。Q1净利润环比扭亏为盈。"})
    assert r["event_type"] == "performance"
    assert r["sentiment"] == "negative"
    assert r["score"] < 0


def test_small_yoy_drop_should_be_weak_negative_not_neutral():
    """14.5 同比小幅下降不能判中性"""
    r = analyze_news_event({"title": "狮头股份：第一季度净利润52.63万元，同比下降9.73%",
                            "content": "营业收入1.14亿元，同比下降2.32%。净利润52.63万元，同比下降9.73%。"})
    assert r["event_type"] == "performance"
    assert r["sentiment"] == "negative"
    assert r["impact_level"] == "weak"


def test_framework_agreement():
    """16.12 框架协议"""
    r = analyze_news_event({"title": "公司与某客户签署战略合作框架协议，具体金额以后续订单为准", "content": ""})
    assert r["event_type"] == "order_contract"
    assert r["certainty"] == "framework"


def test_regulatory_investigation():
    """16.13 立案调查"""
    r = analyze_news_event({"title": "公司因涉嫌信息披露违法违规被证监会立案调查", "content": ""})
    assert r["event_type"] == "regulatory"
    assert r["sentiment"] == "negative"
    assert r["score"] <= -3.0


def test_process_meeting():
    """16.14 流程公告"""
    r = analyze_news_event({"title": "公司召开2024年度股东大会", "content": ""})
    assert r["event_type"] == "process"
    assert r["sentiment"] == "neutral"
    assert r["score"] == 0


def test_mixed_positive_negative():
    """16.15 多空混合"""
    r = analyze_news_event({"title": "公司净利润同比增长200%，但因涉嫌信息披露违法违规被立案调查", "content": ""}, debug=True)
    assert r["event_type"] == "regulatory"
    assert "performance" in str(r.get("debug_info", {}).get("detected_event_candidates", []))
    assert r["sentiment"] in ("negative", "mixed")
    assert r["score"] < 0


def test_output_structure():
    """验证输出结构完整"""
    r = analyze_news_event({"title": "公司净利润同比下降9.73%", "content": ""}, debug=True)
    required_fields = ["sentiment", "score", "raw_score", "event_type", "event_subtype",
                       "impact_level", "confidence", "certainty", "certainty_factor",
                       "facts", "matched_rules", "risk_flags", "reason"]
    for field in required_fields:
        assert field in r, f"缺少字段: {field}"
    assert "debug_info" in r


def test_normalizer_removes_whitespace():
    from backend.services.news_sentiment.normalizer import normalize_text
    t = normalize_text(" 公告称 净利润 增 长 ", " 内 容 ")
    assert " " not in t


def test_score_range():
    """分数应在[-5,5]范围内"""
    texts = [
        ("强制退市", ""),
        ("净利润同比增长300%", ""),
        ("公司召开股东大会", ""),
    ]
    for title, content in texts:
        r = analyze_news_event({"title": title, "content": content})
        assert -5.0 <= r["score"] <= 5.0, f"{title}: score={r['score']} 超出范围"
