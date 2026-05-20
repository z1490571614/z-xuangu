import json

from backend.database import Base, engine
from backend.models import DefaultAuctionTrainingSample, ModelVersion
from backend.models.seal_rate import StockDailyData


def _reset_t0_backtest_test_data(db):
    from backend.models import T0SimulationBacktestDaily, T0SimulationBacktestRun, T0SimulationBacktestTrade

    Base.metadata.create_all(bind=engine)
    db.query(T0SimulationBacktestTrade).delete()
    db.query(T0SimulationBacktestDaily).delete()
    db.query(T0SimulationBacktestRun).delete()
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockDailyData).delete()
    db.query(ModelVersion).filter(ModelVersion.model_name == "default_auction_t0_limit_lgbm").delete()
    db.commit()


def _add_model_version(db):
    db.add(
        ModelVersion(
            model_name="default_auction_t0_limit_lgbm",
            version="v_test",
            model_path="fake.pkl",
            feature_cols=json.dumps(["score"]),
            model_metrics="{}",
            params=json.dumps({"feature_units": {}}),
            is_active=1,
        )
    )


def _as_model_probability(score):
    return score * 100 if 0 <= score <= 1 else score


def _as_label_probability(score):
    return score / 100 if score > 1 else score


def _add_sample(db, trade_date, ts_code, name, score, source="replay_backtest", is_one_line_limit_up=0):
    db.add(
        DefaultAuctionTrainingSample(
            trade_date=trade_date,
            ts_code=ts_code,
            name=name,
            strategy_name="default",
            strategy_version="default_auction_v2",
            sample_source=source,
            feature_json=json.dumps({"score": _as_model_probability(score)}),
            label_t0_limit_success=1 if _as_label_probability(score) >= 0.8 else 0,
            is_t0_one_line_limit_up=is_one_line_limit_up,
        )
    )


def _add_sample_with_features(db, trade_date, ts_code, name, score, features, source="replay_backtest", is_one_line_limit_up=0):
    payload = {"score": _as_model_probability(score), **features}
    db.add(
        DefaultAuctionTrainingSample(
            trade_date=trade_date,
            ts_code=ts_code,
            name=name,
            strategy_name="default",
            strategy_version="default_auction_v2",
            sample_source=source,
            feature_json=json.dumps(payload),
            label_t0_limit_success=1 if _as_label_probability(score) >= 0.8 else 0,
            is_t0_one_line_limit_up=is_one_line_limit_up,
        )
    )


def _add_daily(db, trade_date, ts_code, open_price, close_price, up_limit=None, down_limit=None, high_price=None, low_price=None):
    db.add(
        StockDailyData(
            trade_date=trade_date,
            ts_code=ts_code,
            open=open_price,
            high=max(open_price, close_price) if high_price is None else high_price,
            low=min(open_price, close_price) if low_price is None else low_price,
            close=close_price,
            pre_close=open_price,
            up_limit=up_limit,
            down_limit=down_limit,
            is_adj=1,
        )
    )


def test_t0_simulation_backtest_buys_top2_and_never_exceeds_four_positions(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    for idx, score in enumerate([0.95, 0.90, 0.85], start=1):
        code = f"00000{idx}.SZ"
        _add_sample(db, "20240501", code, f"股票{idx}", score)
        _add_daily(db, "20240501", code, 10, 10.2)
        _add_daily(db, "20240502", code, 10.2, 10.4)
        _add_daily(db, "20240503", code, 10.4, 10.5)
    for idx, score in enumerate([0.99, 0.98, 0.97], start=4):
        code = f"00000{idx}.SZ"
        _add_sample(db, "20240502", code, f"股票{idx}", score)
        _add_daily(db, "20240502", code, 10, 10.1)
        _add_daily(db, "20240503", code, 10.1, 10.2)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    request = service.T0SimulationBacktestCreate(
        start_date="20240501",
        end_date="20240503",
        initial_cash=100000,
        take_profit_pct=50,
        stop_loss_pct=-50,
        max_holding_days=10,
    )
    run = service.create_t0_simulation_backtest_run(db, request)

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).order_by(T0SimulationBacktestTrade.id).all()
    assert payload["summary"]["open_position_count"] == 4
    assert len(trades) == 4
    assert [trade.ts_code for trade in trades] == ["000001.SZ", "000002.SZ", "000004.SZ", "000005.SZ"]
    assert all(trade.buy_time == "09:30" for trade in trades)
    assert all(trade.status == "open" for trade in trades)


