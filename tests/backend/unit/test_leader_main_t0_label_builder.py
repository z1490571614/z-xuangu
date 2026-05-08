from backend.services.backtest.leader_main_t0_label_builder import (
    build_label_from_daily_row,
    calculate_limit_up_price,
    is_one_line_limit_up,
)


def test_is_one_line_limit_up_requires_all_prices_near_limit():
    assert is_one_line_limit_up(
        {"open": 10.0, "high": 10.0, "low": 9.98, "close": 10.0},
        limit_up_price=10.0,
    )

    assert not is_one_line_limit_up(
        {"open": 9.5, "high": 10.0, "low": 9.4, "close": 10.0},
        limit_up_price=10.0,
    )


def test_build_label_excludes_one_line_limit_up_from_training():
    label = build_label_from_daily_row(
        {"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "pre_close": 9.09},
        ts_code="000001.SZ",
    )

    assert label["is_one_line_limit_up"] == 1
    assert label["label_t0_limit_success"] is None
    assert label["t0_touched_limit"] == 1
    assert label["t0_closed_limit"] == 1


def test_build_label_marks_non_one_line_closed_limit_as_success():
    label = build_label_from_daily_row(
        {"open": 9.45, "high": 10.0, "low": 9.4, "close": 9.98, "pre_close": 9.09},
        ts_code="000001.SZ",
    )

    assert label["is_one_line_limit_up"] == 0
    assert label["label_t0_limit_success"] == 1
    assert label["t0_touched_limit"] == 1
    assert label["t0_closed_limit"] == 1
    assert label["t0_high_return"] == 10.01


def test_calculate_limit_up_price_uses_twenty_percent_for_chinext_and_star():
    assert calculate_limit_up_price("300001.SZ", 10.0) == 12.0
    assert calculate_limit_up_price("688001.SH", 10.0) == 12.0
    assert calculate_limit_up_price("000001.SZ", 10.0) == 11.0
