from types import SimpleNamespace

from backend.services.stock_alias_service import StockAliasService


def test_build_aliases_from_stock_basic_rows_includes_fullname_code_and_no_space_name():
    rows = [
        SimpleNamespace(
            ts_code="002081.SZ",
            symbol="002081",
            name="金 螳 螂",
            fullname="苏州金螳螂建筑装饰股份有限公司",
            list_status="L",
        )
    ]

    aliases = StockAliasService.build_aliases_from_rows(rows)

    assert aliases["金螳螂"] == "002081.SZ"
    assert aliases["苏州金螳螂建筑装饰股份有限公司"] == "002081.SZ"
    assert aliases["002081"] == "002081.SZ"
    assert aliases["002081.SZ"] == "002081.SZ"


def test_build_aliases_filters_indexes_etf_and_delisted_rows():
    rows = [
        SimpleNamespace(ts_code="000001.SH", symbol="000001", name="上证指数", fullname="", list_status="L"),
        SimpleNamespace(ts_code="159915.SZ", symbol="159915", name="创业板ETF", fullname="", list_status="L"),
        SimpleNamespace(ts_code="000002.SZ", symbol="000002", name="万 科 A", fullname="万科企业股份有限公司", list_status="D"),
        SimpleNamespace(ts_code="002217.SZ", symbol="002217", name="合力泰", fullname="合力泰科技股份有限公司", list_status="L"),
    ]

    aliases = StockAliasService.build_aliases_from_rows(rows)

    assert "上证指数" not in aliases
    assert "创业板ETF" not in aliases
    assert "万科A" not in aliases
    assert aliases["合力泰"] == "002217.SZ"
