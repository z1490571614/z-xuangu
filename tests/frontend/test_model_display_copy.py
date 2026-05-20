from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_model_center_uses_chinese_names_in_training_diagnostics():
    text = _read("frontend/src/views/ModelCenter.vue")

    assert '<strong :title="name">{{ modelTitle(name) }}</strong>' in text
    assert '<strong :title="attempt.target">{{ modelTitle(attempt.target) }}</strong>' in text
    assert '<span :title="item.target || \'\'">{{ modelTitle(item.target) }}</span>' in text
    assert "<strong>{{ name }}</strong>" not in text
    assert "<strong>{{ attempt.target }}</strong>" not in text
    assert "<span>{{ item.target || '--' }}</span>" not in text


def test_stock_tables_have_target_specific_model_tooltips():
    for path in ("frontend/src/views/StockResults.vue", "frontend/src/views/Dashboard.vue"):
        text = _read(path)

        assert "defaultRelayTitle(stock, 't0')" in text
        assert "defaultRelayTitle(stock, 'premium')" in text
        assert "defaultRelayTitle(stock, 'continue')" in text
        assert "defaultRelayTitle(stock, 'relay')" in text
        assert "function defaultRelayTitle(stock, target)" in text
        assert "当日涨停模型：" in text
        assert "次日溢价模型：" in text
        assert "次日连板模型：" in text
        assert "竞价接力综合分：" in text