def test_t0_simulation_backtest_skips_candidates_below_min_buy_probability(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    for idx, score in enumerate([70.0, 50.0, 49.0], start=1):
        code = f"00000{idx}.SZ"
        _add_sample(db, "20240501", code, f"概率股{idx}", score)
        _add_daily(db, "20240501", code, 10, 10.2)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            initial_cash=100000,
            buy_top_n=3,
            max_positions=3,
            min_buy_prob_pct=50,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).order_by(T0SimulationBacktestTrade.id).all()
    assert [trade.ts_code for trade in trades] == ["000001.SZ", "000002.SZ"]
    assert [trade.model_prob for trade in trades] == [70.0, 50.0]
    assert payload["min_buy_prob_pct"] == 50
    assert payload["summary"]["open_position_count"] == 2
    assert payload["summary"]["skipped_buy_count"] == 1


def test_t0_simulation_backtest_min_buy_probability_uses_percent_unit(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    for idx, score in enumerate([70.0, 50.0, 49.0], start=1):
        code = f"00000{idx}.SZ"
        _add_sample(db, "20240501", code, f"百分概率股{idx}", score)
        _add_daily(db, "20240501", code, 10, 10.2)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            initial_cash=100000,
            buy_top_n=3,
            max_positions=3,
            min_buy_prob_pct=50,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).order_by(T0SimulationBacktestTrade.id).all()
    assert [trade.ts_code for trade in trades] == ["000001.SZ", "000002.SZ"]
    assert [trade.model_prob for trade in trades] == [70.0, 50.0]
    assert payload["summary"]["skipped_low_prob_count"] == 1


def test_t0_simulation_backtest_skips_open_change_below_min_threshold(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample_with_features(db, "20240501", "000001.SZ", "低开过滤", 0.95, {"open_change_pct": -3.1})
    _add_sample_with_features(db, "20240501", "000002.SZ", "刚好通过", 0.90, {"open_change_pct": -3.0})
    _add_daily(db, "20240501", "000001.SZ", 9.69, 10.0)
    _add_daily(db, "20240501", "000002.SZ", 9.70, 10.0)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            initial_cash=100000,
            buy_top_n=2,
            max_positions=2,
            min_open_change_pct=-3,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).all()
    assert [trade.ts_code for trade in trades] == ["000002.SZ"]
    assert payload["min_open_change_pct"] == -3
    assert payload["summary"]["skipped_low_open_change_count"] == 1
    assert payload["summary"]["skipped_buy_count"] == 1


def test_t0_simulation_backtest_carries_last_close_when_holding_price_missing(db, monkeypatch):
    from backend.models import T0SimulationBacktestDaily
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "缺日线持仓", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 11)
    _add_daily(db, "20240502", "000999.SZ", 20, 20)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240502",
            initial_cash=100000,
            buy_top_n=1,
            max_positions=4,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    day1 = db.query(T0SimulationBacktestDaily).filter_by(run_id=run.id, trade_date="20240501").one()
    day2 = db.query(T0SimulationBacktestDaily).filter_by(run_id=run.id, trade_date="20240502").one()
    assert day1.market_value == 27500.0
    assert day2.market_value == 27500.0
    assert day2.equity == day1.equity
    assert day2.daily_return_pct == 0.0
    assert payload["summary"]["missing_price_count"] == 1


