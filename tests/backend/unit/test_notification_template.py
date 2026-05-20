from backend.services.notification import FeishuNotifier


def _card_markdown(message):
    return message["card"]["elements"][0]["content"]


def test_selection_message_uses_limit_probability_template_sorted_desc():
    notifier = FeishuNotifier(webhook_url="https://example.invalid/webhook")

    message = notifier.build_selection_message(
        {
            "trade_date": "20260520",
            "passed_count": 3,
            "execution_time": 1.23,
            "stocks": [
                {
                    "name": "低概率",
                    "ts_code": "000001.SZ",
                    "lu_tag": "首板",
                    "open_change_pct": 1.2,
                    "pre_change_pct": 2.3,
                    "default_t0_limit_prob": 12.3,
                },
                {
                    "name": "高概率",
                    "ts_code": "000002.SZ",
                    "lu_tag": "3天3板",
                    "open_change_pct": 10.0,
                    "pre_change_pct": 9.9,
                    "default_t0_limit_prob": 72.1,
                },
                {
                    "name": "中概率",
                    "ts_code": "000003.SZ",
                    "lu_tag": "换手板",
                    "open_change_pct": 5.5,
                    "pre_change_pct": 6.6,
                    "default_t0_limit_prob": 46.8,
                },
            ],
        }
    )

    content = _card_markdown(message)

    assert "当日涨停概率" in content
    assert "涨停标签" in content
    assert content.index("高概率") < content.index("中概率") < content.index("低概率")
    assert "高概率 000002.SZ" in content
    assert "涨停标签：3天3板" in content
    assert "开涨幅：10.00%" in content
    assert "昨涨幅：9.90%" in content
    assert "当日涨停概率：72.1%" in content
