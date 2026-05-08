from backend.services.tdx_selector import TdxSelectorService, create_default_task


def test_phase1_does_not_filter_on_phase2_metrics():
    def fake_mcp(**kwargs):
        return {
            "meta": {"code": 0, "total": 1},
            "headers": [
                "POS", "market", "sec_code", "sec_name", "now_price", "chg0#",
                "所属行业", "涨停次数", "竞昨比", "竞价换手率",
            ],
            "data": [[1, "SZ", "000889", "中嘉博创", 12.34, 10.02, "通信设备", 0, 0.01, 0.01]],
        }

    result = TdxSelectorService()._execute_task(create_default_task(), fake_mcp)

    assert result["total_count"] == 1
    assert result["stocks"][0].ts_code == "000889.SZ"