def test_t0_simulation_backtest_sells_by_stop_loss_and_max_holding_days(db, monkeypatch):
    from backend.models import T0SimulationBacktestDaily, T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "止盈股", 0.95)
    _add_sample(db, "20240501", "000002.SZ", "止损股", 0.90)
    _add_sample(db, "20240501", "000003.SZ", "未入选", 0.80)
    _add_daily(db, "20240501", "000001.SZ", 10, 10.9)
    _add_daily(db, "20240501", "000002.SZ", 20, 18.8)
    _add_daily(db, "20240501", "000003.SZ", 30, 31)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            initial_cash=100000,
            take_profit_pct=8,
            stop_loss_pct=-5,
            max_holding_days=1,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).order_by(T0SimulationBacktestTrade.ts_code).all()
    assert len(trades) == 2
    assert trades[0].sell_reason == "max_holding_days"
    assert trades[0].sell_time == "15:00"
    assert round(trades[0].return_pct, 4) == 9.0
    assert round(trades[0].profit_amount, 2) == 2250.0
    assert trades[1].sell_reason == "stop_loss"
    assert round(trades[1].return_pct, 4) == -6.0
    assert round(trades[1].profit_amount, 2) == -1500.0
    assert payload["summary"]["final_equity"] == 100750.0
    assert payload["summary"]["total_profit_amount"] == 750.0
    assert payload["summary"]["win_rate"] == 0.5
    daily = db.query(T0SimulationBacktestDaily).filter_by(run_id=run.id, trade_date="20240501").one()
    assert daily.position_count == 0
    assert daily.equity == 100750.0


def test_t0_simulation_backtest_holds_high_profit_until_five_point_pullback(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "高盈回撤股", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 11.4)
    _add_daily(db, "20240502", "000001.SZ", 11.4, 12.0)
    _add_daily(db, "20240503", "000001.SZ", 12.0, 11.4)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240503",
            initial_cash=100000,
            high_profit_hold_pct=13,
            profit_pullback_pct=5,
            stop_loss_pct=-50,
            max_holding_days=1,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trade = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).one()
    assert trade.sell_date == "20240503"
    assert trade.sell_time == "15:00"
    assert trade.sell_price == 11.4
    assert trade.sell_reason == "profit_pullback"
    assert round(trade.return_pct, 4) == 14.0
    assert round(trade.profit_amount, 2) == 3500.0
    assert payload["summary"]["final_equity"] == 103500.0


def test_t0_simulation_backtest_uses_configurable_high_profit_and_pullback_thresholds(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "自定义高盈回撤", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 11.6)
    _add_daily(db, "20240502", "000001.SZ", 11.6, 11.7)
    _add_daily(db, "20240503", "000001.SZ", 11.7, 11.2)
    _add_daily(db, "20240504", "000001.SZ", 11.2, 10.9)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240504",
            initial_cash=100000,
            high_profit_hold_pct=15,
            profit_pullback_pct=6,
            stop_loss_pct=-50,
            max_holding_days=1,
        ),
    )

    service.run_t0_simulation_backtest(db, run.id)

    trade = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).one()
    assert trade.sell_date == "20240504"
    assert trade.sell_time == "15:00"
    assert trade.sell_reason == "profit_pullback"
    assert round(trade.return_pct, 4) == 9.0


def test_t0_simulation_backtest_skips_missing_open_price_without_fake_fill(db, monkeypatch):
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "缺价股", 0.95)
    db.add(StockDailyData(trade_date="20240501", ts_code="000001.SZ", open=None, close=11, pre_close=10, is_adj=1))
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(start_date="20240501", end_date="20240501"),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    assert payload["summary"]["trade_count"] == 0
    assert payload["summary"]["missing_price_count"] == 1
    assert payload["summary"]["skipped_buy_count"] == 1


def test_t0_simulation_backtest_sells_by_max_holding_days(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "持仓股", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 10.1)
    _add_daily(db, "20240502", "000001.SZ", 10.1, 10.2)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240502",
            take_profit_pct=50,
            stop_loss_pct=-50,
            max_holding_days=2,
        ),
    )

    service.run_t0_simulation_backtest(db, run.id)

    trade = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).one()
    assert trade.sell_date == "20240502"
    assert trade.sell_reason == "max_holding_days"
    assert trade.holding_days == 2


def test_t0_simulation_backtest_filters_one_line_limit_up_candidates(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "一字板", 0.99, is_one_line_limit_up=1)
    _add_sample(db, "20240501", "000002.SZ", "可买股", 0.90)
    _add_daily(db, "20240501", "000001.SZ", 11, 11, up_limit=11, high_price=11, low_price=11)
    _add_daily(db, "20240501", "000002.SZ", 10, 10.2, up_limit=11)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            take_profit_pct=50,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).all()
    assert [trade.ts_code for trade in trades] == ["000002.SZ"]
    assert payload["summary"]["skipped_one_line_limit_up_count"] == 1


def test_t0_simulation_backtest_does_not_buy_when_open_change_above_seven_pct(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample_with_features(db, "20240501", "000001.SZ", "高开过滤1", 0.99, {"open_change_pct": 7.1})
    _add_sample_with_features(db, "20240501", "000002.SZ", "高开过滤2", 0.90, {"open_change_pct": 8.0})
    _add_daily(db, "20240501", "000001.SZ", 10.71, 10.8, up_limit=11)
    _add_daily(db, "20240501", "000002.SZ", 10.8, 10.9, up_limit=11)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            buy_top_n=2,
            max_positions=2,
            take_profit_pct=50,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).all()
    assert trades == []
    assert payload["summary"]["open_position_count"] == 0
    assert payload["summary"]["skipped_high_open_change_count"] == 2


def test_t0_simulation_backtest_uses_configurable_max_open_change_threshold(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample_with_features(db, "20240501", "000001.SZ", "高开可买", 0.99, {"open_change_pct": 7.5})
    _add_sample_with_features(db, "20240501", "000002.SZ", "高开过滤", 0.90, {"open_change_pct": 8.1})
    _add_daily(db, "20240501", "000001.SZ", 10.75, 10.8, up_limit=11)
    _add_daily(db, "20240501", "000002.SZ", 10.81, 10.9, up_limit=11)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            buy_top_n=2,
            max_positions=2,
            max_open_change_pct=8,
            take_profit_pct=50,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trades = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).all()
    assert [trade.ts_code for trade in trades] == ["000001.SZ"]
    assert payload["max_open_change_pct"] == 8
    assert payload["summary"]["skipped_high_open_change_count"] == 1


def test_t0_simulation_backtest_keeps_limit_up_position_even_when_sell_rules_hit(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "涨停股", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 11, up_limit=11, high_price=11, low_price=10)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240501",
            take_profit_pct=8,
            stop_loss_pct=-50,
            max_holding_days=1,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trade = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).one()
    assert trade.status == "open"
    assert trade.sell_reason is None
    assert payload["summary"]["open_position_count"] == 1


def test_t0_simulation_backtest_delays_stop_loss_sell_when_close_is_limit_down(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "跌停止损股", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 9, down_limit=9, high_price=10, low_price=9)
    _add_daily(db, "20240502", "000001.SZ", 8.8, 8.7, down_limit=8.1, high_price=8.9, low_price=8.6)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240502",
            initial_cash=100000,
            take_profit_pct=50,
            stop_loss_pct=-5,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trade = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).one()
    assert trade.sell_date == "20240502"
    assert trade.sell_time == "09:30"
    assert trade.sell_price == 8.8
    assert trade.sell_reason == "stop_loss_next_open"
    assert round(trade.return_pct, 4) == -12.0
    assert round(trade.profit_amount, 2) == -3000.0
    assert payload["summary"]["final_equity"] == 97000.0


def test_t0_simulation_backtest_keeps_pending_stop_loss_when_next_open_is_limit_down(db, monkeypatch):
    from backend.models import T0SimulationBacktestTrade
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "连续跌停股", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 9, down_limit=9, high_price=10, low_price=9)
    _add_daily(db, "20240502", "000001.SZ", 8.1, 8.1, down_limit=8.1, high_price=8.1, low_price=8.1)
    _add_daily(db, "20240503", "000001.SZ", 8.0, 8.2, down_limit=7.29, high_price=8.2, low_price=8.0)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240503",
            initial_cash=100000,
            take_profit_pct=50,
            stop_loss_pct=-5,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    trade = db.query(T0SimulationBacktestTrade).filter_by(run_id=run.id).one()
    assert trade.sell_date == "20240503"
    assert trade.sell_time == "09:30"
    assert trade.sell_price == 8.0
    assert trade.sell_reason == "stop_loss_next_open"
    assert round(trade.return_pct, 4) == -20.0
    assert payload["summary"]["final_equity"] == 95000.0


def test_t0_simulation_backtest_daily_assets_mark_open_positions_to_market(db, monkeypatch):
    from backend.models import T0SimulationBacktestDaily
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "持仓股", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 10.2, up_limit=11)
    _add_daily(db, "20240502", "000001.SZ", 10.2, 10.6, up_limit=11.22)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240502",
            initial_cash=100000,
            take_profit_pct=50,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    service.run_t0_simulation_backtest(db, run.id)

    daily = (
        db.query(T0SimulationBacktestDaily)
        .filter_by(run_id=run.id)
        .order_by(T0SimulationBacktestDaily.trade_date.asc())
        .all()
    )
    assert [row.equity for row in daily] == [100500.0, 101500.0]


def test_t0_simulation_backtest_detail_reports_persisted_progress(db):
    from backend.models import T0SimulationBacktestDaily
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_daily(db, "20240501", "000001.SZ", 10, 10.1)
    _add_daily(db, "20240502", "000001.SZ", 10.1, 10.2)
    _add_daily(db, "20240503", "000001.SZ", 10.2, 10.3)
    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(start_date="20240501", end_date="20240503"),
    )
    run.status = "running"
    db.add(
        T0SimulationBacktestDaily(
            run_id=run.id,
            trade_date="20240501",
            cash=100000,
            market_value=0,
            equity=100000,
            daily_return_pct=0,
            drawdown_pct=0,
            position_count=0,
        )
    )
    db.commit()

    payload = service.get_t0_simulation_backtest_run(db, run.id)

    assert payload["processed_trade_days"] == 1
    assert payload["total_trade_days"] == 3
    assert payload["processed_trade_date"] == "20240501"
    assert payload["progress"] == 33.33


def test_t0_simulation_backtest_stops_when_cancel_requested(db, monkeypatch):
    from backend.models import T0SimulationBacktestDaily
    from backend.services.model_engine import t0_simulation_backtest_service as service

    _reset_t0_backtest_test_data(db)
    _add_model_version(db)
    _add_sample(db, "20240501", "000001.SZ", "第一天", 0.95)
    _add_sample(db, "20240502", "000002.SZ", "第二天", 0.95)
    _add_daily(db, "20240501", "000001.SZ", 10, 10.1, up_limit=11)
    _add_daily(db, "20240502", "000002.SZ", 10, 10.1, up_limit=11)
    db.commit()
    monkeypatch.setattr(service.lightgbm_service, "_predict_with_model_path", lambda *args: args[3]["score"])
    cancel_checks = {"count": 0}

    def fake_cancel_requested(_db, _run_id):
        cancel_checks["count"] += 1
        return cancel_checks["count"] > 1

    monkeypatch.setattr(service, "_is_cancel_requested", fake_cancel_requested)

    run = service.create_t0_simulation_backtest_run(
        db,
        service.T0SimulationBacktestCreate(
            start_date="20240501",
            end_date="20240502",
            take_profit_pct=50,
            stop_loss_pct=-50,
            max_holding_days=10,
        ),
    )

    payload = service.run_t0_simulation_backtest(db, run.id)

    daily = db.query(T0SimulationBacktestDaily).filter_by(run_id=run.id).all()
    assert payload["status"] == "canceled"
    assert [row.trade_date for row in daily] == ["20240501"]
